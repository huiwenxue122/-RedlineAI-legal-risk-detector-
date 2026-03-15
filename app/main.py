"""
FastAPI application entry. Mounts health and contracts routes.
Run: uvicorn app.main:app --reload
"""
from fastapi import FastAPI

from app.api.routes import health, contracts, review

app = FastAPI(title="ContractSentinel API", version="0.1.0")
app.include_router(health.router)
app.include_router(contracts.router)
app.include_router(review.router)
