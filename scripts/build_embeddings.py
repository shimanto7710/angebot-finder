"""Load PostgreSQL offers, generate embeddings, and save them to disk."""

import sys
from pathlib import Path

from sentence_transformers import SentenceTransformer

PROJECT_ROOT = Path(__file__).resolve().parents[1]
OUTPUT_DIR = PROJECT_ROOT / "data" / "processed" / "embeddings"
MODEL_NAME = "intfloat/multilingual-e5-base"

# Allow this script to run directly from the project folder.
sys.path.insert(0, str(PROJECT_ROOT / "src"))
from angebotfinder.embeddings import (
    prepare_documents,
    do_chunking,
    do_embedding,
    save_chunks_embeddings,
)
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
    save_chunks_embeddings(chunks, embeddings, OUTPUT_DIR, MODEL_NAME)


def main():
    build_embeddings()


if __name__ == "__main__":
    main()
