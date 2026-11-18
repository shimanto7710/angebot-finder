"""Paginated offer listings for product screens."""

from decimal import Decimal

from pydantic import BaseModel


class OfferResponse(BaseModel):
    record_id: str
    product_name: str
    brand: str | None
    variant: str | None
    category: str | None
    store: str
    pack_size_text: str | None
    offer_price: Decimal | None
    currency: str | None
    requires_loyalty: bool | None
    source_url: str | None
    offer_data: dict


class OfferListResponse(BaseModel):
    items: list[OfferResponse]
    total: int
    limit: int
    offset: int
