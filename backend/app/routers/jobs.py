from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel
from sqlalchemy.orm import Session

from ..auth import current_user
from ..db import get_db
from ..models import User
from ..services import jobs

router = APIRouter(prefix="/api", tags=["jobs"])


class RefreshIn(BaseModel):
    collection_id: int | None = None  # None = every collection
    include_pcgs: bool = False  # PCGS Price Guide + auctions too (2 PCGS calls per coin, 1,000/day)


@router.post("/refresh-prices")
def refresh_prices(body: RefreshIn, db: Session = Depends(get_db), user: User = Depends(current_user)):
    """Start refreshing CPG (and optionally PCGS) for every coin on hand, in the background."""
    scope = jobs.collection_scope(db, user.id, body.collection_id)
    if scope is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Collection not found")
    return jobs.start_refresh(user.id, body.collection_id, scope, body.include_pcgs).public()


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
