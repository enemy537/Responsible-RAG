"""
routes/admin/__init__.py — Admin sub-router
==============================================
Aggregates admin-only endpoints under a single prefix.

Usage:
    router.include_router(admin_router, prefix="/admin", tags=["Admin"])
"""

from fastapi import APIRouter

from src.api.routes.admin.alerts import router as alerts_router
from src.api.routes.admin.dashboard import router as dashboard_router
from src.api.routes.admin.sources import router as sources_router
from src.api.routes.admin.users import router as users_router

admin_router = APIRouter()

admin_router.include_router(dashboard_router, prefix="/dashboard", tags=["Admin"])
admin_router.include_router(sources_router, prefix="/sources", tags=["Admin"])
admin_router.include_router(users_router, prefix="/users", tags=["Admin"])
admin_router.include_router(alerts_router, prefix="/alerts", tags=["Admin"])
