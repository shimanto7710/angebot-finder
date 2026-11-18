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

-- name: filtered_offers
SELECT record_id, product_name, brand, variant, category, store, pack_size_text,
       offer_price, currency, requires_loyalty, source_url, offer_data
FROM offers
WHERE (:include_unsearchable OR is_searchable IS NOT FALSE)
  AND (CAST(:search AS TEXT) IS NULL OR strpos(
      lower(concat_ws(' ', product_name, brand, variant)), lower(CAST(:search AS TEXT))
  ) > 0)
  AND (CAST(:store AS TEXT) IS NULL OR lower(store) = lower(CAST(:store AS TEXT)))
  AND (CAST(:brand AS TEXT) IS NULL OR lower(brand) = lower(CAST(:brand AS TEXT)))
  AND (CAST(:category AS TEXT) IS NULL OR lower(category) = lower(CAST(:category AS TEXT)))
  AND (CAST(:min_price AS NUMERIC) IS NULL OR offer_price >= CAST(:min_price AS NUMERIC))
  AND (CAST(:max_price AS NUMERIC) IS NULL OR offer_price <= CAST(:max_price AS NUMERIC))
  AND (CAST(:requires_loyalty AS BOOLEAN) IS NULL OR requires_loyalty = CAST(:requires_loyalty AS BOOLEAN))
ORDER BY lower(product_name), record_id
LIMIT :limit OFFSET :offset;

-- name: filtered_offers_count
SELECT COUNT(*) AS total
FROM offers
WHERE (:include_unsearchable OR is_searchable IS NOT FALSE)
  AND (CAST(:search AS TEXT) IS NULL OR strpos(
      lower(concat_ws(' ', product_name, brand, variant)), lower(CAST(:search AS TEXT))
  ) > 0)
  AND (CAST(:store AS TEXT) IS NULL OR lower(store) = lower(CAST(:store AS TEXT)))
  AND (CAST(:brand AS TEXT) IS NULL OR lower(brand) = lower(CAST(:brand AS TEXT)))
  AND (CAST(:category AS TEXT) IS NULL OR lower(category) = lower(CAST(:category AS TEXT)))
  AND (CAST(:min_price AS NUMERIC) IS NULL OR offer_price >= CAST(:min_price AS NUMERIC))
  AND (CAST(:max_price AS NUMERIC) IS NULL OR offer_price <= CAST(:max_price AS NUMERIC))
  AND (CAST(:requires_loyalty AS BOOLEAN) IS NULL OR requires_loyalty = CAST(:requires_loyalty AS BOOLEAN));
