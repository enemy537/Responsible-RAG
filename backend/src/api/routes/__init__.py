"""
routes/__init__.py — Route aggregator
======================================
Imports and includes all sub-routers under a single top-level router.

Usage:
    from src.api.routes import router
    app.include_router(router, prefix="/api/v1")
"""

from fastapi import APIRouter

from src.api.routes.admin import admin_router
from src.api.routes.auth import router as auth_router
from src.api.routes.chat import router as chat_router
from src.api.routes.documents import router as documents_router
from src.api.routes.feedback import router as feedback_router
from src.api.routes.health import router as health_router
from src.api.routes.metadata import router as metadata_router
from src.api.routes.profile import router as profile_router
from src.api.routes.search import router as search_router

router = APIRouter()

# ── Health ────────────────────────────────────────────────────────────────────
router.include_router(health_router, prefix="/health", tags=["Health"])

# ── Auth ──────────────────────────────────────────────────────────────────────
router.include_router(auth_router, prefix="/auth", tags=["Auth"])

# ── Metadata extraction ──────────────────────────────────────────────────────
router.include_router(metadata_router, prefix="/metadata", tags=["Metadata"])

# ── Profile & Consent ─────────────────────────────────────────────────────────
router.include_router(profile_router, prefix="/profile", tags=["Profile"])

# ── Chat ──────────────────────────────────────────────────────────────────────
router.include_router(chat_router, prefix="/chat", tags=["Chat"])

# ── Documents (ingestion) ─────────────────────────────────────────────────────
router.include_router(documents_router, prefix="/documents", tags=["Documents"])

# ── Search ────────────────────────────────────────────────────────────────────
router.include_router(search_router, prefix="/search", tags=["Search"])

# ── Feedback ──────────────────────────────────────────────────────────────────
router.include_router(feedback_router, prefix="/feedback", tags=["Feedback"])

# ── Admin ─────────────────────────────────────────────────────────────────────
router.include_router(admin_router, prefix="/admin", tags=["Admin"])
