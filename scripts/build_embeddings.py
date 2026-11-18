"""Generate chunks and embeddings from offers and store them in PostgreSQL."""

import sys
from pathlib import Path

from sentence_transformers import SentenceTransformer

PROJECT_ROOT = Path(__file__).resolve().parents[1]
MODEL_NAME = "intfloat/multilingual-e5-base"

sys.path.insert(0, str(PROJECT_ROOT / "src"))
from angebotfinder.embeddings import (
    prepare_documents,
    do_chunking,
    do_embedding,
)
from angebotfinder.database.embeddings import save_offer_chunks
from angebotfinder.database.offers import fetch_all_offers
from angebotfinder.models import MODEL_CACHE


def build_embeddings():
    offers = fetch_all_offers()
    print(f"Loaded {len(offers)} offers from PostgreSQL.")
    documents = prepare_documents(offers)
    chunks = do_chunking(documents)
    if not chunks:
        raise ValueError("No searchable offers in PostgreSQL. Import offers first.")

    model = SentenceTransformer(MODEL_NAME, cache_folder=str(MODEL_CACHE))
    embeddings = do_embedding(chunks, model)
    save_offer_chunks(chunks, embeddings, MODEL_NAME)


def main():
    build_embeddings()


if __name__ == "__main__":
    main()
