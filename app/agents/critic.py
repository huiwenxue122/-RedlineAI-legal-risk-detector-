"""
Critic Agent (Task 10): evaluate whether a Scanner finding is justified.
Uses full clause text and graph context (definitions, cross-refs, obligations)
to decide if the finding holds. Output: { "justified": bool, "reason": str, "confidence": str } for Evaluator.
"""
import json
import re
from typing import Any, Dict

from openai import OpenAI

from app.config import get_settings
from app.agents.prompts import CRITIC_SYSTEM, CRITIC_USER_TEMPLATE

MAX_CLAUSE_CHARS = 6000
MAX_GRAPH_CONTEXT_CHARS = 4000


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
    return {"justified": False, "reason": "Failed to parse critic response.", "confidence": "low"}


def evaluate_finding(
    finding: Dict[str, Any],
    clause_text: str,
    graph_context: str = "",
    rule_description: str = "",
) -> Dict[str, Any]:
    """
    Run Critic on one Scanner finding: decide if the finding is justified given
    full clause text and graph context (definitions, refs, obligations).

    finding: dict with "clause_ref", "rule_triggered", "evidence_summary".
    rule_description: optional description/criteria of the rule (e.g. from playbook).

    Returns: { "justified": bool, "reason": str, "confidence": str } (confidence: "high" | "medium" | "low").
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

    client = OpenAI(api_key=settings.openai_api_key, timeout=60.0)
    response = client.chat.completions.create(
        model=settings.openai_model,
        messages=[
            {"role": "system", "content": CRITIC_SYSTEM},
            {"role": "user", "content": CRITIC_USER_TEMPLATE.format(
                finding_summary=finding_summary,
                clause_text=clause_text,
                graph_context=graph_context,
                rule_description=rule_description,
            )},
        ],
        temperature=0.2,
        response_format={"type": "json_object"},
        max_tokens=1024,
    )
    content = response.choices[0].message.content or "{}"
    data = _extract_json(content)
    justified = data.get("justified")
    if not isinstance(justified, bool):
        justified = str(justified).lower() in ("true", "1", "yes")
    reason = str(data.get("reason") or "").strip() or "No reason given."
    confidence = str(data.get("confidence") or "").strip().lower()
    if confidence not in ("high", "medium", "low"):
        confidence = "medium"
    return {"justified": justified, "reason": reason, "confidence": confidence}
