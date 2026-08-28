"""
retrievers.py — Ensemble retriever factory
============================================
Combines a dense vector-similarity retriever with a sparse BM25 keyword
retriever via :class:`EnsembleRetriever`.

Rationale
---------
* **Dense (vector)**: Captures semantic similarity — good at paraphrasing and
  concept-level matching.
* **Sparse (BM25)**: Captures exact keyword overlap — good at proper nouns,
  acronyms, and rare domain-specific terms that might be underrepresented in
  the embedding space.
* **Ensemble**: Weighted reciprocal-rank fusion of both result lists gives the
  best of both retrieval strategies.

Default weights (configurable via Settings)
-------------------------------------------
  vector 0.7 + BM25 0.3 = 1.0

Usage
-----
    ensemble = RetrieverFactory.build_ensemble(
        vec_retriever=kb.as_retriever(k=settings.vec_retriever_k),
        all_docs=kb.get_all_documents(),
        settings=settings,
    )
"""

import logging
import math
from typing import Any, List, Optional, cast

from langchain_classic.retrievers.ensemble import EnsembleRetriever
from langchain_community.retrievers import BM25Retriever

#new imports
from langchain_core.callbacks import CallbackManager
from langchain_core.documents import Document
from langchain_core.load.dump import dumpd
from langchain_core.retrievers import BaseRetriever
from langchain_core.runnables import RunnableConfig, ensure_config
from langchain_core.runnables.config import patch_config
from pydantic import PrivateAttr

from src.core.config import Settings, get_settings

logger = logging.getLogger(__name__)

class RetrieverFactory:
    """Static factory for building the ensemble retriever."""

    @staticmethod
    def build_ensemble(
        vec_retriever: BaseRetriever,
        all_docs: list[Document],
        settings: Settings,
    ) -> EnsembleRetriever:
        """
        Build and return a weighted ensemble of vector + BM25 retrievers.

        Parameters
        ----------
        vec_retriever:
            Pre-built vector-similarity retriever (e.g. from
            :class:`KnowledgeBase`'s ``as_retriever()``).
        all_docs:
            The full document corpus for building the BM25 index (in-memory).
        settings:
            Application settings — supplies ``bm25_retriever_k``,
            ``vec_weight``, and ``bm25_weight``.

        Returns
        -------
        EnsembleRetriever
            Ready-to-use ensemble retriever.
        """
        if not all_docs:
            logger.warning(
                "No documents in the vector store — BM25 retriever will be "
                "disabled; using vector-only retrieval."
            )
            return vec_retriever

        bm25 = BM25Retriever.from_documents(
            all_docs,
            search_kwargs={"k": settings.bm25_retriever_k},
        )
        logger.info(
            "Ensemble retriever ready (vec_weight=%.1f, bm25_weight=%.1f).",
            settings.vec_weight,
            settings.bm25_weight,
        )
        return EnsembleRetriever(
            retrievers=[vec_retriever, bm25],
            weights=[settings.vec_weight, settings.bm25_weight],
        )

