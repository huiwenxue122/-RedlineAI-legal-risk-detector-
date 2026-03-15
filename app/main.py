"""
FastAPI application entry. Mounts health, contracts, review routes; CORS and exception handling.
Run: uvicorn app.main:app --reload
"""
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.routes import health, contracts, review

app = FastAPI(title="ContractSentinel API", version="0.1.0")

# CORS: allow frontend (and dev tools)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Global exception handler: unhandled exceptions -> 500 with JSON body (HTTPException is handled by FastAPI)
@app.exception_handler(Exception)
def unhandled_exception_handler(request, exc: Exception):
    from fastapi import HTTPException
    from fastapi.responses import JSONResponse
    if isinstance(exc, HTTPException):
        raise exc
    return JSONResponse(
        status_code=500,
        content={"detail": "Internal server error", "error": str(exc)},
    )

app.include_router(health.router)
app.include_router(contracts.router)
app.include_router(review.router)
