"""Estimated value at purchase: what a coin was worth when it was bought.

In order of preference:
1. The owner's own figure.
2. The coin's own CPG, if one was recorded within 2 months of the purchase (a recent purchase priced now).
3. The price paid.

Off for now (USE_HISTORY / USE_AUCTIONS), between 2 and 3: CPG from the app's own price history if it covers the
purchase date, then the average of up to 10 PCGS auction sales nearest the purchase date. PCGS allows only 100
calls a day; an auction source of our own (e.g. Heritage, Stack's Bowers) may replace it later.

The purchase date is the day the coin was added if none was entered.
"""

from dataclasses import dataclass
from datetime import date, datetime, timedelta, timezone
from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.orm import Session

from ..db import SessionLocal
from ..models import Coin, CpgHistory
from . import details, quota
from .coins import CENTS, CPG

RECENT = timedelta(days=61)  # "within 2 months" of the purchase
HISTORY_GAP = timedelta(days=61)  # a history price unconfirmed for longer than this before the purchase doesn't count
AUCTION_WINDOW_MONTHS = 12
AUCTION_SALES = 10
USE_HISTORY = False  # CPG from the app's price history (step off for now; see the module docstring)
USE_AUCTIONS = False  # PCGS auction sales


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


def _grade(coin: Coin) -> tuple[int | None, bool]:
    """(numeric grade, plus) prices are looked up at: a Details coin's straight-grade equivalent, no plus."""
    return details.price_grade(coin), bool(coin.grade_plus) and not getattr(coin, "details", False)


def auction_key(coin: Coin) -> str | None:
    """What an auction average depends on; None if the coin can't have one (no PCGS # or numeric grade)."""
    grade, plus = _grade(coin)
    if not coin.pcgs_number or not grade or getattr(coin, "is_error", False):
        return None
    return f"{coin.pcgs_number}|{grade}|{int(plus)}|{int(bool(coin.cac))}|{purchase_day(coin).isoformat()}"


def _fmt(d: date) -> str:
    return f"{d:%b} {d.day}, {d.year}"


def _month(ym: str) -> str:
    y, m = ym.split("-")
    return f"{date(int(y), int(m), 1):%b %Y}"


def _own_cpg(coin: Coin, start: date):
    # A quote added this session and not yet saved has no fetched_at yet: it's from today.
    near = [q for q in coin.price_quotes
            if q.source == CPG and q.value is not None and abs((_day(q.fetched_at) or date.today()) - start) <= RECENT]
    return min(near, key=lambda q: (abs((_day(q.fetched_at) or date.today()) - start), q.id or 0), default=None)


def _history_cpg(db: Session, coin: Coin, start: date) -> CpgHistory | None:
    grade, plus = _grade(coin)
    if not grade:
        return None
    from .grade_prices import _key_for  # the coin's price-sheet keys (pcgs:N, gsid:N)

    for key in _key_for(coin):
        rows = db.scalars(select(CpgHistory).where(CpgHistory.key == key, CpgHistory.grade == grade)).all()
        rows = [h for h in rows if ("+" in h.label) == plus]
        # A CAC coin: CAC prices if the history has them for that date, else the plain ones.
        for want_cac in ([True, False] if coin.cac else [False]):
            before = [h for h in rows if h.cac == want_cac and _day(h.first_seen) <= start]
            if not before:
                continue  # the history starts after the purchase
            h = max(before, key=lambda h: h.first_seen)
            if start - _day(h.last_seen) <= HISTORY_GAP:
                return h
    return None


def estimate(db: Session, coin: Coin) -> Estimate:
    e = _estimate(db, coin)
    if getattr(coin, "details", False) and e.value is not None and e.source in ("cpg", "cpg_history", "auctions"):
        # Straight-grade prices: a Details coin was worth its share of them.
        e.value = details.adjust(coin, e.value)
        e.detail = f"{e.detail} × {details.pct(coin)}% (Details coin)"
    return e


