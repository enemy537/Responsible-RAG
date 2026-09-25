"""Audio transcription via Cloudflare Whisper."""

import asyncio
import re
from pathlib import Path

from src.core.cloudflare import Cloudflare

_WHISPER_MODEL = "@cf/openai/whisper-tiny-en"

# Map file extensions to MIME types for the Cloudflare API
_AUDIO_MIME: dict[str, str] = {
    ".mp3": "audio/mpeg",
    ".wav": "audio/wav",
    ".m4a": "audio/mp4",
    ".flac": "audio/flac",
    ".ogg": "audio/ogg",
    ".aac": "audio/aac",
    ".wma": "audio/x-ms-wma",
}


def _normalize(text: str) -> str:
    return re.sub(r"\s+", " ", text or "").strip()


def _extract_text(response: dict) -> str:
    if not isinstance(response, dict):
        return ""
    text = response.get("text")
    if isinstance(text, str) and text.strip():
        return _normalize(text)
    segments = response.get("segments") or response.get("result", {}).get("segments")
    if isinstance(segments, list):
        texts = [s.get("text", "") for s in segments if isinstance(s, dict) and s.get("text")]
        if texts:
            return _normalize(" ".join(t.strip() for t in texts if t.strip()))
    words = response.get("words") or response.get("result", {}).get("words")
    if isinstance(words, list):
        filtered = [w.get("word", "") for w in words if isinstance(w, dict) and w.get("word")]
        if filtered:
            return _normalize(" ".join(filtered))
    return ""


def transcribe(audio_path: str | Path, cf: Cloudflare | None = None) -> str:
    cf = cf or Cloudflare()
    path = Path(audio_path)
    mime = _AUDIO_MIME.get(path.suffix.lower(), "application/octet-stream")
    with open(path, "rb") as f:
        raw = f.read()
    response = cf._post(_WHISPER_MODEL, raw, content_type=mime)
    return _extract_text(response)


async def transcribe_async(audio_path: str | Path, cf: Cloudflare | None = None) -> str:
    """Async variant — runs the I/O-bound transcription in a thread pool."""
    return await asyncio.to_thread(transcribe, audio_path, cf)
