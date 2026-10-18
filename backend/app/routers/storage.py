"""Storage: where the owner keeps coins and bullion (albums, boxes, their own codes), what's in each, and printouts."""

import re
from datetime import date
from decimal import Decimal
from typing import Literal

from fastapi import APIRouter, Depends, HTTPException, Query, status
from fastapi.responses import Response
from pydantic import BaseModel, Field, field_validator
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session, selectinload

from ..auth import current_user
from ..db import get_db
from ..models import BullionItem, Coin, CoinType, StorageSpot, User
from ..services import bullion as bsvc
from ..services import grading, storage_report
from ..services.coins import on_hand, photo_url, value_estimate

router = APIRouter(prefix="/api/storage", tags=["storage"])


class SpotIn(BaseModel):
    name: str = Field(min_length=1, max_length=100)
    notes: str | None = Field(default=None, max_length=2000)

    @field_validator("name", "notes", mode="before")
    @classmethod
    def _trim(cls, v):
        return (v.strip() or None) if isinstance(v, str) else v


class ItemRef(BaseModel):
    kind: Literal["coin", "bullion"]
    inventory_number: str = Field(max_length=20)
    position: str | None = Field(default=None, max_length=60)

    @field_validator("position", mode="before")
    @classmethod
    def _trim(cls, v):
        return (v.strip() or None) if isinstance(v, str) else v


def owned_spot(db: Session, user: User, spot_id: int) -> StorageSpot:
    s = db.get(StorageSpot, spot_id)
    if s is None or s.user_id != user.id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Storage spot not found")
    return s


def _coins(db: Session, user: User, spot_ids: list[int] | None = None):
    q = on_hand(select(Coin).where(Coin.user_id == user.id, Coin.storage_id.is_not(None))).options(
        selectinload(Coin.photos), selectinload(Coin.price_quotes), selectinload(Coin.coin_type))
    if spot_ids is not None:
        q = q.where(Coin.storage_id.in_(spot_ids))
    return db.scalars(q).all()


def _bullion(db: Session, user: User, spot_ids: list[int] | None = None):
    q = (select(BullionItem).where(BullionItem.user_id == user.id, BullionItem.storage_id.is_not(None),
                                   BullionItem.sale_date.is_(None), BullionItem.sale_price.is_(None))
         .options(selectinload(BullionItem.photos), selectinload(BullionItem.collection)))
    if spot_ids is not None:
        q = q.where(BullionItem.storage_id.in_(spot_ids))
    return db.scalars(q).all()


def _spots_now() -> dict[str, Decimal | None]:
    return {m: bsvc.live_spot(m) for m in bsvc.METALS}


def _melt(i: BullionItem, spots: dict[str, Decimal | None]) -> Decimal | None:
    p = spots.get(i.collection.metal)
    return (bsvc.pure_oz(i) * p).quantize(bsvc.CENTS) if p is not None else None


def _summary(s: StorageSpot, coins: list[Coin], items: list[BullionItem], spots: dict) -> dict:
    vals = [value_estimate(c) for c in coins] + [_melt(i, spots) for i in items]
    return {"id": s.id, "name": s.name, "notes": s.notes, "coin_count": len(coins), "bullion_count": len(items),
            "value": str(sum((v for v in vals if v is not None), Decimal(0)).quantize(Decimal("0.01"))),
            "unvalued": sum(1 for v in vals if v is None), "created_at": s.created_at}


@router.get("/spots")
def list_spots(db: Session = Depends(get_db), user: User = Depends(current_user)):
    spots_db = db.scalars(select(StorageSpot).where(StorageSpot.user_id == user.id)).all()
    coins, items, spots = _coins(db, user), _bullion(db, user), _spots_now()
    out = [_summary(s, [c for c in coins if c.storage_id == s.id], [i for i in items if i.storage_id == s.id], spots)
           for s in spots_db]
    return sorted(out, key=lambda s: storage_report.position_key(s["name"], ""))


@router.post("/spots", status_code=status.HTTP_201_CREATED)
def create_spot(body: SpotIn, db: Session = Depends(get_db), user: User = Depends(current_user)):
    s = StorageSpot(user_id=user.id, name=body.name, notes=body.notes)
    db.add(s)
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        raise HTTPException(status.HTTP_409_CONFLICT, f"You already have a storage spot named “{body.name}”.")
    return _summary(s, [], [], {})


@router.put("/spots/{spot_id}")
def update_spot(spot_id: int, body: SpotIn, db: Session = Depends(get_db), user: User = Depends(current_user)):
    s = owned_spot(db, user, spot_id)
    s.name, s.notes = body.name, body.notes
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        raise HTTPException(status.HTTP_409_CONFLICT, f"You already have a storage spot named “{body.name}”.")
    return get_spot(spot_id, db, user)


