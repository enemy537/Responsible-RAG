"""Source loaders and the registry that resolves them."""

from src.core.loaders.audio import AudioFileLoader
from src.core.loaders.base import SourceLoader
from src.core.loaders.pdf import PdfLoader
from src.core.loaders.registry import (
    DEFAULT_SIZE_LIMIT,
    SIZE_LIMITS,
    LoaderRegistry,
)
from src.core.loaders.text import TextFileLoader
from src.core.loaders.web import WebPageLoader
from src.core.loaders.youtube import YouTubeLoader

__all__ = [
    "AudioFileLoader",
    "DEFAULT_SIZE_LIMIT",
    "LoaderRegistry",
    "PdfLoader",
    "SIZE_LIMITS",
    "SourceLoader",
    "TextFileLoader",
    "WebPageLoader",
    "YouTubeLoader",
]
