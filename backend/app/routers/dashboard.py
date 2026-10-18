"""Dashboard: totals across all collections, recent collections and sales, and quick coin search."""

import re
from datetime import datetime, date
from decimal import Decimal

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from ..auth import current_user
from ..db import get_db
from ..models import Coin, Collection, User
from ..schemas import CoinOut, CollectionWithSummary
from ..services.coins import CENTS, CPG, coin_out, on_hand, sold, value_totals
from ..services import price_archive
from ..services.history import value_history
from .collections import _type_label, _with_summary, get_owned_collection

router = APIRouter(prefix="/api", tags=["dashboard"])


class Totals(BaseModel):
    coin_count: int
    collection_count: int
    total_price_paid: Decimal
    total_estimated_value: Decimal
    total_cpg_value: Decimal
    est_wholesale_value: Decimal
    unpriced_count: int
    toner_count: int = 0
    toner_premium_total: Decimal = Decimal(0)
    holder_count: int = 0
    holder_premium_total: Decimal = Decimal(0)
    lowball_count: int = 0
    lowball_premium_total: Decimal = Decimal(0)
    custom_count: int = 0


class SaleCard(BaseModel):
    coin: CoinOut
    collection_name: str
    collection_type_label: str
    profit: Decimal | None


class Mover(BaseModel):
    coin: CoinOut
    old: Decimal
    new: Decimal
    change: Decimal
    pct: float
    changed_on: datetime


class DashboardOut(BaseModel):
    totals: Totals
    recent_collections: list[CollectionWithSummary]
    recent_sales: list[SaleCard]
    gainers: list[Mover] = []
    decliners: list[Mover] = []
    # Grading Tracker cards: still out first (longest waiting first), then the latest ones back.
    submissions: list[dict] = []


MOVERS = 5


def _movers(coins) -> tuple[list[Mover], list[Mover]]:
    """Coins whose CPG changed most at their latest price change (from saved history: no API calls)."""
    moves = []
    for c in coins:
        cpg = [q for q in c.price_quotes if q.source == CPG and q.value is not None]  # newest first
        if not cpg:
            continue
        latest = cpg[0]
        # The market's move only: compare prices for the same grade (a regrade or a new CAC sticker changes the
        # grade priced, not the market).
        prev = None
        for q in cpg[1:]:
            if q.grade_used != latest.grade_used:
                break
            if q.value != latest.value:
                prev = q
                break
        if prev is None or not prev.value:
            continue
        change = latest.value - prev.value
        moves.append(Mover(coin=coin_out(c), old=prev.value, new=latest.value, change=change,
                           pct=round(float(change / prev.value) * 100, 1), changed_on=latest.fetched_at))
    up = sorted((m for m in moves if m.change > 0), key=lambda m: -m.change)[:MOVERS]
    down = sorted((m for m in moves if m.change < 0), key=lambda m: m.change)[:MOVERS]
    return up, down


def _coins(user: User):
    return select(Coin).where(Coin.user_id == user.id).options(
        selectinload(Coin.photos), selectinload(Coin.price_quotes), selectinload(Coin.collection)
    )


@router.get("/dashboard", response_model=DashboardOut)
def dashboard(db: Session = Depends(get_db), user: User = Depends(current_user)):
    held = db.scalars(on_hand(_coins(user))).all()
    paid = sum((c.price_paid or Decimal(0) for c in held), Decimal(0))
    values = value_totals(held)

    cols = db.scalars(select(Collection).where(Collection.user_id == user.id)).all()
    # Most recently opened first; never-opened ones after, newest first.
    cols = sorted(cols, key=lambda c: (c.last_viewed_at is None, -(c.last_viewed_at or c.created_at).timestamp()))

    # Newest sale first (by sale date; coins without one by when they were last edited).
    gone = db.scalars(sold(_coins(user))).all()
    gone = sorted(gone, key=lambda c: (c.sale_date or c.updated_at.date(), c.updated_at), reverse=True)
    up, down = _movers(held)
    from . import grading as grading_router  # its helpers order and summarize submissions

    subs = grading_router.ordered(list(db.scalars(grading_router._query(user)).all()))
    today = date.today()

    return DashboardOut(
        totals=Totals(
            coin_count=len(held),
            collection_count=len(cols),
            total_price_paid=paid.quantize(CENTS),
            **values,
        ),
        recent_collections=[_with_summary(db, c) for c in cols[:20]],
        gainers=up,
        decliners=down,
        recent_sales=[
            SaleCard(
                coin=coin_out(c),
                collection_name=c.collection.name,
                collection_type_label=_type_label(c.coin_type, c.collection.finish),
                profit=(c.sale_price - c.price_paid) if c.sale_price is not None and c.price_paid is not None else None,
            )
            for c in gone[:20]
        ],
        submissions=[grading_router._summary(x, today) for x in subs[:20]],
    )


