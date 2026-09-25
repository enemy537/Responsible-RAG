"""Plain-text document loading."""

import asyncio
import logging
from pathlib import Path

from langchain_community.document_loaders import TextLoader
from langchain_core.documents import Document

from src.core.loaders.base import SourceLoader

logger = logging.getLogger(__name__)


class TextFileLoader(SourceLoader):
    """Loads ``.txt``/``.md``/``.rst`` files verbatim."""

    source_type = "text"
    suffixes = frozenset({".txt", ".md", ".rst", ".markdown"})

    async def load(self, target: str | Path) -> list[Document] | None:
        path = Path(target)
        try:
            documents = await asyncio.to_thread(TextLoader(str(path), encoding="utf-8").load)
        except Exception as exc:
            logger.warning("Could not load '%s': %s", path.name, exc)
            return None

        for document in documents:
            document.metadata.setdefault("source", str(path))
        return documents
