"""
api/__init__.py — FastAPI application factory
==============================================
Usage:
    from src.api import create_app
    app = create_app()

This factory builds the FastAPI app, registers routers, and sets up
lifespan handlers for startup/shutdown.
"""

import logging
from contextlib import asynccontextmanager

# FastAPI is imported lazily inside create_app() so that the core modules
# (db.models, core.config, etc.) can be imported without the web framework.
from fastapi import FastAPI

from src.api.routes import router as api_router

logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    """
    Lifespan handler for startup / shutdown.

    Startup:
        - Connect to MongoDB (single connection pool, maxPoolSize=2).

    Shutdown:
        - Close MongoDB connection.
    """
    # ── Startup ───────────────────────────────────────────────────────────────
    from src.api.db.database import get_db

    client = await get_db()
    if client is not None:
        logger.info("MongoDB connected successfully.")
    else:
        logger.warning("MongoDB not configured — database features disabled.")

    yield

    # ── Shutdown ──────────────────────────────────────────────────────────────
    from src.api.db.database import close_db

    close_db()


def create_app():
    """
    Build and return a configured FastAPI application instance.

    Returns
    -------
    FastAPI
        The fully configured application.
    """
    from fastapi import FastAPI
    from fastapi.middleware.cors import CORSMiddleware

    from src.api.errors import register_exception_handlers
    from src.api.request_context import REQUEST_ID_HEADER, RequestIdMiddleware

    app = FastAPI(
        title="Responsible RAG API",
        description=(
            "Retrieval-Augmented Generation service with audience-aware "
            "profiles, user management, consent, and admin features."
        ),
        version="0.2.0",
        lifespan=lifespan,
        # Low-memory: disable docs in production
        # docs_url=None,
        # redoc_url=None,
    )

    register_exception_handlers(app)

    # ── Middleware ────────────────────────────────────────────────────────────
    # Added first, so CORS (added next) wraps it and still decorates the
    # responses this middleware produces. Starlette prepends each added
    # middleware, making the last addition the outermost layer.
    app.add_middleware(RequestIdMiddleware)

    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],  # Restrict in production
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
        # Correlate a user-visible error with a server log line: a custom
        # response header is unreadable by cross-origin JS unless exposed.
        expose_headers=[REQUEST_ID_HEADER],
    )

    # ── Routers ───────────────────────────────────────────────────────────────
    app.include_router(api_router, prefix="/api/v1")

    # ── Root redirect → Swagger docs (dev convenience) ────────────────────────
    from fastapi.responses import RedirectResponse

    @app.get("/", include_in_schema=False)
    async def root():
        return RedirectResponse(url="/docs")

    return app
