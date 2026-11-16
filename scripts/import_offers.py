"""Import saved offer JSON into PostgreSQL."""

import json
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT / "src"))

from angebotfinder.database.offers import save_offers

DATA_PATH = PROJECT_ROOT / "data" / "processed" / "offers_dataset.json"


def import_offers(data_path=DATA_PATH, deactivate_missing=False):
    with data_path.open(encoding="utf-8") as file:
        data = json.load(file)

    offers = data["offers"]
    save_offers(offers, deactivate_missing=deactivate_missing)
    print(f"Saved {len(offers)} offers.")
    return len(offers)


def main():
    import_offers()


if __name__ == "__main__":
    main()
