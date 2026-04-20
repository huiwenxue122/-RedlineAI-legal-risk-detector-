"""
Scanner Agent: given clause text + optional graph context + Playbook rules, identify candidate risks.
Output: list of { clause_ref, rule_triggered, evidence_summary } for use by Critic/Evaluator.

Debug: set CONTRACT_SENTINEL_DEBUG_SCANNER=1 to print rules_text, clause_text, graph_context sent to the model.
"""
import json
import os
import re
from typing import Any, Dict, List

from openai import OpenAI

from app.config import get_settings
from app.schemas.playbook import Rule
from app.agents.prompts import SCANNER_SYSTEM, SCANNER_USER_TEMPLATE

# Max chars to send for clause/graph to avoid token overflow
MAX_CLAUSE_CHARS = 6000
MAX_GRAPH_CONTEXT_CHARS = 3000


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
            matched.append(rule)  # criteria-only rule: let LLM decide
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


def _extract_json(content: str) -> dict:
    text = content.strip()
    m = re.search(r"```(?:json)?\s*([\s\S]*?)```", text)
    if m:
        text = m.group(1).strip()
    first = text.find("{")
    if first >= 0:
        depth = 0
        for i in range(first, len(text)):
            if text[i] == "{":
                depth += 1
            elif text[i] == "}":
                depth -= 1
                if depth == 0:
                    text = text[first : i + 1]
                    break
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        pass
    try:
        from json_repair import repair_json
        return json.loads(repair_json(text))
    except Exception:
        pass
    return {"findings": []}


def scan_clause(
    clause_text: str,
    clause_ref: str,
    rules: List[Rule],
    graph_context: str = "",
) -> List[Dict[str, Any]]:
    """
    Run Scanner on one clause: check rules and return candidate findings.
    clause_ref: e.g. section_1_1 or "Section 1.1".
    Returns list of { "clause_ref", "rule_triggered", "evidence_summary" }.
    """
    if not rules:
        return []

    clause_text = (clause_text or "")[:MAX_CLAUSE_CHARS]

    # Keyword pre-filter: skip LLM call entirely if no rule has a keyword hit
    candidate_rules = _keyword_filter(clause_text, rules)
    if not candidate_rules:
        return []

    settings = get_settings()
    if not settings.openai_api_key:
        raise ValueError("OPENAI_API_KEY is not set")

    graph_context = (graph_context or "").strip()[:MAX_GRAPH_CONTEXT_CHARS]
    if not graph_context:
        graph_context = "(No graph context provided.)"
    rules_text = _rules_to_text(candidate_rules)  # only send matched rules

    if os.environ.get("CONTRACT_SENTINEL_DEBUG_SCANNER"):
        _debug_len = 800
        print(f"=== RULES ({len(candidate_rules)}/{len(rules)} after keyword filter) ===")
        print(rules_text)
        print("\n=== CLAUSE (first {} chars) ===".format(_debug_len))
        print((clause_text or "")[:_debug_len])
        print("\n=== GRAPH CONTEXT (first {} chars) ===".format(_debug_len))
        print((graph_context or "")[:_debug_len])
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
        temperature=0.2,
        response_format={"type": "json_object"},
        max_tokens=2048,
    )
    content = response.choices[0].message.content or "{}"
    data = _extract_json(content)
    findings = data.get("findings") or []
    # Normalize keys for downstream (accept common LLM variants)
    out = []
    for f in findings:
        if isinstance(f, dict):
            rule_id = f.get("rule_triggered") or f.get("rule_id") or ""
            if not rule_id:
                continue
            out.append({
                "clause_ref": str(f.get("clause_ref") or f.get("clause_ref_id") or clause_ref),
                "rule_triggered": str(rule_id),
                "evidence_summary": str(f.get("evidence_summary") or f.get("evidence") or ""),
            })
    return out
