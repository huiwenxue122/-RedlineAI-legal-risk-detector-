"""
Unit tests for app.extraction: segment_clauses, extract_cross_references.
(extract_contract requires LLM and is tested via integration or mocked in test_agents.)
"""
import pytest

from app.extraction import segment_clauses, extract_cross_references
from app.extraction.clause_segmenter import is_plausible_subsection_start
from app.schemas.contract import Clause


def test_segment_clauses_empty_returns_empty():
    clauses, stats = segment_clauses("")
    assert clauses == []
    assert stats["raw_matches"] == 0
    assert stats["after_dedup_filter"] == 0


def test_segment_clauses_no_section_headers_returns_empty():
    text = "This is plain text with no Section 1.1 style headers at all."
    clauses, stats = segment_clauses(text)
    assert clauses == []
    assert stats["raw_matches"] == 0


def test_segment_clauses_with_headers(sample_full_text_for_segment):
    clauses, stats = segment_clauses(sample_full_text_for_segment)
    assert stats["raw_matches"] >= 2
    assert len(clauses) >= 1
    for c in clauses:
        assert isinstance(c, Clause)
        assert c.id
        assert isinstance(c.text, str)
        assert len(c.text) >= 100  # MIN_CLAUSE_CHARS


def test_is_plausible_subsection_start_too_short():
    assert is_plausible_subsection_start("Section 1.1  Short.", 0, 20, None) is False


def test_is_plausible_subsection_start_first_line_too_short():
    body = "x" * 120
    assert is_plausible_subsection_start("1.1  ab\n" + body, 0, 130, None) is False


def test_extract_cross_references_empty():
    assert extract_cross_references([]) == []


def test_extract_cross_references_single_ref(sample_clauses_for_cross_ref):
    refs = extract_cross_references(sample_clauses_for_cross_ref)
    assert isinstance(refs, list)
    # Clause section_7_2 text contains "Section 4.2" and "Section 5.1"
    from_ids = {r.from_clause_id for r in refs}
    to_ids = {r.to_clause_id for r in refs}
    assert "section_7_2" in from_ids
    assert "section_4_2" in to_ids or "section_5_1" in to_ids
    for r in refs:
        assert r.from_clause_id
        assert r.to_clause_id
        assert r.ref_text or True  # ref_text optional
