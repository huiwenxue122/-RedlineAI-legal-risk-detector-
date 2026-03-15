"""
Demo: run Scanner → Critic → Evaluator on one clause. Run from project root:
  python scripts/run_evaluator_demo.py "EX-10.4(a)" section_7_2
  If clause_id omitted, picks a random clause.
Prints for each finding: rule, evidence, justified, confidence, escalation, fallback_language, reason.
Requires Neo4j + OPENAI_API_KEY.
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))


def main():
    contract_id = sys.argv[1] if len(sys.argv) > 1 else "EX-10.4(a)"
    clause_id = sys.argv[2] if len(sys.argv) > 2 else None

    root = Path(__file__).resolve().parent.parent
    from app.retrieval import get_context_for_clause
    from app.agents import load_playbook, scan_clause, evaluate_finding, evaluate_escalation

    rules = load_playbook(root / "data" / "playbooks" / "default.yaml")
    rule_by_id = {r.rule_id: r for r in rules}

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
    clause_text = (ctx.get("clause_text") or "").strip()
    graph_context = ctx.get("graph_context") or ""

    if not clause_text:
        print(f"Warning: no clause text for {clause_id}.\n")

    print(f"Clause: {clause_ref}\nRunning Scanner ...")
    findings = scan_clause(
        clause_text=ctx.get("clause_text") or "",
        clause_ref=clause_ref,
        rules=rules,
        graph_context=graph_context,
    )
    print(f"Findings: {len(findings)}\n")

    if not findings:
        print("No findings. Run on a clause that triggers a rule (e.g. section_7_2).")
        return

    print("Running Critic → Evaluator on each finding:\n")
    for i, f in enumerate(findings, 1):
        rule = rule_by_id.get(f.get("rule_triggered"))
        rule_desc = (rule.description or "") + (" " + (rule.criteria or "") if rule and rule.criteria else "") if rule else ""
        risk_level = rule.risk_level.value if rule else "Medium"

        critic_result = evaluate_finding(
            finding=f,
            clause_text=clause_text or ctx.get("clause_text") or "",
            graph_context=graph_context,
            rule_description=rule_desc or f"Rule {f.get('rule_triggered')}",
        )
        eval_result = evaluate_escalation(
            finding=f,
            critic_result=critic_result,
            risk_level=risk_level,
            clause_text=clause_text or ctx.get("clause_text") or "",
        )

        print(f"  Finding {i}: [{f['rule_triggered']}] {f['evidence_summary'][:80]}...")
        print(f"    Critic — Justified: {critic_result['justified']}, Confidence: {critic_result.get('confidence', 'medium')}")
        print(f"    Critic reason: {critic_result['reason']}")
        print(f"    Evaluator — Escalation: {eval_result['escalation']}")
        if eval_result.get("fallback_language"):
            print(f"    Fallback language: {eval_result['fallback_language'][:120]}{'...' if len(eval_result.get('fallback_language', '')) > 120 else ''}")
        print(f"    Evaluator reason: {eval_result['reason']}\n")


if __name__ == "__main__":
    main()
