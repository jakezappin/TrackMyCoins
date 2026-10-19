"""Daily limits on calls to paid or rate-limited services (Claude, Greysheet, PCGS), per user and site-wide.

Counted in the database so restarts don't reset them. Only calls that really go out are counted: barcode scans,
saved all-grades results and cached PCGS data cost nothing.
"""

import time
from datetime import date

from sqlalchemy import select, update
from sqlalchemy.dialects.sqlite import insert as sqlite_insert

from ..config import get_settings
from ..db import SessionLocal
from ..models import ApiUsage

SITE = 0
ARCHIVE = -1  # the background price-data upkeep (services/price_archive.py), with its own allowance
PAUSED = -2  # a service that refused us: its row's count is the Unix time it can be called again
NAMES = {"claude": "label reading", "greysheet": "Greysheet price lookups", "pcgs": "PCGS lookups"}


class QuotaExceeded(Exception):
    def __init__(self, message: str, site_wide: bool = False):
        super().__init__(message)
        self.site_wide = site_wide


def _limits(service: str) -> tuple[int, int | None]:
    s = get_settings()
    return {
        "claude": (s.claude_per_user_day, None),
        "greysheet": (s.greysheet_per_user_day, s.greysheet_site_day),
        "pcgs": (s.pcgs_per_user_day, s.pcgs_site_day),
    }[service]


def _take(db, day: date, user_id: int, service: str, n: int, cap: int) -> bool:
    """Add n to a counter only if it stays within cap: one UPDATE, so two requests at the same moment can't both
    slip past the limit."""
    db.execute(sqlite_insert(ApiUsage).values(day=day, user_id=user_id, service=service, count=0)
               .on_conflict_do_nothing(index_elements=["day", "user_id", "service"]))
    done = db.execute(
        update(ApiUsage)
        .where(ApiUsage.day == day, ApiUsage.user_id == user_id, ApiUsage.service == service, ApiUsage.count + n <= cap)
        .values(count=ApiUsage.count + n)
    )
    return done.rowcount == 1


def _wait_text(seconds: float) -> str:
    hours = seconds / 3600
    if hours >= 1.5:
        return f"in about {round(hours)} hours"
    minutes = max(1, round(seconds / 60))
    return f"in about {minutes} minute{'s' if minutes != 1 else ''}"


def pause(service: str, seconds: float) -> None:
    """The service refused us (over its own limit): no calls to it until its Retry-After has passed."""
    until = int(time.time() + max(60, seconds))
    with SessionLocal() as db:
        db.execute(sqlite_insert(ApiUsage).values(day=date(2000, 1, 1), user_id=PAUSED, service=service, count=until)
                   .on_conflict_do_update(index_elements=["day", "user_id", "service"], set_={"count": until}))
        db.commit()


def paused_for(service: str) -> float:
    """Seconds until the service can be called again (0: now)."""
    with SessionLocal() as db:
        until = db.scalar(select(ApiUsage.count).where(ApiUsage.day == date(2000, 1, 1), ApiUsage.user_id == PAUSED,
                                                       ApiUsage.service == service))
    return max(0.0, (until or 0) - time.time())


def paused_message(service: str, seconds: float) -> str:
    if service == "pcgs":
        return (f"PCGS's daily limit for TrackMyCoins (100 lookups a day) is used up. It resets {_wait_text(seconds)}; "
                "everything else works meanwhile.")
    return f"{NAMES[service].capitalize()} are paused by the provider. Try again {_wait_text(seconds)}."


def spend(user_id: int, service: str, n: int = 1, limit: int | None = None) -> None:
    """Record n calls about to be made, or raise QuotaExceeded. Uses its own session and commits at once, so it
    counts even if the caller's work fails, and doesn't disturb the caller's transaction. `limit` replaces the
    per-user allowance (the background upkeep's own); the site-wide limit still applies."""
    if (wait := paused_for(service)) > 0:
        raise QuotaExceeded(paused_message(service, wait), site_wide=True)
    per_user, site = _limits(service)
    per_user = limit if limit is not None else per_user
    today = date.today()
    with SessionLocal() as db:
        if not _take(db, today, user_id, service, n, per_user):
            db.rollback()
            raise QuotaExceeded(f"You've reached today's limit for {NAMES[service]} ({per_user}). It resets tomorrow.")
        if site is not None and not _take(db, today, SITE, service, n, site):
            db.rollback()  # undoes this user's count too
            raise QuotaExceeded(f"The site has reached today's limit for {NAMES[service]}. Try again tomorrow.", site_wide=True)
        db.commit()


def spend_site(service: str, n: int = 1) -> None:
    """Calls made for the site rather than one user (e.g. downloading a series' catalog): the site-wide limit only."""
    _, site = _limits(service)
    if site is None:
        return
    with SessionLocal() as db:
        if not _take(db, date.today(), SITE, service, n, site):
            db.rollback()
            raise QuotaExceeded(f"The site has reached today's limit for {NAMES[service]}. Try again tomorrow.", site_wide=True)
        db.commit()


def used_today(user_id: int, service: str) -> int:
    with SessionLocal() as db:
        row = db.scalar(select(ApiUsage).where(ApiUsage.day == date.today(), ApiUsage.user_id == user_id,
                                               ApiUsage.service == service))
        return row.count if row else 0


def room_for_automatic_pcgs() -> bool:
    """Whether a PCGS call nobody clicked for (the value at purchase a coin page fills in by itself) may go ahead:
    PCGS isn't paused and under half the site's day is used, keeping the rest for lookups people ask for. Otherwise
    it waits; the coin stays pending and is filled on a later visit."""
    return not paused_for("pcgs") and used_today(SITE, "pcgs") < get_settings().pcgs_site_day // 2
