"""
Integration test: PDF → parse → extract → ingest → review → StructuredRiskMemo.

Runs the full pipeline with the sample contract. Requires Neo4j and OPENAI_API_KEY.
Skip if NEO4J_PASSWORD or OPENAI_API_KEY not set (e.g. in CI without secrets).
"""
import os
from pathlib import Path

import pytest

from app.pipeline import run_structural_pipeline
from app.agents import run_review
from app.schemas.risk_memo import StructuredRiskMemo, RiskMemoItem


# Sample contract path (project root relative to this file)
SAMPLE_PDF = Path(__file__).resolve().parent.parent.parent / "data" / "sample_contracts" / "EX-10.4(a).pdf"
CONTRACT_ID = "EX-10.4(a)"


def _integration_ready():
    """Skip if Neo4j or OpenAI not configured (check env so get_settings() is not required)."""
    if not (os.environ.get("OPENAI_API_KEY") or "").strip():
        return False, "OPENAI_API_KEY not set"
    if not (os.environ.get("NEO4J_URI") or "").strip():
        return False, "NEO4J_URI not set"
    if not (os.environ.get("NEO4J_USER") or "").strip():
        return False, "NEO4J_USER not set"
    if not (os.environ.get("NEO4J_PASSWORD") or "").strip():
        return False, "NEO4J_PASSWORD not set"
    return True, None


@pytest.mark.integration
def test_review_pipeline_end_to_end():
    """
    Run: structural pipeline (parse → extract → ingest) then review (Scanner → Critic → Evaluator).
    Assert: StructuredRiskMemo returned and conforms to schema; each item has required fields.
    """
    ok, msg = _integration_ready()
    if not ok:
        pytest.skip(msg)

    if not SAMPLE_PDF.exists():
        pytest.skip(f"Sample PDF not found: {SAMPLE_PDF}")

    # 1) PDF → parse → segment → extract → ingest
    contract, ingest_stats = run_structural_pipeline(SAMPLE_PDF, contract_id=CONTRACT_ID)
    assert contract.contract_id == CONTRACT_ID
    assert len(contract.clauses) >= 1, "Pipeline should produce at least one clause"
    # Ingest may be skipped if Neo4j not reachable; we continue for review (needs graph data)
    if ingest_stats is None:
        pytest.skip("Neo4j ingest was skipped (driver not configured or connection failed)")

    # 2) Review: Scanner → Critic → Evaluator
    memo = run_review(contract_id=CONTRACT_ID)
    assert isinstance(memo, StructuredRiskMemo)
    assert memo.contract_id == CONTRACT_ID
    assert isinstance(memo.items, list)

    # 3) Schema: each item has required fields (Pydantic already validates on construction)
    for item in memo.items:
        assert isinstance(item, RiskMemoItem)
        assert isinstance(item.clause, str)
        assert item.risk_level in ("High", "Medium", "Low", "Critical") or len(item.risk_level) >= 1
        assert isinstance(item.rule_triggered, str)
        assert isinstance(item.reason, str)
        assert item.escalation in (
            "Acceptable",
            "Suggest Revision",
            "Escalate for Human Review",
        )
