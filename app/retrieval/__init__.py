# Graph-augmented retrieval: context for clauses (definitions, refs, obligations).
# Note: snippets currently contains only reference-based snippets. For clauses without
# references, snippets may be empty even when graph_context includes definitions or obligations.
from app.retrieval.graph_context import build_graph_context
from app.retrieval.rag import get_context_for_clause

__all__ = ["build_graph_context", "get_context_for_clause"]
