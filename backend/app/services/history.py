"""Collection value over time, rebuilt from data already stored: price history, purchase and sale dates.

At each date where something changed, a coin counts if it had been bought (purchase date, or the day it was
added) and not yet sold. Its value is its latest estimate as of that day: a CPG price, a "CPG + premiums"
estimate or the owner's own value, whichever was recorded most recently.

Before a coin's first estimate was recorded, the value runs in a straight line from its estimated value at
purchase (see purchase_value.py) to that first estimate; without a value at purchase, the first estimate stands
in. Those points are marked "backfilled" (the chart draws them dashed). Without this, a collection priced for the
first time today would have a value on one day only, and no line.
"""

from datetime import date, datetime, timezone
from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from ..models import Coin
from . import purchase_value
from .coins import CENTS, CPG, CUSTOM, PREMIUM

VALUE_SOURCES = {CPG, PREMIUM, CUSTOM}


def _day(dt: datetime | date | None) -> date | None:
    if dt is None:
        return None
    if isinstance(dt, datetime):
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt.date()
    return dt


def value_history(db: Session, user_id: int, collection_id: int | None = None) -> list[dict]:
    q = select(Coin).where(Coin.user_id == user_id).options(selectinload(Coin.price_quotes))
    if collection_id is not None:
        q = q.where(Coin.collection_id == collection_id)
    coins = db.scalars(q).all()

    # Per coin: when it was held, and its value estimates in time order.
    held, estimates, at_purchase = {}, {}, {}
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
    if not coins:
        return []
    days.add(datetime.now(timezone.utc).date())

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
