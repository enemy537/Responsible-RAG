"""Audio transcription loading."""

import logging
from pathlib import Path

from langchain_core.documents import Document

from src.core.loaders.base import SourceLoader
from src.core.transcriber import transcribe_async

logger = logging.getLogger(__name__)


class AudioFileLoader(SourceLoader):
    """Transcribes audio files through the configured speech-to-text backend."""

    source_type = "audio"
    suffixes = frozenset({".mp3", ".wav", ".m4a", ".flac", ".ogg", ".aac", ".wma"})

    async def load(self, target: str | Path) -> list[Document] | None:
        path = Path(target)
        try:
            text = await transcribe_async(str(path))
        except Exception as exc:
            logger.warning("Could not transcribe '%s': %s", path.name, exc)
            return None

        if not text.strip():
            return None
        return [Document(page_content=text, metadata={"source": str(path), "type": "audio"})]
