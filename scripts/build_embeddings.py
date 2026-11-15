"""Prepare offer chunks, generate embeddings, and save them to disk."""

import sys
from pathlib import Path

from sentence_transformers import SentenceTransformer

PROJECT_ROOT = Path(__file__).resolve().parents[1]
DATA_PATH = PROJECT_ROOT / "data" / "processed" / "offers_dataset.json"
OUTPUT_DIR = PROJECT_ROOT / "data" / "processed" / "embeddings"
MODEL_NAME = "intfloat/multilingual-e5-base"

# Allow this script to run directly from the project folder.
sys.path.insert(0, str(PROJECT_ROOT / "src"))
from angebotfinder.embeddings import (
    load_files,
    prepare_documents,
    do_chunking,
    do_embedding,
    save_chunks_embeddings,
)
from angebotfinder.models import MODEL_CACHE


def main():
    offers = load_files(DATA_PATH)
    documents = prepare_documents(offers)
    chunks = do_chunking(documents)
    if not chunks:
        raise ValueError("No offer chunks to embed.")

    model = SentenceTransformer(MODEL_NAME, cache_folder=str(MODEL_CACHE))
    embeddings = do_embedding(chunks, model)
    save_chunks_embeddings(chunks, embeddings, OUTPUT_DIR, MODEL_NAME)


if __name__ == "__main__":
    main()
