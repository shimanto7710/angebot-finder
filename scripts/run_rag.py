"""Run one question through the offer assistant."""

import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT / "src"))

from angebotfinder.models import load_models
from angebotfinder.rag_pipeline import RAGPipeline
from angebotfinder.retrieval import load_retrieval_data

QUESTION = "Which stores have Haribo offers?"
USE_REWRITING = True
MIN_RERANK_SCORE = 0
LOCAL_FILES_ONLY = True  # Set False when downloading models for the first time.


def main():
    print("Loading saved offers...", flush=True)
    offers, chunks, config, embeddings = load_retrieval_data(PROJECT_ROOT)
    embedding_model, reranker_model, generator_model, generator_tokenizer = load_models(
        config["embedding_model"], local_files_only=LOCAL_FILES_ONLY
    )

    pipeline = RAGPipeline(
        embeddings,
        chunks,
        embedding_model,
        reranker_model,
        generator_model,
        generator_tokenizer,
        use_rewriting=USE_REWRITING,
        min_score=MIN_RERANK_SCORE,
    )

    print("Running the RAG pipeline...", flush=True)
    response = pipeline.ask_question(QUESTION)

    print("Original:", response["question"])
    print("Search:", response["search_question"])
    print("Answer:", response["answer"])


if __name__ == "__main__":
    main()
