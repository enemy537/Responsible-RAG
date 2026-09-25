"""Hybrid retrieval that returns only documents that are actually relevant.

Dense (vector) hits capture semantic similarity; BM25 hits capture exact
keyword overlap. The two ranked lists are combined with reciprocal-rank fusion,
then filtered:

* a dense hit must reach ``retrieval_min_relevance`` (cosine similarity), and
* a keyword-only hit must reach ``bm25_min_relative_score`` of the best BM25
  score in the same query.

The result is "up to n": **however many documents clear the bar (possibly
none), never more than ``retrieval_max_docs``**. An empty result is a valid
outcome — callers then answer without retrieved context.
"""

import hashlib
import logging

from langchain_community.retrievers import BM25Retriever
from langchain_core.documents import Document

from src.core.config import Settings
from src.core.vector_store import KnowledgeBase

logger = logging.getLogger(__name__)


def _document_key(document: Document) -> str:
    """Stable identity for de-duplicating hits across both retrievers."""
    digest = hashlib.sha1(
        document.page_content.encode("utf-8", errors="ignore")
    ).hexdigest()[:16]
    return f"{document.metadata.get('source_id', '')}:{digest}"


class RetrievedDocument:
    """A document plus the scores that decided its inclusion."""

    __slots__ = ("document", "dense_score", "fused_score")

    def __init__(
        self, document: Document, dense_score: float | None, fused_score: float
    ) -> None:
        self.document = document
        self.dense_score = dense_score
        self.fused_score = fused_score


class RelevanceRetriever:
    """Retrieves up to ``max_docs`` relevant documents for a query."""

    #: Reciprocal-rank-fusion constant (standard default).
    RRF_K = 60

    def __init__(
        self,
        knowledge_base: KnowledgeBase,
        settings: Settings,
        all_docs: list[Document] | None = None,
    ) -> None:
        self._knowledge_base = knowledge_base
        self._candidate_k = max(settings.vec_retriever_k, settings.bm25_retriever_k)
        self._max_docs = settings.retrieval_max_docs
        self._min_relevance = settings.retrieval_min_relevance
        self._bm25_min_relative = settings.bm25_min_relative_score
        self._vec_weight = settings.vec_weight
        self._bm25_weight = settings.bm25_weight

        corpus = all_docs or []
        if corpus:
            self._bm25: BM25Retriever | None = BM25Retriever.from_documents(
                corpus, search_kwargs={"k": settings.bm25_retriever_k}
            )
        else:
            logger.warning(
                "No documents available — falling back to dense-only retrieval."
            )
            self._bm25 = None

    def retrieve(self, query: str) -> list[Document]:
        """Return the relevant documents for *query* (possibly none)."""
        return [hit.document for hit in self.retrieve_scored(query)]

    def retrieve_scored(self, query: str) -> list[RetrievedDocument]:
        """Return relevant documents with the scores that qualified them."""
        documents: dict[str, Document] = {}
        fused: dict[str, float] = {}
        dense_scores: dict[str, float] = {}

        dense_hits = self._knowledge_base.similarity_search_with_score(
            query, k=self._candidate_k
        )
        for rank, (document, score) in enumerate(dense_hits):
            key = _document_key(document)
            documents.setdefault(key, document)
            dense_scores[key] = score
            fused[key] = fused.get(key, 0.0) + self._vec_weight / (
                self.RRF_K + rank + 1
            )

        sparse_hits = self._ranked_bm25_hits(query)
        best_sparse = sparse_hits[0][1] if sparse_hits else 0.0
        keyword_relevance: dict[str, float] = {}
        for rank, (document, score) in enumerate(sparse_hits):
            key = _document_key(document)
            documents.setdefault(key, document)
            fused[key] = fused.get(key, 0.0) + self._bm25_weight / (
                self.RRF_K + rank + 1
            )
            if key not in dense_scores and best_sparse > 0:
                keyword_relevance[key] = score / best_sparse

        results: list[RetrievedDocument] = []
        for key, document in documents.items():
            similarity = dense_scores.get(key)
            if similarity is not None:
                keep = similarity >= self._min_relevance
            else:
                keep = keyword_relevance.get(key, 0.0) >= self._bm25_min_relative
            if keep:
                results.append(RetrievedDocument(document, similarity, fused[key]))

        results.sort(key=lambda hit: hit.fused_score, reverse=True)
        if len(results) > self._max_docs:
            logger.debug(
                "Retrieved %d relevant documents — capping at %d.",
                len(results),
                self._max_docs,
            )
        return results[: self._max_docs]

    def _ranked_bm25_hits(self, query: str) -> list[tuple[Document, float]]:
        """Return ``(document, bm25 score)`` pairs, best first."""
        if self._bm25 is None:
            return []
        try:
            scores = self._bm25.vectorizer.get_scores(
                self._bm25.preprocess_func(query)
            )
            ranked = sorted(
                zip(self._bm25.docs, scores, strict=True),
                key=lambda pair: pair[1],
                reverse=True,
            )
        except Exception as exc:  # pragma: no cover - defensive
            logger.warning("BM25 scoring failed (%s) — using dense results only.", exc)
            return []

        return [
            (document, float(score)) for document, score in ranked[: self._candidate_k]
        ]


class RetrieverFactory:
    """Builds the application's retriever from settings."""

    @staticmethod
    def build(
        knowledge_base: KnowledgeBase,
        all_docs: list[Document],
        settings: Settings,
    ) -> RelevanceRetriever:
        """Return a relevance-filtered hybrid retriever."""
        logger.info(
            "Retriever ready (candidates=%d, max_docs=%d, min_relevance=%.2f).",
            max(settings.vec_retriever_k, settings.bm25_retriever_k),
            settings.retrieval_max_docs,
            settings.retrieval_min_relevance,
        )
        return RelevanceRetriever(knowledge_base, settings, all_docs)
