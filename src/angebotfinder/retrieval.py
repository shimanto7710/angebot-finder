"""Load saved offers and retrieve relevant chunks."""

import json
import hashlib
import re
from time import perf_counter

import numpy as np
from rank_bm25 import BM25Okapi

from .database.offers import fetch_all_offers
from .database.embeddings import load_offer_chunks


def load_retrieval_data():
    offers = fetch_all_offers()
    chunks, config, embeddings = load_offer_chunks()

    if embeddings.ndim != 2 or len(chunks) != embeddings.shape[0]:
        raise ValueError("Chunks and embeddings do not match.")
    if len(chunks) != config["chunk_count"]:
        raise ValueError("Chunk count does not match config.")
    if embeddings.shape[1] != config["embedding_dimension"]:
        raise ValueError("Embedding dimension does not match config.")

    eligible_ids = {
        offer["record_id"]
        for offer in offers
        if offer.get("is_searchable") is not False
    }
    indices = [
        index for index, chunk in enumerate(chunks)
        if chunk["record_id"] in eligible_ids
    ]
    chunks = [chunks[index] for index in indices]
    embeddings = embeddings[indices]
    config["chunk_count"] = len(chunks)

    return offers, chunks, config, embeddings


def build_mobile_bundle():
    """Export aligned, searchable chunks and vectors as one JSON bundle."""
    _, chunks, config, embeddings = load_retrieval_data()
    if not chunks:
        raise ValueError("No searchable chunks to export.")
    if not np.isfinite(embeddings).all():
        raise ValueError("Embeddings contain non-finite numbers.")
    chunk_ids = [chunk["chunk_id"] for chunk in chunks]
    if len(set(chunk_ids)) != len(chunk_ids):
        raise ValueError("Chunk IDs must be unique.")
    if config.get("normalized") and not np.allclose(
        np.linalg.norm(embeddings, axis=1), 1.0, atol=1e-4,
    ):
        raise ValueError("Embedding normalization does not match config.")

    mobile_config = {
        **config,
        "query_prefix": "query: ",
        "document_prefix": "passage: ",
        "similarity": "cosine",
        "alignment": "embeddings[i] corresponds to chunks[i]",
    }
    if config["embedding_model"] == "intfloat/multilingual-e5-base":
        mobile_config.update(pooling="attention_mask_mean", max_tokens=512)

    bundle = {
        "schema_version": "1.0",
        "config": mobile_config,
        "chunks": chunks,
        "embeddings": embeddings.tolist(),
    }
    content = json.dumps(bundle, ensure_ascii=False, sort_keys=True, allow_nan=False)
    bundle["dataset_version"] = hashlib.sha256(content.encode("utf-8")).hexdigest()
    return bundle


def tokenize(text):
    return re.findall(r"\b\w+\b", text.lower())


def tokenize_chunks(chunks):
    return [tokenize(chunk["text"]) for chunk in chunks]


def build_bm25(chunks):
    """Build once for the same chunks, in the same order, used by retrieval."""
    tokenized_chunks = tokenize_chunks(chunks)
    if not any(tokenized_chunks):
        return None
    return BM25Okapi(tokenized_chunks)


def build_search_question(question, history=None):
    if not question.strip():
        raise ValueError("Provide a question.")
    if not history:
        return question

    previous_questions = " ".join(turn["question"] for turn in history[-3:])
    return f"Previous questions: {previous_questions}\nCurrent question: {question}"


def hybrid_search(
    question,
    embeddings,
    top_k=30,
    document_chunks=None,
    embedding_model=None,
    candidate_k=30,
    history=None,
    bm25=None,
    semantic_search=None,
):
    if not question.strip():
        raise ValueError("Provide a question.")
    if top_k < 1 or candidate_k < 1:
        raise ValueError("Use positive retrieval limits.")
    if document_chunks is None or embedding_model is None:
        raise ValueError("Pass document_chunks and embedding_model.")
    if len(document_chunks) != len(embeddings):
        raise ValueError("Chunks and embeddings do not match.")

    if not document_chunks:
        return {
            "semantic_ranking": np.array([], dtype=int),
            "bm25_ranking": np.array([], dtype=int),
            "hybrid_ranking": np.array([], dtype=int),
        }

    if bm25 is None or bm25.corpus_size != len(document_chunks):
        raise ValueError("Pass a BM25 index built from the same document_chunks.")

    search_question = build_search_question(question, history)

    query_embedding = embedding_model.encode(
        f"query: {search_question}",
        normalize_embeddings=True,
        convert_to_numpy=True,
    )

    if semantic_search is None:
        semantic_scores = embeddings @ query_embedding
        semantic_ranking = np.argsort(-semantic_scores, kind="stable")
    else:
        chunk_indices = {chunk["chunk_id"]: index for index, chunk in enumerate(document_chunks)}
        ranked_ids = semantic_search(query_embedding, max(candidate_k, top_k))
        semantic_ranking = np.array(
            [chunk_indices[chunk_id] for chunk_id in ranked_ids if chunk_id in chunk_indices],
            dtype=int,
        )

    bm25_scores = bm25.get_scores(tokenize(search_question))

    bm25_ranking = np.array(
        [
            index
            for index in np.argsort(-bm25_scores, kind="stable")
            if bm25_scores[index] > 0
        ],
        dtype=int,
    )

    candidate_k = min(
        max(candidate_k, top_k),
        len(document_chunks),
    )

    rrf_scores = {}

    for ranking in [
        semantic_ranking[:candidate_k],
        bm25_ranking[:candidate_k],
    ]:
        for rank, index in enumerate(ranking, start=1):
            index = int(index)

            rrf_scores[index] = (
                rrf_scores.get(index, 0.0)
                + 1 / (60 + rank)
            )

    hybrid_ranking = np.array(
        sorted(
            rrf_scores,
            key=rrf_scores.get,
            reverse=True,
        ),
        dtype=int,
    )

    return {
        "semantic_ranking": semantic_ranking[:top_k],
        "bm25_ranking": bm25_ranking[:top_k],
        "hybrid_ranking": hybrid_ranking[:top_k],
    }


def rerank_search(
    question,
    embeddings,
    chunks,
    top_k=5,
    candidate_k=30,
    embedding_model=None,
    reranker=None,
    timings=None,
    history=None,
    bm25=None,
    semantic_search=None,
):
    if reranker is None:
        raise ValueError("Pass the loaded reranker.")
    if top_k < 1 or candidate_k < 1:
        raise ValueError("Use positive retrieval limits.")
    search_question = build_search_question(question, history)

    started = perf_counter()
    rankings = hybrid_search(
        search_question,
        embeddings,
        top_k=max(candidate_k, top_k),
        document_chunks=chunks,
        embedding_model=embedding_model,
        candidate_k=candidate_k,
        bm25=bm25,
        semantic_search=semantic_search,
    )

    if timings is not None:
        timings["hybrid_search"] = perf_counter() - started

    started = perf_counter()

    indices = list(dict.fromkeys(
        int(index) for index in rankings["hybrid_ranking"]
    ))

    if not indices:
        return []

    pairs = [
        [search_question, chunks[index]["text"]]
        for index in indices
    ]

    scores = reranker.predict(pairs, batch_size=16)

    results = [
        {
            **chunks[index],
            "reranker_score": float(score),
        }
        for index, score in zip(indices, scores)
    ]

    ranked_results = sorted(
        results,
        key=lambda result: result["reranker_score"],
        reverse=True,
    )[:top_k]
    if timings is not None:
        timings["reranking"] = perf_counter() - started
    return ranked_results
