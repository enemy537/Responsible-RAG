"""rag_chain.py — End-to-end RAG chain.

:class:`RAGChain` retrieves **once** per turn, then answers either from the
retrieved context (grounded, with citations) or from the model's own knowledge
when nothing relevant was found. In the latter case the user is not told that
no documents matched — the answer simply carries no citations.

Usage
-----
    from src.core.config import get_settings
    from src.core.rag_chain import RAGChain

    chain  = RAGChain(get_settings())
    result = chain.invoke("What is predictive policing?", group_prompt)
    print(result.answer, result.sources)
"""

import logging
from dataclasses import dataclass

from langchain.chat_models import init_chat_model
from langchain_core.output_parsers import StrOutputParser
from langchain_core.prompts import ChatPromptTemplate
from langsmith import traceable

from src.core.config import Settings
from src.core.embeddings import EmbeddingFactory
from src.core.retrievers import RelevanceRetriever, RetrieverFactory
from src.core.vector_store import KnowledgeBase

logger = logging.getLogger(__name__)


@dataclass
class RAGResult:
    """Return type for RAG chain invocation."""

    answer: str
    sources: list[dict]


def _get_source_label(doc) -> str:
    """Extract a human-readable source label from a document's metadata."""
    for key in ("source_title", "title", "source"):
        value = doc.metadata.get(key)
        if value:
            return str(value)
    return "Unknown source"


def _format_docs(docs) -> str:
    """Format docs with source references for the LLM context."""
    return "\n\n".join(
        f"[{i + 1}]: {_get_source_label(doc)}\n{doc.page_content}"
        for i, doc in enumerate(docs)
    )


def _extract_source_metadata(docs) -> list[dict]:
    """Extract unique source metadata from retrieved documents.

    Returns one entry per unique source (deduplicated by ``source_id``).
    All metadata fields were stored during ingestion from the MongoDB
    Source record, so no additional database lookup is needed.
    """
    seen = set()
    sources: list[dict] = []
    for doc in docs:
        meta = doc.metadata
        sid = meta.get("source_id") or _get_source_label(doc)
        if sid in seen:
            continue
        seen.add(sid)
        sources.append(
            {
                "source_id": sid,
                "source_title": meta.get("source_title", _get_source_label(doc)),
                "source_type": meta.get("source_type", "pdf"),
                "authors": meta.get("authors", []),
                "publication_date": meta.get("publication_date") or None,
                "publisher": meta.get("publisher") or None,
                "url": meta.get("url", ""),
                "doi": meta.get("doi", ""),
                "language": meta.get("language") or None,
                "description": meta.get("description") or None,
                "tags": meta.get("tags", []),
                "content_sensitivity": meta.get("content_sensitivity", "low"),
                "excerpt": doc.page_content[:300],
            }
        )
    return sources


# ── Prompt templates ──────────────────────────────────────────────────────────

_MEMORY_AND_QUESTION = (
    "Conversation memory: \n{memory_context}\n"
    "Question: {question}\n\n"
    "Audience profile:\n{group_of_people}\n\n"
)

#: Used when relevant documents were found — answers must stay grounded.
_GROUNDED_PROMPT = ChatPromptTemplate.from_template(
    _MEMORY_AND_QUESTION
    + "Answer the question based ONLY on the following context:\n{context}\n\n"
    + "Answer: If the context does not contain the answer, say so plainly — "
    "do NOT fabricate information."
)

#: Used when nothing relevant was retrieved: answer normally, and do not tell
#: the user that no documents matched.
_OPEN_PROMPT = ChatPromptTemplate.from_template(
    _MEMORY_AND_QUESTION + "Answer:"
)


class RAGChain:
    """Retrieval-Augmented Generation chain."""

    def __init__(self, settings: Settings) -> None:
        logger.info("Initialising RAGChain (model=%s).", settings.llm_model)

        self._settings = settings
        embedding_fn = EmbeddingFactory.create(settings)
        knowledge_base = KnowledgeBase(settings, embedding_fn)
        self._retriever: RelevanceRetriever = RetrieverFactory.build(
            knowledge_base,
            knowledge_base.get_all_documents(),
            settings,
        )

        self._llm = init_chat_model(
            model=settings.llm_model,
            temperature=settings.llm_temperature,
        )
        logger.info("RAGChain ready.")

    @traceable(name="rag_chain_invoke", run_type="chain")
    def invoke(
        self, question: str, group_prompt: str, memory_context: str = ""
    ) -> RAGResult:
        """Run the RAG pipeline and return the answer with its sources."""
        documents = self._retriever.retrieve(question)
        return self.answer(question, group_prompt, memory_context, documents)

    def answer(
        self,
        question: str,
        group_prompt: str,
        memory_context: str,
        documents: list,
    ) -> RAGResult:
        """Answer using *documents* when present, otherwise from model knowledge.

        Split out from :meth:`invoke` so the grounded and ungrounded behaviours
        can be tested without a vector store or an LLM.
        """
        payload = {
            "memory_context": memory_context,
            "context": _format_docs(documents) if documents else "",
            "question": question,
            "group_of_people": group_prompt,
        }

        prompt = _GROUNDED_PROMPT if documents else _OPEN_PROMPT
        text = (prompt | self._llm | StrOutputParser()).invoke(payload)

        if not documents:
            logger.info("No relevant documents for this question — answering openly.")

        return RAGResult(answer=text, sources=_extract_source_metadata(documents))
