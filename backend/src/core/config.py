"""
config.py — Application configuration
========================================
All runtime parameters are read from environment variables (or a .env file).
Change defaults here **or** override them per-environment via .env / Docker
environment injection — no code changes required.

Usage
-----
    from src.core.config import get_settings

    cfg = get_settings()          # cached singleton
    print(cfg.llm_model)
"""

from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """
    Application settings.

    All fields map 1-to-1 to an environment variable of the same name
    (case-insensitive).  See example.env for a fully annotated reference.
    """

    # ── LLM ───────────────────────────────────────────────────────────────────
    llm_model: str = "deepseek-chat"
    llm_profile: str = "deepseek-v4-flash"
    llm_temperature: float = 0.5
    deepseek_api_key: str = ""

    # ── Embeddings (Hugging Face Inference API) ───────────────────────────────
    embedding_model: str = "BAAI/bge-large-en-v1.5"
    huggingfacehub_api_token: str = ""     # hf_… token with inference permission

    # ── Embedding provider ────────────────────────────────────────────────────
    # "tei" → uses Hugging Face Text Embeddings Inference server (default)
    # "huggingface" → uses Hugging Face Inference API (requires token)
    embedding_provider: str = "tei"
    local_embedding_url: str = ""   # MUST be set in .env when using tei

    # ── Auth ───────────────────────────────────────────────────────────────
    auth_secret_key: str = "dev-secret-change-in-production-0123456789"
    auth_algorithm: str = "HS256"
    auth_token_expire_minutes: int = 1440        # 24 hours

    # ── Admin credentials (login via .env, not in DB) ──────────────────────
    # Reads from DUMMY_ADMIN_EMAIL / DUMMY_ADMIN_PASSWORD in .env
    admin_email: str = "admin@domain.com"
    admin_password: str = "admin123"

    # ── Domain (used by Caddy in prod profile) ─────────────────────────────
    domain: str = ""

    # ── Frontend URL (OAuth redirects & email verification links) ─────────
    # Dev:     http://localhost:5173 (Vite) or http://localhost:3000 (Docker)
    # Prod:    https://YOUR_DOMAIN
    frontend_url: str = "http://localhost:5173"

    # ── Google OAuth ──────────────────────────────────────────────────────
    google_client_id: str = ""
    google_client_secret: str = ""
    # Must match "Authorized redirect URIs" in Google Cloud Console
    # Dev:  http://localhost:8000/api/v1/auth/google/callback
    # Prod: https://YOUR_DOMAIN/api/v1/auth/google/callback
    google_redirect_uri: str = "http://localhost:8000/api/v1/auth/google/callback"

    # ── SMTP (email verification) ──────────────────────────────────────────
    smtp_host: str = "smtp.gmail.com"
    smtp_port: int = 587
    smtp_user: str = ""
    smtp_password: str = ""
    smtp_from: str = ""

    # ── Chunking ──────────────────────────────────────────────────────────────
    use_semantic_chunking: bool = True
    fallback_chunk_size: int = 1000
    chunk_overlap: int = 200
    max_chunk_size: int = 2000             # Semantic chunks larger than this
                                           # trigger recursive fallback

    # ── Retrieval ─────────────────────────────────────────────────────────────
    vec_retriever_k: int = 5
    bm25_retriever_k: int = 5
    vec_weight: float = 0.7                # Must sum to 1.0 with bm25_weight
    bm25_weight: float = 0.3
    bm25_s: float = 0.7

    # Thresholds for up-to-k ranking
    relevance_threshold: float = 0.0 # set to 0 to disable filtering
    max_returned_sources: int = 5

    # ── MongoDB ───────────────────────────────────────────────────────────────
    mongo_uri: str = ""
    mongo_db: str = "responsible_rag"

    # ── Vector store (Qdrant) ──────────────────────────────────────────────
    # Qdrant is a separate service — the backend connects via HTTP.
    # Use 127.0.0.1 instead of localhost to avoid IPv6 resolution issues on Windows.
    qdrant_host: str = "127.0.0.1"
    qdrant_port: int = 6333
    qdrant_collection_name: str = "rag_kb_collection"
    qdrant_profiles_collection_name: str = "rag_profiles_collection"

    # ── Storage paths ─────────────────────────────────────────────────────────
    resources_dir: str = "../storage/resources"
    upload_dir: str = "../storage/uploads"

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",          # Silently ignore unknown env vars
    )


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    """Return a cached, application-wide Settings singleton."""
    return Settings()
