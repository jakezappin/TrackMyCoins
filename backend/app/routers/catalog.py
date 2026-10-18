from datetime import datetime
from typing import Literal

import httpx
from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..auth import current_user
from ..db import get_db
from ..models import CoinType, User
from ..services import catalog
from ..services.greysheet import PricingError

router = APIRouter(prefix="/api", tags=["catalog"])

Finish = Literal["MS", "PR", "SPR"]


class CatalogStatus(BaseModel):
    count: int
    synced_at: datetime | None
    nodes: list[int] = []


class CandidateOut(BaseModel):
    pcgs_number: str | None
    gsid: int
    name: str
    variety: str | None
    designation: str | None
    exact: bool


class MatchOut(BaseModel):
    candidates: list[CandidateOut]
    best: CandidateOut | None
    message: str | None


def _coin_type(db: Session, coin_type_id: int) -> CoinType:
    ct = db.get(CoinType, coin_type_id)
    if ct is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Unknown coin type")
    return ct


def _ensure_synced(db: Session, ct: CoinType) -> None:
    try:
        catalog.ensure_synced(db, ct)
    except PricingError as e:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, str(e))
    except httpx.HTTPError as e:
        raise HTTPException(status.HTTP_502_BAD_GATEWAY, f"Greysheet error: {e}")


@router.get("/coin-types/{coin_type_id}/catalog", response_model=CatalogStatus)
def catalog_status(coin_type_id: int, db: Session = Depends(get_db), _: User = Depends(current_user)):
    count, last = catalog.status(db, _coin_type(db, coin_type_id).id)
    return CatalogStatus(count=count, synced_at=last)


@router.post("/coin-types/{coin_type_id}/catalog/sync", response_model=CatalogStatus)
def catalog_sync(coin_type_id: int, db: Session = Depends(get_db), _: User = Depends(current_user)):
    try:
        r = catalog.sync(db, _coin_type(db, coin_type_id))
    except PricingError as e:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, str(e))
    except httpx.HTTPError as e:
        raise HTTPException(status.HTTP_502_BAD_GATEWAY, f"Greysheet error: {e}")
    return CatalogStatus(count=r.count, synced_at=r.synced_at, nodes=r.nodes)


@router.get("/coin-types/{coin_type_id}/designations", response_model=list[str])
def catalog_designations(
    coin_type_id: int, finish: Finish = "MS", db: Session = Depends(get_db), _: User = Depends(current_user)
):
    """Designations that exist for this series and finish (for the coin form's dropdown)."""
    ct = _coin_type(db, coin_type_id)
    _ensure_synced(db, ct)
    return catalog.designations(db, ct.id, finish)


@router.get("/catalog/match", response_model=MatchOut)
def catalog_match(
    coin_type_id: int,
    year: int,
    mint_mark: str = "P",
    designation: str | None = None,
    finish: Finish = "MS",
    variety: str | None = None,
    gsa: Literal["hard", "soft"] | None = None,
    db: Session = Depends(get_db),
    _: User = Depends(current_user),
):
    ct = _coin_type(db, coin_type_id)
    _ensure_synced(db, ct)
    r = catalog.match(db, ct.id, year, mint_mark, designation, finish, variety, gsa)
    return MatchOut(
        candidates=[CandidateOut(**c.__dict__) for c in r.candidates],
        best=CandidateOut(**r.best.__dict__) if r.best else None,
        message=r.message,
    )


@router.get("/coin-types/{coin_type_id}/sets")
def catalog_sets(coin_type_id: int, year: int | None = None, db: Session = Depends(get_db), _: User = Depends(current_user)):
    """Mint & proof set series: every set the catalog lists (optionally for one year), for the form's picker.
    `name` is the checklist line ("" for the year's main set); `variety`/`pcgs_number` are what the item stores."""
    from ..models import CatalogEntry
    from ..services import checklist, set_melt

    ct = _coin_type(db, coin_type_id)
    _ensure_synced(db, ct)
    q = select(CatalogEntry).where(CatalogEntry.coin_type_id == ct.id)
    if year is not None:
        q = q.where(CatalogEntry.year == year)
    out = []
    for e in db.scalars(q.order_by(CatalogEntry.year, CatalogEntry.id)):
        line = checklist.set_line_name(ct.slug, e.variety)
        out.append({
            "gsid": e.gsid, "year": e.year, "mint_mark": e.mint_mark, "variety": e.variety, "pcgs_number": e.pcgs_number,
            "name": line or "", "label": f"{e.year}{'' if e.mint_mark == 'P' else '-' + e.mint_mark} {line or 'Main set'}",
            "extra": bool(checklist.EXTRA_SETS.get(ct.slug) and e.variety and checklist.EXTRA_SETS[ct.slug].search(e.variety)),
            "silver_oz": set_melt.silver_oz(ct.slug, e.year, e.variety),
        })
    return out
