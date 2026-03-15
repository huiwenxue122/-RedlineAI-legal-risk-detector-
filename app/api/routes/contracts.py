"""
Contract upload and demo endpoints.

- POST /contracts/upload: multipart PDF -> parse -> extract -> ingest; returns contract_id and status.
- POST /contracts/demo: run the same pipeline on the built-in sample contract (EX-10.4(a).pdf).
  Keeps the MVP demo path working without upload; do not remove.

Note: The extraction pipeline (rule-based clause segmenter) is tuned for contracts with
"Section X.Y" numbering. Other PDFs still run but may produce fewer clauses (LLM-only).

Demo can take 1–3 minutes (LLM extraction is slow); run in thread to avoid blocking the server.
"""
import asyncio
import uuid
from pathlib import Path

from fastapi import APIRouter, File, HTTPException, UploadFile

from app.pipeline import run_structural_pipeline

router = APIRouter(prefix="/contracts", tags=["contracts"])

# Built-in sample used by demo and MVP
SAMPLE_PDF_PATH = Path(__file__).resolve().parent.parent.parent.parent / "data" / "sample_contracts" / "EX-10.4(a).pdf"
SAMPLE_CONTRACT_ID = "EX-10.4(a)"


@router.post("/upload")
async def upload_contract(file: UploadFile = File(...)):
    """
    Upload a PDF contract: parse -> extract -> ingest to Neo4j.
    Returns contract_id (from filename stem or generated) and status.
    """
    if not file.filename or not file.filename.lower().endswith(".pdf"):
        raise HTTPException(status_code=400, detail="A PDF file is required")
    try:
        raw = await file.read()
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"Failed to read file: {e}")
    if not raw:
        raise HTTPException(status_code=400, detail="Empty file")
    contract_id = Path(file.filename).stem or f"contract_{uuid.uuid4().hex[:8]}"
    loop = asyncio.get_event_loop()
    try:
        contract, ingest_stats = await loop.run_in_executor(
            None,
            lambda: run_structural_pipeline(raw, contract_id=contract_id),
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Pipeline failed: {e}")
    return {
        "contract_id": contract_id,
        "status": "success",
        "clauses": len(contract.clauses),
        "definitions": len(contract.definitions),
        "ingest": "ok" if ingest_stats else "skipped",
    }


@router.post("/demo")
async def demo_contract():
    """
    Run the full pipeline on the built-in sample contract (EX-10.4(a).pdf).
    Use this for MVP demo so the sample-based data flow always works without upload.
    May take 1–3 minutes (LLM extraction). If it hangs, check the uvicorn terminal for errors.
    """
    if not SAMPLE_PDF_PATH.exists():
        raise HTTPException(status_code=503, detail="Sample contract file not found")
    loop = asyncio.get_event_loop()
    try:
        contract, ingest_stats = await loop.run_in_executor(
            None,
            lambda: run_structural_pipeline(SAMPLE_PDF_PATH, contract_id=SAMPLE_CONTRACT_ID),
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Pipeline failed: {e}")
    return {
        "contract_id": SAMPLE_CONTRACT_ID,
        "status": "success",
        "clauses": len(contract.clauses),
        "definitions": len(contract.definitions),
        "ingest": "ok" if ingest_stats else "skipped",
    }
