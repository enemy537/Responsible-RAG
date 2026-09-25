"""Webpage scraping loader."""

import asyncio
import logging

from langchain_community.document_loaders import WebBaseLoader
from langchain_core.documents import Document

from src.core.loaders.base import SourceLoader

logger = logging.getLogger(__name__)

_BROWSER_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/131.0.0.0 Safari/537.36"
    ),
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "en-US,en;q=0.9",
}


class WebPageLoader(SourceLoader):
    """Scrapes a webpage into documents."""

    source_type = "webpage"

    async def load(self, target: str) -> list[Document] | None:
        url = str(target)
        try:
            loader = WebBaseLoader(
                web_paths=[url],
                header_template=_BROWSER_HEADERS,
                requests_kwargs={"timeout": 30},
                raise_for_status=False,
            )
            documents = await asyncio.to_thread(loader.load)
        except Exception as exc:
            logger.warning("Failed to scrape webpage '%s': %s", url, exc)
            return None

        if not documents:
            return None
        for document in documents:
            document.metadata.setdefault("source", url)
            document.metadata.setdefault("type", "webpage")
        return documents
