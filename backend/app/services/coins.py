"""Shared helpers for coins: inventory numbers, serialization and collection totals."""

import re
from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.orm import Session, object_session, selectinload

from ..config import get_settings
from ..models import Coin, CoinType, CollectionCounter, InventoryCounter, PriceQuote
from ..series import collection_type_slug
from ..schemas import CoinDetail, CoinFacts, CoinOut, CollectionSummary, PhotoOut, PriceQuoteOut, PurchaseValue
from . import details, metals
from .lookups.pcgs import coin_facts as pcgs_specs

CPG = "CPG"
PREMIUM = "PREMIUM"  # CPG + toner and/or holder premium, recorded as an estimate
CUSTOM = "CUSTOM"  # a value the owner entered themselves
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
    # "012345678" and "12345678" are the same cert.
    return re.sub(r"[^0-9A-Z]", "", (cert or "").upper()).lstrip("0")


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


def latest_cpg_value(coin: Coin) -> Decimal | None:
    q = latest_quote(coin)
    return q.value if q else None


def coin_melt(coin: Coin) -> Decimal | None:
    facts = _facts(coin)
    m = metals.melt(facts.weight_g, facts.metal) if facts else None
    return Decimal(str(m["value"])).quantize(CENTS) if m else None


def market_value(coin: Coin) -> Decimal | None:
    """Latest CPG, made into this coin's value: a Details coin gets its share of the straight-grade CPG
    (never below melt)."""
    cpg = latest_cpg_value(coin)
    if cpg is None or not coin.details:
        return cpg
    return details.adjust(coin, cpg, coin_melt(coin))


def details_basis(coin: Coin) -> str | None:
    if not coin.details:
        return None
    cpg = latest_cpg_value(coin)
    melt = coin_melt(coin)
    plain = details.adjust(coin, cpg) if cpg is not None else None
    return details.basis(coin, melt_used=plain is not None and melt is not None and melt > plain)


def value_estimate(coin: Coin) -> Decimal | None:
    """The coin's estimated value for totals: the owner's own value, or latest CPG (a share of it for a Details
    coin) plus any premiums."""
    if coin.value_source == "custom":
        return coin.custom_value
    base = market_value(coin)
    if base is None:
        return None
    return base + (coin.toner_premium or Decimal(0)) + (coin.holder_premium or Decimal(0))


def value_totals(coins) -> dict:
    """Totals used by collection and dashboard cards."""
    est = cpg = toner = holder = Decimal(0)
    unpriced = toner_count = holder_count = custom_count = 0
    for c in coins:
        v = value_estimate(c)
        if v is None:
            unpriced += 1
            continue
        est += v
        if c.value_source == "custom":
            custom_count += 1
        else:
            cpg += market_value(c) or 0
            if c.toner_premium:
                toner += c.toner_premium
                toner_count += 1
            if c.holder_premium:
                holder += c.holder_premium
                holder_count += 1
    discount = Decimal(str(get_settings().wholesale_discount))
    return dict(
        total_estimated_value=est.quantize(CENTS),
        total_cpg_value=cpg.quantize(CENTS),
        est_wholesale_value=(est * (1 - discount)).quantize(CENTS),
        unpriced_count=unpriced,
        toner_count=toner_count,
        toner_premium_total=toner.quantize(CENTS),
        holder_count=holder_count,
        holder_premium_total=holder.quantize(CENTS),
        custom_count=custom_count,
    )


def coin_out(coin: Coin) -> CoinOut:
    out = CoinOut.model_validate(coin)
    out.value_estimate = value_estimate(coin)
    out.details_basis = details_basis(coin)
    out.details_value = market_value(coin) if coin.details else None
    if coin.location == "grading" and (db := object_session(coin)) is not None:
        from . import grading  # it uses this module's neighbours

        out.grading = grading.current(db, coin)
    q = latest_quote(coin)
    out.latest_cpg = PriceQuoteOut.model_validate(q) if q else None
    g = latest_quote(coin, GREYSHEET)
    out.latest_greysheet = PriceQuoteOut.model_validate(g) if g else None
    out.photo_count = len(coin.photos)
    out.thumbnail_url = f"{photo_url(coin.photos[0].id)}?size=thumb" if coin.photos else None
    out.coin_type_slug = coin.coin_type.slug
    out.collection_number = coin.collection.number
    out.collection_type_slug = collection_type_slug(coin.coin_type.slug, coin.collection.finish)
    out.finish = coin.collection.finish
    return out


def coin_facts(coin: Coin) -> CoinFacts | None:
    """Mintage, specs and population: from the PCGS market data if fetched, else from a PCGS cert lookup."""
    facts = _facts(coin)
    if facts is not None:
        facts.melt = metals.melt(facts.weight_g, facts.metal)
    return facts


def _facts(coin: Coin) -> CoinFacts | None:
    m = coin.pcgs_market or {}
    if m.get("facts"):
        return CoinFacts(**m["facts"], population=m.get("population"), pop_higher=m.get("pop_higher"),
                         pop_grade=m.get("grade"), as_of=m.get("fetched_at"), source="pcgs_market",
                         pcgs_number=m.get("pcgs_number"))
    raw = coin.lookup_raw or {}
    if raw.get("PCGSNo") and (raw.get("Mintage") or raw.get("Population")):
        pop = raw.get("Population")
        return CoinFacts(**pcgs_specs(raw), population=pop if isinstance(pop, int) else None,
                         pop_higher=raw.get("PopHigher") if isinstance(raw.get("PopHigher"), int) else None,
                         pop_grade=raw.get("Grade") or None, as_of=coin.created_at, source="cert_lookup",
                         pcgs_number=str(raw.get("PCGSNo")))
    return None


def coin_detail(coin: Coin) -> CoinDetail:
    base = coin_out(coin).model_dump()
    return CoinDetail(
        **base,
        photos=[
            PhotoOut(id=p.id, sort_order=p.sort_order, source=p.source, url=photo_url(p.id),
                     thumb_url=f"{photo_url(p.id)}?size=thumb")
            for p in coin.photos
        ],
        price_quotes=[PriceQuoteOut.model_validate(q) for q in coin.price_quotes],
        collection_name=coin.collection.name,
        pcgs_market=coin.pcgs_market,
        facts=coin_facts(coin),
        purchase_value=_purchase_value(coin),
        set_melt=_set_melt(coin),
        grading_history=_grading_history(coin),
    )


def _grading_history(coin: Coin) -> list[dict]:
    from . import grading

    db = object_session(coin)
    return grading.history_for(db, coin) if db is not None else []


def _set_melt(coin: Coin) -> dict | None:
    from ..series import BY_SLUG
    from . import set_melt

    s = BY_SLUG.get(coin.coin_type.slug)
    return set_melt.melt(s.slug, coin.year, coin.variety) if s and s.is_set else None


def _purchase_value(coin: Coin) -> PurchaseValue | None:
    from . import purchase_value  # it uses this module

    db = object_session(coin)
    if db is None:
        return None
    e = purchase_value.estimate(db, coin)
    return PurchaseValue(value=e.value, source=e.source, detail=e.detail, pending=e.pending)


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
    return CollectionSummary(coin_count=len(coins), total_price_paid=total_paid.quantize(CENTS), **value_totals(coins))
