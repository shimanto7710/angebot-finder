"""Invalid collections must not touch existing database vectors."""

import sys
import unittest
from pathlib import Path
from unittest.mock import patch

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from angebotfinder.database.embeddings import save_offer_chunks


class EmbeddingStorageTests(unittest.TestCase):
    def test_invalid_collections_rejected_before_opening_database(self):
        chunks = [{"chunk_id": "a", "record_id": "a", "text": "Offer"}]
        with patch("angebotfinder.database.embeddings.get_connection") as connect:
            for vectors in [np.zeros((1, 768)), np.ones((1, 2)), np.full((1, 768), np.nan)]:
                with self.subTest(shape=vectors.shape):
                    with self.assertRaises(ValueError):
                        save_offer_chunks(chunks, vectors, "model")
            with self.assertRaises(ValueError):
                save_offer_chunks([], np.empty((0, 768)), "model")
            connect.assert_not_called()
