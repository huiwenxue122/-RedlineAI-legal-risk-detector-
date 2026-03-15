"""
诊断测试 1：人工构造一条 100% 应命中的条款，验证 Scanner 能否返回 findings。

若这条仍返回空 → 问题在 Scanner 逻辑 / prompt / rules_text 组装 / 解析。
若这条能命中 R003（甚至 R001）→ 代码正常，问题在 playbook 覆盖或合同措辞。

用法（项目根目录、已激活 .venv）：
  python scripts/run_scanner_diagnostic.py
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

def main():
    from app.agents.scanner import scan_clause
    from app.agents.playbook_loader import load_playbook

    playbook_path = Path(__file__).resolve().parent.parent / "data" / "playbooks" / "default.yaml"
    rules = load_playbook(playbook_path)

    clause_text = """
Supplier shall indemnify, defend, and hold harmless Company
from any and all damages, liabilities, losses, and claims,
without limitation.
""".strip()

    print("=== 诊断测试 1：人工构造必中条款 ===\n")
    print("Clause text (应触发 R003 Broad indemnification，可能触达 R001):")
    print(clause_text)
    print()

    findings = scan_clause(
        clause_text=clause_text,
        clause_ref="Test Clause",
        rules=rules,
        graph_context="",
    )

    print(f"Findings: {len(findings)}")
    if findings:
        for i, f in enumerate(findings, 1):
            print(f"  {i}. [{f['rule_triggered']}] {f['evidence_summary'][:120]}{'...' if len(f['evidence_summary']) > 120 else ''}")
        print("\n结论: Scanner 能命中明确措辞 → 代码/解析正常，可优先加强 playbook 或 prompt 敏感度。")
    else:
        print("  (none)")
        print("\n结论: 人工必中条款仍为空 → 需检查 Scanner prompt / rules_text 组装 / response 解析。")
        print("建议: 设置 CONTRACT_SENTINEL_DEBUG_SCANNER=1 后重跑，查看实际传入模型的 rules/clause/context。")

if __name__ == "__main__":
    main()
