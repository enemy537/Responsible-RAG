"""Admin source management (all data lives in Qdrant).

Endpoints:
    GET    /admin/sources           list sources
    GET    /admin/sources/{id}      source details
    POST   /admin/sources           create metadata-only source
    PUT    /admin/sources/{id}      update metadata, kick off pending ingest
    DELETE /admin/sources/{id}      delete source and its chunks
    POST   /admin/sources/upload    file -> background ingest
    POST   /admin/sources/webpage   URL -> background scrape
    POST   /admin/sources/youtube   URL -> background transcription
"""

import asyncio
import logging
import os
from collections.abc import Callable
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

from fastapi import APIRouter, Depends, File, HTTPException, Query, UploadFile

from src.api.deps import get_source_service
from src.api.schemas.source import (
    SourceCreateRequest,
    SourceListResponse,
    SourceResponse,
    SourceUpdateRequest,
    UploadResponse,
    URLUploadRequest,
    YouTubeUploadRequest,
)
from src.api.security import require_admin
from src.api.services.source_service import SourceService
from src.core.config import get_settings

router = APIRouter()
logger = logging.getLogger(__name__)

# Dedicated pool for ingestion so blocking work never stalls the event loop.
_ingestion_pool = ThreadPoolExecutor(max_workers=2)


def _meta_to_response(meta: dict) -> SourceResponse:
    """Convert a Qdrant payload dict into a ``SourceResponse``."""
    return SourceResponse(
        id=meta.get("source_id", ""),
        title=meta.get("title", ""),
        source_type=meta.get("source_type", "pdf"),
        authors=meta.get("authors", []),
        publication_date=meta.get("publication_date") or None,
        publisher=meta.get("publisher") or None,
        url=meta.get("url") or "",
        doi=meta.get("doi") or None,
        language=meta.get("language") or None,
        description=meta.get("description") or None,
        tags=meta.get("tags", []),
        content_sensitivity=meta.get("content_sensitivity", "low"),
        internal_notes=meta.get("internal_notes") or None,
        status=meta.get("status", "indexed"),
        error_message=meta.get("error_message") or None,
        chunk_count=meta.get("chunk_count", 0),
    )


def _schedule_ingestion(job: Callable[..., None], *args) -> None:
    """Run an ingestion job on the background executor."""
    asyncio.get_running_loop().run_in_executor(_ingestion_pool, job, *args)


def _url_source_fields(
    body: URLUploadRequest | YouTubeUploadRequest,
    *,
    source_type: str,
    default_publisher: str = "",
) -> dict:
    """Extract the metadata shared by all URL-based sources."""
    return {
        "title": body.title,
        "source_type": source_type,
        "authors": body.authors,
        "publication_date": body.publication_date,
        "publisher": body.publisher or default_publisher,
        "url": body.url,
        "language": body.language,
        "description": body.description,
        "tags": body.tags,
        "content_sensitivity": body.content_sensitivity,
        "internal_notes": body.internal_notes,
    }


def _start_url_ingestion(
    service: SourceService, meta: dict, *, url: str, source_type: str
) -> UploadResponse:
    """Schedule ingestion for a URL-based source and return its processing status."""
    _schedule_ingestion(service.ingest_url_source, meta["source_id"], url, source_type)
    return UploadResponse(
        id=meta["source_id"],
        filename=url,
        source_type=source_type,
        status="processing",
        chunk_count=0,
    )


def _validate_filename(service: SourceService, filename: str | None) -> str:
    if not filename:
        raise HTTPException(status_code=400, detail="No filename provided")
    if not service.is_supported_file(filename):
        raise HTTPException(
            status_code=400,
            detail=(
                f"Unsupported file type: {Path(filename).suffix}. "
                f"Supported: {service.supported_suffixes_label()}"
            ),
        )
    return filename


def _enforce_size_limit(service: SourceService, source_type: str, *sizes: int | None) -> None:
    limit = service.size_limit_for(source_type)
    if any(size is not None and size > limit for size in sizes):
        raise HTTPException(
            status_code=413,
            detail=(
                f"File too large. Maximum size for {source_type.upper()} files "
                f"is {limit // (1024 * 1024)}MB."
            ),
        )


# ── Source CRUD ───────────────────────────────────────────────────────────────


