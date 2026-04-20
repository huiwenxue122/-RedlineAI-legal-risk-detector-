"""
Evaluator Agent: decide escalation and optional fallback language via tool calling.

Uses OpenAI function calling (submit_escalation tool) instead of JSON mode —
the enum constraint on "escalation" is enforced by the API schema.

Output: { "escalation": str, "fallback_language": str | None, "reason": str }
"""
import json
from typing import Any, Dict, Optional

from openai import OpenAI

from app.config import get_settings
from app.agents.prompts import EVALUATOR_SYSTEM, EVALUATOR_USER_TEMPLATE

VALID_ESCALATIONS = ("Acceptable", "Suggest Revision", "Escalate for Human Review")
MAX_CLAUSE_EXCERPT = 500

# ── Output tool ───────────────────────────────────────────────────────────────

SUBMIT_ESCALATION_TOOL: Dict[str, Any] = {
    "type": "function",
    "function": {
        "name": "submit_escalation",
        "description": "Submit the escalation decision for this contract finding.",
        "parameters": {
            "type": "object",
            "properties": {
                "escalation": {
                    "type": "string",
                    "enum": ["Acceptable", "Suggest Revision", "Escalate for Human Review"],
                    "description": "Final escalation decision",
                },
                "reason": {
                    "type": "string",
                    "description": "Plain-English explanation of the risk and why it matters to a small SaaS vendor",
                },
                "fallback_language": {
                    "type": ["string", "null"],
                    "description": (
                        "Suggested replacement clause or short email line the vendor can send "
                        "to push back. Required for Suggest Revision; optional for Escalate; "
                        "null for Acceptable."
                    ),
                },
            },
            "required": ["escalation", "reason", "fallback_language"],
        },
    },
}

# ── Main entry point ──────────────────────────────────────────────────────────

def evaluate_escalation(
    finding: Dict[str, Any],
    critic_result: Dict[str, Any],
    risk_level: str = "Medium",
    clause_text: str = "",
) -> Dict[str, Any]:
    """
    Run Evaluator: given Scanner finding + Critic result + rule risk level,
    output escalation decision and optional fallback language via tool calling.

    Returns: { "escalation": str, "fallback_language": str | None, "reason": str }
    """
    settings = get_settings()
    if not settings.openai_api_key:
        raise ValueError("OPENAI_API_KEY is not set")

    finding_summary = (
        f"Clause: {finding.get('clause_ref', '')} | "
        f"Rule: {finding.get('rule_triggered', '')} | "
        f"Evidence: {finding.get('evidence_summary', '')}"
    )
    clause_excerpt = (clause_text or "")[:MAX_CLAUSE_EXCERPT].strip() or "(No excerpt provided.)"

    client = OpenAI(api_key=settings.openai_api_key, timeout=60.0)
    response = client.chat.completions.create(
        model=settings.openai_model,
        messages=[
            {"role": "system", "content": EVALUATOR_SYSTEM},
            {"role": "user", "content": EVALUATOR_USER_TEMPLATE.format(
                finding_summary=finding_summary,
                risk_level=risk_level,
                critic_justified=critic_result.get("justified", False),
                critic_confidence=critic_result.get("confidence", "medium"),
                critic_reason=critic_result.get("reason", ""),
                clause_excerpt=clause_excerpt,
            )},
        ],
        tools=[SUBMIT_ESCALATION_TOOL],
        tool_choice={"type": "function", "function": {"name": "submit_escalation"}},
        temperature=0.2,
        max_tokens=1024,
    )

    tc = response.choices[0].message.tool_calls
    if not tc:
        return {
            "escalation": "Escalate for Human Review",
            "fallback_language": None,
            "reason": "Evaluator returned no tool call.",
        }

    data = json.loads(tc[0].function.arguments)
    escalation = str(data.get("escalation") or "").strip()
    if escalation not in VALID_ESCALATIONS:
        escalation = "Escalate for Human Review"

    fallback = data.get("fallback_language")
    if fallback is not None:
        fallback = str(fallback).strip() or None

    reason = str(data.get("reason") or "").strip() or "No reason given."
    return {"escalation": escalation, "fallback_language": fallback, "reason": reason}
