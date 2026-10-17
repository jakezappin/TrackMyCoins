"""Shared helpers for coins: inventory numbers, serialization and collection totals."""

import re
from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from ..config import get_settings
from ..models import Coin, CoinType, CollectionCounter, InventoryCounter, PriceQuote
from ..series import collection_type_slug
from ..schemas import CoinDetail, CoinOut, CollectionSummary, PhotoOut, PriceQuoteOut

CPG = "CPG"
GREYSHEET = "GREYSHEET"  # wholesale; only on Greysheet's Advanced API tier
PCGS_GUIDE = "PCGS"  # PCGS Price Guide value
CENTS = Decimal("0.01")


def next_inventory_number(db: Session, user_id: int, coin_type: CoinType) -> str:
    counter = db.get(InventoryCounter, (user_id, coin_type.id))
    if counter is None:
        counter = InventoryCounter(user_id=user_id, coin_type_id=coin_type.id, next_seq=1)
        db.add(counter)
    seq = counter.next_seq
    counter.next_seq = seq + 1
    return f"{coin_type.inventory_prefix}-{seq:05d}"


def next_collection_number(db: Session, user_id: int, coin_type: CoinType, finish: str) -> int:
    counter = db.get(CollectionCounter, (user_id, coin_type.id, finish))
    if counter is None:
        counter = CollectionCounter(user_id=user_id, coin_type_id=coin_type.id, finish=finish, next_number=1)
        db.add(counter)
    n = counter.next_number
    counter.next_number = n + 1
    return n


def _cert_key(cert: str | None) -> str:
    return re.sub(r"[^0-9A-Z]", "", (cert or "").upper())


def find_duplicate_cert(
    db: Session, user_id: int, service: str, cert: str | None, exclude_coin_id: int | None = None
) -> Coin | None:
    """Another on-hand coin of this user with the same grading service + cert. Sold coins don't count
    (you can buy a coin back)."""
    key = _cert_key(cert)
    if not key or service == "RAW":
        return None
    candidates = db.scalars(
        on_hand(select(Coin).where(Coin.user_id == user_id, Coin.grading_service == service, Coin.cert_number.is_not(None)))
    ).all()
    return next((c for c in candidates if c.id != exclude_coin_id and _cert_key(c.cert_number) == key), None)


def duplicate_info(coin: Coin) -> dict:
    return {
        "inventory_number": coin.inventory_number,
        "description": f"{coin.year}{'' if coin.mint_mark == 'P' else '-' + coin.mint_mark} "
        f"{coin.grade_prefix or ''}{coin.grade or ''}".strip(),
        "collection_name": coin.collection.name,
        "coin_type_slug": coin.coin_type.slug,
        "collection_type_slug": collection_type_slug(coin.coin_type.slug, coin.collection.finish),
        "collection_number": coin.collection.number,
    }


def photo_url(photo_id: int) -> str:
    return f"/api/photos/{photo_id}"


def latest_quote(coin: Coin, source: str = CPG) -> PriceQuote | None:
    # price_quotes relationship is ordered newest first
    return next((q for q in coin.price_quotes if q.source == source), None)


def coin_out(coin: Coin) -> CoinOut:
    out = CoinOut.model_validate(coin)
    q = latest_quote(coin)
    out.latest_cpg = PriceQuoteOut.model_validate(q) if q else None
    g = latest_quote(coin, GREYSHEET)
    out.latest_greysheet = PriceQuoteOut.model_validate(g) if g else None
    out.photo_count = len(coin.photos)
    out.thumbnail_url = photo_url(coin.photos[0].id) if coin.photos else None
    out.coin_type_slug = coin.coin_type.slug
    out.collection_number = coin.collection.number
    out.collection_type_slug = collection_type_slug(coin.coin_type.slug, coin.collection.finish)
    out.finish = coin.collection.finish
    return out


def coin_detail(coin: Coin) -> CoinDetail:
    base = coin_out(coin).model_dump()
    return CoinDetail(
        **base,
        photos=[
            PhotoOut(id=p.id, sort_order=p.sort_order, source=p.source, url=photo_url(p.id))
            for p in coin.photos
        ],
        price_quotes=[PriceQuoteOut.model_validate(q) for q in coin.price_quotes],
        collection_name=coin.collection.name,
        pcgs_market=coin.pcgs_market,
    )


def on_hand(query):
    return query.where(Coin.sale_date.is_(None), Coin.sale_price.is_(None))


def sold(query):
    return query.where((Coin.sale_date.is_not(None)) | (Coin.sale_price.is_not(None)))


def collection_summary(db: Session, collection_id: int) -> CollectionSummary:
    coins = db.scalars(
        on_hand(select(Coin).where(Coin.collection_id == collection_id)).options(
            selectinload(Coin.price_quotes)
        )
    ).all()
    total_paid = sum((c.price_paid or Decimal(0) for c in coins), Decimal(0))
    total_cpg = Decimal(0)
    unpriced = 0
    for c in coins:
        q = latest_quote(c)
        if q is None or q.value is None:
            unpriced += 1
        else:
            total_cpg += q.value
    discount = Decimal(str(get_settings().wholesale_discount))
    return CollectionSummary(
        coin_count=len(coins),
        total_price_paid=total_paid.quantize(CENTS),
        total_cpg_value=total_cpg.quantize(CENTS),
        est_wholesale_value=(total_cpg * (1 - discount)).quantize(CENTS),
        unpriced_count=unpriced,
    )
