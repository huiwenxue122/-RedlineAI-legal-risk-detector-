"""
Shared fixtures for unit tests. Minimal PDF, sample text/clauses, mock Neo4j driver.
"""
from unittest.mock import MagicMock

import pytest

# Minimal one-page PDF (PyMuPDF)
try:
    import fitz
    HAS_FITZ = True
except ImportError:
    HAS_FITZ = False


@pytest.fixture
def minimal_pdf_bytes():
    """Create a minimal valid PDF in memory for parse_pdf tests."""
    if not HAS_FITZ:
        pytest.skip("PyMuPDF (fitz) not installed")
    doc = fitz.open()
    page = doc.new_page()
    page.insert_text((72, 72), "Section 1.1  Test clause content for parsing.")
    pdf_bytes = doc.tobytes()
    doc.close()
    return pdf_bytes


@pytest.fixture
def sample_full_text_for_segment():
    """Full text with Section X.Y headers in first 55%; long enough to pass segmenter heuristics."""
    # MIN_CLAUSE_CHARS=100, MIN_FIRST_LINE_CHARS=40, MAIN_BODY_FRACTION=0.55
    line1 = "Section 1.1  Definitions and interpretation."
    body1 = "The following terms have the meanings set forth below. " * 5
    line2 = "Section 1.2  Entire agreement."
    body2 = "This agreement constitutes the entire agreement between the parties. " * 5
    return f"{line1}\n\n{body1}\n\n{line2}\n\n{body2}"


@pytest.fixture
def sample_clauses_for_cross_ref():
    """Clauses with section ids and text containing 'Section 4.2' for extract_cross_references."""
    from app.schemas.contract import Clause
    return [
        Clause(id="section_7_2", section_id="7.2", text="Indemnification is subject to Section 4.2 and Section 5.1."),
        Clause(id="section_4_2", section_id="4.2", text="Limitation of liability applies."),
        Clause(id="section_5_1", section_id="5.1", text="Term and termination."),
    ]


@pytest.fixture
def sample_contract():
    """Minimal Contract for ingest_contract tests."""
    from app.schemas.contract import Contract, Clause, Definition, Party, Obligation, CrossReference
    return Contract(
        contract_id="test_contract",
        raw_text="Sample text",
        clauses=[
            Clause(id="section_1_1", section_id="1.1", text="First clause text."),
        ],
        definitions=[Definition(term="Agreement", definition="This Agreement.", source_clause_id="section_1_1")],
        cross_references=[],
        parties=[Party(name="Company", description="The Company")],
        obligations=[Obligation(description="Pay fees.", clause_id="section_1_1")],
    )


@pytest.fixture
def mock_neo4j_driver():
    """Mock Neo4j driver and session for graph tests."""
    session = MagicMock()
    driver = MagicMock()
    driver.session.return_value.__enter__ = MagicMock(return_value=session)
    driver.session.return_value.__exit__ = MagicMock(return_value=False)
    return driver, session
