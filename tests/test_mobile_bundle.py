"""Aligned Android exports, validation and dataset versions."""

import sys
import unittest
from pathlib import Path
from unittest.mock import patch

import numpy as np
from fastapi.testclient import TestClient

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from angebotfinder.api.app import app
from angebotfinder.retrieval import build_mobile_bundle


class MobileBundleTests(unittest.TestCase):
    def setUp(self):
        self.chunks = [
            {"record_id": "a", "chunk_id": "a::1", "text": "Coffee"},
            {"record_id": "b", "chunk_id": "b::1", "text": "Tea"},
        ]
        self.config = {
            "embedding_model": "intfloat/multilingual-e5-base",
            "normalized": True, "embedding_dimension": 2, "chunk_count": 2,
        }
        self.vectors = np.eye(2)

    def export(self):
        with patch("angebotfinder.retrieval.load_retrieval_data", return_value=(
            [], self.chunks, self.config, self.vectors,
        )):
            return build_mobile_bundle()

    def test_bundle_alignment_and_version(self):
        bundle = self.export()
        self.assertEqual(bundle["chunks"], self.chunks)
        self.assertEqual(bundle["embeddings"], [[1.0, 0.0], [0.0, 1.0]])
        self.assertEqual(bundle["config"]["query_prefix"], "query: ")
        self.assertEqual(bundle["dataset_version"], self.export()["dataset_version"])
        self.chunks[0]["text"] = "Updated coffee"
        self.assertNotEqual(bundle["dataset_version"], self.export()["dataset_version"])

    def test_rejects_invalid_vectors_and_duplicate_ids(self):
        self.vectors[0, 0] = np.nan
        with self.assertRaisesRegex(ValueError, "non-finite"):
            self.export()
        self.vectors = np.eye(2) * 2
        with self.assertRaisesRegex(ValueError, "normalization"):
            self.export()
        self.vectors = np.eye(2)
        self.chunks[1]["chunk_id"] = self.chunks[0]["chunk_id"]
        with self.assertRaisesRegex(ValueError, "unique"):
            self.export()

    def test_database_filter_keeps_vectors_aligned_without_offer_json_file(self):
        with patch("angebotfinder.retrieval.fetch_all_offers", return_value=[
            {"record_id": "a", "is_searchable": False},
            {"record_id": "b", "is_searchable": True},
        ]), patch("angebotfinder.retrieval.load_offer_chunks", return_value=(
            self.chunks, self.config, self.vectors,
        )):
            bundle = build_mobile_bundle()
        self.assertEqual(bundle["chunks"], [self.chunks[1]])
        self.assertEqual(bundle["embeddings"], [[0.0, 1.0]])
        self.assertEqual(bundle["config"]["chunk_count"], 1)

    def test_public_endpoint_returns_bundle(self):
        bundle = self.export()
        with patch("angebotfinder.api.routes.rag.build_mobile_bundle", return_value=bundle):
            response = TestClient(app).get("/rag/data")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json(), bundle)

    def test_unavailable_data_returns_503(self):
        with patch("angebotfinder.api.routes.rag.build_mobile_bundle", side_effect=FileNotFoundError()), patch(
            "angebotfinder.api.routes.rag.logger"
        ):
            response = TestClient(app).get("/rag/data")
        self.assertEqual(response.status_code, 503)
