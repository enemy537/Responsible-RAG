"""YouTube transcription loader."""

import logging

from langchain_core.documents import Document

from src.core.loaders.base import SourceLoader
from src.core.youtube import transcribe_youtube_async

logger = logging.getLogger(__name__)


class YouTubeLoader(SourceLoader):
    """Transcribes YouTube audio into documents."""

    source_type = "youtube"

    async def load(self, target: str) -> list[Document] | None:
        url = str(target)
        try:
            text = await transcribe_youtube_async(url)
        except Exception as exc:
            logger.warning("Failed to transcribe YouTube '%s': %s", url, exc)
            return None

        if not text.strip():
            return None
        return [Document(page_content=text, metadata={"source": url, "type": "youtube"})]
