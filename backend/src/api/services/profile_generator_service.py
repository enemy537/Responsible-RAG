"""
services/profile_generator_service.py — Personalised profile prompt generation
================================================================================
Wraps :class:`src.core.profiles.ProfileAugmenter` as a lazy singleton for the
API layer, using Hugging Face Inference API embeddings (same as other services).

Low-memory strategy:
    - ``ProfileAugmenter`` (and its underlying vector-store retriever) are
      initialised once on first use and cached for the lifetime of the process.
    - The embedding model is already shared via ``EmbeddingFactory``.
"""

import logging

from src.core.config import get_settings
from src.core.embeddings import EmbeddingFactory
from src.core.profiles import ProfileAugmenter

logger = logging.getLogger(__name__)


class ProfileGeneratorService:
    """
    Generates personalised system prompts from demographic profiles.

    Wraps :class:`ProfileAugmenter` with lazy initialisation so that the
    embedding model and profiles vector store are only loaded on demand.
    """

    def __init__(self):
        self._augmenter: ProfileAugmenter | None = None

    # ── Lazy init ─────────────────────────────────────────────────────────────

    def _get_augmenter(self) -> ProfileAugmenter:
        if self._augmenter is None:
            settings = get_settings()
            embeddings = EmbeddingFactory.create(settings)
            self._augmenter = ProfileAugmenter(embedding_function=embeddings)
            logger.info(
                "ProfileAugmenter initialised (model=%s)",
                settings.embedding_model,
            )
        return self._augmenter

    # ── Prompt generation ─────────────────────────────────────────────────────

    @property
    def last_source_titles(self) -> list[str]:
        """Source titles used in the most recent generation (delegates to augmenter)."""
        return self._get_augmenter().last_source_titles

    def generate_prompt(
        self,
        *,
        user_profile: dict[str, str] | None = None,
        user_query: str = "",
        retrieved_documents: str = "",
    ) -> str:
        """
        Build a personalised system prompt using the profiles knowledge base.

        Parameters
        ----------
        user_profile:
            Demographic data (keys match ``STANDARD_PROFILE`` in
            ``src.core.profiles``).  Missing keys fall back to defaults.
        user_query:
            The user's question.
        retrieved_documents:
            Pre-formatted context from the main RAG retriever (optional).

        Returns
        -------
        str
            Fully rendered ``DYNAMIC_PROFILE_TEMPLATE`` prompt string.
        """
        augmenter = self._get_augmenter()
        return augmenter.build_prompt(
            user_profile=user_profile,
            user_query=user_query,
            retrieved_documents=retrieved_documents,
        )
