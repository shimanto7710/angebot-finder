"""Check refresh ordering and failures without websites or model inference."""

import json
import tempfile
import types
import unittest
from contextlib import ExitStack
from pathlib import Path
from unittest.mock import Mock, patch

from scripts import refresh_data


class RefreshDataTests(unittest.TestCase):
    def setUp(self):
        self.stack = ExitStack()
        self.addCleanup(self.stack.close)
        directory = self.stack.enter_context(tempfile.TemporaryDirectory())
        self.path = Path(directory) / "offers_dataset.json"
        self.path.write_text('{"previous": true}')
        self.stack.enter_context(patch.object(refresh_data, "DATA_PATH", self.path))
        self.events = []
        self.status = "saved"
        self.offers = [{"record_id": "new", "is_searchable": True}]

        def fetch(**kwargs):
            self.events.append("fetch")
            kwargs["output_path"].write_text(json.dumps({"offers": self.offers}))
            return {"success": True, "updated": True, "status": self.status}

        self.fetch = self.stack.enter_context(patch(
            "scripts.fetch_offers.refresh_all_offers_json", side_effect=fetch
        ))

        def import_data(path, deactivate_missing=False):
            self.events.append("import")
            self.assertTrue(deactivate_missing)
            self.assertEqual(json.loads(path.read_text())["offers"], self.offers)

        self.import_data = self.stack.enter_context(patch(
            "scripts.import_offers.import_offers", side_effect=import_data
        ))
        module = types.ModuleType("scripts.build_embeddings")
        module.build_embeddings = Mock(side_effect=lambda: self.events.append("embed"))
        self.build = module.build_embeddings
        self.stack.enter_context(patch.dict("sys.modules", {"scripts.build_embeddings": module}))
        self.stack.enter_context(patch("builtins.print"))

    def test_disabled_does_nothing(self):
        refresh_data.refresh_data()
        self.fetch.assert_not_called()
        self.import_data.assert_not_called()
        self.build.assert_not_called()
        self.assertEqual(self.events, [])

    def test_success_runs_in_order_and_publishes_json(self):
        refresh_data.refresh_data(enabled=True)
        self.assertEqual(self.events, ["fetch", "import", "embed"])
        self.assertEqual(json.loads(self.path.read_text())["offers"], self.offers)

    def test_partial_rejected_keeps_existing_data(self):
        self.status = "partial_saved"
        with self.assertRaisesRegex(RuntimeError, "Some shops"):
            refresh_data.refresh_data(enabled=True)
        self.assertEqual(self.events, ["fetch"])
        self.assertEqual(json.loads(self.path.read_text()), {"previous": True})

    def test_partial_requires_explicit_acceptance(self):
        self.status = "partial_saved"
        refresh_data.refresh_data(enabled=True, allow_partial=True)
        self.assertEqual(self.events, ["fetch", "import", "embed"])

    def test_fetch_failure_stops_before_import(self):
        self.fetch.side_effect = None
        self.fetch.return_value = {"success": False, "updated": False}
        with self.assertRaisesRegex(RuntimeError, "Fetch failed"):
            refresh_data.refresh_data(enabled=True)
        self.import_data.assert_not_called()
        self.build.assert_not_called()

    def test_empty_collection_keeps_existing_data(self):
        self.offers = []
        with self.assertRaisesRegex(ValueError, "No searchable offers"):
            refresh_data.refresh_data(enabled=True)
        self.import_data.assert_not_called()
        self.assertEqual(json.loads(self.path.read_text()), {"previous": True})

    def test_import_failure_keeps_json_and_skips_embeddings(self):
        self.import_data.side_effect = RuntimeError("Import failed")
        with self.assertRaisesRegex(RuntimeError, "Import failed"):
            refresh_data.refresh_data(enabled=True)
        self.build.assert_not_called()
        self.assertEqual(json.loads(self.path.read_text()), {"previous": True})

    def test_embedding_failure_explains_recovery(self):
        self.build.side_effect = RuntimeError("Model failed")
        with self.assertRaisesRegex(RuntimeError, "Offers were imported"):
            refresh_data.refresh_data(enabled=True)
        self.assertEqual(json.loads(self.path.read_text())["offers"], self.offers)
