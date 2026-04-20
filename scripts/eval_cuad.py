"""
CUAD Evaluation Script for RedlineAI Scanner

Measures Scanner precision and recall against CUAD expert annotations.

CUAD categories → our playbook rules:
  Uncapped Liability              → S001
  Cap On Liability                → S002
  Minimum Commitment              → S007  (lock-in)
  Termination For Convenience     → S008  (no vendor exit right)
  Renewal Term                    → S009  (auto-renewal)
  Notice Period To Terminate Renewal → S010
  Revenue/Profit Sharing          → S005  (payment terms proxy)

Usage:
  python scripts/eval_cuad.py --n 25 --out data/benchmark/eval_results.json
"""
import argparse
import json
import os
import re
import sys
import time
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

# allow imports from project root
sys.path.insert(0, str(Path(__file__).parent.parent))

from dotenv import load_dotenv
load_dotenv()

from datasets import load_dataset
from app.extraction.clause_segmenter import segment_clauses
from app.agents.playbook_loader import load_playbook
from app.agents.scanner import scan_clause

# ── CUAD category → rule mapping ─────────────────────────────────────────────

CUAD_TO_RULES: Dict[str, List[str]] = {
    "Uncapped Liability":                  ["S001"],
    "Cap On Liability":                    ["S002"],
    "Minimum Commitment":                  ["S007"],
    "Termination For Convenience":         ["S008"],
    "Renewal Term":                        ["S009"],
    "Notice Period To Terminate Renewal":  ["S010"],
    "Revenue/Profit Sharing":              ["S005"],
}

RULE_TO_CUAD: Dict[str, List[str]] = {}
for cat, rules in CUAD_TO_RULES.items():
    for r in rules:
        RULE_TO_CUAD.setdefault(r, []).append(cat)


def extract_cuad_category(question: str) -> Optional[str]:
    m = re.search(r'"(.+?)"', question)
    return m.group(1) if m else None


