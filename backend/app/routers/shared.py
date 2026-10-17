"""Public, read-only view of a collection the owner chose to share (no login)."""

from decimal import Decimal

from typing import Literal

from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.responses import FileResponse
from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from ..db import get_db
from ..models import Coin, CoinPhoto, Collection
from ..schemas import SharedCoin, SharedCollection
from ..series import BY_SLUG
from ..services import checklist
from ..services import photos as store
from ..services.coins import CENTS, on_hand, value_estimate
from .collections import _type_label

router = APIRouter(prefix="/api/shared", tags=["shared"])

NOT_FOUND = "This link isn't shared any more, or never was."


def _shared_collection(db: Session, token: str) -> Collection:
    col = db.scalar(select(Collection).where(Collection.share_token == token)) if token else None
    if col is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, NOT_FOUND)
    return col


@router.get("/{token}", response_model=SharedCollection)
def shared_collection(token: str, db: Session = Depends(get_db)):
    col = _shared_collection(db, token)
    q = on_hand(select(Coin).where(Coin.collection_id == col.id)).options(
        selectinload(Coin.photos), selectinload(Coin.price_quotes)
    )
    coins = sorted(db.scalars(q).all(), key=lambda c: (c.year, checklist.MINT_ORDER.get(c.mint_mark, 9), c.id))
    show = col.share_show_values
    out = []
    for c in coins:
        fields = {k: getattr(c, k) for k in SharedCoin.model_fields if k not in ("value_estimate", "photo_urls", "thumb_url")}
        out.append(SharedCoin(
            **fields,
            value_estimate=value_estimate(c) if show else None,
            photo_urls=[f"/api/shared/{token}/photos/{p.id}" for p in c.photos],
            thumb_url=f"/api/shared/{token}/photos/{c.photos[0].id}?size=thumb" if c.photos else None,
        ))
    series = BY_SLUG.get(col.coin_type.slug)
    total = None
    if show:
        total = sum((o.value_estimate or Decimal(0) for o in out), Decimal(0)).quantize(CENTS)
    return SharedCollection(
        name=col.name,
        owner=f"{col.user.first_name} {col.user.last_name[:1]}.".strip() if col.user.last_name else col.user.first_name,
        collection_type_label=_type_label(col.coin_type, col.finish),
        coin_type_name=col.coin_type.name,
        metal=series.metal if series else "silver",
        show_values=show,
        coin_count=len(out),
        total_estimated_value=total,
        coins=out,
    )


@router.get("/{token}/photos/{photo_id}")
def shared_photo(token: str, photo_id: int, size: Literal["full", "thumb"] = "full", db: Session = Depends(get_db)):
    col = _shared_collection(db, token)
    photo = db.get(CoinPhoto, photo_id)
    sold = photo is not None and (photo.coin.sale_date is not None or photo.coin.sale_price is not None)
    if photo is None or photo.coin.collection_id != col.id or sold:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Photo not found")
    found = store.file_for(photo, size)
    if found is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Photo file missing")
    return FileResponse(found[0], media_type=found[1], headers={"Cache-Control": "public, max-age=3600"})
