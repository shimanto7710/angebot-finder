"""Fetch and save offer data using named SQL queries."""

import aiosql
from psycopg.rows import dict_row
from psycopg.types.json import Jsonb

from .connection import PROJECT_ROOT, get_connection

queries = aiosql.from_path(
    PROJECT_ROOT / "sql" / "queries" / "offers.sql",
    "psycopg",
    mandatory_parameters=False,
)

OFFER_COLUMNS = (
    "record_id",
    "offer_id",
    "product_id",
    "product_name",
    "brand",
    "variant",
    "category",
    "pack_size_text",
    "store_id",
    "store",
    "branch_region",
    "postal_code",
    "offer_price",
    "currency",
    "requires_loyalty",
    "loyalty_conditions",
    "valid_from",
    "valid_to",
    "validity_text",
    "source_url",
    "fetched_at",
    "is_searchable",
)


def fetch_all_offers():
    with get_connection() as connection:
        connection.row_factory = dict_row
        return [row["offer_data"] for row in queries.all_offers(connection)]


def fetch_offers_by_store(store):
    with get_connection() as connection:
        connection.row_factory = dict_row
        return list(queries.offers_by_store(connection, store=store))


def save_offers(offers, deactivate_missing=False):
    if deactivate_missing and not offers:
        raise ValueError("Cannot replace the searchable collection with no offers.")

    with get_connection() as connection:
        for offer in offers:
            values = {column: offer.get(column) for column in OFFER_COLUMNS}
            values["offer_data"] = Jsonb(offer)
            queries.save_offer(connection, **values)
        if deactivate_missing:
            queries.deactivate_missing_offers(
                connection, record_ids=[offer["record_id"] for offer in offers]
            )
