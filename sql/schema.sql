CREATE TABLE IF NOT EXISTS offers (
    record_id TEXT PRIMARY KEY,
    offer_id TEXT,
    product_id TEXT,

    product_name TEXT NOT NULL,
    brand TEXT,
    variant TEXT,
    category TEXT,
    pack_size_text TEXT,

    store_id TEXT,
    store TEXT NOT NULL,
    branch_region TEXT,
    postal_code TEXT,

    offer_price NUMERIC(10, 2),
    currency TEXT,
    requires_loyalty BOOLEAN,
    loyalty_conditions TEXT,

    valid_from DATE,
    valid_to DATE,
    validity_text TEXT,

    source_url TEXT,
    fetched_at TIMESTAMPTZ,
    is_searchable BOOLEAN,

    offer_data JSONB NOT NULL
);

CREATE TABLE IF NOT EXISTS users (
    id UUID PRIMARY KEY,
    name TEXT NOT NULL CHECK (length(trim(name)) BETWEEN 1 AND 100),
    email TEXT NOT NULL,
    password_hash TEXT NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,

    CONSTRAINT users_email_unique UNIQUE (email)
);

CREATE TABLE IF NOT EXISTS chat_turns (
    id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    user_id UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    question TEXT NOT NULL,
    answer TEXT NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS chat_turns_user_id_id_idx
    ON chat_turns (user_id, id DESC);

CREATE EXTENSION IF NOT EXISTS vector;

CREATE TABLE IF NOT EXISTS embedding_settings (
    id INTEGER PRIMARY KEY CHECK (id = 1),
    embedding_model TEXT NOT NULL,
    embedding_dimension INTEGER NOT NULL CHECK (embedding_dimension = 768),
    normalized BOOLEAN NOT NULL,
    updated_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS offer_chunks (
    chunk_id TEXT PRIMARY KEY,
    record_id TEXT NOT NULL REFERENCES offers(record_id) ON DELETE CASCADE,
    text TEXT NOT NULL,
    metadata JSONB NOT NULL,
    embedding_model TEXT NOT NULL,
    embedding VECTOR(768) NOT NULL
);

CREATE INDEX IF NOT EXISTS offer_chunks_record_id_idx
    ON offer_chunks (record_id);

CREATE INDEX IF NOT EXISTS offer_chunks_embedding_idx
    ON offer_chunks USING hnsw (embedding vector_cosine_ops);
