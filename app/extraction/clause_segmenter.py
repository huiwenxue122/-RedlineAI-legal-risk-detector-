"""
Rule-based clause segmenter: split contract full text into clause-level segments.

Supports multiple common heading styles and auto-detects the best fit:
  - Numbered subsection:   "1.1 ...", "Section 1.1 ..."
  - Article numbered:      "Article 1 ..."
  - Article roman:         "Article I ...", "Article III ..."
  - Section numbered:      "Section 1 ..."
  - Section roman:         "Section I ..."
  - § symbol:              "§ 1.1 ...", "§ 2 ..."
  - Simple numbered:       "1. TITLE ..." (requires uppercase word cue)

Auto-detection: each pattern is tried; the one producing the most plausible clauses wins.
If no pattern finds clauses, returns empty list (caller falls back to LLM extraction).
"""
import re
from dataclasses import dataclass
from typing import Any, Dict, List, Optional, Tuple

from app.schemas.contract import Clause

# Minimum clause body length (chars) to count as real clause, not TOC or ref line
MIN_CLAUSE_CHARS = 100
# First line (to newline) longer than this suggests real body; shorter may be TOC line
MIN_FIRST_LINE_CHARS = 40
# Only consider clause starts in the first fraction of doc (exhibits often reuse numbers)
MAIN_BODY_FRACTION = 0.75


@dataclass
class HeadingPattern:
    name: str
    regex: re.Pattern


# Ordered from most specific to least — auto-detection picks winner by clause count,
# but specificity order breaks ties naturally (more specific patterns come first).
HEADING_PATTERNS: List[HeadingPattern] = [
    HeadingPattern(
        name="subsection",
        regex=re.compile(r"(?m)^\s*(?:Section\s+)?(\d+\.\d+(?:\.\d+)?)\s+"),
    ),
    HeadingPattern(
        name="article_numbered",
        regex=re.compile(r"(?m)^\s*Article\s+(\d+)\b\s*[.\-:]?\s*"),
    ),
    HeadingPattern(
        name="article_roman",
        # Matches "Article I", "Article XIV" etc.; [IVXLCDM]+ is safe here because
        # "Article " prefix already constrains the context.
        regex=re.compile(r"(?m)^\s*Article\s+([IVXLCDM]+)\b\s*[.\-:]?\s*"),
    ),
    HeadingPattern(
        name="section_number",
        regex=re.compile(r"(?m)^\s*Section\s+(\d+)\b\s*[.\-:]?\s*"),
    ),
    HeadingPattern(
        name="section_roman",
        regex=re.compile(r"(?m)^\s*Section\s+([IVXLCDM]+)\b\s*[.\-:]?\s*"),
    ),
    HeadingPattern(
        name="paragraph_symbol",
        regex=re.compile(r"(?m)^\s*§\s*(\d+(?:\.\d+)?)\s+"),
    ),
    HeadingPattern(
        name="simple_numbered",
        # Require two uppercase letters after "N. " to avoid matching plain lists.
        regex=re.compile(r"(?m)^\s*(\d+)\.\s+[A-Z]{2}"),
    ),
]


def _first_line(s: str) -> str:
    idx = s.find("\n")
    return (s[:idx] if idx >= 0 else s).strip()


def _is_plausible(text: str, start: int, prev_start: Optional[int]) -> bool:
    if not text or len(text) < MIN_CLAUSE_CHARS:
        return False
    # Short first line is suspicious (e.g. TOC entry "1.1 Title .... 5") unless the
    # total body is substantial — Article/Section headings are often short titles on
    # their own line, with the real body following on subsequent lines.
    first = _first_line(text)
    if len(first) < MIN_FIRST_LINE_CHARS and len(text) < MIN_CLAUSE_CHARS * 2:
        return False
    # Dense cluster (likely TOC block): very close to previous match and still short
    if prev_start is not None and (start - prev_start) < 100 and len(text) < 200:
        return False
    return True


def _make_ids(pattern_name: str, num: str) -> Tuple[str, str]:
    """Return (clause_id, section_id) for a given pattern and captured number."""
    num_safe = num.replace(".", "_")
    if "article" in pattern_name:
        return f"article_{num_safe}", f"Article {num}"
    elif "paragraph" in pattern_name:
        return f"section_{num_safe}", f"§ {num}"
    else:
        return f"section_{num_safe}", f"Section {num}"


def _run_pattern(full_text: str, pattern: HeadingPattern) -> List[Clause]:
    """Apply one heading pattern and return plausible, deduped clauses."""
    matches = list(pattern.regex.finditer(full_text))
    if not matches:
        return []

    positions = [m.start() for m in matches]
    numbers = [m.group(1) for m in matches]
    main_body_end = int(len(full_text) * MAIN_BODY_FRACTION)

    candidates: List[Tuple[str, int, str]] = []  # (num, start, text)
    prev_start: Optional[int] = None
    for i, (start, num) in enumerate(zip(positions, numbers)):
        if start > main_body_end:
            continue
        end = positions[i + 1] if i + 1 < len(positions) else len(full_text)
        text = full_text[start:end].strip()
        if not _is_plausible(text, start, prev_start):
            continue
        candidates.append((num, start, text))
        prev_start = start

    # Dedup by number: keep the candidate with the longest text
    by_num: Dict[str, Tuple[int, str]] = {}
    for num, start, text in candidates:
        if num not in by_num or len(text) > len(by_num[num][1]):
            by_num[num] = (start, text)

    # Sort by position to preserve document order
    chosen = sorted(by_num.items(), key=lambda x: x[1][0])
    clauses = []
    for num, (_, text) in chosen:
        clause_id, section_id = _make_ids(pattern.name, num)
        clauses.append(Clause(id=clause_id, section_id=section_id, text=text, page=None))

    return clauses


def segment_clauses(full_text: str) -> Tuple[List[Clause], Dict[str, Any]]:
    """
    Auto-detect heading style and split contract text into clause-level segments.
    Tries each known heading pattern; picks the one producing the most plausible clauses.
    Returns (clauses, stats). clauses is empty if no pattern matches (LLM fallback).
    stats includes "pattern" (winner name) and "candidates_by_pattern" (count per pattern).
    """
    stats: Dict[str, Any] = {
        "pattern": None,
        "candidates_by_pattern": {},
        "after_dedup_filter": 0,
    }

    if not (full_text or "").strip():
        return [], stats

    best_clauses: List[Clause] = []
    best_pattern_name: Optional[str] = None

    for pattern in HEADING_PATTERNS:
        clauses = _run_pattern(full_text, pattern)
        stats["candidates_by_pattern"][pattern.name] = len(clauses)
        if len(clauses) > len(best_clauses):
            best_clauses = clauses
            best_pattern_name = pattern.name

    stats["pattern"] = best_pattern_name
    stats["after_dedup_filter"] = len(best_clauses)
    return best_clauses, stats
