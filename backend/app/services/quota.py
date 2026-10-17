"""Daily limits on calls to paid or rate-limited services (Claude, Greysheet, PCGS), per user and site-wide.

Counted in the database so restarts don't reset them. Only calls that really go out are counted: barcode scans,
saved all-grades results and cached PCGS data cost nothing.
"""

from datetime import date

from sqlalchemy import select

from ..config import get_settings
from ..db import SessionLocal
from ..models import ApiUsage

SITE = 0
NAMES = {"claude": "label reading", "greysheet": "Greysheet price lookups", "pcgs": "PCGS lookups"}


class QuotaExceeded(Exception):
    def __init__(self, message: str, site_wide: bool = False):
        super().__init__(message)
        self.site_wide = site_wide


def _limits(service: str) -> tuple[int, int | None]:
    s = get_settings()
    return {
        "claude": (s.claude_per_user_day, None),
        "greysheet": (s.greysheet_per_user_day, None),
        "pcgs": (s.pcgs_per_user_day, s.pcgs_site_day),
    }[service]


def _row(db, day: date, user_id: int, service: str) -> ApiUsage:
    row = db.scalar(select(ApiUsage).where(ApiUsage.day == day, ApiUsage.user_id == user_id, ApiUsage.service == service))
    if row is None:
        row = ApiUsage(day=day, user_id=user_id, service=service, count=0)
        db.add(row)
    return row


def spend(user_id: int, service: str, n: int = 1) -> None:
    """Record n calls about to be made, or raise QuotaExceeded. Uses its own session and commits at once, so it
    counts even if the caller's work fails, and doesn't disturb the caller's transaction."""
    per_user, site = _limits(service)
    today = date.today()
    with SessionLocal() as db:
        mine = _row(db, today, user_id, service)
        if mine.count + n > per_user:
            raise QuotaExceeded(f"You've reached today's limit for {NAMES[service]} ({per_user}). It resets tomorrow.")
        if site is not None:
            everyone = _row(db, today, SITE, service)
            if everyone.count + n > site:
                raise QuotaExceeded(
                    f"The site has reached today's limit for {NAMES[service]}. Try again tomorrow.", site_wide=True
                )
            everyone.count += n
        mine.count += n
        db.commit()


def used_today(user_id: int, service: str) -> int:
    with SessionLocal() as db:
        row = db.scalar(select(ApiUsage).where(ApiUsage.day == date.today(), ApiUsage.user_id == user_id,
                                               ApiUsage.service == service))
        return row.count if row else 0
