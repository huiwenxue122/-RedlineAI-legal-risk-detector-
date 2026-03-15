"""
Build a single "graph context" text from clause neighborhood (definitions, references, obligations).
Used to augment clause text for review/Scanner.
"""
from typing import Any, Dict

from app.graph.query import get_clause_neighborhood


def build_graph_context(
    contract_id: str,
    clause_id: str,
    max_refs: int = 20,
) -> str:
    """
    Fetch clause neighborhood from Neo4j and format as one string for LLM context.
    Includes: definitions in this clause, obligations, outgoing/incoming references (section ids + ref_text).
    """
    nb = get_clause_neighborhood(contract_id, clause_id, max_refs=max_refs)
    parts = []

    if nb.get("definitions"):
        parts.append("Definitions in this clause:")
        for d in nb["definitions"]:
            parts.append(f"  - {d['term']}: {_truncate(d['definition'], 200)}")

    if nb.get("obligations"):
        parts.append("Obligations in this clause:")
        for o in nb["obligations"]:
            parts.append(f"  - {_truncate(o['description'], 200)}")

    if nb.get("references_out"):
        parts.append("This clause references:")
        for r in nb["references_out"]:
            parts.append(f"  - {r['to_section_id'] or r.get('to_clause_id', '')} ({r['ref_text']})")

    if nb.get("references_in"):
        parts.append("Referenced by:")
        for r in nb["references_in"]:
            parts.append(f"  - {r['from_section_id'] or r.get('from_clause_id', '')} ({r['ref_text']})")

    if not parts:
        return "No related definitions, obligations, or cross-references in the graph for this clause."
    return "\n".join(parts)


def _truncate(s: str, max_len: int) -> str:
    if not s:
        return ""
    return (s[:max_len] + "...") if len(s) > max_len else s
