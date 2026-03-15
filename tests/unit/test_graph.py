"""
Unit tests for app.graph: ingest_contract (with mocked driver), get_clause_neighborhood (with mocked driver).
"""
from unittest.mock import patch, MagicMock

import pytest

from app.schemas.contract import Contract, Clause
from app.graph import ingest_contract
from app.graph.query import get_clause_neighborhood


@pytest.fixture
def mock_driver_session():
    session = MagicMock()
    driver = MagicMock()
    driver.session.return_value.__enter__ = MagicMock(return_value=session)
    driver.session.return_value.__exit__ = MagicMock(return_value=False)
    return driver, session


def test_ingest_contract_calls_session_run(mock_driver_session, sample_contract):
    driver, session = mock_driver_session
    with patch("app.graph.ingest.get_driver", return_value=driver):
        stats = ingest_contract(sample_contract)
    assert session.run.call_count >= 4  # DETACH DELETE, Contract, at least Clause, Definition, Party, Obligation
    assert "node_counts" in stats
    assert "relationship_counts" in stats
    assert stats["node_counts"].get("Contract") == 1


def test_ingest_contract_empty_clauses_still_creates_contract(mock_driver_session):
    c = Contract(contract_id="empty_c", raw_text="", clauses=[])
    driver, session = mock_driver_session
    with patch("app.graph.ingest.get_driver", return_value=driver):
        stats = ingest_contract(c)
    assert stats["node_counts"].get("Contract") == 1


def test_get_clause_neighborhood_returns_structure(mock_driver_session):
    driver, session = mock_driver_session
    # First run: clause text (has .single()); rest are iterables for "for rec in r"
    session.run.side_effect = [
        MagicMock(single=MagicMock(return_value={"text": "Clause text here.", "section_id": "1.1"})),
        [],
        [],
        [],
        [],
    ]
    with patch("app.graph.query.get_driver", return_value=driver):
        result = get_clause_neighborhood("c1", "section_1_1")
    assert result["contract_id"] == "c1"
    assert result["clause_id"] == "section_1_1"
    assert result["clause_text"] == "Clause text here."
    assert result["section_id"] == "1.1"
    assert "references_out" in result
    assert "references_in" in result
    assert "definitions" in result
    assert "obligations" in result
