"""Knowledge-base source management backed by Qdrant.

All source metadata and processing status live in Qdrant point payloads:
``processing`` -> ``indexed`` | ``error``. Loading/parsing of each source type
is delegated to :mod:`src.core.loaders`.
"""

import asyncio
import logging
import os
from pathlib import Path
from uuid import uuid4

from langchain_core.documents import Document

from src.core.chunker import SmartChunker
from src.core.config import get_settings
from src.core.loaders import LoaderRegistry
from src.core.vector_store import KnowledgeBase, get_shared_knowledge_base

logger = logging.getLogger(__name__)

# Fields that describe how a source was uploaded, not what it contains.
_TRANSIENT_META_KEYS = ("chunk_index", "pending_file_path", "pending_filename")


class SourceService:
    """Source CRUD and ingestion orchestration."""

    def __init__(
        self,
        *,
        knowledge_base: KnowledgeBase | None = None,
        chunker: SmartChunker | None = None,
        loaders: LoaderRegistry | None = None,
    ) -> None:
        self._knowledge_base = knowledge_base
        self._chunker = chunker
        self._loaders = loaders or LoaderRegistry()

    # ── Lazy resources ────────────────────────────────────────────────────────

    @property
    def kb(self) -> KnowledgeBase:
        """The Qdrant-backed knowledge base, resolved on first use."""
        if self._knowledge_base is None:
            self._knowledge_base = get_shared_knowledge_base()
        return self._knowledge_base

    def _chunker_instance(self) -> SmartChunker:
        if self._chunker is None:
            settings = get_settings()
            self._chunker = SmartChunker(
                use_semantic=settings.use_semantic_chunking,
                embedding_function=self.kb.embedding_function,
                fallback_chunk_size=settings.fallback_chunk_size,
                chunk_overlap=settings.chunk_overlap,
                max_chunk_size=settings.max_chunk_size,
            )
        return self._chunker

    # ── Upload policy ─────────────────────────────────────────────────────────

    def is_supported_file(self, filename: str) -> bool:
        return self._loaders.is_supported_file(filename)

    def source_type_for(self, filename: str) -> str:
        return self._loaders.source_type_for(filename)

    @staticmethod
    def size_limit_for(source_type: str) -> int:
        return LoaderRegistry.size_limit_for(source_type)

    def supported_suffixes_label(self) -> str:
        return self._loaders.supported_suffixes_label()

    # ── CRUD ──────────────────────────────────────────────────────────────────

    def list_sources(self) -> list[dict]:
        """Return one metadata dict per unique source."""
        sources = self.kb.list_sources()
        for source in sources:
            source["chunk_count"] = self.kb.chunk_count(source.get("source_id", ""))
            source.setdefault("status", "indexed")
        return sources

    def get_source(self, source_id: str) -> dict | None:
        meta = self.kb.get_source(source_id)
        if meta:
            meta["chunk_count"] = self.kb.chunk_count(source_id)
            meta.setdefault("status", "indexed")
        return meta

    def create_source(self, data: dict) -> dict:
        """Create a source that is indexed immediately."""
        meta = self._build_meta(data, status="indexed")
        self.kb.add_documents(meta["source_id"], meta, [self._placeholder_doc()])
        meta["chunk_count"] = self.kb.chunk_count(meta["source_id"])
        logger.info("Created source %s (%s)", meta["source_id"], meta["title"])
        return meta

    def create_placeholder(self, data: dict) -> dict:
        """Create a source in ``processing`` state, awaiting ingestion."""
        meta = self._build_meta(data, status="processing")
        meta["pending_file_path"] = data.get("pending_file_path", "")
        meta["pending_filename"] = data.get("pending_filename", "")
        self.kb.add_documents(meta["source_id"], meta, [self._placeholder_doc()])
        meta["chunk_count"] = 0
        logger.info("Created placeholder source %s (%s)", meta["source_id"], meta["title"])
        return meta

    def update_source(self, source_id: str, data: dict) -> dict | None:
        update = {k: v for k, v in data.items() if v is not None and k != "source_id"}
        if not update:
            return self.kb.get_source(source_id)
        if not self.kb.update_source_metadata(source_id, update):
            return None
        return self.get_source(source_id)

    def delete_source(self, source_id: str) -> bool:
        return self.kb.delete_source(source_id)

    def clear_pending(self, source_id: str) -> None:
        """Drop pending-upload markers once ingestion has started."""
        self.kb.update_source_metadata(source_id, {"pending_file_path": "", "pending_filename": ""})

    def finalize_source(
        self,
        source_id: str,
        docs: list[Document],
        override_meta: dict | None = None,
    ) -> None:
        """Replace the placeholder with real chunks and mark the source indexed."""
        if override_meta is not None:
            source_meta = dict(override_meta)
        else:
            existing = self.kb.get_source(source_id)
            if not existing:
                logger.warning("finalize_source: source %s not found", source_id)
                return
            source_meta = dict(existing)

        self.kb.delete_source(source_id)
        for key in _TRANSIENT_META_KEYS:
            source_meta.pop(key, None)
        source_meta["status"] = "indexed"
        source_meta["error_message"] = ""

        self.kb.add_documents(source_id, source_meta, docs)
        logger.info("Finalized source %s — %d chunks indexed", source_id, len(docs))

    def fail_source(self, source_id: str, error: str) -> None:
        """Mark a source as failed, recording a truncated error message."""
        self.kb.update_source_metadata(
            source_id, {"status": "error", "error_message": str(error)[:500]}
        )
        logger.warning("Source %s failed: %s", source_id, error)

    def get_stats(self) -> dict:
        """Aggregate source statistics for the admin dashboard."""
        sources = self.kb.list_sources()
        by_status = {"indexed": 0, "processing": 0, "error": 0}
        incomplete = 0
        for source in sources:
            status = source.get("status") or "indexed"
            by_status[status] = by_status.get(status, 0) + 1
            if status == "indexed" and (not source.get("title") or not source.get("description")):
                incomplete += 1

        return {
            # Every source, whatever its status. This previously reported
            # by_status["indexed"], so processing and error sources were
            # invisible in the dashboard total.
            "total_sources": len(sources),
            "indexed_sources": by_status["indexed"],
            "processing_sources": by_status["processing"],
            "error_sources": by_status["error"],
            "incomplete_metadata": incomplete,
        }

    # ── Ingestion (load -> chunk) ─────────────────────────────────────────────

    async def ingest_file(self, path: Path) -> list[Document] | None:
        """Load and chunk a file, returning ``None`` when it cannot be processed."""
        loader = self._loaders.for_file(path.name)
        if loader is None:
            logger.warning("No loader registered for '%s'", path.name)
            return None
        return self._chunk(await loader.load(path))

    async def ingest_url(self, url: str, source_type: str) -> list[Document] | None:
        """Load and chunk a URL, returning ``None`` when it cannot be processed."""
        loader = self._loaders.for_source_type(source_type)
        if loader is None:
            logger.warning("No loader registered for source type '%s'", source_type)
            return None
        return self._chunk(await loader.load(url))

    # ── Background jobs (blocking, run in a worker thread) ────────────────────

    def ingest_uploaded_file(
        self,
        source_id: str,
        content: bytes,
        filename: str,
        meta: dict | None = None,
    ) -> None:
        """Persist an uploaded blob, chunk it, then finalize or fail the source."""
        tmp_path = Path(get_settings().upload_dir) / f"bg_{os.urandom(8).hex()}_{filename}"
        try:
            tmp_path.parent.mkdir(parents=True, exist_ok=True)
            tmp_path.write_bytes(content)
            documents = asyncio.run(self.ingest_file(tmp_path))
        except Exception as exc:
            self._fail(source_id, exc)
            return
        finally:
            tmp_path.unlink(missing_ok=True)

        self._finalize(source_id, documents, meta, label=filename)

    def ingest_url_source(self, source_id: str, url: str, source_type: str) -> None:
        """Fetch a URL, chunk it, then finalize or fail the source."""
        try:
            documents = asyncio.run(self.ingest_url(url, source_type))
        except Exception as exc:
            self._fail(source_id, exc)
            return

        self._finalize(source_id, documents, None, label=source_type)

    # ── Internals ─────────────────────────────────────────────────────────────

    def _chunk(self, documents: list[Document] | None) -> list[Document] | None:
        if not documents:
            return None
        return self._chunker_instance().chunk(documents)

    def _finalize(
        self,
        source_id: str,
        documents: list[Document] | None,
        override_meta: dict | None,
        *,
        label: str,
    ) -> None:
        if not documents:
            self.fail_source(source_id, "Processing returned no content")
            return
        self.finalize_source(source_id, documents, override_meta=override_meta)
        logger.info(
            "Ingest complete for source %s (%s, %d chunks)",
            source_id,
            label,
            len(documents),
        )

    def _fail(self, source_id: str, exc: Exception) -> None:
        logger.error("Ingest failed for source %s: %s", source_id, exc)
        self.fail_source(source_id, str(exc))

    @staticmethod
    def _placeholder_doc() -> Document:
        return Document(page_content="", metadata={})

    @staticmethod
    def _build_meta(data: dict, *, status: str) -> dict:
        return {
            "source_id": data.get("source_id") or str(uuid4()),
            "title": data.get("title", "Untitled"),
            "source_type": data.get("source_type", "pdf"),
            "authors": data.get("authors", []),
            "publication_date": data.get("publication_date") or "",
            "publisher": data.get("publisher") or "",
            "url": data.get("url") or "",
            "doi": data.get("doi") or "",
            "language": data.get("language") or "",
            "description": data.get("description") or "",
            "tags": data.get("tags") or [],
            "content_sensitivity": data.get("content_sensitivity", "low"),
            "internal_notes": data.get("internal_notes") or "",
            "status": status,
            "error_message": "",
        }
