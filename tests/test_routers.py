"""
test_routers.py — FastAPI route coverage tests
=================================================
Tests endpoint behaviour with mocked dependencies (DB, RAG chain, auth).
Validates routes, serialization, and status codes without loading heavy
models or needing a running MongoDB.
"""

import os
import sys

# Ensure backend/src is on the path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "backend"))

from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi.testclient import TestClient

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

_FAKE_USER = {"sub": "user-123", "email": "test@test.com", "role": "user"}
_FAKE_ADMIN = {"sub": "admin-1", "email": "admin@test.com", "role": "admin"}


@pytest.fixture()
def client():
    """Create a TestClient with auth and DB mocked out."""
    # Mock database before importing the app
    with patch("src.api.db.database.get_database", return_value=None), \
         patch("src.api.db.database.get_db", new_callable=AsyncMock, return_value=None), \
         patch("src.api.db.database.close_db"):

        from src.api import create_app
        app = create_app()

        # Heavy services must never be constructed in tests
        from src.api.deps import get_profile_generator, get_rag_chain
        from src.api.security import get_current_user

        app.dependency_overrides[get_rag_chain] = lambda: MagicMock()
        app.dependency_overrides[get_profile_generator] = lambda: MagicMock()
        app.dependency_overrides[get_current_user] = lambda: _FAKE_USER

        with TestClient(app) as c:
            yield c

        app.dependency_overrides.clear()


@pytest.fixture()
def admin_client():
    """Create a TestClient with admin auth."""
    with patch("src.api.db.database.get_database", return_value=None), \
         patch("src.api.db.database.get_db", new_callable=AsyncMock, return_value=None), \
         patch("src.api.db.database.close_db"):

        from src.api import create_app
        app = create_app()

        from src.api.deps import get_profile_generator, get_rag_chain
        from src.api.security import get_current_user

        app.dependency_overrides[get_rag_chain] = lambda: MagicMock()
        app.dependency_overrides[get_profile_generator] = lambda: MagicMock()
        app.dependency_overrides[get_current_user] = lambda: _FAKE_ADMIN

        with TestClient(app) as c:
            yield c

        app.dependency_overrides.clear()


# ---------------------------------------------------------------------------
# Health endpoints
# ---------------------------------------------------------------------------

class TestHealth:
    def test_health_ok(self, client):
        resp = client.get("/api/v1/health")
        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "ok"
        assert "version" in data

    def test_readiness(self, client):
        resp = client.get("/api/v1/health/ready")
        assert resp.status_code == 200
        assert resp.json()["status"] == "ok"


# ---------------------------------------------------------------------------
# Root redirect
# ---------------------------------------------------------------------------

class TestRoot:
    def test_root_redirects_to_docs(self, client):
        resp = client.get("/", follow_redirects=False)
        assert resp.status_code in (301, 302, 307)
        assert "/docs" in resp.headers.get("location", "")


# ---------------------------------------------------------------------------
# Search endpoint
# ---------------------------------------------------------------------------

class TestSearch:
    def test_search_returns_empty(self, client):
        """Search is a stub — should return an empty result list."""
        resp = client.post("/api/v1/search", json={"query": "test"})
        assert resp.status_code == 200
        data = resp.json()
        assert data["query"] == "test"
        assert data["results"] == []


# ---------------------------------------------------------------------------
# Embedding core tests (no network, no torch)
# ---------------------------------------------------------------------------

class TestEmbeddingsCore:
    """Test the refactored embeddings module imports without torch."""

    def test_imports_without_torch(self):
        """Verify embeddings.py can be imported without loading torch."""
        import src.core.embeddings as emb
        assert hasattr(emb, "HFInferenceEmbeddings")
        assert hasattr(emb, "EmbeddingFactory")
        assert hasattr(emb, "validate_embedding")

    def test_validate_embedding_valid(self):
        from src.core.embeddings import validate_embedding
        # Should not raise
        validate_embedding([0.1, 0.2, 0.3])

    def test_validate_embedding_empty(self):
        from src.core.embeddings import EmbeddingValidationError, validate_embedding
        with pytest.raises(EmbeddingValidationError, match="empty"):
            validate_embedding([])

    def test_validate_embedding_all_zeros(self):
        from src.core.embeddings import EmbeddingValidationError, validate_embedding
        with pytest.raises(EmbeddingValidationError, match="all zeros"):
            validate_embedding([0.0, 0.0, 0.0])

    def test_validate_embedding_nan(self):
        from src.core.embeddings import EmbeddingValidationError, validate_embedding
        with pytest.raises(EmbeddingValidationError, match="NaN"):
            validate_embedding([0.1, float("nan"), 0.3])

    def test_validate_embeddings_batch(self):
        from src.core.embeddings import validate_embeddings
        # Should not raise
        validate_embeddings([[0.1, 0.2], [0.3, 0.4]], expected_dim=2)

    def test_validate_embeddings_dim_mismatch(self):
        from src.core.embeddings import EmbeddingValidationError, validate_embeddings
        with pytest.raises(EmbeddingValidationError, match="dimensions"):
            validate_embeddings([[0.1, 0.2], [0.3]], expected_dim=2)



