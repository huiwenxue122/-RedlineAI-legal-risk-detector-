"""
Unit tests for app.retrieval: get_context_for_clause, build_graph_context (with mocked get_clause_neighborhood).
"""
from unittest.mock import patch, MagicMock

import pytest

from app.retrieval.rag import get_context_for_clause
from app.retrieval.graph_context import build_graph_context


@pytest.fixture
def mock_neighborhood():
    return {
        "contract_id": "c1",
        "clause_id": "section_1_1",
        "clause_text": "Sample clause text.",
        "section_id": "1.1",
        "references_out": [{"to_clause_id": "section_4_2", "to_section_id": "4.2", "ref_text": "Section 4.2"}],
        "references_in": [],
        "definitions": [{"term": "Agreement", "definition": "This Agreement."}],
        "obligations": [{"description": "Pay fees."}],
    }


def test_get_context_for_clause_returns_required_keys(mock_neighborhood):
    with patch("app.retrieval.rag.get_clause_neighborhood", return_value=mock_neighborhood):
        with patch("app.retrieval.graph_context.get_clause_neighborhood", return_value=mock_neighborhood):
            ctx = get_context_for_clause("c1", "section_1_1")
    assert "clause_text" in ctx
    assert "section_id" in ctx
    assert "graph_context" in ctx
    assert "snippets" in ctx
    assert ctx["clause_text"] == "Sample clause text."
    assert ctx["section_id"] == "1.1"
    assert len(ctx["snippets"]) >= 1


def test_build_graph_context_formats_string(mock_neighborhood):
    with patch("app.retrieval.graph_context.get_clause_neighborhood", return_value=mock_neighborhood):
        s = build_graph_context("c1", "section_1_1")
    assert isinstance(s, str)
    assert "Definition" in s or "definition" in s or "Agreement" in s
    assert "reference" in s.lower() or "Section 4.2" in s or "Obligation" in s or "Pay" in s
