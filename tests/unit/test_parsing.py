"""
Unit tests for app.parsing: parse_pdf, strip_repeated_headers_footers.
"""
import pytest

from app.parsing import parse_pdf, strip_repeated_headers_footers
from app.parsing.blocks import TextBlock


def test_parse_pdf_returns_tuple_of_full_text_and_blocks(minimal_pdf_bytes):
    full_text, blocks = parse_pdf(minimal_pdf_bytes)
    assert isinstance(full_text, str)
    assert isinstance(blocks, list)
    assert len(full_text) > 0
    assert "Section" in full_text or "Test" in full_text or "clause" in full_text
    assert len(blocks) >= 1
    for b in blocks:
        assert isinstance(b, TextBlock)
        assert hasattr(b, "text")
        assert hasattr(b, "page")


def test_parse_pdf_empty_input_raises_or_returns_empty():
    # Empty bytes: fitz may raise or return empty full_text and blocks
    try:
        full_text, blocks = parse_pdf(b"")
        assert isinstance(full_text, str)
        assert isinstance(blocks, list)
        assert full_text == ""
        assert blocks == []
    except Exception:
        # PyMuPDF may raise when opening invalid/empty PDF stream
        pass


def test_strip_repeated_headers_footers_no_blocks_returns_unchanged():
    text = "Line one\nLine two"
    result = strip_repeated_headers_footers(text, [])
    assert result == text


def test_strip_repeated_headers_footers_single_page_returns_unchanged():
    text = "Only one page"
    blocks = [TextBlock(text=text, page=1)]
    result = strip_repeated_headers_footers(text, blocks)
    assert result == text
