"""Data setup ordering and disabled/failure behavior without external calls."""

import unittest
from unittest.mock import patch

from scripts import setup_data


class SetupDataTests(unittest.TestCase):
    def test_disabled_does_not_touch_database_or_web(self):
        with patch.object(setup_data, "setup_database") as database, patch.object(
            setup_data, "refresh_data"
        ) as refresh:
            setup_data.setup_data()
            database.assert_not_called()
            refresh.assert_not_called()

    def test_schema_setup_runs_before_refresh(self):
        steps = []
        with patch.object(setup_data, "setup_database", side_effect=lambda: steps.append("schema")), patch.object(
            setup_data, "refresh_data", side_effect=lambda **kwargs: steps.append("refresh")
        ) as refresh:
            setup_data.setup_data(enabled=True)
            refresh.assert_called_once_with(enabled=True, allow_partial=False)
        self.assertEqual(steps, ["schema", "refresh"])

    def test_database_failure_stops_before_fetching(self):
        with patch.object(setup_data, "setup_database", side_effect=RuntimeError("Database unavailable")), patch.object(
            setup_data, "refresh_data"
        ) as refresh:
            with self.assertRaisesRegex(RuntimeError, "Database unavailable"):
                setup_data.setup_data(enabled=True)
            refresh.assert_not_called()

    def test_partial_acceptance_is_explicit(self):
        with patch.object(setup_data, "setup_database"), patch.object(setup_data, "refresh_data") as refresh:
            setup_data.setup_data(enabled=True, allow_partial=True)
            refresh.assert_called_once_with(enabled=True, allow_partial=True)

    def test_refresh_failure_propagates(self):
        with patch.object(setup_data, "setup_database"), patch.object(
            setup_data, "refresh_data", side_effect=RuntimeError("Fetch failed")
        ):
            with self.assertRaisesRegex(RuntimeError, "Fetch failed"):
                setup_data.setup_data(enabled=True)
