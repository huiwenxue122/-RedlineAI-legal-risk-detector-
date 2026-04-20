"""
LangGraph 3-node multi-agent orchestration: Scanner → Critic → Evaluator.

Each agent is a separate graph node with a single responsibility:
  scanner_node   — loads one clause from the graph, runs Scanner, produces findings
  critic_node    — validates one finding against clause text + graph context
  evaluator_node — decides escalation and fallback language; advances state pointers

Routing:
  scanner  → critic    (findings found for current clause)
           → scanner   (no findings: advance to next clause and repeat)
           → END       (no more clauses)
  critic   → evaluator (always)
  evaluator→ critic    (more findings remain on current clause)
           → scanner   (clause exhausted: advance to next clause)
           → END       (all clauses processed)
"""
import operator
from pathlib import Path
from typing import Annotated, Any, Dict, List, Literal, Optional, TypedDict

from langgraph.graph import END, START, StateGraph

from app.schemas.risk_memo import RiskMemoItem, StructuredRiskMemo
from app.schemas.playbook import Rule


class ReviewState(TypedDict):
    contract_id: str
    clause_ids: List[str]
    rules_list: List[Dict[str, Any]]          # serialized Rule dicts

    items: Annotated[List[Dict[str, Any]], operator.add]  # append-only results

    clause_index: int                         # index into clause_ids
    clause_ctx: Optional[Dict[str, Any]]      # loaded context for current clause
    findings: List[Dict[str, Any]]            # Scanner output for current clause
    finding_index: int                        # index into findings

    current_finding: Optional[Dict[str, Any]] # finding in flight (Scanner → Critic)
    critic_result: Optional[Dict[str, Any]]   # Critic output in flight (Critic → Evaluator)


# ── Helpers ───────────────────────────────────────────────────────────────────

def _get_clause_ids(contract_id: str) -> List[str]:
    from app.graph.client import get_driver
    driver = get_driver()
    with driver.session() as session:
        r = session.run(
            "MATCH (c:Clause {contract_id: $contract_id}) RETURN c.id AS id ORDER BY c.id",
            contract_id=contract_id,
        )
        return [rec["id"] for rec in r if rec.get("id")]


def _rules_from_state(state: ReviewState) -> tuple[List[Rule], Dict[str, Rule]]:
    rules = [Rule.model_validate(r) for r in state["rules_list"]]
    return rules, {r.rule_id: r for r in rules}


# ── Nodes ─────────────────────────────────────────────────────────────────────

def scanner_node(state: ReviewState) -> Dict[str, Any]:
    """
    Load the current clause from the graph and run the Scanner against all playbook rules.
    If no findings: advance clause_index so the router moves on.
    If findings: store them in state and set finding_index to 0.
    """
    from app.retrieval import get_context_for_clause
    from app.agents.scanner import scan_clause

    clause_ids = state["clause_ids"]
    clause_index = state["clause_index"]
    rules, _ = _rules_from_state(state)

    if clause_index >= len(clause_ids):
        return {"clause_index": clause_index}

    clause_id = clause_ids[clause_index]
    ctx = get_context_for_clause(state["contract_id"], clause_id)
    clause_ref = ctx.get("section_id") or clause_id

    findings = scan_clause(
        clause_text=ctx.get("clause_text") or "",
        clause_ref=clause_ref,
        rules=rules,
        graph_context=ctx.get("graph_context") or "",
    )

    if not findings:
        return {
            "clause_index": clause_index + 1,
            "clause_ctx": None,
            "findings": [],
            "finding_index": 0,
        }

    return {
        "clause_ctx": ctx,
        "findings": findings,
        "finding_index": 0,
    }


def critic_node(state: ReviewState) -> Dict[str, Any]:
    """
    Run the Critic on findings[finding_index].
    Passes clause text and graph context so the Critic can check cross-references
    and definitions that may weaken or strengthen the Scanner's claim.
    """
    from app.agents.critic import evaluate_finding

    _, rule_by_id = _rules_from_state(state)
    clause_ctx = state["clause_ctx"] or {}
    f = state["findings"][state["finding_index"]]

    rule = rule_by_id.get(f.get("rule_triggered"))
    rule_description = (
        (rule.description or "")
        + (" " + rule.criteria if rule and rule.criteria else "")
        if rule else f"Rule {f.get('rule_triggered')}"
    )

    critic_result = evaluate_finding(
        finding=f,
        clause_text=(clause_ctx.get("clause_text") or "").strip(),
        graph_context=clause_ctx.get("graph_context") or "",
        rule_description=rule_description,
        contract_id=state["contract_id"],
    )
    return {"current_finding": f, "critic_result": critic_result}