def text_overlap(a: str, b: str, threshold: float = 0.3) -> bool:
    """True if at least `threshold` of the shorter string appears in the longer."""
    a, b = a.lower().strip(), b.lower().strip()
    if not a or not b:
        return False
    shorter, longer = (a, b) if len(a) <= len(b) else (b, a)
    # sliding window: check if any 40-char chunk of shorter appears in longer
    chunk = 40
    if len(shorter) < chunk:
        return shorter in longer
    hits = sum(1 for i in range(0, len(shorter) - chunk + 1, chunk // 2)
               if shorter[i:i+chunk] in longer)
    windows = max(1, (len(shorter) - chunk) // (chunk // 2) + 1)
    return hits / windows >= threshold


def get_ground_truth(paragraphs: List[Dict]) -> Dict[str, List[str]]:
    """
    Returns dict: cuad_category → [answer_text, ...] for relevant categories.
    Only includes categories that map to our rules.
    """
    gt: Dict[str, List[str]] = {cat: [] for cat in CUAD_TO_RULES}
    for para in paragraphs:
        for qa in para["qas"]:
            cat = extract_cuad_category(qa["question"])
            if cat not in CUAD_TO_RULES:
                continue
            if not qa["is_impossible"]:
                for ans in qa["answers"]:
                    text = ans["text"].strip()
                    if text:
                        gt[cat].append(text)
    return gt


def run_scanner_on_contract(
    contract_text: str,
    rules: List[Any],
) -> Tuple[List[Dict], Dict[str, str]]:
    """
    Segment contract and run Scanner on each clause.
    Returns (findings, clause_texts) where clause_texts maps clause_ref → full text.
    """
    clauses, _ = segment_clauses(contract_text)
    if not clauses:
        from app.schemas.contract import Clause
        clauses = [Clause(
            id="full_text",
            section_id="full_text",
            heading="Full Contract",
            text=contract_text[:8000],
            contract_id="eval",
        )]

    all_findings = []
    clause_texts: Dict[str, str] = {}
    for clause in clauses:
        ref = clause.section_id or clause.id
        clause_texts[ref] = clause.text
        try:
            findings = scan_clause(
                clause_text=clause.text,
                clause_ref=ref,
                rules=rules,
                graph_context="",
            )
            all_findings.extend(findings)
        except Exception as e:
            print(f"  [warn] scan error on {ref}: {e}")
        time.sleep(0.3)

    return all_findings, clause_texts


def evaluate_contract(
    contract_text: str,
    ground_truth: Dict[str, List[str]],
    rules: List[Any],
) -> Dict[str, Any]:
    """
    Run Scanner and compare against ground truth.
    Overlap is checked against full clause text (not evidence summary).
    Returns per-rule TP/FP/FN counts.
    """
    findings, clause_texts = run_scanner_on_contract(contract_text, rules)

    # group findings by rule → list of clause texts
    found_rules: Dict[str, List[str]] = {}
    for f in findings:
        rid = f.get("rule_triggered", "")
        clause_ref = f.get("clause_ref", "")
        clause_text = clause_texts.get(clause_ref, f.get("evidence_summary", ""))
        found_rules.setdefault(rid, []).append(clause_text)

    results: Dict[str, Dict] = {}

    for cuad_cat, gt_spans in ground_truth.items():
        rule_ids = CUAD_TO_RULES[cuad_cat]
        has_gt = len(gt_spans) > 0

        scanner_flagged = any(rid in found_rules for rid in rule_ids)

        # Overlap: compare full clause text to CUAD answer span
        true_positive = False
        if scanner_flagged and has_gt:
            for rid in rule_ids:
                for clause_text in found_rules.get(rid, []):
                    for span in gt_spans:
                        if text_overlap(clause_text, span):
                            true_positive = True
                            break

        for rid in rule_ids:
            if rid not in results:
                results[rid] = {"tp": 0, "fp": 0, "fn": 0, "cuad_cat": cuad_cat}

            if has_gt and true_positive:
                results[rid]["tp"] += 1
            elif has_gt and not scanner_flagged:
                results[rid]["fn"] += 1
            elif not has_gt and scanner_flagged and rid in found_rules:
                results[rid]["fp"] += 1

    return {"findings": findings, "per_rule": results}


def aggregate_metrics(per_contract: List[Dict]) -> Dict[str, Dict]:
    totals: Dict[str, Dict] = {}
    for contract_result in per_contract:
        for rid, counts in contract_result["per_rule"].items():
            if rid not in totals:
                totals[rid] = {"tp": 0, "fp": 0, "fn": 0,
                               "cuad_cat": counts["cuad_cat"]}
            totals[rid]["tp"] += counts["tp"]
            totals[rid]["fp"] += counts["fp"]
            totals[rid]["fn"] += counts["fn"]

    metrics = {}
    for rid, c in totals.items():
        tp, fp, fn = c["tp"], c["fp"], c["fn"]
        precision = tp / (tp + fp) if (tp + fp) > 0 else None
        recall    = tp / (tp + fn) if (tp + fn) > 0 else None
        f1 = (2 * precision * recall / (precision + recall)
              if precision and recall else None)
        metrics[rid] = {
            "cuad_category": c["cuad_cat"],
            "tp": tp, "fp": fp, "fn": fn,
            "precision": round(precision, 3) if precision is not None else None,
            "recall":    round(recall,    3) if recall    is not None else None,
            "f1":        round(f1,        3) if f1        is not None else None,
        }
    return metrics


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--n", type=int, default=25,
                        help="Number of contracts to evaluate (default 25)")
    parser.add_argument("--out", type=str,
                        default="data/benchmark/eval_results.json",
                        help="Output JSON path")
    parser.add_argument("--playbook", type=str,
                        default="data/playbooks/saas_customer.yaml")
    args = parser.parse_args()

    print(f"Loading playbook: {args.playbook}")
    rules = load_playbook(args.playbook)
    print(f"  {len(rules)} rules loaded")

    print("Loading CUAD dataset...")
    ds = load_dataset("kenlevine/CUAD", verification_mode="no_checks")
    contracts = ds["train"][0]["data"]
    contracts = contracts[:args.n]
    print(f"  Evaluating {len(contracts)} contracts")

    Path(args.out).parent.mkdir(parents=True, exist_ok=True)

    per_contract_results = []
    for i, contract in enumerate(contracts):
        title = contract["title"]
        print(f"\n[{i+1}/{len(contracts)}] {title[:60]}")

        paragraphs = contract["paragraphs"]
        contract_text = paragraphs[0]["context"] if paragraphs else ""
        if not contract_text:
            print("  [skip] empty contract")
            continue

        ground_truth = get_ground_truth(paragraphs)
        gt_summary = {c: len(v) for c, v in ground_truth.items() if v}
        print(f"  GT clauses present: {gt_summary}")

        try:
            result = evaluate_contract(contract_text, ground_truth, rules)
            result["title"] = title
            per_contract_results.append(result)
            findings_count = len(result["findings"])
            print(f"  Scanner findings: {findings_count}")
        except Exception as e:
            print(f"  [error] {e}")

    print("\n" + "="*60)
    print("AGGREGATE METRICS")
    print("="*60)

    metrics = aggregate_metrics(per_contract_results)

    all_tp = all_fp = all_fn = 0
    for rid, m in sorted(metrics.items()):
        print(f"\n{rid} ({m['cuad_category']})")
        print(f"  TP={m['tp']}  FP={m['fp']}  FN={m['fn']}")
        print(f"  Precision={m['precision']}  Recall={m['recall']}  F1={m['f1']}")
        all_tp += m["tp"]
        all_fp += m["fp"]
        all_fn += m["fn"]

    macro_p = sum(m["precision"] for m in metrics.values() if m["precision"] is not None)
    macro_r = sum(m["recall"]    for m in metrics.values() if m["recall"]    is not None)
    n = len([m for m in metrics.values() if m["precision"] is not None])

    print(f"\nMACRO AVERAGE (across {n} rules with data):")
    if n:
        print(f"  Precision={macro_p/n:.3f}  Recall={macro_r/n:.3f}")

    output = {
        "config": {"n_contracts": len(per_contract_results), "playbook": args.playbook},
        "per_rule_metrics": metrics,
        "macro_avg": {
            "precision": round(macro_p/n, 3) if n else None,
            "recall":    round(macro_r/n, 3) if n else None,
        },
    }

    with open(args.out, "w") as f:
        json.dump(output, f, indent=2)
    print(f"\nResults saved to {args.out}")


if __name__ == "__main__":
    main()
