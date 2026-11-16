"""Refresh web offers, import the collection, and rebuild embeddings."""

import json
import sys
from pathlib import Path
from tempfile import TemporaryDirectory

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))
sys.path.insert(0, str(PROJECT_ROOT / "src"))

FETCH_DATA = False
ALLOW_PARTIAL_REFRESH = False
DATA_PATH = PROJECT_ROOT / "data" / "processed" / "offers_dataset.json"


def refresh_data(enabled=False, allow_partial=False):
    if not isinstance(enabled, bool) or not isinstance(allow_partial, bool):
        raise ValueError("Refresh flags must be True or False.")
    if not enabled:
        print("Refresh disabled. Set FETCH_DATA = True when ready.")
        return

    from scripts.import_offers import import_offers

    DATA_PATH.parent.mkdir(parents=True, exist_ok=True)
    with TemporaryDirectory(dir=DATA_PATH.parent, prefix=".refresh-") as directory:
        json_path = Path(directory) / "offers_dataset.json"

        print("Step 1: Fetch offers from the internet.", flush=True)
        fetch_offers(json_path, allow_partial)

        print("Step 2: Save offers to PostgreSQL.", flush=True)
        import_offers(json_path, deactivate_missing=True)
        json_path.replace(DATA_PATH)

    print("Step 3: Build embeddings from PostgreSQL offers.", flush=True)
    build_offer_embeddings()
    print("Done. You can now run: python scripts/run_rag.py")


def fetch_offers(json_path, allow_partial=False):
    """Fetch and check the collection before it reaches the database."""
    from scripts.fetch_offers import refresh_all_offers_json

    result = refresh_all_offers_json(enabled=True, output_path=json_path)
    for source in result.get("sources", []):
        print(f"{source['store']}: {source['status']} ({source['records']} offers)")

    if not result.get("success") or not result.get("updated"):
        raise RuntimeError("Fetch failed. Existing data kept; import was not started.")
    if result["status"] == "partial_saved" and not allow_partial:
        raise RuntimeError(
            "Some shops failed or need inspection. Existing data kept. "
            "Review the source statuses; set ALLOW_PARTIAL_REFRESH = True "
            "only if you want to use the partial collection."
        )
    if result["status"] not in {"saved", "partial_saved"}:
        raise RuntimeError(f"Unexpected fetch status: {result['status']}")

    dataset = json.loads(json_path.read_text(encoding="utf-8"))
    if not any(offer.get("is_searchable") is not False for offer in dataset["offers"]):
        raise ValueError("No searchable offers fetched. Existing data kept.")


def build_offer_embeddings():
    try:
        from scripts.build_embeddings import build_embeddings

        build_embeddings()
    except Exception as error:
        raise RuntimeError(
            "Offers were imported, but embeddings failed. Fix the error and run "
            "python scripts/build_embeddings.py before using RAG."
        ) from error


if __name__ == "__main__":
    refresh_data(enabled=FETCH_DATA, allow_partial=ALLOW_PARTIAL_REFRESH)
