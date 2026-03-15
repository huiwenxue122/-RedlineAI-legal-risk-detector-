"""
Demo: run Scanner on one clause (random or specified). Run from project root:
  python scripts/run_scanner_demo.py [contract_id] [clause_id]
  If clause_id omitted, picks a random section from the graph.
Requires Neo4j with ingested contract + OPENAI_API_KEY.
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

def main():
    contract_id = sys.argv[1] if len(sys.argv) > 1 else "EX-10.4(a)"
    clause_id = sys.argv[2] if len(sys.argv) > 2 else None

    from app.retrieval import get_context_for_clause
    from app.agents import load_playbook, scan_clause

    # Resolve clause_id if not provided (random from graph)
    if clause_id is None:
        from app.graph.client import get_driver
        driver = get_driver()
        with driver.session() as session:
            r = session.run(
                "MATCH (c:Clause {contract_id: $contract_id}) RETURN c.id AS id ORDER BY c.id",
                contract_id=contract_id,
            )
            ids = [rec["id"] for rec in r if rec.get("id")]
        if not ids:
            print(f"No clauses in graph for {contract_id}. Run run_structural_pipeline.py first.")
            sys.exit(1)
        import random
        clause_id = random.choice(ids)
        print(f"Random clause: {clause_id} (from {len(ids)} in graph)\n")

    ctx = get_context_for_clause(contract_id, clause_id)
    clause_ref = ctx.get("section_id") or clause_id
    clause_text = ctx.get("clause_text") or ""
    if not clause_text.strip():
        print(
            f"Warning: clause_text is empty for {clause_id}. "
            "Clause may not exist in Neo4j or has no text (e.g. only rule-based segments were ingested and this section was not included). "
            "Scanner will return 0 findings.\n"
        )
    rules = load_playbook(Path(__file__).resolve().parent.parent / "data" / "playbooks" / "default.yaml")

    print(f"Scanning: {clause_ref}\n")
    findings = scan_clause(
        clause_text=clause_text,
        clause_ref=clause_ref,
        rules=rules,
        graph_context=ctx.get("graph_context") or "",
    )
    print(f"Findings: {len(findings)}")
    for i, f in enumerate(findings, 1):
        s = f["evidence_summary"]
        print(f"  {i}. [{f['rule_triggered']}] {(s[:120] + '...') if len(s) > 120 else s}")
    if not findings:
        print("  (none)")

if __name__ == "__main__":
    main()
