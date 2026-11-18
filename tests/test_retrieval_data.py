"""Check database eligibility against saved chunks and vectors."""

import sys
import unittest
from pathlib import Path
from unittest.mock import patch

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from angebotfinder.retrieval import load_retrieval_data


class RetrievalDataTests(unittest.TestCase):
    def test_database_offers_control_chunk_and_vector_filtering(self):
        offers = [
            {"record_id": "new-db-offer", "is_searchable": True},
            {"record_id": "blocked", "is_searchable": False},
            {"record_id": "unknown", "is_searchable": None},
        ]
        chunks = [
            {"record_id": record_id}
            for record_id in ["deleted", "new-db-offer", "blocked", "unknown"]
        ]
        vectors = np.arange(8).reshape(4, 2)

        config = {"chunk_count": 4, "embedding_dimension": 2}
        with patch("angebotfinder.retrieval.fetch_all_offers", return_value=offers), patch(
            "angebotfinder.retrieval.load_offer_chunks", return_value=(chunks, config, vectors)
        ):
            loaded, selected, config, embeddings = load_retrieval_data()

        self.assertEqual(loaded, offers)
        self.assertEqual(selected, [chunks[1], chunks[3]])
        np.testing.assert_array_equal(embeddings, vectors[[1, 3]])
        self.assertEqual(config["chunk_count"], 2)
