"""Offer-list request validation and response serialization."""

import sys
import unittest
from decimal import Decimal
from pathlib import Path
from unittest.mock import patch

from fastapi.testclient import TestClient

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from angebotfinder.api.app import app


class OffersAPITests(unittest.TestCase):
    def setUp(self):
        self.client = TestClient(app)

    def test_filters_and_pagination_passed_to_repository(self):
        with patch("angebotfinder.api.routes.offers.list_offers", return_value={
            "items": [], "total": 0, "limit": 5, "offset": 10,
        }) as repository:
            response = self.client.get("/offers", params={
                "search": "coffee", "store": "REWE", "brand": "Test",
                "category": "Drinks", "min_price": "1.00", "max_price": "5.50",
                "requires_loyalty": "false", "include_unsearchable": "true",
                "limit": 5, "offset": 10,
            })
        self.assertEqual(response.status_code, 200)
        repository.assert_called_once_with(
            search="coffee", store="REWE", brand="Test", category="Drinks",
            min_price=Decimal("1.00"), max_price=Decimal("5.50"),
            requires_loyalty=False, include_unsearchable=True, limit=5, offset=10,
        )

    def test_invalid_filters_rejected_without_database_call(self):
        with patch("angebotfinder.api.routes.offers.list_offers") as repository:
            for params in [
                {"min_price": -1}, {"min_price": 5, "max_price": 2},
                {"max_price": "NaN"}, {"min_price": "Infinity"},
                {"limit": 0}, {"limit": 101}, {"offset": -1},
                {"requires_loyalty": "maybe"}, {"search": ""},
            ]:
                with self.subTest(params=params):
                    self.assertEqual(self.client.get("/offers", params=params).status_code, 422)
            repository.assert_not_called()

    def test_price_and_complete_json_returned_without_login(self):
        item = {
            "record_id": "test", "product_name": "Coffee", "brand": None,
            "variant": None, "category": None, "store": "REWE",
            "pack_size_text": "250 g", "offer_price": Decimal("2.49"),
            "currency": "EUR", "requires_loyalty": None, "source_url": None,
            "offer_data": {"quality": {"warnings": ["Stock unknown"]}},
        }
        with patch("angebotfinder.api.routes.offers.list_offers", return_value={
            "items": [item], "total": 1, "limit": 20, "offset": 0,
        }):
            response = self.client.get("/offers")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["items"][0]["offer_price"], "2.49")
        self.assertIsNone(response.json()["items"][0]["requires_loyalty"])
        self.assertEqual(response.json()["items"][0]["offer_data"], item["offer_data"])