#test code for new features
class EnsembleWithScores(EnsembleRetriever):
    """
    Inspired by: https://www.reddit.com/r/LangChain/comments/1c6dlyu/bm25_retriever_with_score_threshold/

    Extends EnsembleRetriever to also return a similarity score for each document, instead of just a bare list of Documents.
    """

    # these vars are declared this way to get around Pydantic checks, so I can still put a fallback retriever in without it passing the Pydantic check
    _ensemble: Any = PrivateAttr(default=None)
    _bm25_s: float = PrivateAttr(default=0.7)
    _relevance_threshold: float = PrivateAttr(default=0.6)
    _top_k: int = PrivateAttr(default=5)

    def __init__(
        self,
        retrievers: list,
        weights: List[float],
        settings: Optional[Settings] = None,
        ensemble: Optional[Any] = None,
        c: int = 60,
        relevance_threshold: float = 0.6,
        top_k: Optional[int] = 5,
        bm25_s: float = 0.7,
        **kwargs: Any,
    ):

        if top_k is None:
            active_settings = settings or get_settings()
            top_k = getattr(active_settings, "bm25_retriever_k", 3)

        if relevance_threshold is None:
            if settings is not None:
                relevance_threshold = settings.relevance_threshold
            else:
                relevance_threshold = get_settings().relevance_threshold

        if bm25_s is None:
            if settings is not None:
                bm25_s = settings.bm25_s
            else:
                bm25_s = get_settings().bm25_s

        super().__init__(
            retrievers=retrievers,
            weights=weights,
            c=c,
            **kwargs,
        )

        self._ensemble = ensemble
        self._bm25_s = bm25_s
        self._relevance_threshold = relevance_threshold
        self._top_k = top_k
    
    
    @property 
    def bm25_s(self) -> float:
        return self._bm25_s
    @property
    def relevance_threshold(self) -> float:
        return self._relevance_threshold

    @property
    def top_k(self) -> int:
        return self._top_k
    


    def invoke(self, input: str, config: Optional[RunnableConfig] = None, **kwargs: Any):
        """
        Retrieve documents using weighted score fusion instead of RRF, which is implicitly used by Retrieva;lFactory.
        Steps:
          1. Scores every candidate doc using weighted_score_fusion (comparable 0-1 scale, penalising docs weak in either signal), like in the paper I mentioned
          2. Filters out anything below self.relevance_threshold
          3. Caps the result at top_k
          4. Stashes each doc's score in doc.metadata["relevance_score"]
        """
        config = ensure_config(config)

        callback_manager = CallbackManager.configure(
            config.get("callbacks"),
            None,
            verbose=kwargs.get("verbose", False),
            inheritable_tags=config.get("tags", []),
            local_tags=self.tags,
            inheritable_metadata=config.get("metadata", {}),
            local_metadata=self.metadata,
        )

        run_manager = callback_manager.on_retriever_start(
            dumpd(self), input, name=config.get("run_name"), **kwargs
        )

        try:
            scored = self.weighted_score_fusion(input)

            # Filter out anything below the relevance threshold.
            filtered = [(doc, score) for doc, score in scored if score >= self.relevance_threshold]

            #return early if empty
            if not scored:
                return []


            #if everything gets filtered out, fall back to the single best-scoring doc
            if not filtered:
                logger.warning(
                    "weighted_score_fusion: all %d candidates fell below "
                    "relevance_threshold=%.3f for query %r; falling back "
                    "to the single best match (score=%.3f).",
                    len(scored), self.relevance_threshold, input, scored[0][1],
                )
                filtered = scored[:1]

            #return a maximum of top_k docs
            capped = filtered[: self.top_k]

            result = []
            for doc, score in capped:
                #store score in metadata
                doc.metadata["relevance_score"] = round(score, 4)
                result.append(doc)

        except Exception as e:
            run_manager.on_retriever_error(e)
            raise e
        else:
            run_manager.on_retriever_end(result, **kwargs)
            return result
    def _bm25_scores(self, query: str, bm25_retriever) -> dict[str, tuple]:
        """
        Returns {page_content: (Document, normalised_score)} for BM25
        """
        # Use sigmoid instead of min-max normalisation so weak matches stay weak, rather than being stretched to fill the 0-1 range.
        retriever = getattr(bm25_retriever, "bound", bm25_retriever)
        vectorizer = getattr(retriever, "vectorizer", None)
        preprocess_func = getattr(retriever, "preprocess_func", lambda s: s.lower().split())
        tokenized_query = preprocess_func(query)
        raw_scores = vectorizer.get_scores(tokenized_query)

        #using sigmoid ensures that weak scores stay weak rather than being stretched
        normalised = self._sigmoid_scale(list(raw_scores), k=self.bm25_s)
        docs = getattr(retriever, "docs", [])

        return {
            doc.page_content: (doc, score)
            for doc, score in zip(docs, normalised)
        }
        
    def weighted_score_fusion(self, query: str) -> List[tuple]:
        """
        Combine vector + BM25 scores on a shared [0, 1] scale, penaliss single-point failures

        Returns: 
        List[tuple]
            (Document, combined_score) pairs, sorted by combined_score descending. combined_score is a weighted GEOMETRIC mean of the two normalised scores: v**vec_weight * b**bm25_weight.
        """
        vec_retriever, bm25_retriever = self.retrievers  # order set by RetrieverFactory.build_ensemble
        vec_weight, bm25_weight = self.weights

        vec_scored = self._vector_scores(query, vec_retriever)
        bm25_scored = self._bm25_scores(query, bm25_retriever)

        # Union of every document either retriever surfaced, so a doc found
        # by only one side is still scored (just penalised, not dropped).
        all_content = set(vec_scored) | set(bm25_scored)

        fused: List[tuple] = []
        for content in all_content:
            doc, v = vec_scored.get(content, (None, 0.0))
            doc_b, b = bm25_scored.get(content, (None, 0.0))
            doc = doc or doc_b  # whichever retriever actually returned the Document object

            combined_score = (v ** vec_weight) * (b ** bm25_weight)
            fused.append((doc, combined_score))

        fused.sort(key=lambda pair: pair[1], reverse=True)
        return fused


    def __ror__(self, other):
        """
        Fallback for the `|` (or) operator, e.g. `some_runnable | ensemble`.
        If this scored wrapper can't be composed directly, fall back to
        piping into the plain EnsembleRetriever passed in as `ensemble`.
        """
        if self._ensemble is None:
            raise ValueError(
                "EnsembleWithScores has no fallback `ensemble` set — "
                "pass one via the `ensemble=` argument to use `|`."
            )
        return other | self._ensemble


    @staticmethod
    def _sigmoid_scale(raw_scores: List[float], k: float = 0.5) -> List[float]:
        """
        Subtract minimum +ve score so docs that get a score of 0 sit closer to 0 on output.
        I chose not to use a normalisation funcion because if all the docs are 'irrelevant' and the scores get normalised, then there will always be one that is 'seen' as relevant, even if it actually isn't.
        Now scores aren't stretched to fill the gaps, and retain some of their 'true' value.
        """
        # Shift so the lowest non-zero score maps below 0.5
        floor = min((s for s in raw_scores if s > 0), default=0.0)
        return [1 / (1 + math.exp(-k * (s - floor))) for s in raw_scores]

    def _vector_scores(self, query: str, vec_retriever: BaseRetriever) -> dict[str, tuple]:
        """
        Langchain already normalises these scores as they are cosine/similarity distances.
        Clamping again just to prevent any errors.
        Returns: {page_content: (Document, normalised_score)} for vector
        """
        vectorstore = vec_retriever.vectorstore
        k = getattr(vec_retriever, "search_kwargs", {}).get("k", 10)
        results = vectorstore.similarity_search_with_relevance_scores(query, k=k)
        return {
            doc.page_content: (doc, max(0.0, min(1.0, score)))
            for doc, score in results
        }

