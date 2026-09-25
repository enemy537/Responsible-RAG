"""Public document ingestion endpoint."""

from pathlib import Path

from fastapi import APIRouter, BackgroundTasks, Depends, File, HTTPException, UploadFile

from src.api.deps import get_source_service
from src.api.schemas.source import UploadResponse
from src.api.security import get_current_user
from src.api.services.source_service import SourceService

router = APIRouter()


@router.post("/upload", response_model=UploadResponse, status_code=202)
async def upload_document(
    file: UploadFile = File(...),
    background_tasks: BackgroundTasks = BackgroundTasks(),
    service: SourceService = Depends(get_source_service),
    current_user: dict = Depends(get_current_user),
):
    """Upload a document for background ingestion.

    Returns immediately with ``status="processing"``; poll
    ``GET /admin/sources/{id}`` for the resulting status.
    """
    if not file.filename:
        raise HTTPException(status_code=400, detail="No filename provided")
    if not service.is_supported_file(file.filename):
        raise HTTPException(
            status_code=400,
            detail=(
                f"Unsupported file type: {Path(file.filename).suffix}. "
                f"Supported: {service.supported_suffixes_label()}"
            ),
        )

    source_type = service.source_type_for(file.filename)
    content = await file.read()
    meta = service.create_placeholder({"title": file.filename, "source_type": source_type})
    background_tasks.add_task(
        service.ingest_uploaded_file, meta["source_id"], content, file.filename
    )

    return UploadResponse(
        id=meta["source_id"],
        filename=file.filename,
        source_type=source_type,
        status="processing",
        chunk_count=0,
    )
