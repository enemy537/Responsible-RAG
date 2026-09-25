"""Loader contract for turning a source (file or URL) into documents."""

from abc import ABC, abstractmethod
from pathlib import Path

from langchain_core.documents import Document


class SourceLoader(ABC):
    """Loads one category of source into LangChain documents."""

    source_type: str = ""
    suffixes: frozenset[str] = frozenset()

    def supports(self, suffix: str) -> bool:
        return suffix.lower() in self.suffixes

    @abstractmethod
    async def load(self, target: str | Path) -> list[Document] | None:
        """Return documents for *target*, or ``None`` when loading fails."""
