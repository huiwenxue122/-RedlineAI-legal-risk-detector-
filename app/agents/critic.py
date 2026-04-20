"""
Critic Agent: evaluate whether a Scanner finding is justified.

Uses full clause text and graph context. When contract_id is provided,
the Critic can also call get_clause() to fetch cross-referenced sections
from Neo4j on demand — so "subject to Section 4.2" is actually verified,
not just assumed to exist.

Tool-calling loop: LLM may call get_clause() up to MAX_TOOL_ITERATIONS
times before giving a final JSON answer.

Without contract_id: falls back to a single-shot call (original behaviour).

Output: { "justified": bool, "reason": str, "confidence": str }
"""
import json
from typing import Any, Dict, List, Optional

from openai import OpenAI

from app.config import get_settings
from app.agents.prompts import CRITIC_SYSTEM, CRITIC_USER_TEMPLATE

MAX_CLAUSE_CHARS = 6000
MAX_GRAPH_CONTEXT_CHARS = 4000
MAX_TOOL_ITERATIONS = 4  # cap tool rounds to prevent runaway loops

# ── Tool definition ───────────────────────────────────────────────────────────

SUBMIT_VERDICT_TOOL: Dict[str, Any] = {
    "type": "function",
    "function": {
        "name": "submit_verdict",
        "description": "Submit your final verdict on whether the Scanner finding is justified.",
        "parameters": {
            "type": "object",
            "properties": {
                "justified": {
                    "type": "boolean",
                    "description": "True if the finding is genuinely supported by the clause text and context",
                },
                "reason": {
                    "type": "string",
                    "description": "1-3 plain sentences explaining the verdict (no legal jargon)",
                },
                "confidence": {
                    "type": "string",
                    "enum": ["high", "medium", "low"],
                    "description": "Confidence in the verdict",
                },
            },
            "required": ["justified", "reason", "confidence"],
        },
    },
}

GET_CLAUSE_TOOL: Dict[str, Any] = {
    "type": "function",
    "function": {
        "name": "get_clause",
        "description": (
            "Fetch the full text of a clause in this contract by its section identifier "
            "(e.g. 'Section 4.2', 'Article 3', '§ 2.1'). "
            "Call this whenever the clause under review references another section "
            "and you need to read that section to verify whether it limits, qualifies, "
            "or changes the risk the Scanner identified."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "section_id": {
                    "type": "string",
                    "description": "Section identifier to look up, e.g. 'Section 4.2'",
                }
            },
            "required": ["section_id"],
        },
    },
}


# ── Graph query ───────────────────────────────────────────────────────────────

def _fetch_clause_text(contract_id: str, section_id: str) -> str:
    """Query Neo4j for the clause whose section_id matches in this contract."""
    try:
        from app.graph.client import get_driver
        driver = get_driver()
        with driver.session() as session:
            result = session.run(
                "MATCH (c:Clause {contract_id: $cid}) "
                "WHERE c.section_id = $sid RETURN c.text AS text LIMIT 1",
                cid=contract_id,
                sid=section_id,
            )
            record = result.single()
            if record and record.get("text"):
                return f"[{section_id}]\n{record['text']}"
    except Exception as e:
        return f"(Error fetching '{section_id}': {e})"
    return f"(Section '{section_id}' not found in this contract.)"


# ── Main entry point ──────────────────────────────────────────────────────────

def evaluate_finding(
    finding: Dict[str, Any],
    clause_text: str,
    graph_context: str = "",
    rule_description: str = "",
    contract_id: Optional[str] = None,
) -> Dict[str, Any]:
    """
    Run Critic on one Scanner finding.

    If contract_id is provided, the Critic may call get_clause() to fetch
    cross-referenced sections on demand before reaching a verdict.
    Without contract_id, a single-shot LLM call is made (original behaviour).

    Returns: { "justified": bool, "reason": str, "confidence": str }
    """
    settings = get_settings()
    if not settings.openai_api_key:
        raise ValueError("OPENAI_API_KEY is not set")

    clause_text = (clause_text or "")[:MAX_CLAUSE_CHARS]
    graph_context = (graph_context or "").strip()[:MAX_GRAPH_CONTEXT_CHARS]
    if not graph_context:
        graph_context = "(No graph context provided.)"

    finding_summary = (
        f"Clause: {finding.get('clause_ref', '')} | "
        f"Rule: {finding.get('rule_triggered', '')} | "
        f"Evidence: {finding.get('evidence_summary', '')}"
    )
    if not rule_description:
        rule_description = f"Rule {finding.get('rule_triggered', '')} (no description provided)."

    messages: List[Dict[str, Any]] = [
        {"role": "system", "content": CRITIC_SYSTEM},
        {"role": "user", "content": CRITIC_USER_TEMPLATE.format(
            finding_summary=finding_summary,
            clause_text=clause_text,
            graph_context=graph_context,
            rule_description=rule_description,
        )},
    ]

    client = OpenAI(api_key=settings.openai_api_key, timeout=60.0)

    # Tools available to the Critic:
    #   get_clause     — fetch a cross-referenced clause on demand
    #   submit_verdict — structured output; terminates the loop
    tools = [GET_CLAUSE_TOOL, SUBMIT_VERDICT_TOOL]
    if contract_id is None:
        tools = [SUBMIT_VERDICT_TOOL]  # no graph access without contract_id

    for _ in range(MAX_TOOL_ITERATIONS):
        response = client.chat.completions.create(
            model=settings.openai_model,
            messages=messages,
            tools=tools,
            tool_choice="required",  # always call a tool; loop ends on submit_verdict
            temperature=0.2,
            max_tokens=1024,
        )
        msg = response.choices[0].message
        messages.append(msg)

        verdict_data: Optional[Dict[str, Any]] = None
        for tc in (msg.tool_calls or []):
            if tc.function.name == "submit_verdict":
                verdict_data = json.loads(tc.function.arguments)
                # Still need to send a tool result back so the message thread is valid
                messages.append({
                    "role": "tool",
                    "tool_call_id": tc.id,
                    "content": "Verdict recorded.",
                })
            elif tc.function.name == "get_clause" and contract_id:
                args = json.loads(tc.function.arguments)
                fetched = _fetch_clause_text(contract_id, args.get("section_id", ""))
                messages.append({
                    "role": "tool",
                    "tool_call_id": tc.id,
                    "content": fetched,
                })

        if verdict_data is not None:
            break
    else:
        verdict_data = {}

    justified = verdict_data.get("justified")
    if not isinstance(justified, bool):
        justified = str(justified).lower() in ("true", "1", "yes")
    reason = str(verdict_data.get("reason") or "").strip() or "No reason given."
    confidence = str(verdict_data.get("confidence") or "").strip().lower()
    if confidence not in ("high", "medium", "low"):
        confidence = "medium"
    return {"justified": justified, "reason": reason, "confidence": confidence}
