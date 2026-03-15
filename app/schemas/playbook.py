"""
Playbook: review rules with risk levels. Used by Scanner / review agents.
"""
from enum import Enum
from typing import List, Optional

from pydantic import BaseModel, Field


class RiskLevel(str, Enum):
    """Risk severity for a rule or finding."""
    Low = "Low"
    Medium = "Medium"
    High = "High"
    Critical = "Critical"


class Rule(BaseModel):
    """A single playbook rule for contract review."""
    rule_id: str = Field(..., description="Unique rule id, e.g. R001")
    description: str = Field(..., description="What this rule checks for")
    risk_level: RiskLevel = Field(..., description="Severity if triggered")
    keywords: List[str] = Field(default_factory=list, description="Keywords/phrases to match in clause text")
    criteria: Optional[str] = Field(None, description="Optional free-form matching criteria for LLM")
