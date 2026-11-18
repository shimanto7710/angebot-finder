"""Prepare database tables, web offers, chunks and vectors before starting the API."""

import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))

from scripts.setup_database import setup_database
from scripts.refresh_data import refresh_data

SETUP_DATA = False
ALLOW_PARTIAL_REFRESH = False


def setup_data(enabled=False, allow_partial=False):
    if not isinstance(enabled, bool) or not isinstance(allow_partial, bool):
        raise ValueError("Setup flags must be True or False.")
    if not enabled:
        print("Data setup disabled. Set SETUP_DATA = True to run.")
        return

    print("Checking database schema...", flush=True)
    setup_database()

    print("Refreshing offers and embeddings...", flush=True)
    refresh_data(enabled=True, allow_partial=allow_partial)

    print("Data setup complete.", flush=True)


if __name__ == "__main__":
    setup_data(enabled=SETUP_DATA, allow_partial=ALLOW_PARTIAL_REFRESH)
