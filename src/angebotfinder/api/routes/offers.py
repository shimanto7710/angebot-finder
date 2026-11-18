"""Browse and filter the saved offer catalogue."""

from decimal import Decimal

from fastapi import APIRouter, HTTPException, Query

from ..schemas.offers import OfferListResponse
from ...database.offers import list_offers

router = APIRouter(prefix="/offers", tags=["Offers"])


@router.get("", response_model=OfferListResponse)
def get_offers(
    search: str | None = Query(default=None, min_length=1, max_length=200),
    store: str | None = Query(default=None, min_length=1, max_length=100),
    brand: str | None = Query(default=None, min_length=1, max_length=100),
    category: str | None = Query(default=None, min_length=1, max_length=100),
    min_price: Decimal | None = Query(default=None, ge=0, max_digits=10, decimal_places=2, allow_inf_nan=False),
    max_price: Decimal | None = Query(default=None, ge=0, max_digits=10, decimal_places=2, allow_inf_nan=False),
    requires_loyalty: bool | None = None,
    include_unsearchable: bool = False,
    limit: int = Query(default=20, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
):
    if min_price is not None and max_price is not None and min_price > max_price:
        raise HTTPException(status_code=422, detail="min_price must not exceed max_price.")

    return list_offers(
        search=search, store=store, brand=brand, category=category,
        min_price=min_price, max_price=max_price,
        requires_loyalty=requires_loyalty, include_unsearchable=include_unsearchable,
        limit=limit, offset=offset,
    )
