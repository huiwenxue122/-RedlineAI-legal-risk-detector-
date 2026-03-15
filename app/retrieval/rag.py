"""
RAG / graph-context API: given contract_id and clause_id, return clause text + graph context + snippets.
For use by Scanner and review agents.
"""
from typing import Any, Dict, List

from app.graph.query import get_clause_neighborhood
from app.retrieval.graph_context import build_graph_context


def get_context_for_clause(
    contract_id: str,
    clause_id: str,
    max_refs: int = 20,
    include_snippets: bool = True,
) -> Dict[str, Any]:
    """
    Return structured context for one clause: its text, graph context string, and optional snippets.
    Output: { "clause_text", "section_id", "graph_context", "snippets" }.
    """
    nb = get_clause_neighborhood(contract_id, clause_id, max_refs=max_refs)
    clause_text = nb.get("clause_text") or ""
    section_id = nb.get("section_id") or clause_id
    graph_context = build_graph_context(contract_id, clause_id, max_refs=max_refs)

    snippets: List[Dict[str, Any]] = []
    if include_snippets:
        for r in nb.get("references_out", []):
            snippets.append({"section_id": r.get("to_section_id") or r.get("to_clause_id"), "ref_text": r.get("ref_text", ""), "role": "out"})
        for r in nb.get("references_in", []):
            snippets.append({"section_id": r.get("from_section_id") or r.get("from_clause_id"), "ref_text": r.get("ref_text", ""), "role": "in"})

    return {
        "contract_id": contract_id,
        "clause_id": clause_id,
        "section_id": section_id,
        "clause_text": clause_text,
        "graph_context": graph_context,
        "snippets": snippets,
    }
