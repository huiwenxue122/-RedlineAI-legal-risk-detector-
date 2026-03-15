"""
实施文档中的两项 Scanner 验证。

验证 1：区分「空文本导致 0」vs「有文本但未命中」
  - 类别 1：跑有 text 的 clause（如 section_5_1），确认 CLAUSE/GRAPH 非空且 Findings: 0 → 规则未命中
  - 类别 2：跑一个会触发 Warning 的 clause（图里无此条或无 text）→ 图里没数据

验证 2：在真实条款上打出非空 findings
  - 先查图中 section_7_2 / section_7_6 / section_5_5 / section_9_1 是否有 text
  - 对有 text 的跑 Scanner，看是否出现非空 findings

用法（项目根、已激活 .venv，需 Neo4j + OPENAI_API_KEY）：
  python scripts/run_scanner_verifications.py
  python scripts/run_scanner_verifications.py "EX-10.4(a)"
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))


def _get_clause_ids_in_graph(contract_id: str):
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

    from app.retrieval import get_context_for_clause
    from app.agents import load_playbook, scan_clause

    playbook_path = Path(__file__).resolve().parent.parent / "data" / "playbooks" / "default.yaml"
    rules = load_playbook(playbook_path)
    ids_in_graph = _get_clause_ids_in_graph(contract_id)
    if not ids_in_graph:
        print(f"No clauses in graph for {contract_id}. Run run_structural_pipeline.py first.")
        sys.exit(1)

    print(f"Contract: {contract_id}  图中共 {len(ids_in_graph)} 个 clause\n")
    print("=" * 60)
    print("验证 1：区分「空文本导致 0」vs「有文本但未命中」")
    print("=" * 60)

    # 类别 1：有 text 的 clause（优先 section_5_1，否则用图中第一个有 text 的）
    prefer_1 = ["section_5_1", "section_5_2", "section_1_1"]
    c1_id = None
    ctx1 = None
    for cid in prefer_1 + ids_in_graph:
        if cid in ids_in_graph or cid in prefer_1:
            ctx = get_context_for_clause(contract_id, cid)
            if (ctx.get("clause_text") or "").strip():
                c1_id = cid
                ctx1 = ctx
                break
    if not c1_id:
        c1_id = ids_in_graph[0]
        ctx1 = get_context_for_clause(contract_id, c1_id)
    clause_text_1 = (ctx1.get("clause_text") or "").strip()
    graph_1 = (ctx1.get("graph_context") or "").strip()
    has_text_1 = bool(clause_text_1)
    has_graph_1 = bool(graph_1)

    print(f"\n类别 1 — 有 text 的 clause: {c1_id}")
    print(f"  clause_text 非空: {has_text_1}  (前 80 字: {repr((clause_text_1[:80] + ('...' if len(clause_text_1) > 80 else '')))}")
    print(f"  graph_context 非空: {has_graph_1}")
    if has_text_1:
        findings_1 = scan_clause(
            clause_text=ctx1["clause_text"],
            clause_ref=ctx1.get("section_id") or c1_id,
            rules=rules,
            graph_context=ctx1.get("graph_context") or "",
        )
        print(f"  Findings: {len(findings_1)}")
        if findings_1:
            for f in findings_1:
                print(f"    - [{f['rule_triggered']}] {f['evidence_summary'][:80]}...")
        else:
            print("  → 结论: 有文本但 0 findings，属于「规则未命中」，不是数据缺失。")
    else:
        print("  → 图中所有 clause 的 text 均为空，无法演示类别 1；请先跑 run_structural_pipeline.py 确保有条文写入。")

    # 类别 2：会触发 Warning 的 clause（图里不存在或无 text）
    c2_id = None
    for cid in ["section_9_1", "section_10_1", "section_12_1", "section_99_1"]:
        ctx2 = get_context_for_clause(contract_id, cid)
        if not (ctx2.get("clause_text") or "").strip():
            c2_id = cid
            break
    if not c2_id:
        c2_id = "section_99_1"  # 通常不存在
    ctx2 = get_context_for_clause(contract_id, c2_id)
    clause_text_2 = (ctx2.get("clause_text") or "").strip()
    print(f"\n类别 2 — 会触发 Warning 的 clause: {c2_id} (图中存在: {c2_id in ids_in_graph})")
    print(f"  clause_text 非空: {bool(clause_text_2)}")
    if not clause_text_2:
        print("  → 结论: clause_text 为空，属于「图里没数据」；demo 会打 Warning。")
    else:
        print("  → 该 clause 在图中有 text，未触发「图里没数据」。")

    print("\n" + "=" * 60)
    print("验证 2：在真实条款上打出非空 findings")
    print("=" * 60)

    candidates_v2 = ["section_7_2", "section_7_6", "section_5_5", "section_9_1"]
    print("\n先检查图中这些 clause 是否有 text：")
    for cid in candidates_v2:
        ctx = get_context_for_clause(contract_id, cid)
        text = (ctx.get("clause_text") or "").strip()
        in_graph = cid in ids_in_graph
        print(f"  {cid}: 在图中={in_graph}, text 非空={bool(text)}, len={len(text)}")
    print("\n对有 text 的 clause 跑 Scanner：")
    for cid in candidates_v2:
        ctx = get_context_for_clause(contract_id, cid)
        text = (ctx.get("clause_text") or "").strip()
        if not text:
            print(f"  {cid}: 无 text，跳过")
            continue
        findings = scan_clause(
            clause_text=ctx["clause_text"],
            clause_ref=ctx.get("section_id") or cid,
            rules=rules,
            graph_context=ctx.get("graph_context") or "",
        )
        print(f"  {cid}: Findings={len(findings)}")
        for f in findings:
            print(f"    - [{f['rule_triggered']}] {f['evidence_summary'][:100]}...")

    print("\n完成。")


if __name__ == "__main__":
    main()
