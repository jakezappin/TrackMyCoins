"""Precious Metals page: spot prices and how they've moved, the gold/silver ratio, melt values of U.S. coins and the
metal in the user's own bullion and coins. Spot comes from gold-api.com (cached); history from the daily prices the
app keeps (bundled back to 2000, topped up while it runs)."""

import math
import statistics
from datetime import date, datetime, timedelta, timezone
from typing import Literal

from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from ..auth import current_user
from ..db import get_db
from ..models import BullionItem, Coin, SpotPrice, User
from ..services import bullion, melt_table, metals, set_melt
from ..services.coins import on_hand

router = APIRouter(prefix="/api/metals", tags=["metals"])

PRECIOUS = ("gold", "silver", "platinum", "palladium")
RATIO_YEARS = 25  # the gold/silver ratio is judged against its average over this many years
RANGES = {"1w": 8, "1m": 31, "6m": 183, "1y": 366, "5y": 5 * 366, "10y": 10 * 366, "all": None}
MAX_POINTS = 400


def _today() -> date:
    return datetime.now(timezone.utc).date()


def _series(db: Session, metal: str) -> list[tuple[date, float]]:
    rows = db.execute(select(SpotPrice.day, SpotPrice.price).where(SpotPrice.metal == metal).order_by(SpotPrice.day))
    return [(d, float(p)) for d, p in rows]


def _on(series: list[tuple[date, float]], day: date) -> float | None:
    """The latest price on or before `day` (within a week: weekends and holidays have none)."""
    lo, hi = 0, len(series)
    while lo < hi:
        mid = (lo + hi) // 2
        if series[mid][0] <= day:
            lo = mid + 1
        else:
            hi = mid
    if lo == 0 or (day - series[lo - 1][0]).days > bullion.SPOT_GAP_DAYS:
        return None
    return series[lo - 1][1]


def _pct(now: float | None, then: float | None) -> float | None:
    return round((now - then) / then * 100, 2) if now is not None and then else None


def _spot_card(metal: str, series: list[tuple[date, float]], today: date) -> dict:
    price, as_of = metals.spot(metal)
    now = price if price is not None else (series[-1][1] if series else None)
    # Daily change: against the previous trading day's close. Markets close for the weekend, so on a Saturday or
    # Sunday it's Friday's move (Friday vs Thursday), not a flat $0.00.
    last_trading = today - timedelta(days=max(0, today.weekday() - 4))
    before = [(d, p) for d, p in series if d < last_trading and d.weekday() < 5]
    prev_day, prev = before[-1] if before else (None, None)
    year = [p for d, p in series if d > today - timedelta(days=365)] + ([price] if price is not None else [])
    changes = {
        label: _pct(now, _on(series, day))
        for label, day in (("1w", today - timedelta(days=7)), ("1m", today - timedelta(days=30)),
                           ("ytd", date(today.year - 1, 12, 31)), ("1y", today - timedelta(days=365)))
    }
    return {
        "metal": metal,
        "price": round(now, 2) if now is not None else None,
        "live": price is not None,
        "as_of": as_of,
        "prev_close": round(prev, 2) if prev is not None else None,
        "prev_day": prev_day,
        "market_closed": today.weekday() >= 5,
        "change": round(now - prev, 2) if now is not None and prev is not None else None,
        "change_pct": _pct(now, prev),
        "changes": changes,
        "high_52w": round(max(year), 2) if year else None,
        "low_52w": round(min(year), 2) if year else None,
    }


def _ratio(gold: list[tuple[date, float]], silver: list[tuple[date, float]], g_now, s_now, today: date) -> dict:
    """Gold/silver ratio now, against its long-run average: well above it, silver is cheap next to gold (a time to
    trade gold for silver); well below it, gold is the cheap one."""
    silver_by_day = dict(silver)
    since = today - timedelta(days=365 * RATIO_YEARS)
    hist = [g / silver_by_day[d] for d, g in gold if d >= since and silver_by_day.get(d)]
    now = g_now / s_now if g_now and s_now else (hist[-1] if hist else None)
    if not hist or now is None:
        return {"value": round(now, 2) if now else None, "signal": None}
    mean, sd = statistics.fmean(hist), statistics.pstdev(hist)
    high, low = mean + sd, mean - sd
    signal = "trade_gold" if now >= high else "trade_silver" if now <= low else "neutral"
    below = sum(1 for r in hist if r < now)
    return {
        "value": round(now, 2),
        "signal": signal,  # trade_gold: trade gold for silver | trade_silver: silver for gold | neutral
        "average": round(mean, 2),
        "high": round(high, 2),
        "low": round(low, 2),
        "years": RATIO_YEARS,
        "percentile": round(below / len(hist) * 100),
        "min": round(min(hist), 2),
        "max": round(max(hist), 2),
    }


