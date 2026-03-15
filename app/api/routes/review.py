"""
Review trigger and risk memo API.

POST /review: body { contract_id, optional playbook_id } -> run LangGraph review, return StructuredRiskMemo.
GET /review: query contract_id, optional playbook_id -> same.
"""
from pathlib import Path
from typing import Optional

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel, Field

from app.agents import run_review
from app.schemas.risk_memo import StructuredRiskMemo

router = APIRouter(tags=["review"])


class ReviewRequest(BaseModel):
    """Request body for POST /review."""
    contract_id: str = Field(..., description="Contract id in Neo4j")
    playbook_id: Optional[str] = Field(None, description="Playbook id, e.g. default")

PLAYBOOKS_DIR = Path(__file__).resolve().parent.parent.parent.parent / "data" / "playbooks"
DEFAULT_PLAYBOOK = "default.yaml"


def _playbook_path(playbook_id: str | None) -> str:
    if not playbook_id or playbook_id.strip() == "":
        return str(PLAYBOOKS_DIR / DEFAULT_PLAYBOOK)
    # Allow "default" or filename without extension
    name = playbook_id.strip()
    if not name.endswith(".yaml") and not name.endswith(".yml"):
        name = f"{name}.yaml"
    path = PLAYBOOKS_DIR / name
    if not path.exists():
        return str(PLAYBOOKS_DIR / DEFAULT_PLAYBOOK)
    return str(path)


@router.post("/review", response_model=StructuredRiskMemo)
def trigger_review_post(body: ReviewRequest):
    """
    Run review pipeline (Scanner → Critic → Evaluator) for the given contract.
    Returns StructuredRiskMemo (risk items with clause, risk_level, rule_triggered, reason, escalation, citation).
    """
    contract_id = (body.contract_id or "").strip()
    if not contract_id:
        raise HTTPException(status_code=400, detail="contract_id is required")
    playbook_path = _playbook_path(body.playbook_id)
    try:
        memo = run_review(contract_id=contract_id, playbook_path=playbook_path)
        return memo
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Review failed: {e}")


@router.get("/review", response_model=StructuredRiskMemo)
def trigger_review_get(
    contract_id: str = Query(..., description="Contract id in Neo4j"),
    playbook_id: str | None = Query(None, description="Playbook id, e.g. default"),
):
    """
    Same as POST /review: run review pipeline and return StructuredRiskMemo.
    """
    if not (contract_id or "").strip():
        raise HTTPException(status_code=400, detail="contract_id is required")
    playbook_path = _playbook_path(playbook_id)
    try:
        memo = run_review(contract_id=contract_id.strip(), playbook_path=playbook_path)
        return memo
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Review failed: {e}")
