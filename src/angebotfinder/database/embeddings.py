"""Store one complete chunk collection and search its pgvector embeddings."""

import aiosql
import numpy as np
from pgvector.psycopg import register_vector
from psycopg.rows import dict_row
from psycopg.types.json import Jsonb

from .connection import PROJECT_ROOT, get_connection

queries = aiosql.from_path(PROJECT_ROOT / "sql" / "queries" / "embeddings.sql", "psycopg")


def save_offer_chunks(chunks, embeddings, model_name, normalized=True):
    embeddings = np.asarray(embeddings, dtype=np.float32)
    if not chunks or embeddings.shape != (len(chunks), 768):
        raise ValueError("Provide one 768-dimensional embedding per chunk.")
    if not np.isfinite(embeddings).all():
        raise ValueError("Embeddings must contain finite numbers.")
    if normalized and not np.allclose(np.linalg.norm(embeddings, axis=1), 1, atol=1e-4):
        raise ValueError("Expected normalized embeddings.")
    if len({chunk["chunk_id"] for chunk in chunks}) != len(chunks):
        raise ValueError("Chunk IDs must be unique.")

    with get_connection() as connection:
        register_vector(connection)
        queries.lock_collection(connection)
        queries.clear_chunks(connection)
        queries.save_settings(connection, model_name=model_name, dimension=768, normalized=normalized)
        for chunk, embedding in zip(chunks, embeddings):
            metadata = {
                key: value for key, value in chunk.items()
                if key not in {"chunk_id", "record_id", "text", "embedding"}
            }
            queries.insert_chunk(
                connection, chunk_id=chunk["chunk_id"], record_id=chunk["record_id"],
                text=chunk["text"], metadata=Jsonb(metadata),
                model_name=model_name, embedding=embedding,
            )
    print(f"Saved {len(chunks)} chunks and embeddings to PostgreSQL.")


def load_offer_chunks():
    with get_connection() as connection:
        register_vector(connection)
        connection.row_factory = dict_row
        rows = list(queries.load_collection(connection))
    if not rows:
        raise ValueError("No embedding collection in PostgreSQL. Build embeddings first.")

    config = {key: rows[0][key] for key in (
        "embedding_model", "embedding_dimension", "normalized",
    )}
    rows = [row for row in rows if row["chunk_id"] is not None]
    chunks = [
        {**row["metadata"], "chunk_id": row["chunk_id"],
         "record_id": row["record_id"], "text": row["text"]}
        for row in rows
    ]
    embeddings = np.array([row["embedding"].to_list() for row in rows], dtype=np.float32).reshape(-1, 768)
    config["chunk_count"] = len(chunks)
    return chunks, config, embeddings


def search_chunk_ids(query_embedding, candidate_k, model_name):
    query_embedding = np.asarray(query_embedding, dtype=np.float32)
    if query_embedding.shape != (768,) or not np.isfinite(query_embedding).all():
        raise ValueError("Provide a finite 768-dimensional query embedding.")
    with get_connection() as connection:
        register_vector(connection)
        connection.row_factory = dict_row
        return [row["chunk_id"] for row in queries.nearest_chunks(
            connection, query_embedding=query_embedding,
            model_name=model_name, candidate_k=candidate_k,
        )]
