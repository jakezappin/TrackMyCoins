"""Background jobs: refresh prices for many coins without the browser waiting on each one.

The app runs as a single process, so jobs live in memory; a restart forgets finished jobs, which is fine.
"""

import threading
import time
import uuid
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone

import httpx
from sqlalchemy import select

from ..db import SessionLocal
from ..models import Coin, Collection, PriceRefreshRun
from . import greysheet, lookups, price_refresh, quota
from .coins import on_hand


@dataclass
class Job:
    id: str
    user_id: int
    kind: str  # "refresh-prices"
    scope: str  # e.g. "Morgan Dollar Collection 1" or "All collections"
    include_pcgs: bool
    total: int = 0
    done: int = 0
    updated: int = 0
    skipped: int = 0
    failed: int = 0
    status: str = "running"  # running | finished | failed
    current: str | None = None  # coin being priced
    messages: list[str] = field(default_factory=list)
    pcgs_stopped: str | None = None
    started_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    finished_at: str | None = None
    run_id: int | None = None  # PriceRefreshRun row, marked finished at the end

    def public(self) -> dict:
        d = asdict(self)
        d.pop("user_id")
        d["messages"] = self.messages[-50:]
        return d


_jobs: dict[str, Job] = {}
_lock = threading.Lock()
# Pause between coins so we stay polite to Greysheet/PCGS.
PAUSE_SECONDS = 0.25


def get(job_id: str, user_id: int) -> Job | None:
    job = _jobs.get(job_id)
    return job if job and job.user_id == user_id else None


def running_for(user_id: int) -> Job | None:
    return next((j for j in _jobs.values() if j.user_id == user_id and j.status == "running"), None)


def start_refresh(user_id: int, collection_id: int | None, scope: str, include_pcgs: bool,
                  run_id: int | None = None) -> Job:
    with _lock:
        existing = running_for(user_id)
        if existing:
            return existing
        job = Job(id=uuid.uuid4().hex[:12], user_id=user_id, kind="refresh-prices", scope=scope, include_pcgs=include_pcgs,
                  run_id=run_id)
        _jobs[job.id] = job
    threading.Thread(target=_run_refresh, args=(job, collection_id), daemon=True).start()
    return job


def _label(coin: Coin) -> str:
    date = f"{coin.year}" if coin.mint_mark == "P" else f"{coin.year}-{coin.mint_mark}"
    return f"{coin.inventory_number} {date} {coin.grade_prefix or ''}{coin.grade or ''}".strip()


def _run_refresh(job: Job, collection_id: int | None) -> None:
    db = SessionLocal()
    try:
        q = on_hand(select(Coin.id).where(Coin.user_id == job.user_id))
        if collection_id is not None:
            q = q.where(Coin.collection_id == collection_id)
        ids = list(db.scalars(q.order_by(Coin.year, Coin.mint_mark)).all())
        job.total = len(ids)
        pcgs_ok = job.include_pcgs
        cpg_ok = True
        for coin_id in ids:
            coin = db.get(Coin, coin_id)
            job.current = _label(coin)
            if not coin.grade:
                job.skipped += 1
                job.messages.append(f"{job.current}: skipped, no numeric grade")
                job.done += 1
                continue
            changed = called = False
            try:
                if cpg_ok:
                    called |= price_refresh.refresh_cpg(db, coin)
                    changed = True
            except quota.QuotaExceeded as e:  # out of today's Greysheet allowance: no more CPG this run
                cpg_ok = False
                job.messages.append(f"CPG stopped: {e}")
            except (greysheet.PricingError, lookups.LookupError) as e:
                job.messages.append(f"{job.current}: CPG: {e}")
            except httpx.HTTPError as e:
                job.messages.append(f"{job.current}: CPG: Greysheet error ({e.__class__.__name__})")
            if pcgs_ok:
                try:
                    called |= price_refresh.refresh_pcgs(db, coin)
                    changed = True
                except quota.QuotaExceeded as e:
                    pcgs_ok = False
                    job.pcgs_stopped = str(e)
                except (greysheet.PricingError, lookups.LookupError) as e:
                    if "limit" in str(e).lower():
                        pcgs_ok = False
                        job.pcgs_stopped = str(e)
                    else:
                        job.messages.append(f"{job.current}: PCGS: {e}")
                except httpx.HTTPError as e:
                    job.messages.append(f"{job.current}: PCGS: error ({e.__class__.__name__})")
            if changed:
                db.commit()
                job.updated += 1
            else:
                db.rollback()
                job.failed += 1
            job.done += 1
            if called:  # be gentle with the price APIs; no pause when priced from a saved result
                time.sleep(PAUSE_SECONDS)
        job.status = "finished"
    except Exception as e:  # keep the job record honest even on an unexpected error
        job.status = "failed"
        job.messages.append(f"Stopped: {e}")
    finally:
        job.current = None
        job.finished_at = datetime.now(timezone.utc).isoformat()
        if job.run_id is not None:
            try:
                run = db.get(PriceRefreshRun, job.run_id)
                if run is not None:
                    run.finished_at = datetime.now(timezone.utc)
                    db.commit()
            except Exception:  # pragma: no cover - never let bookkeeping hide the job's own result
                db.rollback()
        db.close()


def collection_scope(db, user_id: int, collection_id: int | None) -> str | None:
    """Label for the job, or None if the collection isn't the user's."""
    if collection_id is None:
        return "All collections"
    col = db.get(Collection, collection_id)
    return col.name if col and col.user_id == user_id else None
