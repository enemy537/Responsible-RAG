"""Loader registry plus upload policy (suffixes, source types, size limits)."""

from pathlib import Path

from src.core.loaders.audio import AudioFileLoader
from src.core.loaders.base import SourceLoader
from src.core.loaders.pdf import PdfLoader
from src.core.loaders.text import TextFileLoader
from src.core.loaders.web import WebPageLoader
from src.core.loaders.youtube import YouTubeLoader

_MEGABYTE = 1024 * 1024

#: Upload size ceiling per source type.
SIZE_LIMITS: dict[str, int] = {
    "pdf": 100 * _MEGABYTE,
    "audio": 500 * _MEGABYTE,
    "text": 15 * _MEGABYTE,
}
DEFAULT_SIZE_LIMIT = 50 * _MEGABYTE


class LoaderRegistry:
    """Resolves the loader responsible for a given file or source type."""

    def __init__(self, loaders: list[SourceLoader] | None = None) -> None:
        self._loaders = loaders or [
            PdfLoader(),
            TextFileLoader(),
            AudioFileLoader(),
            WebPageLoader(),
            YouTubeLoader(),
        ]

    @property
    def supported_suffixes(self) -> frozenset[str]:
        return frozenset(suffix for loader in self._loaders for suffix in loader.suffixes)

    def supported_suffixes_label(self) -> str:
        return ", ".join(sorted(self.supported_suffixes))

    def for_file(self, filename: str) -> SourceLoader | None:
        suffix = Path(filename).suffix.lower()
        return next((loader for loader in self._loaders if loader.supports(suffix)), None)

    def for_source_type(self, source_type: str) -> SourceLoader | None:
        return next(
            (loader for loader in self._loaders if loader.source_type == source_type),
            None,
        )

    def is_supported_file(self, filename: str) -> bool:
        return self.for_file(filename) is not None

    def source_type_for(self, filename: str) -> str:
        loader = self.for_file(filename)
        return loader.source_type if loader else "text"

    @staticmethod
    def size_limit_for(source_type: str) -> int:
        return SIZE_LIMITS.get(source_type, DEFAULT_SIZE_LIMIT)
