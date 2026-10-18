"""Grading Tracker: service tiers, turnaround progress (business or calendar days) and coin snapshots.

The tier list (fees, maximum declared values, turnaround) is app/grading_tiers.json, gathered from the graders'
own pages; a submission copies its tier when it's chosen, so later price changes don't rewrite old submissions.
"""

import json
from datetime import date, timedelta
from decimal import Decimal
from functools import lru_cache
from pathlib import Path

from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from ..models import Coin, GradingSubmission, GradingSubmissionCoin
from . import details

TIERS_FILE = Path(__file__).resolve().parent.parent / "grading_tiers.json"
COMPANIES = {
    "NGC": "NGC", "PCGS": "PCGS", "CACG": "CAC Grading (CACG)", "CAC": "CAC sticker", "ANACS": "ANACS", "ICG": "ICG",
}
KINDS = {"grading": "Grading", "crossover": "Crossover", "regrade": "Regrade / Review", "reholder": "Reholder",
         "sticker": "CAC sticker review"}
OUTCOMES = {
    "pending": "Pending",
    "graded": "Graded",
    "details": "Details grade",
    "no_grade": "No grade (body bag)",
    "not_crossed": "Didn't cross",
    "sticker_green": "Green sticker",
    "sticker_gold": "Gold sticker",
    "no_sticker": "No sticker",
    "returned": "Back (no result recorded)",
}
# Turnaround colors: share of the stated days used so far.
GREEN_UPTO, YELLOW_UPTO, ORANGE_UPTO = 60, 90, 100


@lru_cache
def tiers() -> dict:
    """{"checked": "...", "tiers": [...], "addons": [...], "order_fees": [...], "notes": [...]}"""
    try:
        return json.loads(TIERS_FILE.read_text())
    except FileNotFoundError:
        return {"checked": None, "tiers": [], "addons": [], "order_fees": [], "notes": []}


def tier(key: str | None) -> dict | None:
    return next((t for t in tiers()["tiers"] if t.get("key") == key), None) if key else None


# ---- Days -----------------------------------------------------------------------------------------------------

def _nth_weekday(year: int, month: int, weekday: int, n: int) -> date:
    d = date(year, month, 1)
    d += timedelta(days=(weekday - d.weekday()) % 7)
    return d + timedelta(weeks=n - 1)


def _last_weekday(year: int, month: int, weekday: int) -> date:
    d = date(year, month + 1, 1) - timedelta(days=1) if month < 12 else date(year, 12, 31)
    return d - timedelta(days=(d.weekday() - weekday) % 7)


def _observed(d: date) -> date:
    return d - timedelta(days=1) if d.weekday() == 5 else d + timedelta(days=1) if d.weekday() == 6 else d


@lru_cache(maxsize=64)
def holidays(year: int) -> frozenset[date]:
    """U.S. federal holidays (as observed), which graders don't count as business days."""
    mon, thu = 0, 3
    return frozenset({
        _observed(date(year, 1, 1)), _nth_weekday(year, 1, mon, 3), _nth_weekday(year, 2, mon, 3),
        _last_weekday(year, 5, mon), _observed(date(year, 6, 19)), _observed(date(year, 7, 4)),
        _nth_weekday(year, 9, mon, 1), _nth_weekday(year, 10, mon, 2), _observed(date(year, 11, 11)),
        _nth_weekday(year, 11, thu, 4), _observed(date(year, 12, 25)),
    })


def is_business_day(d: date) -> bool:
    return d.weekday() < 5 and d not in holidays(d.year)


def days_between(start: date, end: date, business: bool) -> int:
    """Days after `start` up to and including `end` (the day it arrives is day 0)."""
    if end <= start:
        return 0
    if not business:
        return (end - start).days
    n, d = 0, start
    while d < end:
        d += timedelta(days=1)
        n += is_business_day(d)
    return n


def add_days(start: date, days: int, business: bool) -> date:
    """The date `days` (business) days after `start`: when the turnaround is due."""
    if not business:
        return start + timedelta(days=days)
    d, n = start, 0
    while n < days:
        d += timedelta(days=1)
        n += is_business_day(d)
    return d


# ---- Progress --------------------------------------------------------------------------------------------------

def status(s: GradingSubmission) -> str:
    if s.date_returned:
        return "returned"
    if s.date_shipped_back:
        return "shipped_back"
    if s.date_received:
        return "at_grader"
    if s.date_sent:
        return "sent"
    return "preparing"


def color(pct: float | None) -> str | None:
    if pct is None:
        return None
    return "green" if pct <= GREEN_UPTO else "yellow" if pct <= YELLOW_UPTO else "orange" if pct <= ORANGE_UPTO else "red"


