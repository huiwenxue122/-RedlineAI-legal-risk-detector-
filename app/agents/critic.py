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
import re
from typing import Any, Dict, List, Optional

from openai import OpenAI

from app.config import get_settings
from app.agents.prompts import CRITIC_SYSTEM, CRITIC_USER_TEMPLATE

MAX_CLAUSE_CHARS = 6000
MAX_GRAPH_CONTEXT_CHARS = 4000
MAX_TOOL_ITERATIONS = 4  # cap tool rounds to prevent runaway loops

# ── Tool definition ───────────────────────────────────────────────────────────

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


# ── JSON parsing ──────────────────────────────────────────────────────────────

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
    use_tools = contract_id is not None

    content = "{}"
    for _ in range(MAX_TOOL_ITERATIONS):
        kwargs: Dict[str, Any] = {
            "model": settings.openai_model,
            "messages": messages,
            "temperature": 0.2,
            "max_tokens": 1024,
        }
        if use_tools:
            kwargs["tools"] = [GET_CLAUSE_TOOL]
            kwargs["tool_choice"] = "auto"
        else:
            kwargs["response_format"] = {"type": "json_object"}

        response = client.chat.completions.create(**kwargs)
        msg = response.choices[0].message

        if msg.tool_calls:
            messages.append(msg)
            for tc in msg.tool_calls:
                if tc.function.name == "get_clause":
                    args = json.loads(tc.function.arguments)
                    fetched = _fetch_clause_text(contract_id, args.get("section_id", ""))
                    messages.append({
                        "role": "tool",
                        "tool_call_id": tc.id,
                        "content": fetched,
                    })
        else:
            content = msg.content or "{}"
            break

    data = _extract_json(content)
    justified = data.get("justified")
    if not isinstance(justified, bool):
        justified = str(justified).lower() in ("true", "1", "yes")
    reason = str(data.get("reason") or "").strip() or "No reason given."
    confidence = str(data.get("confidence") or "").strip().lower()
    if confidence not in ("high", "medium", "low"):
        confidence = "medium"
    return {"justified": justified, "reason": reason, "confidence": confidence}