@router.delete("/spots/{spot_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_spot(spot_id: int, db: Session = Depends(get_db), user: User = Depends(current_user)):
    """The items stay; they're just no longer stored anywhere."""
    s = owned_spot(db, user, spot_id)
    for model in (Coin, BullionItem):
        for x in db.scalars(select(model).where(model.storage_id == s.id)):
            x.storage_id, x.storage_position = None, None
    db.delete(s)
    db.commit()


@router.get("/spots/{spot_id}")
def get_spot(spot_id: int, db: Session = Depends(get_db), user: User = Depends(current_user)):
    s = owned_spot(db, user, spot_id)
    coins, items, spots = _coins(db, user, [s.id]), _bullion(db, user, [s.id]), _spots_now()
    out = _summary(s, coins, items, spots)
    rows = []
    for c in coins:
        v = value_estimate(c)
        rows.append({"kind": "coin", "inventory_number": c.inventory_number, "position": c.storage_position,
                     "title": f"{c.year}{'' if c.mint_mark == 'P' else '-' + c.mint_mark} {c.coin_type.name}",
                     "subtitle": " · ".join(x for x in (c.variety, c.vam) if x) or None,
                     "grade": grading.grade_label(c), "value": str(v) if v is not None else None,
                     "at_grading": c.location == "grading",
                     "thumbnail_url": f"{photo_url(c.photos[0].id)}?size=thumb" if c.photos else None})
    for i in items:
        v = _melt(i, spots)
        rows.append({"kind": "bullion", "inventory_number": i.inventory_number, "position": i.storage_position,
                     "title": i.description, "subtitle": i.collection.name,
                     "grade": f"{bsvc.pure_oz(i).normalize()} ozt {i.collection.metal}", "value": str(v) if v is not None else None,
                     "at_grading": False,
                     "thumbnail_url": f"/api/bullion/photos/{i.photos[0].id}?size=thumb" if i.photos else None})
    rows.sort(key=lambda r: storage_report.position_key(r["position"], r["inventory_number"]))
    out["items"] = rows
    return out


def _find(db: Session, user: User, ref: ItemRef):
    model = Coin if ref.kind == "coin" else BullionItem
    x = db.scalar(select(model).where(model.user_id == user.id, model.inventory_number == ref.inventory_number.strip().upper()))
    if x is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, f"{ref.inventory_number} not found")
    return x


@router.post("/spots/{spot_id}/items")
def put_item(spot_id: int, body: ItemRef, db: Session = Depends(get_db), user: User = Depends(current_user)):
    """Store an item here (moving it from wherever it was), or change its position."""
    s = owned_spot(db, user, spot_id)
    x = _find(db, user, body)
    if x.sale_date is not None or x.sale_price is not None:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, f"{x.inventory_number} has been sold.")
    x.storage_id, x.storage_position = s.id, body.position
    db.commit()
    return get_spot(spot_id, db, user)


@router.delete("/spots/{spot_id}/items/{kind}/{inventory_number}")
def remove_item(spot_id: int, kind: Literal["coin", "bullion"], inventory_number: str, db: Session = Depends(get_db),
                user: User = Depends(current_user)):
    s = owned_spot(db, user, spot_id)
    x = _find(db, user, ItemRef(kind=kind, inventory_number=inventory_number))
    if x.storage_id == s.id:
        x.storage_id, x.storage_position = None, None
        db.commit()
    return get_spot(spot_id, db, user)


@router.get("/spots/{spot_id}/report")
def report(spot_id: int, values: bool = Query(True), db: Session = Depends(get_db), user: User = Depends(current_user)):
    """PDF of everything in this storage spot: with values, or as a checklist to tick off."""
    s = owned_spot(db, user, spot_id)
    coins, items = _coins(db, user, [s.id]), _bullion(db, user, [s.id])
    names = {t.id: t.name for t in db.scalars(select(CoinType))}
    pdf = storage_report.build_pdf(user, s, coins, items, names, _spots_now() if values else {}, values)
    safe = re.sub(r"[^A-Za-z0-9]+", "_", s.name).strip("_") or "Storage"
    kind = "Inventory" if values else "Checklist"
    return Response(pdf, media_type="application/pdf", headers={
        "Content-Disposition": f'attachment; filename="{safe}_{kind}_{date.today():%Y-%m-%d}.pdf"'})


def check_spot(db: Session, user: User, spot_id: int | None) -> None:
    """For the coin and bullion forms: the chosen storage spot must be the user's."""
    if spot_id is not None:
        owned_spot(db, user, spot_id)