"""
    def rank_fusion(
        self, query: str, run_manager: CallbackManager, *, config: Optional[RunnableConfig] = None
    ) -> List[tuple]:
        
        Retrieve results from every retriever and fuse them into a single, weighted-scored list.
        Args:
            query: The search query.
        Returns:
            A list of (Document, score) tuples, sorted by score descending.      
        

        #Each retriever runs against the query so LangSmith shows them as separate spans under the trace
        retriever_docs = [
            retriever.invoke(
                query,
                patch_config(config, callbacks=run_manager.get_child(tag=f"retriever_{i + 1}")),
            )
            for i, retriever in enumerate(self.retrievers)
        ]

        #normalise output to documents for robustness
        for i in range(len(retriever_docs)):
            retriever_docs[i] = [
                Document(page_content=cast(str, doc)) if isinstance(doc, str) else doc
                for doc in retriever_docs[i]
            ]

        # combine each of the retriever's ranked lists into one weight-scored one
        fused_documents_with_scores = self.weighted_reciprocal_rank(retriever_docs)
        return fused_documents_with_scores


    def weighted_reciprocal_rank(self, doc_lists: List[List[Document]]) -> List[tuple]:

        
        Perform weighted Reciprocal Rank Fusion on multiple rank lists.

        Args:
        doc_lists: A list of rank lists, where each rank list contains unique items.

        Returns:
        list of tuples: Each tuple contains a Document and its corresponding weighted RRF score sorted by the scores in descending order.

        

        if len(doc_lists) != len(self.weights):
            raise ValueError("Number of rank lists must be equal to the number of weights.")

        #build a set of documents from either retriever
        all_documents = set()
        for doc_list in doc_lists:
            for doc in doc_list:
                all_documents.add(doc.page_content)

        # start every document's fused score at 0
        rrf_score_dic = {doc: 0.0 for doc in all_documents}


        # for each retriever's ranked list, add a weighted reciprocal-rank contribution per document
        
        RRF (reciprocal Rank Fusion) Formula : 
        1 / (rank + self.c)
        - doc 1 gets highest rank and then falls off for the rest (what LangChain implicitly uses)
        - c softens the fall
        - multiply by weight of the retrievers set in the .env
        - Scores from both retrievers contribute to the final 'relevancy_score' which is stored in the metadata, so a doc ranked highly by both does better than a doc only ranked highly by one
        
    
        for doc_list, weight in zip(doc_lists, self.weights):
            for rank, doc in enumerate(doc_list, start=1):
                rrf_score = weight * (1 / (rank + self.c))
                rrf_score_dic[doc.page_content] += rrf_score

        # sort documents by their final fused score, highest first
        sorted_documents = sorted(rrf_score_dic.items(), key=lambda x: x[1], reverse=True)


        # map docs to dict using page content
        page_content_to_doc_map = {
            doc.page_content: doc for doc_list in doc_lists for doc in doc_list
        }

        sorted_docs_with_scores = [
            (page_content_to_doc_map[page_content], score)
            for page_content, score in sorted_documents
        ]

        return sorted_docs_with_scores
"""