def _melt_rows(prices: dict[str, float | None]) -> list[dict]:
    out = []
    for e in melt_table.ENTRIES:
        p = prices.get(e.metal)
        value = e.amount * p if p is not None else None
        out.append({
            "key": e.key, "group": e.group, "name": e.name, "years": e.years, "face": e.face, "metal": e.metal,
            "amount": e.amount, "unit": "lb" if e.metal == "copper" else "ozt", "composition": e.composition,
            "melt": round(value, 4 if value is not None and value < 1 else 2) if value is not None else None,
            "x_face": round(value / e.face, 2) if value is not None and e.face else None,
        })
    return out


def _holdings(db: Session, user: User, prices: dict[str, float | None]) -> dict:
    """Pure metal the user holds: bullion on hand, and the precious metal in their coins (by series and date)."""
    oz_bullion: dict[str, float] = {}
    items = db.scalars(
        select(BullionItem).where(BullionItem.user_id == user.id).options(selectinload(BullionItem.collection))
    ).all()
    for i in items:
        if bullion.is_sold(i):
            continue
        m = i.collection.metal
        oz_bullion[m] = oz_bullion.get(m, 0.0) + float(bullion.pure_oz(i))
    oz_coins: dict[str, float] = {}
    counted = 0
    coins = db.scalars(on_hand(select(Coin).where(Coin.user_id == user.id)).options(
        selectinload(Coin.coin_type), selectinload(Coin.collection))).all()
    for c in coins:
        slug, finish = c.coin_type.slug, c.collection.finish
        e = melt_table.entry_for(slug, c.year, finish, c.mint_mark)
        if e is not None and e.metal in PRECIOUS:
            oz_coins[e.metal] = oz_coins.get(e.metal, 0.0) + e.amount
            counted += 1
            continue
        oz = set_melt.silver_oz(slug, c.year, c.variety)
        if oz:
            oz_coins["silver"] = oz_coins.get("silver", 0.0) + oz
            counted += 1
    metals_ = []
    for m in PRECIOUS:
        b, k = oz_bullion.get(m, 0.0), oz_coins.get(m, 0.0)
        if not b and not k:
            continue
        p = prices.get(m)
        metals_.append({"metal": m, "bullion_oz": round(b, 4), "coin_oz": round(k, 4), "oz": round(b + k, 4),
                        "value": round((b + k) * p, 2) if p is not None else None})
    return {"metals": metals_, "coins_counted": counted, "coins_total": len(coins)}


@router.get("")
def overview(db: Session = Depends(get_db), user: User = Depends(current_user)):
    today = _today()
    series = {m: _series(db, m) for m in PRECIOUS}
    cards = [_spot_card(m, series[m], today) for m in PRECIOUS]
    prices = {c["metal"]: c["price"] for c in cards}
    copper, copper_as_of = metals.spot("copper")
    prices["copper"] = copper
    return {
        "spot": cards,
        "copper": {"price": round(copper, 4) if copper is not None else None, "as_of": copper_as_of},
        "ratio": _ratio(series["gold"], series["silver"], prices["gold"], prices["silver"], today),
        "coins": _melt_rows(prices),
        "junk_oz_per_dollar": melt_table.JUNK_OZ_PER_DOLLAR,
        "holdings": _holdings(db, user, prices),
    }


@router.get("/history")
def history(
    series: Literal["gold", "silver", "platinum", "palladium", "ratio"] = "gold",
    range: Literal["1w", "1m", "6m", "1y", "5y", "10y", "all"] = "1y",
    db: Session = Depends(get_db),
    _: User = Depends(current_user),
):
    """Daily prices (or the gold/silver ratio) over a range, thinned to at most MAX_POINTS points; today's live
    price ends the line."""
    today = _today()
    days = RANGES[range]
    since = today - timedelta(days=days) if days else date.min
    if series == "ratio":
        gold, silver = _series(db, "gold"), dict(_series(db, "silver"))
        points = [(d, g / silver[d]) for d, g in gold if d >= since and silver.get(d)]
        g, s = metals.spot("gold")[0], metals.spot("silver")[0]
        live = g / s if g and s else None
    else:
        points = [(d, p) for d, p in _series(db, series) if d >= since]
        live = metals.spot(series)[0]
    if live is not None:
        points = [p for p in points if p[0] < today] + [(today, live)]
    step = max(1, math.ceil(len(points) / MAX_POINTS))
    thinned = points[::step]
    if points and thinned[-1] != points[-1]:
        thinned.append(points[-1])
    return [{"date": d.isoformat(), "value": round(v, 4 if series == "ratio" else 2)} for d, v in thinned]

