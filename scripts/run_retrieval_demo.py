"""
Demo: get graph context for one clause. Run from project root:
  python scripts/run_retrieval_demo.py [contract_id]
  If clause_id is omitted, a random section is picked from the contract.
  e.g. python scripts/run_retrieval_demo.py EX-10.4(a)
Requires Neo4j with data from run_structural_pipeline.py.
"""
import random
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))


def _list_clause_ids(contract_id: str):
    from app.graph.client import get_driver
    driver = get_driver()
    with driver.session() as session:
        r = session.run(
            "MATCH (c:Clause {contract_id: $contract_id}) RETURN c.id AS id ORDER BY c.id",
            contract_id=contract_id,
        )
        return [rec["id"] for rec in r if rec.get("id")]


def main():
    contract_id = sys.argv[1] if len(sys.argv) > 1 else "EX-10.4(a)"
    clause_id = sys.argv[2] if len(sys.argv) > 2 else None

    if clause_id is None:
        ids = _list_clause_ids(contract_id)
        if not ids:
            print(f"No clauses found for contract_id={contract_id}. Run run_structural_pipeline.py first.")
            sys.exit(1)
        clause_id = random.choice(ids)
        print(f"Random section: {clause_id} (from {len(ids)} clauses)\n")

    from app.retrieval import get_context_for_clause

    print(f"Contract: {contract_id}  Clause: {clause_id}\n")
    ctx = get_context_for_clause(contract_id, clause_id)
    print("--- clause_text (first 300 chars) ---")
    print(ctx["clause_text"][:300] or "(empty)")
    print("\n--- graph_context ---")
    print(ctx["graph_context"])
    print("\n--- snippets ---")
    print(ctx["snippets"])


if __name__ == "__main__":
    main()
