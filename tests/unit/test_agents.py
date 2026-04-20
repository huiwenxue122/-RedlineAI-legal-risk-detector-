"""
Unit tests for app.agents: scan_clause, evaluate_finding, evaluate_escalation with mocked OpenAI.
"""
from unittest.mock import patch, MagicMock

import pytest

from app.schemas.playbook import Rule, RiskLevel
from app.agents.scanner import scan_clause
from app.agents.critic import evaluate_finding
from app.agents.evaluator import evaluate_escalation


@pytest.fixture
def sample_rules():
    return [
        Rule(rule_id="R001", description="Unlimited liability", risk_level=RiskLevel.High, keywords=["indemnify", "without limitation"]),
    ]


@pytest.fixture
def mock_openai_chat():
    """Mock OpenAI client: chat.completions.create returns a response with .choices[0].message.content."""
    def make_mock(content: str):
        mock_create = MagicMock()
        mock_create.return_value.choices = [MagicMock(message=MagicMock(content=content))]
        return mock_create
    return make_mock


def test_scan_clause_returns_list_with_mocked_client(sample_rules, mock_openai_chat):
    content = '{"findings": [{"rule_triggered": "R001", "evidence_summary": "Clause contains indemnity."}]}'
    with patch("app.agents.scanner.OpenAI") as mock_openai_class:
        mock_client = MagicMock()
        mock_client.chat.completions.create = mock_openai_chat(content)
        mock_openai_class.return_value = mock_client
        findings = scan_clause(
            clause_text="Party A shall indemnify Party B without limitation.",
            clause_ref="section_7_2",
            rules=sample_rules,
            graph_context="",
        )
    assert isinstance(findings, list)
    assert len(findings) >= 1
    assert findings[0].get("rule_triggered") == "R001"
    assert "evidence_summary" in findings[0]


def test_scan_clause_skips_llm_when_no_keyword_match(sample_rules):
    """Keyword pre-filter: clause with no matching keywords must return [] without calling LLM."""
    with patch("app.agents.scanner.OpenAI") as mock_openai_class:
        findings = scan_clause(
            clause_text="Governing law is New York.",  # no "indemnify" / "without limitation"
            clause_ref="section_9_1",
            rules=sample_rules,
            graph_context="",
        )
    mock_openai_class.assert_not_called()
    assert findings == []


def test_scan_clause_keyword_match_calls_llm(sample_rules, mock_openai_chat):
    """Keyword pre-filter: clause that matches a keyword must call the LLM."""
    content = '{"findings": []}'
    with patch("app.agents.scanner.OpenAI") as mock_openai_class:
        mock_client = MagicMock()
        mock_client.chat.completions.create = mock_openai_chat(content)
        mock_openai_class.return_value = mock_client
        scan_clause(
            clause_text="Party A shall indemnify Party B.",  # matches "indemnify"
            clause_ref="section_7_2",
            rules=sample_rules,
            graph_context="",
        )
    mock_openai_class.assert_called_once()


def test_keyword_filter_only_matched_rules_passed():
    """_keyword_filter returns only rules whose keywords appear in the clause text."""
    from app.agents.scanner import _keyword_filter
    rules = [
        Rule(rule_id="S001", description="Liability", risk_level=RiskLevel.High,
             keywords=["unlimited liability", "without limitation"]),
        Rule(rule_id="S005", description="Payment", risk_level=RiskLevel.Medium,
             keywords=["net 60", "net 90"]),
    ]
    matched = _keyword_filter("Fees are due net 90 days from invoice.", rules)
    assert len(matched) == 1
    assert matched[0].rule_id == "S005"


def test_keyword_filter_criteria_only_rule_always_passes():
    """Rules with no keywords (criteria-only) always pass the pre-filter."""
    from app.agents.scanner import _keyword_filter
    rule = Rule(rule_id="S999", description="Criteria only", risk_level=RiskLevel.Low, keywords=[])
    matched = _keyword_filter("Completely unrelated text.", [rule])
    assert matched == [rule]


def test_evaluate_finding_returns_justified_and_reason(mock_openai_chat):
    content = '{"justified": true, "reason": "Evidence supports the finding.", "confidence": "high"}'
    with patch("app.agents.critic.OpenAI") as mock_openai_class:
        mock_client = MagicMock()
        mock_client.chat.completions.create = mock_openai_chat(content)
        mock_openai_class.return_value = mock_client
        result = evaluate_finding(
            finding={"clause_ref": "section_7_2", "rule_triggered": "R001", "evidence_summary": "Indemnity language."},
            clause_text="Full clause text.",
            graph_context="",
        )
    assert "justified" in result
    assert "reason" in result
    assert result["justified"] is True


def test_evaluate_escalation_returns_escalation_and_reason(mock_openai_chat):
    content = '{"escalation": "Suggest Revision", "fallback_language": "Limit to 24 months.", "reason": "Open-ended survival."}'
    with patch("app.agents.evaluator.OpenAI") as mock_openai_class:
        mock_client = MagicMock()
        mock_client.chat.completions.create = mock_openai_chat(content)
        mock_openai_class.return_value = mock_client
        result = evaluate_escalation(
            finding={"rule_triggered": "R001", "evidence_summary": "Survival clause."},
            critic_result={"justified": True, "reason": "Yes."},
            risk_level="High",
            clause_text="Indemnity survives termination.",
        )
    assert "escalation" in result
    assert result["escalation"] in ("Acceptable", "Suggest Revision", "Escalate for Human Review")
    assert "reason" in result
