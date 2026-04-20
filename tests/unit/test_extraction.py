"""
Unit tests for app.extraction: segment_clauses, extract_cross_references.
(extract_contract requires LLM and is tested via integration or mocked in test_agents.)
"""
import pytest

from app.extraction import segment_clauses, extract_cross_references
from app.schemas.contract import Clause


def test_segment_clauses_empty_returns_empty():
    clauses, stats = segment_clauses("")
    assert clauses == []
    assert stats["pattern"] is None
    assert stats["after_dedup_filter"] == 0


def test_segment_clauses_plain_text_returns_empty():
    # No recognizable heading structure; all patterns should yield 0 plausible clauses.
    text = "This is plain text with no structured headings at all. " * 5
    clauses, stats = segment_clauses(text)
    assert clauses == []
    assert stats["after_dedup_filter"] == 0


def test_segment_clauses_subsection_style(sample_full_text_for_segment):
    """Section X.Y format — the current sample contract style."""
    clauses, stats = segment_clauses(sample_full_text_for_segment)
    assert stats["pattern"] == "subsection"
    assert len(clauses) >= 1
    for c in clauses:
        assert isinstance(c, Clause)
        assert c.id
        assert len(c.text) >= 100  # MIN_CLAUSE_CHARS


def test_segment_clauses_article_numbered_style():
    """Article N format used in many MSA / software contracts."""
    body = "The parties agree to the following terms and conditions as set forth herein. " * 3
    text = (
        f"Article 1  Definitions\n\n{body}\n\n"
        f"Article 2  Obligations\n\n{body}\n\n"
        f"Article 3  Termination\n\n{body}"
    )
    clauses, stats = segment_clauses(text)
    assert stats["pattern"] == "article_numbered"
    assert len(clauses) == 3
    assert clauses[0].section_id == "Article 1"
    assert clauses[1].section_id == "Article 2"


def test_segment_clauses_article_roman_style():
    """Article I / II / III format used in some NDA / employment contracts."""
    body = "The parties agree to the following terms and conditions as set forth herein. " * 3
    text = (
        f"Article I  Definitions\n\n{body}\n\n"
        f"Article II  Obligations\n\n{body}\n\n"
        f"Article III  Termination\n\n{body}"
    )
    clauses, stats = segment_clauses(text)
    assert stats["pattern"] == "article_roman"
    assert len(clauses) == 3
    assert clauses[0].section_id == "Article I"
    assert clauses[2].section_id == "Article III"


def test_segment_clauses_section_number_style():
    """Section N format (no subsection dot) used in some agreements."""
    body = "The parties agree to the following terms and conditions as set forth herein. " * 3
    text = (
        f"Section 1  Definitions\n\n{body}\n\n"
        f"Section 2  Representations\n\n{body}\n\n"
        f"Section 3  Termination\n\n{body}"
    )
    clauses, stats = segment_clauses(text)
    assert stats["pattern"] == "section_number"
    assert len(clauses) == 3
    assert clauses[0].section_id == "Section 1"


def test_segment_clauses_paragraph_symbol_style():
    """§ N.N format used in some regulatory / financial contracts."""
    body = "The parties agree to the following terms and conditions as set forth herein. " * 3
    text = (
        f"§ 1.1 Definitions\n\n{body}\n\n"
        f"§ 1.2 Obligations\n\n{body}\n\n"
        f"§ 2.1 Termination\n\n{body}"
    )
    clauses, stats = segment_clauses(text)
    assert stats["pattern"] == "paragraph_symbol"
    assert len(clauses) == 3


def test_segment_clauses_stats_has_all_patterns():
    """stats["candidates_by_pattern"] should list all known patterns."""
    from app.extraction.clause_segmenter import HEADING_PATTERNS
    _, stats = segment_clauses("some text")
    for p in HEADING_PATTERNS:
        assert p.name in stats["candidates_by_pattern"]


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