def progress(s: GradingSubmission, today: date) -> dict:
    """How far along the turnaround is. The clock runs from when the grader received it (or, until that's known,
    when it was sent) to when they shipped it back (or it came back)."""
    start = s.date_received or s.date_sent
    end = s.date_shipped_back or s.date_returned or today
    out = {"status": status(s), "start": start, "elapsed": None, "target": s.turnaround_days, "pct": None,
           "color": None, "due": None, "business_days": s.business_days, "clock_from": None}
    if start is None:
        return out
    elapsed = days_between(start, end, s.business_days)
    out.update(elapsed=elapsed, clock_from="received" if s.date_received else "sent")
    if s.turnaround_days:
        pct = round(elapsed / s.turnaround_days * 100, 1)
        out.update(pct=pct, color=color(pct), due=add_days(start, s.turnaround_days, s.business_days))
    return out


def fees(s: GradingSubmission, coin_count: int) -> dict:
    """What the tier and add-ons should come to (the owner enters what was actually paid)."""
    per_coin = (s.tier_fee or Decimal(0)) + sum(
        (Decimal(str(a.get("fee") or 0)) for a in s.addons or [] if a.get("per", "coin") == "coin"), Decimal(0))
    per_order = sum((Decimal(str(a.get("fee") or 0)) for a in s.addons or [] if a.get("per") == "order"), Decimal(0))
    known = s.tier_fee is not None
    return {"per_coin": str(per_coin) if known else None,
            "estimate": str((per_coin * coin_count + per_order).quantize(Decimal("0.01"))) if known else None}


# ---- Coins ---------------------------------------------------------------------------------------------------

GRADE_FIELDS = ("grading_service", "cert_number", "grade_prefix", "grade", "grade_plus", "grade_star",
                "strike_designation", "cac", "cac_sticker", "details", "details_problem")


def snapshot(c: Coin) -> dict:
    """The coin's grade as it stands, e.g. before it's sent."""
    snap = {k: getattr(c, k) for k in GRADE_FIELDS}
    snap["label"] = grade_label(c)
    return snap


def grade_label(c) -> str:
    """"Raw", "NGC MS64+ #1234567-001", "PCGS AU Details · Cleaned"."""
    if c.grading_service == "RAW":
        g = details.label(c) if c.details else f"{c.grade_prefix or ''}{c.grade or ''}"
        return f"Raw {g}".strip()
    if c.details:
        g = details.label(c)
    else:
        g = f"{c.grade_prefix or ''}{c.grade or ''}{'+' if c.grade_plus else ''}{'★' if c.grade_star else ''}"
        if c.strike_designation:
            g += f" {c.strike_designation}"
    out = f"{c.grading_service} {g}".strip()
    if c.cac:
        out += f" CAC{f' ({c.cac_sticker})' if c.cac_sticker else ''}"
    return out + (f" #{c.cert_number}" if c.cert_number else "")


def active_link(c: Coin, links: list[GradingSubmissionCoin]) -> GradingSubmissionCoin | None:
    return next((link for link in links if link.coin_id == c.id and link.outcome == "pending"), None)


def history_for(db: Session, coin: Coin) -> list[dict]:
    """A coin's trips to the graders, newest first (for its page)."""
    links = db.scalars(select(GradingSubmissionCoin).where(GradingSubmissionCoin.coin_id == coin.id)
                       .options(selectinload(GradingSubmissionCoin.submission))).all()
    out = []
    for link in sorted(links, key=lambda x: (x.submission.date_sent or date.min, x.id), reverse=True):
        s = link.submission
        out.append({"submission_id": s.id, "number": s.number, "company": s.company,
                    "company_label": COMPANIES.get(s.company, s.company), "tier_name": s.tier_name,
                    "kind_label": KINDS.get(s.kind, s.kind), "date_sent": s.date_sent,
                    "returned_on": link.returned_on, "expected_grade": link.expected_grade,
                    "outcome": link.outcome, "outcome_label": OUTCOMES.get(link.outcome, link.outcome),
                    "before": (link.before or {}).get("label"), "after": (link.after or {}).get("label")})
    return out


def current(db: Session, coin: Coin) -> dict | None:
    """The submission the coin is in while at grading."""
    link = db.scalar(select(GradingSubmissionCoin).where(GradingSubmissionCoin.coin_id == coin.id,
                                                         GradingSubmissionCoin.outcome == "pending"))
    if link is None:
        return None
    s = link.submission
    return {"id": s.id, "number": s.number, "company": s.company, "company_label": COMPANIES.get(s.company, s.company),
            "name": s.name, "status": status(s), "expected_grade": link.expected_grade}
