"""Collection value over time, rebuilt from data already stored: price history, purchase and sale dates.

At each date where something changed, a coin counts if it had been bought (purchase date, or the day it was
added) and not yet sold. Its value is its latest estimate as of that day: a CPG price, a "CPG + premiums"
estimate or the owner's own value, whichever was recorded most recently.
"""

from datetime import date, datetime, timezone
from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from ..models import Coin
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
    held, estimates = {}, {}
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
    if not coins:
        return []
    days.add(datetime.now(timezone.utc).date())

    points = []
    for d in sorted(days):
        cost = value = Decimal(0)
        count = priced = 0
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
            }
        )
    return points
