"""Tests for relevance-filtered ("up to n") retrieval and prompt grounding."""

import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "backend"))

from langchain_core.documents import Document
from langchain_core.messages import AIMessage
from langchain_core.runnables import RunnableLambda

from src.core.config import Settings
from src.core.rag_chain import RAGChain
from src.core.retrievers import RelevanceRetriever


def make_doc(title: str, content: str, source_id: str = "s1") -> Document:
    return Document(
        page_content=content,
        metadata={"source_id": source_id, "source_title": title, "source_type": "pdf"},
    )


class FakeKnowledgeBase:
    """Returns pre-scored dense hits, ignoring the query."""

    def __init__(self, hits: list[tuple[Document, float]]) -> None:
        self._hits = hits

    def similarity_search_with_score(self, query: str, k: int):
        return self._hits[:k]


def build_retriever(
    dense_hits: list[tuple[Document, float]],
    all_docs: list[Document] | None = None,
    **settings_overrides,
) -> RelevanceRetriever:
    return RelevanceRetriever(
        FakeKnowledgeBase(dense_hits), Settings(**settings_overrides), all_docs or []
    )


class TestRelevanceFilter:
    def test_drops_hits_below_the_relevance_floor(self):
        strong, medium, weak = (
            make_doc("Strong", "a", "s1"),
            make_doc("Medium", "b", "s2"),
            make_doc("Weak", "c", "s3"),
        )
        retriever = build_retriever(
            [(strong, 0.91), (medium, 0.55), (weak, 0.12)],
            retrieval_min_relevance=0.35,
        )

        hits = retriever.retrieve("query")

        assert [hit.metadata["source_title"] for hit in hits] == ["Strong", "Medium"]

    def test_returns_nothing_when_nothing_is_relevant(self):
        retriever = build_retriever(
            [(make_doc("Weak", "a"), 0.10), (make_doc("Weaker", "b"), 0.05)],
            retrieval_min_relevance=0.35,
        )

        assert retriever.retrieve("query") == []

    def test_never_returns_more_than_max_docs(self):
        hits = [
            (make_doc(f"Doc {index}", f"content {index}", f"s{index}"), 0.9)
            for index in range(30)
        ]
        retriever = build_retriever(hits, retrieval_max_docs=15)

        assert len(retriever.retrieve("query")) == 15

    def test_document_found_by_both_retrievers_appears_once(self):
        shared = make_doc("Shared", "predictive policing", "s1")
        retriever = build_retriever([(shared, 0.9)], all_docs=[shared])

        hits = retriever.retrieve("predictive policing")

        assert hits == [shared]

    def test_keyword_only_hit_survives_on_strong_bm25(self):
        irrelevant = make_doc("Dense only", "totally unrelated prose", "s1")
        keyword_match = make_doc(
            "Keyword only",
            "predictive policing predictive policing predictive policing",
            "s2",
        )
        # BM25 IDF is zero for a term present in half of a two-document corpus,
        # so use a corpus where the term is genuinely rare.
        filler = [make_doc(f"Filler {i}", f"filler prose number {i}", f"f{i}") for i in range(8)]
        retriever = build_retriever(
            [(irrelevant, 0.10)],
            all_docs=[irrelevant, keyword_match, *filler],
            bm25_min_relative_score=0.5,
        )

        hits = retriever.retrieve("predictive policing")

        assert [hit.metadata["source_title"] for hit in hits] == ["Keyword only"]

    def test_weak_keyword_only_hit_is_excluded(self):
        irrelevant = make_doc("Dense only", "totally unrelated prose", "s1")
        retriever = build_retriever(
            [(irrelevant, 0.10)],
            all_docs=[irrelevant],
            bm25_min_relative_score=0.5,
        )

        assert retriever.retrieve("unmatched query terms") == []


class TestPromptGrounding:
    """Nothing relevant must not be announced to the user."""

    @staticmethod
    def _chain() -> tuple[RAGChain, dict]:
        chain = object.__new__(RAGChain)  # bypass the heavy __init__
        captured: dict = {}

        def fake_model(prompt_value):
            captured["prompt"] = prompt_value.to_string()
            return AIMessage(content="an answer")

        chain._llm = RunnableLambda(fake_model)
        return chain, captured

    def test_without_documents_it_answers_openly_and_silently(self):
        chain, captured = self._chain()

        result = chain.answer("What is RAG?", "profile text", "", [])

        assert result.sources == []
        assert result.answer == "an answer"
        assert "based ONLY on the following context" not in captured["prompt"]
        assert "do NOT fabricate" not in captured["prompt"]
        assert "What is RAG?" in captured["prompt"]

    def test_with_documents_it_grounds_the_answer(self):
        chain, captured = self._chain()
        documents = [make_doc("A paper", "Predictive policing is ...", "s1")]

        result = chain.answer("What is predictive policing?", "profile text", "", documents)

        assert "based ONLY on the following context" in captured["prompt"]
        assert "Predictive policing is ..." in captured["prompt"]
        assert len(result.sources) == 1
        assert result.sources[0]["source_title"] == "A paper"

    def test_invoke_retrieves_exactly_once(self):
        chain, _ = self._chain()

        class CountingRetriever:
            def __init__(self) -> None:
                self.calls = 0

            def retrieve(self, query: str) -> list[Document]:
                self.calls += 1
                return []

        chain._retriever = CountingRetriever()

        chain.invoke("question", "profile")

        assert chain._retriever.calls == 1
