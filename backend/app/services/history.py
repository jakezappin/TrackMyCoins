"""Collection value over time, rebuilt from data already stored: price history, purchase and sale dates.

At each date where something changed, a coin counts if it had been bought (purchase date, or the day it was
added) and not yet sold. Its value is its latest estimate as of that day: a CPG price, a "CPG + premiums"
estimate or the owner's own value, whichever was recorded most recently.

Before a coin's first estimate was recorded, the value runs from its estimated value at purchase (see
purchase_value.py) to that first estimate. Where the auction archive has sales of the issue and grade around
those dates, the line follows the market's ups and downs, scaled so it still starts and ends at those two values;
otherwise it's a straight line. Without a value at purchase, the first estimate stands in. Those points are marked
"backfilled" (the chart draws them dashed). There's a point at the start of every month so the shape shows.
"""

from datetime import date, datetime, timedelta, timezone
from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from ..models import Coin
from . import price_archive, purchase_value
from .coins import CENTS, CPG, CUSTOM, PREMIUM

MARKET_WINDOW_MONTHS = 6  # sales this close to a date describe the market then

VALUE_SOURCES = {CPG, PREMIUM, CUSTOM}


def _day(dt: datetime | date | None) -> date | None:
    if dt is None:
        return None
    if isinstance(dt, datetime):
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt.date()
    return dt


def value_history(db: Session, user_id: int, collection_id: int | None = None, coin_id: int | None = None) -> list[dict]:
    q = select(Coin).where(Coin.user_id == user_id).options(selectinload(Coin.price_quotes))
    if collection_id is not None:
        q = q.where(Coin.collection_id == collection_id)
    if coin_id is not None:
        q = q.where(Coin.id == coin_id)
    coins = db.scalars(q).all()

    # Per coin: when it was held, and its value estimates in time order.
    held, estimates, at_purchase = {}, {}, {}
    sales: dict[tuple, list] = {}  # archived auction sales per issue and grade
    market_key: dict[int, tuple] = {}
    market_cache: dict[tuple, Decimal | None] = {}

    def market(c_id: int, d: date) -> Decimal | None:
        """Average auction price of the coin's issue and grade around a date, or None without sales then."""
        key = market_key.get(c_id)
        if key is None:
            return None
        if (key, d) not in market_cache:
            got = purchase_value.average_near(sales[key], d, MARKET_WINDOW_MONTHS)
            market_cache[(key, d)] = got[0] if got else None
        return market_cache[(key, d)]
    days: set[date] = set()
    for c in coins:
        start = c.purchase_date or _day(c.created_at)
        end = c.sale_date  # sold on this day: no longer held from then on
        held[c.id] = (start, end)
        days.add(start)
        if end:
            days.add(end)
        quotes = sorted(
            (q for q in c.price_quotes if q.source in VALUE_SOURCES and q.value is not None),
            key=lambda q: (q.fetched_at, q.id),
        )
        estimates[c.id] = [(_day(q.fetched_at), q.value) for q in quotes]
        days.update(d for d, _ in estimates[c.id])
        if estimates[c.id] and estimates[c.id][0][0] > start:
            at_purchase[c.id] = purchase_value.estimate(db, c).value
            if c.pcgs_number and c.grade:
                key = (str(c.pcgs_number), int(c.grade), bool(c.grade_plus))
                if key not in sales:
                    sales[key] = price_archive.sales_for(db, *key, cac=False)  # the market's shape: plain sales
                market_key[c.id] = key
    if not coins:
        return []
    today = datetime.now(timezone.utc).date()
    days.add(today)
    # The first of every month, so lines that follow the market show their shape.
    m = min(days).replace(day=1)
    while m < today:
        if m > min(days):
            days.add(m)
        m = (m + timedelta(days=32)).replace(day=1)

    points = []
    for d in sorted(days):
        cost = value = Decimal(0)
        count = priced = 0
        backfilled = False
        for c in coins:
            start, end = held[c.id]
            if start > d or (end is not None and end <= d):
                continue
            count += 1
            cost += c.price_paid or 0
            latest = None
            for qd, v in estimates[c.id]:
                if qd <= d:
                    latest = v
                else:
                    break
            if latest is None and estimates[c.id]:
                # Not priced yet on this day: on the line from its value at purchase to its first estimate.
                first_day, first = estimates[c.id][0]
                pv = at_purchase.get(c.id)
                if pv is not None and first_day > start:
                    share = Decimal((d - start).days) / Decimal((first_day - start).days)
                    m0, m1, md = market(c.id, start), market(c.id, first_day), market(c.id, d)
                    if m0 and m1 and md:
                        # The market's shape, scaled to meet the value at purchase and the first estimate.
                        k0, k1 = pv / m0, first / m1
                        latest = md * (k0 + (k1 - k0) * share)
                    else:
                        latest = pv + (first - pv) * share
                else:
                    latest = first
                backfilled = True
            if latest is not None:
                value += latest
                priced += 1
        points.append(
            {
                "date": d.isoformat(),
                "coin_count": count,
                "priced_count": priced,
                "cost": str(cost.quantize(CENTS)),
                "value": str(value.quantize(CENTS)) if priced else None,
                "backfilled": backfilled,
            }
        )
    return points
