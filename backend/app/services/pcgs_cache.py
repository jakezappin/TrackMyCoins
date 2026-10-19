"""Lasting store of PCGS answers (PCGS allows 100 calls a day, so nothing is asked twice). A cert's lookup is kept
for good; an issue and grade's Price Guide and auctions for a week. Its own session, like the quota counters."""

from datetime import datetime, timedelta, timezone

from ..db import SessionLocal
from ..models import PcgsCache

MARKET_DAYS = 7


def get(key: str, max_age: timedelta | None = None) -> dict | None:
    """The stored answer, or None when there's none (or it's older than `max_age`)."""
    with SessionLocal() as db:
        row = db.get(PcgsCache, key)
        if row is None:
            return None
        at = row.fetched_at if row.fetched_at.tzinfo else row.fetched_at.replace(tzinfo=timezone.utc)
        if max_age is not None and datetime.now(timezone.utc) - at > max_age:
            return None
        return row.data


def put(key: str, data: dict) -> None:
    with SessionLocal() as db:
        row = db.get(PcgsCache, key) or PcgsCache(key=key)
        row.data = data
        row.fetched_at = datetime.now(timezone.utc)
        db.add(row)
        db.commit()


def cert_key(cert: str) -> str:
    return f"cert:{cert}"


def market_key(pcgs_number: str, grade: int, plus: bool) -> str:
    return f"market:{pcgs_number}|{int(grade)}|{int(bool(plus))}"
