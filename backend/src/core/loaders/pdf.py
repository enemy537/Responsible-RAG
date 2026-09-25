"""PDF loading with reference-section trimming."""

import asyncio
import logging
import re
from pathlib import Path

import pymupdf
import pymupdf4llm
from langchain_core.documents import Document

from src.core.loaders.base import SourceLoader

logger = logging.getLogger(__name__)

# Academic reference/bibliography headings, dropped before embedding.
_REFERENCE_HEADING = re.compile(
    r"^#{1,3}\s*(?:References|REFERENCES|Bibliography|BIBLIOGRAPHY"
    r"|Works\s+Cited|WORKS\s+CITED"
    r"|References\s+and\s+Notes|REFERENCES\s+AND\s+NOTES"
    r"|Cited\s+References|CITED\s+REFERENCES"
    r"|References\s+and\s+Further\s+Reading"
    r"|Reference\s+List|REFERENCE\s+LIST)\s*$"
)


def strip_references(markdown: str) -> str:
    """Cut everything from the first reference heading onward."""
    lines = markdown.split("\n")
    for index, line in enumerate(lines):
        if _REFERENCE_HEADING.match(line.strip()):
            return "\n".join(lines[:index]).strip()
    return markdown.strip()


def _to_markdown(path: Path) -> str | None:
    """Convert a PDF to markdown, or return ``None`` on failure."""
    try:
        document = pymupdf.open(str(path))
    except Exception as exc:
        logger.warning("Could not open PDF '%s': %s", path.name, exc)
        return None

    try:
        markdown = pymupdf4llm.to_markdown(
            document,
            header=False,
            footer=False,
            page_separators=True,
            ignore_images=True,
            write_images=False,
            image_path=None,
        )
    except Exception as exc:
        logger.warning("Could not convert PDF '%s' to markdown: %s", path.name, exc)
        return None
    finally:
        document.close()

    cleaned = strip_references(markdown)
    # Drop lone surrogates that pymupdf4llm can leave behind.
    return cleaned.encode("utf-8", errors="surrogatepass").decode("utf-8", errors="ignore")


class PdfLoader(SourceLoader):
    """Converts a PDF to reference-free markdown."""

    source_type = "pdf"
    suffixes = frozenset({".pdf"})

    async def load(self, target: str | Path) -> list[Document] | None:
        path = Path(target)
        markdown = await asyncio.to_thread(_to_markdown, path)
        if not markdown:
            return None
        return [Document(page_content=markdown, metadata={"source": str(path), "type": "pdf"})]
