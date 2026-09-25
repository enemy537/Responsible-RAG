"""
routes/metadata.py — URL metadata extraction
==============================================
Extracts metadata (title, description, author, etc.) from YouTube URLs
so the frontend can pre-populate the source metadata form with real data
instead of hardcoded mock values.

Endpoints:
    GET /api/v1/metadata?url=...  — Extract metadata from a URL
"""

import logging

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel

logger = logging.getLogger(__name__)

router = APIRouter()


class MetadataResponse(BaseModel):
    title: str | None = None
    authors: list[str] = []
    publicationDate: str | None = None
    publisher: str | None = None
    description: str | None = None
    thumbnailUrl: str | None = None
    language: str | None = None


def _get_youtube_video_id(url: str) -> str | None:
    """Extract the video ID from various YouTube URL formats."""
    import re
    # youtube.com/watch?v=...
    match = re.search(r"[?&]v=([\w-]+)", url)
    if match:
        return match.group(1)
    # youtu.be/...
    match = re.search(r"youtu\.be/([\w-]+)", url)
    if match:
        return match.group(1)
    # youtube.com/embed/...
    match = re.search(r"youtube\.com/embed/([\w-]+)", url)
    if match:
        return match.group(1)
    return None


def _fetch_youtube_metadata(url: str) -> MetadataResponse:
    """Extract metadata from a YouTube video using pytubefix."""
    import pytubefix

    try:
        yt = pytubefix.YouTube(url)
    except Exception as exc:
        logger.warning("pytubefix failed for %s: %s", url, exc)
        # Fallback: try yt-dlp
        return _fetch_youtube_metadata_ytdlp(url)

    video_id = _get_youtube_video_id(url) or yt.video_id

    # Parse publish date
    pub_date = None
    try:
        if yt.publish_date:
            pub_date = yt.publish_date.strftime("%Y-%m-%d")
    except Exception:
        pass

    return MetadataResponse(
        title=yt.title or None,
        authors=[yt.author] if yt.author else [],
        publicationDate=pub_date,
        publisher="YouTube",
        description=(yt.description or "")[:500] if yt.description else None,
        thumbnailUrl=f"https://img.youtube.com/vi/{video_id}/hqdefault.jpg",
        language=None,
    )


def _fetch_youtube_metadata_ytdlp(url: str) -> MetadataResponse:
    """Fallback metadata extraction using yt-dlp."""
    import yt_dlp

    video_id = _get_youtube_video_id(url) or ""

    try:
        with yt_dlp.YoutubeDL({"quiet": True, "no_warnings": True}) as ydl:
            info = ydl.extract_info(url, download=False)
            if info:
                return MetadataResponse(
                    title=info.get("title"),
                    authors=[info.get("channel", info.get("uploader", ""))] if info.get("channel") or info.get("uploader") else [],
                    publicationDate=info.get("upload_date")[:10] if info.get("upload_date") else None,
                    publisher="YouTube",
                    description=(info.get("description") or "")[:500] if info.get("description") else None,
                    thumbnailUrl=info.get("thumbnail") or f"https://img.youtube.com/vi/{video_id}/hqdefault.jpg",
                    language=info.get("language"),
                )
    except Exception as exc:
        logger.warning("yt-dlp also failed for %s: %s", url, exc)

    # Return minimal response with just the thumbnail
    return MetadataResponse(
        thumbnailUrl=f"https://img.youtube.com/vi/{video_id}/hqdefault.jpg",
    )


def _is_youtube_url(url: str) -> bool:
    import re
    return bool(re.search(
        r"(youtube\.com/(watch\?v=|embed/)|youtu\.be/)",
        url,
    ))


@router.get("", response_model=MetadataResponse)
async def extract_metadata(
    url: str = Query(..., description="The URL to extract metadata from"),
):
    """
    Extract metadata from a URL.

    Currently supports YouTube URLs. Returns title, authors, publication date,
    description, thumbnail, and language when available.
    """
    if not url.strip():
        raise HTTPException(status_code=400, detail="URL is required")

    # Normalise the URL
    url = url.strip()

    if _is_youtube_url(url):
        try:
            return _fetch_youtube_metadata(url)
        except Exception as exc:
            logger.error("Failed to extract YouTube metadata for %s: %s", url, exc)
            # Return a minimal response so the UI doesn't break
            video_id = _get_youtube_video_id(url)
            return MetadataResponse(
                thumbnailUrl=f"https://img.youtube.com/vi/{video_id}/hqdefault.jpg" if video_id else None,
            )

    # For non-YouTube URLs, we could add webpage metadata extraction
    # (Open Graph tags, etc.) in the future.
    raise HTTPException(
        status_code=400,
        detail="Unsupported URL type. Only YouTube URLs are supported for metadata extraction.",
    )
