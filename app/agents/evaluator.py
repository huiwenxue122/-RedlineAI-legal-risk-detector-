"""
Evaluator Agent (Task 11): decide escalation and optional fallback language.
Input: Scanner finding + Critic conclusion + risk level. Output: escalation (Acceptable / Suggest Revision / Escalate for Human Review), fallback_language, reason. Aligns with risk_memo for API/frontend.
"""
import json
import re
from typing import Any, Dict

from openai import OpenAI

from app.config import get_settings
from app.agents.prompts import EVALUATOR_SYSTEM, EVALUATOR_USER_TEMPLATE

VALID_ESCALATIONS = ("Acceptable", "Suggest Revision", "Escalate for Human Review")
MAX_CLAUSE_EXCERPT = 500


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
    return {
        "escalation": "Escalate for Human Review",
        "fallback_language": None,
        "reason": "Failed to parse evaluator response.",
    }


def evaluate_escalation(
    finding: Dict[str, Any],
    critic_result: Dict[str, Any],
    risk_level: str = "Medium",
    clause_text: str = "",
) -> Dict[str, Any]:
    """
    Run Evaluator: given Scanner finding + Critic result + rule risk level,
    output escalation decision and optional fallback language.

    finding: dict with clause_ref, rule_triggered, evidence_summary.
    critic_result: dict with justified, reason, confidence.
    risk_level: e.g. "High", "Medium", "Low" (from playbook).
    clause_text: optional; first MAX_CLAUSE_EXCERPT chars used as excerpt.

    Returns: { "escalation": str, "fallback_language": str | None, "reason": str }
    where escalation is one of "Acceptable" | "Suggest Revision" | "Escalate for Human Review".
    """
    settings = get_settings()
    if not settings.openai_api_key:
        raise ValueError("OPENAI_API_KEY is not set")

    finding_summary = (
        f"Clause: {finding.get('clause_ref', '')} | "
        f"Rule: {finding.get('rule_triggered', '')} | "
        f"Evidence: {finding.get('evidence_summary', '')}"
    )
    critic_justified = critic_result.get("justified", False)
    critic_confidence = critic_result.get("confidence", "medium")
    critic_reason = critic_result.get("reason", "")
    clause_excerpt = (clause_text or "")[:MAX_CLAUSE_EXCERPT]
    if not clause_excerpt.strip():
        clause_excerpt = "(No clause excerpt provided.)"

    client = OpenAI(api_key=settings.openai_api_key, timeout=60.0)
    response = client.chat.completions.create(
        model=settings.openai_model,
        messages=[
            {"role": "system", "content": EVALUATOR_SYSTEM},
            {"role": "user", "content": EVALUATOR_USER_TEMPLATE.format(
                finding_summary=finding_summary,
                risk_level=risk_level,
                critic_justified=critic_justified,
                critic_confidence=critic_confidence,
                critic_reason=critic_reason,
                clause_excerpt=clause_excerpt,
            )},
        ],
        temperature=0.2,
        response_format={"type": "json_object"},
        max_tokens=1024,
    )
    content = response.choices[0].message.content or "{}"
    data = _extract_json(content)
    escalation = str(data.get("escalation") or "").strip()
    if escalation not in VALID_ESCALATIONS:
        for v in VALID_ESCALATIONS:
            if v.lower() in escalation.lower():
                escalation = v
                break
        else:
            escalation = "Escalate for Human Review"
    fallback = data.get("fallback_language")
    if fallback is not None:
        fallback = str(fallback).strip() or None
    reason = str(data.get("reason") or "").strip() or "No reason given."
    return {"escalation": escalation, "fallback_language": fallback, "reason": reason}
