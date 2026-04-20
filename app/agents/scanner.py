"""
Scanner Agent: given clause text + optional graph context + Playbook rules,
identify candidate risks and return structured findings via tool calling.

Uses OpenAI function calling (report_findings tool) instead of JSON mode —
the schema is enforced by the API, so no brittle JSON parsing is needed.

Keyword pre-filter: runs before any LLM call. If no rule keyword matches the
clause text, returns [] immediately (no API call, no tokens spent).

Debug: set CONTRACT_SENTINEL_DEBUG_SCANNER=1 to inspect inputs sent to model.
"""
import json
import os
from typing import Any, Dict, List

from openai import OpenAI

from app.config import get_settings
from app.schemas.playbook import Rule
from app.agents.prompts import SCANNER_SYSTEM, SCANNER_USER_TEMPLATE

MAX_CLAUSE_CHARS = 6000
MAX_GRAPH_CONTEXT_CHARS = 3000

# ── Output tool ───────────────────────────────────────────────────────────────

REPORT_FINDINGS_TOOL: Dict[str, Any] = {
    "type": "function",
    "function": {
        "name": "report_findings",
        "description": "Report the risk findings identified in this clause.",
        "parameters": {
            "type": "object",
            "properties": {
                "findings": {
                    "type": "array",
                    "description": "List of triggered rules. Empty list if none.",
                    "items": {
                        "type": "object",
                        "properties": {
                            "clause_ref": {
                                "type": "string",
                                "description": "The clause reference (e.g. 'Section 7.2')",
                            },
                            "rule_triggered": {
                                "type": "string",
                                "description": "Rule id from the playbook, e.g. 'S001'",
                            },
                            "evidence_summary": {
                                "type": "string",
                                "description": "1-2 sentences quoting the risky language and why it matters",
                            },
                        },
                        "required": ["clause_ref", "rule_triggered", "evidence_summary"],
                    },
                }
            },
            "required": ["findings"],
        },
    },
}

# ── Keyword pre-filter ────────────────────────────────────────────────────────

def _keyword_filter(clause_text: str, rules: List[Rule]) -> List[Rule]:
    """
    Return only rules that have at least one keyword present in clause_text.
    Case-insensitive substring match. Rules with no keywords always pass through
    (they rely on criteria-only matching by the LLM).
    """
    text_lower = clause_text.lower()
    matched = []
    for rule in rules:
        if not rule.keywords:
            matched.append(rule)
            continue
        if any(kw.lower() in text_lower for kw in rule.keywords):
            matched.append(rule)
    return matched


def _rules_to_text(rules: List[Rule]) -> str:
    lines = []
    for r in rules:
        parts = [f"- {r.rule_id} [{r.risk_level.value}]: {r.description}"]
        if r.keywords:
            parts.append(f"  Keywords: {', '.join(r.keywords)}")
        if r.criteria:
            parts.append(f"  Criteria: {r.criteria}")
        lines.append("\n".join(parts))
    return "\n\n".join(lines)


# ── Main entry point ──────────────────────────────────────────────────────────

def scan_clause(
    clause_text: str,
    clause_ref: str,
    rules: List[Rule],
    graph_context: str = "",
) -> List[Dict[str, Any]]:
    """
    Run Scanner on one clause: keyword pre-filter then LLM tool call.
    Returns list of { "clause_ref", "rule_triggered", "evidence_summary" }.
    Returns [] without an LLM call if no keyword matches.
    """
    if not rules:
        return []

    clause_text = (clause_text or "")[:MAX_CLAUSE_CHARS]

    candidate_rules = _keyword_filter(clause_text, rules)
    if not candidate_rules:
        return []

    settings = get_settings()
    if not settings.openai_api_key:
        raise ValueError("OPENAI_API_KEY is not set")

    graph_context = (graph_context or "").strip()[:MAX_GRAPH_CONTEXT_CHARS]
    if not graph_context:
        graph_context = "(No graph context provided.)"
    rules_text = _rules_to_text(candidate_rules)

    if os.environ.get("CONTRACT_SENTINEL_DEBUG_SCANNER"):
        _n = 800
        print(f"=== RULES ({len(candidate_rules)}/{len(rules)} after keyword filter) ===")
        print(rules_text)
        print(f"\n=== CLAUSE (first {_n} chars) ===")
        print(clause_text[:_n])
        print(f"\n=== GRAPH CONTEXT (first {_n} chars) ===")
        print(graph_context[:_n])
        print()

    client = OpenAI(api_key=settings.openai_api_key, timeout=60.0)
    response = client.chat.completions.create(
        model=settings.openai_model,
        messages=[
            {"role": "system", "content": SCANNER_SYSTEM},
            {"role": "user", "content": SCANNER_USER_TEMPLATE.format(
                clause_ref=clause_ref,
                clause_text=clause_text,
                graph_context=graph_context,
                rules_text=rules_text,
            )},
        ],
        tools=[REPORT_FINDINGS_TOOL],
        tool_choice={"type": "function", "function": {"name": "report_findings"}},
        temperature=0.2,
        max_tokens=2048,
    )

    tc = response.choices[0].message.tool_calls
    if not tc:
        return []

    data = json.loads(tc[0].function.arguments)
    findings = data.get("findings") or []

    out = []
    for f in findings:
        if not isinstance(f, dict):
            continue
        rule_id = f.get("rule_triggered") or f.get("rule_id") or ""
        if not rule_id:
            continue
        out.append({
            "clause_ref": str(f.get("clause_ref") or clause_ref),
            "rule_triggered": str(rule_id),
            "evidence_summary": str(f.get("evidence_summary") or ""),
        })
    return out
