"""Connect question rewriting, retrieval, filtering, and generation."""

import numpy as np

from .generation import generate_answer, rewrite_question
from .retrieval import build_bm25, rerank_search


class RAGPipeline:
    """Reuse loaded models and offer data across questions."""

    def __init__(
        self,
        embeddings,
        chunks,
        embedding_model,
        reranker_model,
        generator_model,
        generator_tokenizer,
        *,
        use_rewriting=False,
        min_score=None,
        semantic_search=None,
    ):
        self.embeddings = embeddings
        self.chunks = chunks
        self.bm25 = build_bm25(chunks)
        self.embedding_model = embedding_model
        self.reranker_model = reranker_model
        self.generator_model = generator_model
        self.generator_tokenizer = generator_tokenizer
        self.use_rewriting = use_rewriting
        self.min_score = min_score
        self.semantic_search = semantic_search

    def ask_question(
        self,
        question,
        history=None,
        top_k=5,
        candidate_k=30,
        max_new_tokens=300,
    ):
        if not question.strip():
            raise ValueError("Provide a question.")
        if not isinstance(self.use_rewriting, bool):
            raise ValueError("use_rewriting must be True or False.")

        if self.min_score is not None:
            if (
                isinstance(self.min_score, bool)
                or not isinstance(self.min_score, (int, float))
                or not np.isfinite(self.min_score)
            ):
                raise ValueError("min_score must be a finite number or None.")

        search_question = question
        if self.use_rewriting:
            search_question = rewrite_question(
                question,
                self.generator_model,
                self.generator_tokenizer,
                history=history,
            )

        ranked_results = rerank_search(
            search_question,
            self.embeddings,
            self.chunks,
            top_k=top_k,
            candidate_k=candidate_k,
            embedding_model=self.embedding_model,
            reranker=self.reranker_model,
            bm25=self.bm25,
            semantic_search=self.semantic_search,
        )
        if self.min_score is not None:
            ranked_results = [
                chunk
                for chunk in ranked_results
                if chunk["reranker_score"] >= self.min_score
            ]

        if not ranked_results:
            return {
                "question": question,
                "search_question": search_question,
                "status": "no_relevant_evidence",
                "answer": (
                    "I couldn't find sufficiently relevant offers in the saved data "
                    "for this question."
                ),
                "sources": [],
            }

        response = generate_answer(
            search_question,
            ranked_results,
            self.generator_model,
            self.generator_tokenizer,
            max_new_tokens=max_new_tokens,
            history=history,
        )
        response["status"] = "generated"
        response["question"] = question
        response["search_question"] = search_question
        return response
