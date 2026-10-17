"""Estimated value at purchase: what a coin was worth when it was bought.

In order of preference:
1. The owner's own figure.
2. The coin's own CPG, if one was recorded within 2 months of the purchase (a recent purchase priced now).
3. CPG from the app's own price history (every price sheet fetched is kept), if it covers the purchase date.
   It starts empty, so this takes over gradually as the history grows.
4. The average of up to 10 PCGS auction sales of the issue and grade nearest the purchase date (within a year).
   PCGS only returns about 3 years of sales, so the result is saved on the coin once worked out.
5. The price paid.

The purchase date is the day the coin was added if none was entered.
"""

import time
from dataclasses import dataclass
from datetime import date, datetime, timedelta, timezone
from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.orm import Session

from ..models import Coin, CpgHistory
from . import quota
from .coins import CENTS, CPG
from .lookups import pcgs

RECENT = timedelta(days=61)  # "within 2 months" of the purchase
HISTORY_GAP = timedelta(days=61)  # a history price unconfirmed for longer than this before the purchase doesn't count
AUCTION_WINDOW_MONTHS = 12
AUCTION_SALES = 10


@dataclass
class Estimate:
    value: Decimal | None
    source: str | None  # custom | cpg | cpg_history | auctions | paid
    detail: str
    pending: bool = False  # auction sales not looked up yet (the coin page asks for them)


def _day(dt) -> date | None:
    if dt is None:
        return None
    if isinstance(dt, datetime):
        return (dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)).date()
    return dt


def purchase_day(coin: Coin) -> date:
    return coin.purchase_date or _day(coin.created_at) or date.today()


def auction_key(coin: Coin) -> str | None:
    """What an auction average depends on; None if the coin can't have one (no PCGS # or numeric grade)."""
    if not coin.pcgs_number or not coin.grade:
        return None
    return f"{coin.pcgs_number}|{coin.grade}|{int(bool(coin.grade_plus))}|{purchase_day(coin).isoformat()}"


def _fmt(d: date) -> str:
    return f"{d:%b} {d.day}, {d.year}"


def _month(ym: str) -> str:
    y, m = ym.split("-")
    return f"{date(int(y), int(m), 1):%b %Y}"


def _own_cpg(coin: Coin, start: date):
    near = [q for q in coin.price_quotes
            if q.source == CPG and q.value is not None and abs(_day(q.fetched_at) - start) <= RECENT]
    return min(near, key=lambda q: (abs(_day(q.fetched_at) - start), q.id), default=None)


def _history_cpg(db: Session, coin: Coin, start: date) -> CpgHistory | None:
    if not coin.grade:
        return None
    from .grade_prices import _key_for  # the coin's price-sheet keys (pcgs:N, gsid:N)

    for key in _key_for(coin):
        rows = db.scalars(select(CpgHistory).where(CpgHistory.key == key, CpgHistory.grade == coin.grade)).all()
        rows = [h for h in rows if ("+" in h.label) == bool(coin.grade_plus)] or []
        cac = [h for h in rows if h.cac]
        rows = cac if coin.cac and cac else [h for h in rows if not h.cac]
        before = [h for h in rows if _day(h.first_seen) <= start]
        if not before:
            continue  # the history starts after the purchase
        h = max(before, key=lambda h: h.first_seen)
        if start - _day(h.last_seen) <= HISTORY_GAP:
            return h
    return None


def estimate(db: Session, coin: Coin) -> Estimate:
    start = purchase_day(coin)
    if coin.purchase_value_custom is not None:
        return Estimate(coin.purchase_value_custom, "custom", "Your own value")
    q = _own_cpg(coin, start)
    if q is not None:
        return Estimate(q.value, "cpg", f"CPG on {_fmt(_day(q.fetched_at))}")
    h = _history_cpg(db, coin, start)
    if h is not None:
        return Estimate(h.value, "cpg_history", f"CPG as of {_fmt(_day(h.first_seen))} (TrackMyCoins price history)")
    key = auction_key(coin)
    pending = key is not None and coin.purchase_auction_key != key
    if not pending and coin.purchase_auction_value is not None:
        n = coin.purchase_auction_count or 0
        lo, _, hi = (coin.purchase_auction_span or "").partition("..")
        span = _month(lo) if lo == hi or not hi else f"{_month(lo)} – {_month(hi)}"
        return Estimate(coin.purchase_auction_value, "auctions",
                        f"Average of {n} PCGS auction sale{'s' if n != 1 else ''} at this grade, {span}")
    if coin.price_paid is not None:
        return Estimate(coin.price_paid, "paid", "Price paid", pending=pending)
    return Estimate(None, None, "", pending=pending)


# One PCGS call returns ~3 years of sales for an issue and grade; share it between coins for a day.
_sales_cache: dict[tuple, tuple[float, list[dict]]] = {}


def _sales(pcgs_number: str, grade: int, plus: bool, user_id: int) -> list[dict]:
    key = (pcgs_number, grade, plus)
    hit = _sales_cache.get(key)
    if hit and time.time() - hit[0] < 24 * 3600:
        return hit[1]
    quota.spend(user_id, "pcgs")
    params = {"PCGSNo": pcgs_number, "GradeNo": grade, "PlusGrade": "true" if plus else "false"}
    with pcgs._client() as c:
        apr = pcgs._get(c, "/coindetail/GetAPRByGrade", **params, NumberOfRecords=1000)
    sales = []
    for a in apr.get("Auctions") or []:
        ym = pcgs._sale_date(a.get("Date"))
        try:
            price = Decimal(str(a.get("Price")))
        except Exception:
            continue
        if ym and price > 0:
            sales.append((ym, price))
    _sales_cache[key] = (time.time(), sales)
    return sales


def _months_apart(ym: str, d: date) -> int:
    y, m = (int(x) for x in ym.split("-"))
    return (y - d.year) * 12 + (m - d.month)


def average_near(sales: list[tuple[str, Decimal]], start: date) -> tuple[Decimal, int, str] | None:
    """(average, count, "first..last" months) of up to 10 sales nearest the purchase month, within a year.
    Ties go to the sale before the purchase (what the market was then)."""
    near = [(abs(_months_apart(ym, start)), _months_apart(ym, start) > 0, ym, p) for ym, p in sales
            if abs(_months_apart(ym, start)) <= AUCTION_WINDOW_MONTHS]
    near.sort(key=lambda s: (s[0], s[1]))
    picked = near[:AUCTION_SALES]
    if not picked:
        return None
    avg = (sum(p for *_, p in picked) / len(picked)).quantize(CENTS)
    months = sorted(ym for _, _, ym, _ in picked)
    return avg, len(picked), f"{months[0]}..{months[-1]}"


def fill_auctions(coin: Coin, user_id: int) -> bool:
    """Look up and save the auction average if the coin needs one. Returns True if PCGS was asked.
    Raises quota.QuotaExceeded or pcgs.LookupError (the caller decides whether that matters)."""
    key = auction_key(coin)
    if key is None or coin.purchase_auction_key == key:
        return False
    sales = _sales(str(coin.pcgs_number), int(coin.grade), bool(coin.grade_plus), user_id)
    got = average_near(sales, purchase_day(coin))
    coin.purchase_auction_value, coin.purchase_auction_count, coin.purchase_auction_span = got or (None, 0, None)
    coin.purchase_auction_key = key
    return True


def needs_auctions(db: Session, coin: Coin) -> bool:
    """Whether the auction step would be reached and hasn't been worked out yet."""
    return estimate(db, coin).pending