@router.get("", response_model=SourceListResponse)
def list_sources(
    page: int = Query(1, ge=1),
    limit: int = Query(120, ge=1, le=2000),
    service: SourceService = Depends(get_source_service),
    admin: dict = Depends(require_admin),
):
    """List knowledge-base sources. Reads Qdrant only — no embedding calls.

    ``total`` is always the full number of sources, independent of ``limit``,
    so clients can page through everything instead of silently showing only
    the first page.
    """
    try:
        sources = service.list_sources()
    except Exception:
        logger.exception("Unexpected error listing sources")
        raise HTTPException(status_code=500, detail="Failed to list sources") from None

    start = (page - 1) * limit
    return SourceListResponse(
        sources=[_meta_to_response(source) for source in sources[start : start + limit]],
        total=len(sources),
        page=page,
        limit=limit,
    )


@router.get("/{source_id}", response_model=SourceResponse)
def get_source(
    source_id: str,
    service: SourceService = Depends(get_source_service),
    admin: dict = Depends(require_admin),
):
    """Return metadata for a single source."""
    try:
        meta = service.get_source(source_id)
    except Exception:
        logger.exception("Unexpected error getting source")
        raise HTTPException(status_code=500, detail="Failed to get source") from None
    if meta is None:
        raise HTTPException(status_code=404, detail="Source not found")
    return _meta_to_response(meta)


@router.post("", response_model=SourceResponse, status_code=201)
def create_source(
    body: SourceCreateRequest,
    service: SourceService = Depends(get_source_service),
    admin: dict = Depends(require_admin),
):
    """Create an indexed source from metadata alone."""
    return _meta_to_response(service.create_source(body.model_dump()))


@router.put("/{source_id}", response_model=SourceResponse)
async def update_source(
    source_id: str,
    body: SourceUpdateRequest,
    service: SourceService = Depends(get_source_service),
    admin: dict = Depends(require_admin),
):
    """Update metadata, starting background ingestion when a pending upload exists."""
    meta = service.update_source(source_id, body.model_dump(exclude_none=True))
    if meta is None:
        raise HTTPException(status_code=404, detail="Source not found")

    pending_path = meta.get("pending_file_path")
    if pending_path:
        path = Path(pending_path)
        if path.exists():
            content = path.read_bytes()
            filename = meta.get("pending_filename", path.name)
            path.unlink(missing_ok=True)
            service.clear_pending(source_id)
            _schedule_ingestion(service.ingest_uploaded_file, source_id, content, filename, meta)

    return _meta_to_response(meta)


@router.delete("/{source_id}")
def delete_source(
    source_id: str,
    service: SourceService = Depends(get_source_service),
    admin: dict = Depends(require_admin),
):
    """Delete a source and all of its chunks."""
    if not service.delete_source(source_id):
        raise HTTPException(status_code=404, detail="Source not found")
    return {"status": "deleted", "source_id": source_id}


# ── Background ingestion entry points ─────────────────────────────────────────


@router.post("/upload", response_model=UploadResponse, status_code=202)
async def upload_source(
    file: UploadFile = File(...),
    title: str | None = None,
    service: SourceService = Depends(get_source_service),
    admin: dict = Depends(require_admin),
):
    """Store an upload and await metadata submission before ingesting."""
    filename = _validate_filename(service, file.filename)
    source_type = service.source_type_for(filename)
    content = await file.read()
    _enforce_size_limit(service, source_type, file.size, len(content))

    settings = get_settings()
    upload_dir = Path(settings.upload_dir)
    upload_dir.mkdir(parents=True, exist_ok=True)
    tmp_path = upload_dir / f"pending_{os.urandom(8).hex()}_{filename}"
    tmp_path.write_bytes(content)

    meta = service.create_placeholder(
        {
            "title": title or filename,
            "source_type": source_type,
            "pending_file_path": str(tmp_path),
            "pending_filename": filename,
        }
    )
    return UploadResponse(
        id=meta["source_id"],
        filename=filename,
        source_type=source_type,
        status="processing",
        chunk_count=0,
    )


@router.post("/webpage", response_model=UploadResponse, status_code=202)
async def upload_webpage(
    body: URLUploadRequest,
    service: SourceService = Depends(get_source_service),
    admin: dict = Depends(require_admin),
):
    """Scrape a webpage in the background and index it."""
    meta = service.create_placeholder(_url_source_fields(body, source_type="webpage"))
    return _start_url_ingestion(service, meta, url=body.url, source_type="webpage")


@router.post("/youtube", response_model=UploadResponse, status_code=202)
async def upload_youtube(
    body: YouTubeUploadRequest,
    service: SourceService = Depends(get_source_service),
    admin: dict = Depends(require_admin),
):
    """Transcribe a YouTube video in the background and index it."""
    meta = service.create_placeholder(
        _url_source_fields(body, source_type="youtube", default_publisher="YouTube")
    )
    return _start_url_ingestion(service, meta, url=body.url, source_type="youtube")
