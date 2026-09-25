"""
schemas/source.py — Knowledge-base source documents
=====================================================
Metadata plus lightweight status tracking (stored in Qdrant payload).
"""


from pydantic import BaseModel, Field

SourceType = str   # "pdf" | "text" | "audio" | "webpage" | "youtube"
ContentSensitivity = str  # "low" | "medium" | "high"


class SourceCreateRequest(BaseModel):
    """Create / ingest a new source document."""

    title: str = Field(..., min_length=1, max_length=300, description="Document title.")
    source_type: str = Field(
        ..., description="Type of source.",
        example="pdf",
    )
    authors: list[str] = Field(
        default_factory=list, description="Author names.",
    )
    publication_date: str | None = Field(None, description="Publication date (ISO-8601 or year).")
    publisher: str | None = Field(None, max_length=200)
    url: str = Field(..., min_length=1, description="Source URL (required).")
    doi: str | None = Field(None, description="Digital Object Identifier.")
    language: str | None = Field(None, description="Language code (e.g. 'en', 'fr').")
    description: str | None = Field(None, max_length=2000)
    tags: list[str] = Field(default_factory=list)
    content_sensitivity: str = Field(
        "low", description="'low', 'medium', or 'high'.",
    )
    internal_notes: str | None = Field(None, max_length=2000)


class SourceUpdateRequest(BaseModel):
    """Partial update to a source document's metadata."""

    title: str | None = Field(None, max_length=300)
    authors: list[str] | None = Field(None)
    publication_date: str | None = Field(None)
    publisher: str | None = Field(None, max_length=200)
    url: str | None = Field(None)
    doi: str | None = Field(None)
    language: str | None = Field(None)
    description: str | None = Field(None, max_length=2000)
    tags: list[str] | None = Field(None)
    content_sensitivity: str | None = Field(None)
    internal_notes: str | None = Field(None, max_length=2000)


class SourceResponse(BaseModel):
    """Source metadata as stored in Qdrant point payload."""

    source_id: str = Field(..., alias="id")
    title: str = Field(...)
    source_type: str = Field(...)
    authors: list[str] = Field(default_factory=list)
    publication_date: str | None = None
    publisher: str | None = None
    url: str = Field("")
    doi: str | None = None
    language: str | None = None
    description: str | None = None
    tags: list[str] = Field(default_factory=list)
    content_sensitivity: str = Field("low")
    internal_notes: str | None = None
    status: str = Field("indexed")
    error_message: str | None = None
    chunk_count: int = Field(0)

    model_config = {"populate_by_name": True}


class SourceListResponse(BaseModel):
    """Paginated list of sources."""

    sources: list[SourceResponse] = Field(default_factory=list)
    total: int = Field(0)
    page: int = Field(1)
    limit: int = Field(20)


class URLUploadRequest(BaseModel):
    """Submit a URL (webpage / YouTube) for background processing."""

    url: str = Field(..., description="Source URL.")
    title: str = Field(..., min_length=1, max_length=300, description="Source title.")
    source_type: str = Field("webpage", description="'webpage' or 'youtube'.")
    authors: list[str] = Field(default_factory=list)
    publication_date: str | None = Field(None)
    publisher: str | None = Field(None, max_length=200)
    language: str | None = Field(None)
    description: str | None = Field(None, max_length=2000)
    tags: list[str] = Field(default_factory=list)
    content_sensitivity: str = Field("low")
    internal_notes: str | None = Field(None, max_length=2000)


class YouTubeUploadRequest(BaseModel):
    """Submit a YouTube URL for background transcription and ingestion."""
    url: str = Field(..., description="YouTube video URL.")
    title: str = Field(..., min_length=1, max_length=300, description="Source title.")
    authors: list[str] = Field(default_factory=list)
    publication_date: str | None = Field(None)
    publisher: str | None = Field(None, max_length=200)
    language: str | None = Field(None)
    description: str | None = Field(None, max_length=2000)
    tags: list[str] = Field(default_factory=list)
    content_sensitivity: str = Field("low")
    internal_notes: str | None = Field(None, max_length=2000)


class UploadResponse(BaseModel):
    """Response after uploading a file for ingestion."""

    id: str = Field(..., description="Source document ID.")
    filename: str = Field(..., description="Original filename.")
    source_type: str = Field(..., description="Detected source type.")
    status: str = Field("processing", description="'processing' | 'indexed' | 'error'.")
    chunk_count: int = Field(0, description="Number of chunks generated.")
