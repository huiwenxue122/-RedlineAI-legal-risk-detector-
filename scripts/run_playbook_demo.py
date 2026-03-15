"""
Load and print default playbook rules. Run from project root:
  python scripts/run_playbook_demo.py
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.agents import load_playbook

def main():
    path = Path(__file__).resolve().parent.parent / "data" / "playbooks" / "default.yaml"
    rules = load_playbook(path)
    print(f"Loaded {len(rules)} rules from {path.name}\n")
    for r in rules:
        print(f"  {r.rule_id}  [{r.risk_level.value}]  {r.description}")
        print(f"    keywords: {r.keywords}")
        if r.criteria:
            print(f"    criteria: {(r.criteria[:80] + '...') if len(r.criteria) > 80 else r.criteria}")
        print()

if __name__ == "__main__":
    main()
