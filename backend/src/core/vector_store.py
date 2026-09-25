"""
vector_store.py — Vector-store lifecycle manager (Qdrant)
===========================================================
:class:`KnowledgeBase` wraps the Qdrant vector database for document
ingestion, retrieval, and source management.  All metadata is stored
as Qdrant payload — no external database required.

Qdrant handles all storage, persistence, and concurrency — the client
is stateless and thread-safe.

Embedding validation
--------------------
Before accepting new documents, :meth:`add_documents` performs a quick
sanity check on a sample embedding to guard against corrupted API
responses (NaN, all-zeros, wrong dimensions).
"""

import logging

from langchain_core.documents import Document
from langchain_core.retrievers import BaseRetriever
from langchain_qdrant import FastEmbedSparse, QdrantVectorStore, RetrievalMode
from qdrant_client import QdrantClient
from qdrant_client.models import (
    Distance,
    FieldCondition,
    Filter,
    HnswConfigDiff,
    MatchValue,
    OptimizersConfigDiff,
    SparseVectorParams,
    VectorParams,
)

from src.core.chunker import SmartChunker
from src.core.config import Settings, get_settings
from src.core.embeddings import (
    EmbeddingFactory,
    EmbeddingValidationError,
    validate_embedding,
)

logger = logging.getLogger(__name__)


# ═══════════════════════════════════════════════════════════════════════════════
# Known embedding-model dimensions
# ═══════════════════════════════════════════════════════════════════════════════
# Used as a fallback when the Qdrant collection doesn't exist yet and the
# embedding API is unreachable.  Add entries here for any model you configure
# via the EMBEDDING_MODEL env-var.

_KNOWN_MODEL_DIMS: dict[str, int] = {
    "BAAI/bge-large-en-v1.5": 1024,
    "BAAI/bge-base-en-v1.5": 768,
    "BAAI/bge-small-en-v1.5": 384,
    "text-embedding-ada-002": 1536,
    "text-embedding-3-small": 1536,
    "text-embedding-3-large": 3072,
    "sentence-transformers/all-MiniLM-L6-v2": 384,
    "sentence-transformers/all-mpnet-base-v2": 768,
    "intfloat/e5-large-v2": 1024,
    "intfloat/e5-base-v2": 768,
    "thenlper/gte-large": 1024,
    "thenlper/gte-base": 768,
}


def _known_model_dim(model_name: str) -> int | None:
    """Return the known dimension for *model_name*, or ``None`` if unknown."""
    # Try exact match first, then suffix-less match (strip fast-lane suffix).
    dim = _KNOWN_MODEL_DIMS.get(model_name)
    if dim is not None:
        return dim
    # Some models are uploaded with a revision hash appended.
    base = model_name.split("/")[-1].split("@")[0]
    for key, d in _KNOWN_MODEL_DIMS.items():
        if key.endswith("/" + base):
            return d
    return None


# ═══════════════════════════════════════════════════════════════════════════════
# KnowledgeBase
# ═══════════════════════════════════════════════════════════════════════════════


