"""
Load playbook from YAML: rules with rule_id, description, risk_level, keywords/criteria.
Returns List[Rule] for Scanner use.
"""
from pathlib import Path
from typing import List, Union

import yaml

from app.schemas.playbook import Rule


def load_playbook(path: Union[str, Path]) -> List[Rule]:
    """
    Load playbook YAML and return list of Rule. Expects top-level key "rules" (list of rule dicts).
    """
    path = Path(path)
    if not path.exists():
        raise FileNotFoundError(f"Playbook not found: {path}")
    with open(path, "r", encoding="utf-8") as f:
        data = yaml.safe_load(f)
    if not data or "rules" not in data:
        return []
    return [Rule.model_validate(r) for r in data["rules"]]
