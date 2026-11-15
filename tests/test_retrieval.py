import sys
import unittest
from pathlib import Path
from unittest.mock import patch

import numpy as np
from rank_bm25 import BM25Okapi

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from angebotfinder.rag_pipeline import RAGPipeline
from angebotfinder.retrieval import build_bm25, hybrid_search, tokenize_chunks


class FakeEmbeddingModel:
    def encode(self, text, **kwargs):
        return np.array([1.0, 0.0])


class FakeReranker:
    def predict(self, pairs, **kwargs):
        return np.ones(len(pairs))


class RetrievalTests(unittest.TestCase):
    def setUp(self):
        self.chunks = [
            {"text": "Haribo sweets"},
            {"text": "Coffee beans"},
            {"text": "Fresh milk"},
        ]
        self.embeddings = np.array([[1.0, 0.0], [0.0, 1.0], [0.5, 0.5]])

    def test_pipeline_builds_once_for_multiple_questions(self):
        with patch(
            "angebotfinder.retrieval.BM25Okapi", wraps=BM25Okapi
        ) as constructor, patch(
            "angebotfinder.rag_pipeline.generate_answer",
            return_value={"answer": "Test answer", "sources": []},
        ):
            pipeline = RAGPipeline(
                self.embeddings, self.chunks,
                FakeEmbeddingModel(), FakeReranker(), None, None,
            )
            for question in ["Haribo", "Coffee"]:
                response = pipeline.ask_question(question)
                self.assertEqual(response["status"], "generated")

            constructor.assert_called_once()

    def test_cached_index_preserves_rankings(self):
        cached = build_bm25(self.chunks)
        for question in ["Haribo", "Coffee", "unmatched"]:
            kwargs = dict(
                question=question,
                embeddings=self.embeddings,
                document_chunks=self.chunks,
                embedding_model=FakeEmbeddingModel(),
            )
            actual = hybrid_search(**kwargs, bm25=cached)
            fresh = BM25Okapi(tokenize_chunks(self.chunks))
            expected = hybrid_search(**kwargs, bm25=fresh)
            for key in actual:
                np.testing.assert_array_equal(actual[key], expected[key])

    def test_rejects_missing_or_wrong_size_index(self):
        for index in [None, build_bm25(self.chunks[:1])]:
            with self.assertRaisesRegex(ValueError, "BM25 index"):
                hybrid_search(
                    "Haribo", self.embeddings,
                    document_chunks=self.chunks,
                    embedding_model=FakeEmbeddingModel(), bm25=index,
                )

    def test_empty_data_returns_no_results(self):
        self.assertIsNone(build_bm25([]))
        result = hybrid_search(
            "Haribo", np.empty((0, 2)), document_chunks=[],
            embedding_model=FakeEmbeddingModel(),
        )
        self.assertEqual(len(result["hybrid_ranking"]), 0)


if __name__ == "__main__":
    unittest.main()