def evaluator_node(state: ReviewState) -> Dict[str, Any]:
    """
    Run the Evaluator on the current finding + Critic result.
    Build a RiskMemoItem and append it to items.
    Advance finding_index; if the clause is exhausted, advance clause_index too.
    """
    from app.agents.evaluator import evaluate_escalation

    _, rule_by_id = _rules_from_state(state)
    f = state["current_finding"]
    critic_result = state["critic_result"]
    clause_ctx = state["clause_ctx"] or {}
    clause_text = (clause_ctx.get("clause_text") or "").strip()

    rule = rule_by_id.get(f.get("rule_triggered"))
    risk_level = rule.risk_level.value if rule else "Medium"

    eval_result = evaluate_escalation(
        finding=f,
        critic_result=critic_result,
        risk_level=risk_level,
        clause_text=clause_text,
    )

    clause_ref = clause_ctx.get("section_id") or clause_ctx.get("clause_id") or ""
    item = {
        "clause": clause_text[:500],
        "clause_ref": clause_ref,
        "risk_level": risk_level,
        "rule_triggered": f.get("rule_triggered", ""),
        "reason": eval_result.get("reason", ""),
        "fallback_language": eval_result.get("fallback_language"),
        "escalation": eval_result.get("escalation", ""),
        "citation": {"section": clause_ref, "page": None},
        "evidence_summary": f.get("evidence_summary"),
        "justified": critic_result.get("justified"),
        "confidence": critic_result.get("confidence"),
    }

    new_finding_index = state["finding_index"] + 1
    clause_done = new_finding_index >= len(state["findings"])

    update: Dict[str, Any] = {
        "items": [item],
        "finding_index": new_finding_index,
        "current_finding": None,
        "critic_result": None,
    }
    if clause_done:
        update["clause_index"] = state["clause_index"] + 1
        update["clause_ctx"] = None
        update["findings"] = []
        update["finding_index"] = 0

    return update


# ── Routing ───────────────────────────────────────────────────────────────────

def _route_after_scanner(state: ReviewState) -> Literal["critic", "scanner", "__end__"]:
    if state["clause_index"] >= len(state["clause_ids"]):
        return "__end__"
    if state["findings"]:
        return "critic"
    return "scanner"  # no findings: load next clause


def _route_after_evaluator(state: ReviewState) -> Literal["critic", "scanner", "__end__"]:
    if state["finding_index"] < len(state["findings"]):
        return "critic"  # more findings on current clause
    if state["clause_index"] >= len(state["clause_ids"]):
        return "__end__"
    return "scanner"  # advance to next clause


# ── Graph assembly ────────────────────────────────────────────────────────────

def build_review_graph():
    """Build and compile the 3-node Scanner → Critic → Evaluator LangGraph."""
    builder = StateGraph(ReviewState)

    builder.add_node("scanner", scanner_node)
    builder.add_node("critic", critic_node)
    builder.add_node("evaluator", evaluator_node)

    builder.add_edge(START, "scanner")
    builder.add_conditional_edges(
        "scanner", _route_after_scanner,
        {"critic": "critic", "scanner": "scanner", "__end__": END},
    )
    builder.add_edge("critic", "evaluator")
    builder.add_conditional_edges(
        "evaluator", _route_after_evaluator,
        {"critic": "critic", "scanner": "scanner", "__end__": END},
    )

    return builder.compile()


# ── Entry point ───────────────────────────────────────────────────────────────

def run_review(
    contract_id: str,
    clause_ids: Optional[List[str]] = None,
    rules: Optional[List[Rule]] = None,
    playbook_path: Optional[str] = None,
) -> StructuredRiskMemo:
    """
    Run the full review pipeline (Scanner → Critic → Evaluator) on the given contract.
    Returns StructuredRiskMemo for the API / frontend.
    """
    from app.agents.playbook_loader import load_playbook

    if rules is None:
        if not playbook_path:
            playbook_path = str(
                Path(__file__).resolve().parent.parent.parent
                / "data" / "playbooks" / "saas_customer.yaml"
            )
        rules = load_playbook(playbook_path)

    if clause_ids is None:
        clause_ids = _get_clause_ids(contract_id)
    if not clause_ids:
        return StructuredRiskMemo(contract_id=contract_id, items=[])

    initial: ReviewState = {
        "contract_id": contract_id,
        "clause_ids": clause_ids,
        "rules_list": [r.model_dump() for r in rules],
        "items": [],
        "clause_index": 0,
        "clause_ctx": None,
        "findings": [],
        "finding_index": 0,
        "current_finding": None,
        "critic_result": None,
    }

    graph = build_review_graph()
    final = graph.invoke(initial)
    items = [RiskMemoItem.model_validate(i) for i in (final.get("items") or [])]
    return StructuredRiskMemo(contract_id=contract_id, items=items)