# ---- Value over time ----------------------------------------------------------------------


@router.get("/history")
def history(
    collection_id: int | None = None, db: Session = Depends(get_db), user: User = Depends(current_user)
):
    """Cost and estimated value over time, for one collection or everything."""
    if collection_id is not None:
        get_owned_collection(db, user, collection_id)
    return value_history(db, user.id, collection_id)


# ---- Quick search -------------------------------------------------------------------------

class SearchHit(BaseModel):
    coin: CoinOut
    type_name: str
    collection_name: str


_DATE_MINT = re.compile(r"^(1[789]\d\d|20\d\d)(?:[-\s]?(cc|o|s|d|p|w))?$", re.I)


def _norm(s: str | None) -> str:
    return re.sub(r"[^0-9a-z]", "", (s or "").lower())


def _score(coin: Coin, query: str) -> int:
    """0 = no match. Every word of the query must match something about the coin."""
    q = query.strip()
    nq = _norm(q)
    if not nq:
        return 0
    inv, cert = _norm(coin.inventory_number), _norm(coin.cert_number)
    # Whole-query matches on identifiers rank highest.
    if nq == inv:
        return 1000
    if cert and nq == cert:
        return 950
    if len(nq) >= 4 and cert.startswith(nq):
        return 700
    if len(nq) >= 3 and inv.startswith(nq):
        return 650
    if len(nq) >= 3 and (nq in inv or (len(nq) >= 5 and nq in cert)):
        return 500

    m = _DATE_MINT.match(q.replace(" ", "")) or _DATE_MINT.match(q)
    if m:
        year, mint = int(m.group(1)), (m.group(2) or "").upper()
        if coin.year == year and (not mint or coin.mint_mark == mint):
            return 400 if mint else 300
        return 0

    text = " ".join(
        str(v)
        for v in (
            f"{coin.year}-{coin.mint_mark}",
            coin.year,
            coin.variety,
            coin.vam,
            coin.grading_service,
            coin.other_service,
            f"{coin.grade_prefix or ''}{coin.grade or ''}",
            coin.strike_designation,
            coin.purchased_from,
            coin.sold_to,
            coin.notes,
            coin.coin_type.name,
            coin.collection.name,
            "cac" if coin.cac else "",
            "raw" if coin.grading_service == "RAW" else "",
        )
        if v
    ).lower()
    words = [w for w in re.split(r"\s+", q.lower()) if w]
    if all(w in text for w in words):
        return 100 + 10 * len(words)
    return 0


@router.get("/search/coins", response_model=list[SearchHit])
def search_coins(
    q: str = Query(..., min_length=1, max_length=100),
    limit: int = Query(8, ge=1, le=25),
    db: Session = Depends(get_db),
    user: User = Depends(current_user),
):
    coins = db.scalars(_coins(user).options(selectinload(Coin.coin_type))).all()
    scored = [(s, c) for c in coins if (s := _score(c, q)) > 0]
    # Best match first; coins on hand before sold ones; then by date.
    scored.sort(key=lambda sc: (-sc[0], sc[1].is_sold, sc[1].year, sc[1].inventory_number))
    return [
        SearchHit(coin=coin_out(c), type_name=c.coin_type.name, collection_name=c.collection.name)
        for _, c in scored[:limit]
    ]


@router.get("/price-data")
def price_data(db: Session = Depends(get_db), _: User = Depends(current_user)):
    """How much price history TrackMyCoins has collected (shared by everyone), and the database size."""
    return price_archive.stats(db)