class KnowledgeBase:
    """
    Manages document ingestion and source CRUD via Qdrant.

    All source metadata is stored as Qdrant payload — no external database.
    Qdrant handles persistence and concurrency, so this class carries no
    locks or in-memory state beyond the client connection.

    Parameters
    ----------
    settings:
        Application settings used for Qdrant connection, chunking config, etc.
    embedding_function:
        A LangChain-compatible embeddings instance.
    """

    def __init__(
        self, settings: Settings, embedding_function,
    ) -> None:
        self._settings = settings
        self._embedding_function = embedding_function
        self._chunker = SmartChunker(
            use_semantic=settings.use_semantic_chunking,
            embedding_function=embedding_function,
            fallback_chunk_size=settings.fallback_chunk_size,
            chunk_overlap=settings.chunk_overlap,
            max_chunk_size=settings.max_chunk_size,
        )
        # Connect to Qdrant first so we can read the vector size from an
        # existing collection — avoids an unnecessary (and potentially
        # failing) call to the embedding API just for size detection.
        self._client = QdrantClient(
            url=f"http://{settings.qdrant_host}:{settings.qdrant_port}",
            timeout=120,
        )
        self._collection_name = settings.qdrant_collection_name
        # Determine vector dimension — prefer reading from the existing
        # Qdrant collection; fall back to probing the embedding API.
        self._vector_size: int = self._detect_vector_size()
        self._ensure_collection()

        # LangChain QdrantVectorStore for embedding-based operations
        # Uses HYBRID mode (dense + sparse) for better retrieval accuracy.
        self._sparse_embedding = FastEmbedSparse(
            model_name="Qdrant/bm42-all-minilm-l6-v2-attentions",
        )
        self._vector_store = QdrantVectorStore(
            client=self._client,
            collection_name=self._collection_name,
            embedding=self._embedding_function,
            sparse_embedding=self._sparse_embedding,
            retrieval_mode=RetrievalMode.HYBRID,
        )

    # ── Public API ────────────────────────────────────────────────────────────

    @property
    def embedding_function(self):
        """The embedding function shared by ingestion and retrieval."""
        return self._embedding_function

    def as_retriever(self, k: int = 5) -> BaseRetriever:
        """Return a LangChain-compatible retriever backed by Qdrant."""
        return self._vector_store.as_retriever(search_kwargs={"k": k})

    def similarity_search_with_score(
        self, query: str, k: int
    ) -> list[tuple[Document, float]]:
        """Dense search returning ``(document, score)`` pairs.

        The collection uses COSINE distance, so a *higher* score means the
        document is more similar to the query.
        """
        return self._vector_store.similarity_search_with_score(query, k=k)

    def get_all_documents(self) -> list[Document]:
        """Return every document currently stored in the Qdrant collection.

        Uses the standard LangChain payload layout where content lives under
        ``page_content`` and metadata is nested under ``metadata``.
        """
        docs: list[Document] = []
        next_offset = None
        while True:
            page = self._client.scroll(
                collection_name=self._collection_name,
                limit=100,
                offset=next_offset,
                with_payload=True,
            )
            points, next_offset = page
            for point in points:
                payload = dict(point.payload or {})
                text = payload.pop("page_content", "")
                meta = payload.pop("metadata", {})
                docs.append(Document(page_content=text, metadata=meta))
            if next_offset is None:
                break
        return docs

    # ── Source CRUD (all metadata lives in Qdrant payload) ────────────────────

    def add_documents(
        self, source_id: str, source_metadata: dict, docs: list[Document],
    ) -> list[str]:
        """
        Store documents (chunks) in Qdrant with source metadata attached.

        Performs a lightweight embedding validation before enqueuing the
        write — if the embedding function returns corrupted vectors the
        operation is rejected early.

        Parameters
        ----------
        source_id:
            Unique identifier for the source.  Used to group chunks.
        source_metadata:
            Source-level fields (title, authors, tags, …) applied to every
            chunk so that retrieved chunks carry full citation info.
        docs:
            LangChain Document objects to store (pre-chunked).

        Returns
        -------
        list[str]
            Qdrant point IDs (UUIDs) for the stored documents.
        """
        # ── Embedding sanity check ────────────────────────────────────────────
        if docs:
            self._validate_embedding_sample()

        # Attach metadata to every chunk
        for doc in docs:
            doc.metadata["source_id"] = source_id
            doc.metadata.update(source_metadata)

        # Delegate to QdrantVectorStore for embedding + upsert
        ids = self._vector_store.add_documents(docs)
        logger.info(
            "Stored %d document(s) for source %s",
            len(ids), source_id,
        )
        return ids

    @staticmethod
    def _extract_meta(payload: dict) -> dict:
        """
        Extract metadata from a Qdrant point payload.

        LangChain's ``QdrantVectorStore`` nests metadata under a ``"metadata"``
        key.  This helper returns the nested dict if present, falling back to
        the raw payload for backward compatibility with flat-stored points.
        """
        meta = payload.get("metadata")
        if isinstance(meta, dict):
            return meta
        # Flat layout fallback — strip known non-metadata keys
        return {
            k: v for k, v in payload.items()
            if k not in ("page_content", "text", "langchain-sparse")
        }

    def delete_source(self, source_id: str) -> bool:
        """Delete every chunk belonging to *source_id* from Qdrant."""
        self._client.delete(
            collection_name=self._collection_name,
            points_selector=Filter(
                must=[
                    FieldCondition(
                        key="metadata.source_id",
                        match=MatchValue(value=source_id),
                    ),
                ],
            ),
        )
        # Verify deletion
        remaining = self.chunk_count(source_id)
        if remaining > 0:
            logger.warning(
                "delete_source: %d chunks still remain for source %s",
                remaining, source_id,
            )
            return False
        logger.info("Deleted source %s", source_id)
        return True

    def get_source(self, source_id: str) -> dict | None:
        """Return the source metadata for *source_id* (from the first chunk)."""
        results = self._client.query_points(
            collection_name=self._collection_name,
            query_filter=Filter(
                must=[
                    FieldCondition(
                        key="metadata.source_id",
                        match=MatchValue(value=source_id),
                    ),
                ],
            ),
            limit=1,
            with_payload=True,
        )
        if not results.points:
            return None
        payload = dict(results.points[0].payload or {})
        return self._extract_meta(payload)

    def list_sources(self) -> list[dict]:
        """
        Return one metadata dict per unique ``source_id`` in the store.

        Scrolls all points and deduplicates by ``source_id``.
        """
        seen: set[str] = set()
        sources: list[dict] = []
        next_offset = None
        while True:
            page = self._client.scroll(
                collection_name=self._collection_name,
                limit=100,
                offset=next_offset,
                with_payload=True,
            )
            points, next_offset = page
            for point in points:
                meta = self._extract_meta(dict(point.payload or {}))
                sid = meta.get("source_id", "")
                if sid and sid not in seen:
                    seen.add(sid)
                    sources.append(meta)
            if next_offset is None:
                break
        return sources

    def update_source_metadata(self, source_id: str, metadata: dict) -> bool:
        """
        Update metadata on **every** chunk belonging to *source_id*.

        Because metadata is nested under the ``"metadata"`` payload key
        (LangChain convention), this reads the existing metadata, merges
        the updates, and writes the full merged dict back.
        """
        # Read existing metadata from the first chunk to merge
        existing = self.get_source(source_id)
        if existing is None:
            logger.warning(
                "update_source_metadata: source %s not found", source_id,
            )
            return False
        merged = {**existing, **metadata}
        self._client.set_payload(
            collection_name=self._collection_name,
            payload={"metadata": merged},
            points=Filter(
                must=[
                    FieldCondition(
                        key="metadata.source_id",
                        match=MatchValue(value=source_id),
                    ),
                ],
            ),
        )
        logger.info(
            "Updated metadata on all chunks for source %s", source_id,
        )
        return True

    def source_count(self) -> int:
        """Return the number of unique sources (by scrolling distinct IDs)."""
        return len(self.list_sources())

    def chunk_count(self, source_id: str) -> int:
        """Return the number of chunks for *source_id* (uses Qdrant ``count``)."""
        result = self._client.count(
            collection_name=self._collection_name,
            count_filter=Filter(
                must=[
                    FieldCondition(
                        key="metadata.source_id",
                        match=MatchValue(value=source_id),
                    ),
                ],
            ),
        )
        return result.count

    # ── Embedding validation ─────────────────────────────────────────────────

    def _validate_embedding_sample(self) -> None:
        """
        Embed a short probe string and validate the result.

        Raises :class:`EmbeddingValidationError` on corrupted output.
        """
        try:
            result = self._embedding_function.embed_query("probe")
            validate_embedding(result, label="add_documents probe")
        except EmbeddingValidationError:
            raise
        except Exception as exc:
            logger.warning("Embedding probe failed: %s", exc)
            raise EmbeddingValidationError(
                f"Embedding probe failed — rejecting write: {exc}"
            ) from exc

    # ── Private helpers ───────────────────────────────────────────────────────

    def _detect_vector_size(self) -> int:
        """Return the embedding dimension — prefer existing Qdrant collection."""
        # 1. If the collection already exists, read the vector size directly
        #    from Qdrant — no API call needed.
        try:
            collections = self._client.get_collections().collections
            if self._collection_name in {c.name for c in collections}:
                info = self._client.get_collection(self._collection_name)
                dim = info.config.params.vectors.size
                logger.info(
                    "Read vector size %d from existing collection '%s'",
                    dim, self._collection_name,
                )
                return dim
        except Exception as exc:
            logger.debug("Could not read vector size from Qdrant: %s", exc)

        # 2. Check the known-model table so we don't need an API call for
        #    well-known embedding models.
        dim = _known_model_dim(self._settings.embedding_model)
        if dim is not None:
            logger.info(
                "Using known dimension %d for model '%s'",
                dim, self._settings.embedding_model,
            )
            return dim

        # 3. Fall back to probing the embedding API.
        try:
            result = self._embedding_function.embed_query("probe")
            validate_embedding(result, label="dimension probe")
            return len(result)
        except Exception as exc:
            raise RuntimeError(
                f"Failed to determine embedding dimension: {exc}"
            ) from exc

    def _ensure_collection(self) -> None:
        """Create the Qdrant collection if it does not already exist.

        Safe against concurrent creation: if another request (or another
        replica) already created the collection, the 409 Conflict response
        is caught and treated as a no-op.
        """
        # 1. Fast-path — collection already exists.
        try:
            collections = self._client.get_collections().collections
            existing = {c.name for c in collections}
            if self._collection_name in existing:
                info = self._client.get_collection(self._collection_name)
                current_size = info.config.params.vectors.size
                if current_size != self._vector_size:
                    logger.warning(
                        "Collection '%s' has vector size %d, "
                        "but embedding model produces %d. "
                        "Consider recreating the collection.",
                        self._collection_name, current_size,
                        self._vector_size,
                    )
                logger.info(
                    "Using Qdrant collection '%s' (size=%d, distance=COSINE)",
                    self._collection_name, current_size,
                )
                return
        except Exception as exc:
            logger.debug("Could not list collections: %s", exc)

        # 2. Attempt creation — tolerate 409 (already exists).
        logger.info(
            "Creating Qdrant collection '%s' (dense=%d, sparse=langchain-sparse, distance=COSINE)",
            self._collection_name, self._vector_size,
        )
        try:
            self._client.create_collection(
                collection_name=self._collection_name,
                vectors_config=VectorParams(
                    size=self._vector_size,
                    distance=Distance.COSINE,
                    hnsw_config=HnswConfigDiff(m=16, ef_construct=100),
                ),
                sparse_vectors_config={
                    "langchain-sparse": SparseVectorParams(),
                },
                optimizers_config=OptimizersConfigDiff(
                    default_segment_number=2,
                    indexing_threshold=10000,
                ),
            )
        except Exception as exc:
            exc_str = str(exc)
            if "already exists" in exc_str or "409" in exc_str:
                logger.info(
                    "Collection '%s' already exists (concurrent creation).",
                    self._collection_name,
                )
            else:
                raise


# Process-wide instance

_shared_knowledge_base: KnowledgeBase | None = None


def get_shared_knowledge_base() -> KnowledgeBase:
    """Return the per-process cached :class:`KnowledgeBase`.

    Each worker process keeps its own instance; Qdrant handles concurrency
    server-side, so no locking is required.
    """
    global _shared_knowledge_base
    if _shared_knowledge_base is None:
        settings = get_settings()
        _shared_knowledge_base = KnowledgeBase(
            settings, EmbeddingFactory.create(settings)
        )
    return _shared_knowledge_base

