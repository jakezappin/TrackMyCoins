import threading
from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..auth import current_user
from ..db import get_db
from ..config import get_settings
from ..models import PriceRefreshRun, User
from ..services import jobs

_starting = threading.Lock()

router = APIRouter(prefix="/api", tags=["jobs"])


class RefreshIn(BaseModel):
    collection_id: int | None = None  # None = every collection
    include_pcgs: bool = False  # PCGS Price Guide + auctions too (2 PCGS calls per coin, 1,000/day)


WEEK = timedelta(days=7)
GRACE = timedelta(minutes=30)


def _aware(dt: datetime) -> datetime:
    return dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)


def allowance(db: Session, user_id: int) -> dict:
    """How many bulk refreshes are left in the rolling week, and when the next one frees up."""
    limit = get_settings().refresh_limit_per_week
    now = datetime.now(timezone.utc)
    runs = db.execute(
        select(PriceRefreshRun.started_at, PriceRefreshRun.finished_at).where(
            PriceRefreshRun.user_id == user_id, PriceRefreshRun.started_at > now - WEEK
        )
    ).all()
    # Finished runs count; so does one started in the last half hour (still running). A run that never finished
    # (the server stopped mid-way) is given back.
    recent = sorted(_aware(s) for s, f in runs if f is not None or now - _aware(s) < GRACE)
    left = max(0, limit - len(recent))
    next_at = None if left else recent[len(recent) - limit] + WEEK
    return {"limit": limit, "used": len(recent), "left": left, "next_available_at": next_at}


@router.get("/refresh-prices/allowance")
def refresh_allowance(db: Session = Depends(get_db), user: User = Depends(current_user)):
    return allowance(db, user.id)


@router.post("/refresh-prices")
def refresh_prices(body: RefreshIn, db: Session = Depends(get_db), user: User = Depends(current_user)):
    """Start refreshing CPG (and optionally PCGS) for every coin on hand, in the background."""
    scope = jobs.collection_scope(db, user.id, body.collection_id)
    if scope is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Collection not found")
    with _starting:  # two quick clicks: one run, counted once
        running = jobs.running_for(user.id)
        if running:
            return running.public()
        a = allowance(db, user.id)
        if not a["left"]:
            when = a["next_available_at"].astimezone(timezone.utc)
            raise HTTPException(
                status.HTTP_429_TOO_MANY_REQUESTS,
                f"Prices can be refreshed {a['limit']} times a week. The next refresh is available "
                f"{when:%a %b} {when.day} at {when:%-I:%M %p} UTC.",
            )
        run = PriceRefreshRun(user_id=user.id, scope=scope[:200])
        db.add(run)
        db.commit()
        return jobs.start_refresh(user.id, body.collection_id, scope, body.include_pcgs, run_id=run.id).public()


@router.get("/jobs/current")
def current_job(user: User = Depends(current_user)):
    job = jobs.running_for(user.id)
    return job.public() if job else None


@router.get("/jobs/{job_id}")
def job_status(job_id: str, user: User = Depends(current_user)):
    job = jobs.get(job_id, user.id)
    if job is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Job not found")
    return job.public()
