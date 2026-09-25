"""
routes/health.py — Health-check endpoint
==========================================
Lightweight readiness/liveness probe. Does NOT load the RAG chain, so it
always responds quickly even under memory pressure.

Endpoints:
    GET /api/v1/health          → {"status": "ok", "version": "0.1.0"}
    GET /api/v1/health/ready    → {"status": "ok", "rag_chain_loaded": bool}
"""

from fastapi import APIRouter, Depends

from src.api.deps import get_settings
from src.core.config import Settings

router = APIRouter()


@router.get("")
async def health():
    """
    Basic liveness check.
    Always responds 200 as long as the server is running.
    """
    return {"status": "ok", "version": "0.1.0"}


@router.get("/ready")
async def readiness(settings: Settings = Depends(get_settings)):
    """
    Readiness probe. Checks that critical dependencies are available.

    - Settings loaded
    - RAG chain initialised (lazy)
    - Vector store reachable (optional)
    """
    # TODO: Add real readiness checks
    # from src.api.deps import get_rag_chain
    # chain = await get_rag_chain()
    return {
        "status": "ok",
        "rag_chain_loaded": False,
        "qdrant_connected": False,
    }
