CREATE TABLE offers (
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
