-- name: lock_collection()!
LOCK TABLE offer_chunks IN EXCLUSIVE MODE;

-- name: clear_chunks()!
DELETE FROM offer_chunks;

-- name: save_settings(model_name, dimension, normalized)!
INSERT INTO embedding_settings (id, embedding_model, embedding_dimension, normalized)
VALUES (1, :model_name, :dimension, :normalized)
ON CONFLICT (id) DO UPDATE SET
    embedding_model = EXCLUDED.embedding_model,
    embedding_dimension = EXCLUDED.embedding_dimension,
    normalized = EXCLUDED.normalized,
    updated_at = CURRENT_TIMESTAMP;

-- name: insert_chunk(chunk_id, record_id, text, metadata, model_name, embedding)!
INSERT INTO offer_chunks (chunk_id, record_id, text, metadata, embedding_model, embedding)
VALUES (:chunk_id, :record_id, :text, :metadata, :model_name, :embedding);

-- name: load_collection()
SELECT s.embedding_model, s.embedding_dimension, s.normalized,
       c.chunk_id, c.record_id, c.text, c.metadata, c.embedding
FROM embedding_settings AS s
LEFT JOIN (
    offer_chunks AS c
    JOIN offers AS o ON o.record_id = c.record_id AND o.is_searchable IS NOT FALSE
) ON c.embedding_model = s.embedding_model
WHERE s.id = 1
ORDER BY c.chunk_id;

-- name: nearest_chunks(query_embedding, model_name, candidate_k)
SELECT c.chunk_id
FROM offer_chunks AS c
JOIN offers AS o ON o.record_id = c.record_id
WHERE o.is_searchable IS NOT FALSE
  AND c.embedding_model = :model_name
ORDER BY c.embedding <=> :query_embedding
LIMIT :candidate_k;
