-- name: all_offers()
SELECT offer_data
FROM offers
ORDER BY record_id;

-- name: deactivate_missing_offers(record_ids)!
UPDATE offers
SET is_searchable = false,
    offer_data = jsonb_set(offer_data, '{is_searchable}', 'false'::jsonb)
WHERE NOT (record_id = ANY(:record_ids));

-- name: offers_by_store(store)
SELECT record_id, product_name, offer_price, currency
FROM offers
WHERE store = :store
ORDER BY offer_price ASC NULLS LAST, record_id;

-- name: save_offer!
INSERT INTO offers (
    record_id, offer_id, product_id,
    product_name, brand, variant, category, pack_size_text,
    store_id, store, branch_region, postal_code,
    offer_price, currency, requires_loyalty, loyalty_conditions,
    valid_from, valid_to, validity_text,
    source_url, fetched_at, is_searchable, offer_data
)
VALUES (
    :record_id, :offer_id, :product_id,
    :product_name, :brand, :variant, :category, :pack_size_text,
    :store_id, :store, :branch_region, :postal_code,
    :offer_price, :currency, :requires_loyalty, :loyalty_conditions,
    :valid_from, :valid_to, :validity_text,
    :source_url, :fetched_at, :is_searchable, :offer_data
)
ON CONFLICT (record_id) DO UPDATE SET
    offer_id = EXCLUDED.offer_id,
    product_id = EXCLUDED.product_id,
    product_name = EXCLUDED.product_name,
    brand = EXCLUDED.brand,
    variant = EXCLUDED.variant,
    category = EXCLUDED.category,
    pack_size_text = EXCLUDED.pack_size_text,
    store_id = EXCLUDED.store_id,
    store = EXCLUDED.store,
    branch_region = EXCLUDED.branch_region,
    postal_code = EXCLUDED.postal_code,
    offer_price = EXCLUDED.offer_price,
    currency = EXCLUDED.currency,
    requires_loyalty = EXCLUDED.requires_loyalty,
    loyalty_conditions = EXCLUDED.loyalty_conditions,
    valid_from = EXCLUDED.valid_from,
    valid_to = EXCLUDED.valid_to,
    validity_text = EXCLUDED.validity_text,
    source_url = EXCLUDED.source_url,
    fetched_at = EXCLUDED.fetched_at,
    is_searchable = EXCLUDED.is_searchable,
    offer_data = EXCLUDED.offer_data;