def _estimate(db: Session, coin: Coin) -> Estimate:
    start = purchase_day(coin)
    if coin.purchase_value_custom is not None:
        return Estimate(coin.purchase_value_custom, "custom", "Your own value")
    if getattr(coin, "is_error", False):
        # No catalog prices or auction sales for an error coin: what was paid.
        return Estimate(coin.price_paid, "paid", "Price paid") if coin.price_paid is not None else Estimate(None, None, "")
    q = _own_cpg(coin, start)
    if q is not None:
        return Estimate(q.value, "cpg", f"CPG on {_fmt(_day(q.fetched_at) or date.today())}")
    h = _history_cpg(db, coin, start) if USE_HISTORY else None
    if h is not None:
        return Estimate(h.value, "cpg_history", f"CPG as of {_fmt(_day(h.first_seen))} (TrackMyCoins price history)")
    key = auction_key(coin) if USE_AUCTIONS else None
    pending = key is not None and coin.purchase_auction_key != key
    if key is not None and not pending and coin.purchase_auction_value is not None:
        n = coin.purchase_auction_count or 0
        lo, _, hi = (coin.purchase_auction_span or "").partition("..")
        span = _month(lo) if lo == hi or not hi else f"{_month(lo)} – {_month(hi)}"
        return Estimate(coin.purchase_auction_value, "auctions",
                        f"Average of {n} PCGS auction sale{'s' if n != 1 else ''} at this grade, {span}")
    if coin.price_paid is not None:
        return Estimate(coin.price_paid, "paid", "Price paid", pending=pending)
    return Estimate(None, None, "", pending=pending)


def _sales(pcgs_number: str, grade: int, plus: bool, user_id: int, cac: bool | None = None) -> list[tuple[str, Decimal]]:
    """Archived sales for this issue and grade, after fetching PCGS's full list if it hasn't been in 3 months
    (one call, charged to the user). The archive keeps sales PCGS has since dropped."""
    from . import price_archive

    with SessionLocal() as db:
        last = price_archive.last_full_fetch(db, pcgs_number, grade, plus)
        if last is None or datetime.now(timezone.utc) - last > price_archive.AUCTIONS_EVERY:
            quota.spend(user_id, "pcgs")
            price_archive.fetch_full(db, pcgs_number, grade, plus)
            db.commit()
        return price_archive.sales_for(db, pcgs_number, grade, plus, cac)


def _months_apart(ym: str, d: date) -> int:
    y, m = (int(x) for x in ym.split("-"))
    return (y - d.year) * 12 + (m - d.month)


def average_near(sales: list[tuple[str, Decimal]], start: date,
                 window: int = AUCTION_WINDOW_MONTHS) -> tuple[Decimal, int, str] | None:
    """(average, count, "first..last" months) of up to 10 sales nearest the purchase month, within a year.
    Ties go to the sale before the purchase (what the market was then)."""
    near = [(abs(_months_apart(ym, start)), _months_apart(ym, start) > 0, ym, p) for ym, p in sales
            if abs(_months_apart(ym, start)) <= window]
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
    grade, plus = _grade(coin)
    args = (str(coin.pcgs_number), int(grade), plus, user_id)
    # Like for like: CAC sales sell higher, so plain coins use plain sales; a CAC coin uses CAC sales when there
    # were some around then, else plain ones.
    got = average_near(_sales(*args, cac=True), purchase_day(coin)) if coin.cac else None
    if got is None:
        got = average_near(_sales(*args, cac=False), purchase_day(coin))
    coin.purchase_auction_value, coin.purchase_auction_count, coin.purchase_auction_span = got or (None, 0, None)
    coin.purchase_auction_key = key
    return True


def needs_auctions(db: Session, coin: Coin) -> bool:
    """Whether the auction step would be reached and hasn't been worked out yet."""
    return estimate(db, coin).pending
