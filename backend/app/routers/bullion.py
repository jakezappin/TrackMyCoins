"""Bullion collections and items (silver, gold, platinum, palladium): values from spot, kept apart from coins."""

from datetime import date, datetime, timezone
from decimal import Decimal
from typing import Literal
from urllib.parse import quote

from fastapi import APIRouter, Depends, HTTPException, Query, UploadFile, status
from fastapi.responses import FileResponse
from pydantic import BaseModel, Field, field_validator, model_validator
from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from ..auth import current_user
from ..config import get_settings
from ..db import get_db
from ..models import BullionAttachment, BullionCollection, BullionItem, BullionPhoto, User
from ..services import attachments as docs
from ..services import bullion as svc
from ..services import photos as store

router = APIRouter(prefix="/api/bullion", tags=["bullion"])
settings = get_settings()
Metal = Literal["silver", "gold", "platinum", "palladium"]


def _photo_key(item_id: int) -> str:
    return f"bullion-{item_id}"  # bullion photos and documents live apart from coins


# ---- Schemas ------------------------------------------------------------------------------------------------

class CollectionIn(BaseModel):
    name: str = Field(min_length=1, max_length=200)
    metal: Metal


class CollectionUpdate(BaseModel):
    name: str = Field(min_length=1, max_length=200)


class ItemIn(BaseModel):
    collection_id: int
    description: str = Field(min_length=1, max_length=200)
    packaging: Literal["single", "roll", "tube", "box"] = "single"
    quantity: int = Field(default=1, ge=1, le=100000)
    weight: Decimal | None = Field(default=None, gt=0, max_digits=14, decimal_places=4)
    weight_unit: Literal["ozt", "g", "kg"] = "ozt"
    purity: Decimal = Field(gt=0, le=1, max_digits=6, decimal_places=5)
    face_value: Decimal | None = Field(default=None, gt=0, max_digits=12, decimal_places=2)
    price_paid: Decimal | None = Field(default=None, ge=0, max_digits=12, decimal_places=2)
    purchase_date: date | None = None
    purchased_from: str | None = Field(default=None, max_length=200)
    sale_price: Decimal | None = Field(default=None, ge=0, max_digits=12, decimal_places=2)
    sale_date: date | None = None
    sold_to: str | None = Field(default=None, max_length=200)
    notes: str | None = Field(default=None, max_length=5000)

    @field_validator("description", "purchased_from", "sold_to", "notes", mode="before")
    @classmethod
    def _blank(cls, v):
        return v.strip() or None if isinstance(v, str) else v

    @field_validator("purchase_date", "sale_date")
    @classmethod
    def _sane_date(cls, v, info):
        label = "Purchase date" if info.field_name == "purchase_date" else "Sale date"
        if v is not None and (v.year < 1900 or v > datetime.now(timezone.utc).date()):
            raise ValueError(f"{label} {v.isoformat()} looks mistyped (it's in the future or before 1900).")
        return v

    @model_validator(mode="after")
    def _amount(self):
        if self.face_value is None and self.weight is None:
            raise ValueError("Enter the weight of one piece (or, for junk silver, the face value).")
        if self.face_value is not None and self.purity.normalize() not in svc.FACE_OZ:
            raise ValueError("Face value is for 90%, 40% and 35% silver coins; enter a weight for anything else.")
        if self.purchase_date and self.sale_date and self.sale_date < self.purchase_date:
            raise ValueError("The sale date is before the purchase date.")
        return self


class SellIn(BaseModel):
    quantity: int | None = Field(default=None, ge=1)  # pieces sold (rolls / tubes); None = all of it
    face_value: Decimal | None = Field(default=None, gt=0, max_digits=12, decimal_places=2)  # junk silver
    sale_price: Decimal = Field(ge=0, max_digits=12, decimal_places=2)
    sale_date: date
    sold_to: str | None = Field(default=None, max_length=200)


# ---- Helpers ------------------------------------------------------------------------------------------------

def _collection(db: Session, user: User, collection_id: int) -> BullionCollection:
    col = db.get(BullionCollection, collection_id)
    if col is None or col.user_id != user.id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Bullion collection not found")
    return col


def _item(db: Session, user: User, inv: str) -> BullionItem:
    item = db.scalar(
        select(BullionItem).where(BullionItem.user_id == user.id, BullionItem.inventory_number == inv)
        .options(selectinload(BullionItem.photos), selectinload(BullionItem.collection))
    )
    if item is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Item not found")
    return item


def _spots(metals) -> dict[str, Decimal | None]:
    return {m: svc.live_spot(m) for m in metals}


def _photo_url(p: BullionPhoto) -> str:
    return f"/api/bullion/photos/{p.id}"


def _item_out(item: BullionItem, series: svc.SpotSeries | None, spot_now: Decimal | None) -> dict:
    metal = item.collection.metal
    v = svc.value(item, metal, series, spot_now)
    cost = item.price_paid
    sold = svc.is_sold(item)
    basis = item.sale_price if sold else v.value_now
    change = (Decimal(str(basis)) - Decimal(str(cost))) if basis is not None and cost is not None else None
    return {
        "id": item.id, "inventory_number": item.inventory_number, "collection_id": item.collection_id,
        "collection_name": item.collection.name, "metal": metal, "description": item.description,
        "packaging": item.packaging, "quantity": item.quantity,
        "weight": str(item.weight) if item.weight is not None else None, "weight_unit": item.weight_unit,
        "purity": str(Decimal(str(item.purity)).normalize()),
        "face_value": str(item.face_value) if item.face_value is not None else None,
        "price_paid": str(cost) if cost is not None else None, "purchase_date": item.purchase_date,
        "purchased_from": item.purchased_from, "sale_price": str(item.sale_price) if item.sale_price is not None else None,
        "sale_date": item.sale_date, "sold_to": item.sold_to, "notes": item.notes, "is_sold": sold,
        "created_at": item.created_at,
        "oz": str(v.oz), "spot_now": str(v.spot_now.quantize(svc.CENTS)) if v.spot_now is not None else None,
        "value_now": str(v.value_now) if v.value_now is not None else None,
        "spot_at_purchase": str(v.spot_at_purchase.quantize(svc.CENTS)) if v.spot_at_purchase is not None else None,
        "value_at_purchase": str(v.value_at_purchase) if v.value_at_purchase is not None else None,
        "premium_pct": v.premium_pct,
        "change": str(change.quantize(svc.CENTS)) if change is not None else None,
        "change_pct": round(float(change / Decimal(str(cost))) * 100, 1) if change is not None and cost else None,
        "photos": [{"id": p.id, "url": _photo_url(p), "thumb_url": f"{_photo_url(p)}?size=thumb"} for p in item.photos],
        "thumbnail_url": f"{_photo_url(item.photos[0])}?size=thumb" if item.photos else None,
    }


def _collection_out(db: Session, col: BullionCollection, with_items: bool) -> dict:
    items = list(col.items)
    spot = svc.live_spot(col.metal)
    out = {"id": col.id, "name": col.name, "metal": col.metal, "created_at": col.created_at,
           "summary": svc.summary(items, lambda i: col.metal, {col.metal: spot})}
    if with_items:
        series = svc.SpotSeries.load(db, col.metal)
        out["items"] = [_item_out(i, series, spot) for i in sorted(items, key=lambda i: i.inventory_number)]
    return out


def _apply(item: BullionItem, body: ItemIn) -> None:
    for k, v in body.model_dump(exclude={"collection_id"}).items():
        setattr(item, k, v)
    if body.face_value is not None:  # junk silver: the face value is the amount
        item.weight, item.quantity = None, 1


# ---- Reference data -----------------------------------------------------------------------------------------

@router.get("/meta")
def meta(_: User = Depends(current_user)):
    return {"metals": list(svc.METALS), "purities": svc.PURITIES, "units": list(svc.UNITS),
            "packaging": list(svc.PACKAGING), "face_purities": [str(p) for p in svc.FACE_OZ],
            "spot": {m: (str(p) if p is not None else None) for m, p in _spots(svc.METALS).items()}}


# ---- Collections --------------------------------------------------------------------------------------------

@router.get("/collections")
def list_collections(db: Session = Depends(get_db), user: User = Depends(current_user)):
    cols = db.scalars(select(BullionCollection).where(BullionCollection.user_id == user.id)
                      .options(selectinload(BullionCollection.items)).order_by(BullionCollection.metal, BullionCollection.id))
    return [_collection_out(db, c, False) for c in cols]


@router.post("/collections", status_code=status.HTTP_201_CREATED)
def create_collection(body: CollectionIn, db: Session = Depends(get_db), user: User = Depends(current_user)):
    col = BullionCollection(user_id=user.id, metal=body.metal, name=body.name.strip())
    db.add(col)
    db.commit()
    return _collection_out(db, col, False)


@router.get("/collections/{collection_id}")
def get_collection(collection_id: int, db: Session = Depends(get_db), user: User = Depends(current_user)):
    return _collection_out(db, _collection(db, user, collection_id), True)


@router.put("/collections/{collection_id}")
def rename_collection(collection_id: int, body: CollectionUpdate, db: Session = Depends(get_db),
                      user: User = Depends(current_user)):
    col = _collection(db, user, collection_id)
    col.name = body.name.strip()
    db.commit()
    return _collection_out(db, col, False)


@router.delete("/collections/{collection_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_collection(collection_id: int, db: Session = Depends(get_db), user: User = Depends(current_user)):
    col = _collection(db, user, collection_id)
    if col.items:
        raise HTTPException(status.HTTP_409_CONFLICT, "This collection still has items (including sold ones).")
    db.delete(col)
    db.commit()


@router.get("/collections/{collection_id}/history")
def collection_history(collection_id: int, db: Session = Depends(get_db), user: User = Depends(current_user)):
    col = _collection(db, user, collection_id)
    return svc.history(db, list(col.items), lambda i: col.metal)


# ---- Everything (dashboard) ---------------------------------------------------------------------------------

def _all_items(db: Session, user: User) -> list[BullionItem]:
    return list(db.scalars(select(BullionItem).where(BullionItem.user_id == user.id)
                           .options(selectinload(BullionItem.collection))))


@router.get("/summary")
def bullion_summary(db: Session = Depends(get_db), user: User = Depends(current_user)):
    items = _all_items(db, user)
    metals = sorted({i.collection.metal for i in items})
    out = svc.summary(items, lambda i: i.collection.metal, _spots(metals))
    out["by_metal"] = {
        m: svc.summary([i for i in items if i.collection.metal == m], lambda i: m, {m: Decimal(out["spot"][m]) if out["spot"][m] else None})
        for m in metals
    }
    return out


@router.get("/history")
def all_history(db: Session = Depends(get_db), user: User = Depends(current_user)):
    return svc.history(db, _all_items(db, user), lambda i: i.collection.metal)


# ---- Items --------------------------------------------------------------------------------------------------

@router.post("/items", status_code=status.HTTP_201_CREATED)
def create_item(body: ItemIn, db: Session = Depends(get_db), user: User = Depends(current_user)):
    col = _collection(db, user, body.collection_id)
    item = BullionItem(user_id=user.id, collection_id=col.id,
                       inventory_number=svc.next_inventory_number(db, user.id, col.metal))
    _apply(item, body)
    db.add(item)
    db.commit()
    return _item_out(_item(db, user, item.inventory_number), svc.SpotSeries.load(db, col.metal), None)


@router.get("/items/{inv}")
def get_item(inv: str, db: Session = Depends(get_db), user: User = Depends(current_user)):
    item = _item(db, user, inv)
    return _item_out(item, svc.SpotSeries.load(db, item.collection.metal), None)


@router.put("/items/{inv}")
def update_item(inv: str, body: ItemIn, db: Session = Depends(get_db), user: User = Depends(current_user)):
    item = _item(db, user, inv)
    target = _collection(db, user, body.collection_id)
    if target.metal != item.collection.metal:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, "Move it to a collection of the same metal.")
    item.collection_id = target.id
    _apply(item, body)
    db.commit()
    db.expire_all()
    return get_item(inv, db, user)


@router.delete("/items/{inv}", status_code=status.HTTP_204_NO_CONTENT)
def delete_item(inv: str, db: Session = Depends(get_db), user: User = Depends(current_user)):
    item = _item(db, user, inv)
    item_id = item.id
    db.delete(item)
    db.commit()
    store.delete_coin_photo_files(_photo_key(item_id))
    docs.delete_coin_files(_photo_key(item_id))


@router.get("/items/{inv}/history")
def item_history(inv: str, db: Session = Depends(get_db), user: User = Depends(current_user)):
    item = _item(db, user, inv)
    return svc.history(db, [item], lambda i: item.collection.metal)


@router.post("/items/{inv}/sell")
def sell_item(inv: str, body: SellIn, db: Session = Depends(get_db), user: User = Depends(current_user)):
    """Record a sale. Selling part of a roll, tube or face value splits it: the sold part becomes its own item."""
    item = _item(db, user, inv)
    if svc.is_sold(item):
        raise HTTPException(status.HTTP_409_CONFLICT, "This item is already sold.")
    if body.sale_date > datetime.now(timezone.utc).date() or (item.purchase_date and body.sale_date < item.purchase_date):
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, "Check the sale date.")
    partial = (body.quantity is not None and body.quantity < (item.quantity or 1) and item.face_value is None) or (
        body.face_value is not None and item.face_value is not None and body.face_value < item.face_value)
    target = item
    if partial:
        try:
            target = svc.split_for_sale(db, item, item.collection.metal, quantity=body.quantity, face_value=body.face_value)
        except ValueError as e:
            raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, str(e))
    target.sale_price, target.sale_date, target.sold_to = body.sale_price, body.sale_date, (body.sold_to or None)
    db.commit()
    return {"sold": target.inventory_number, "kept": item.inventory_number if partial else None}


# ---- Photos -------------------------------------------------------------------------------------------------

@router.post("/items/{inv}/photos")
async def upload_photos(inv: str, files: list[UploadFile], db: Session = Depends(get_db), user: User = Depends(current_user)):
    item = _item(db, user, inv)
    if len(item.photos) + len(files) > settings.max_photos_per_coin:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, f"An item can have at most {settings.max_photos_per_coin} photos.")
    start = len(item.photos)
    for n, f in enumerate(files):
        data = await f.read(settings.max_photo_bytes + 1)
        try:
            name, ctype = store.save_bytes(_photo_key(item.id), data, f.content_type or "")
        except store.PhotoError as e:
            raise HTTPException(status.HTTP_400_BAD_REQUEST, f"{f.filename}: {e}")
        db.add(BullionPhoto(item_id=item.id, file_name=name, content_type=ctype, sort_order=start + n))
    db.commit()
    db.expire_all()
    return get_item(inv, db, user)


def _owned_photo(db: Session, user: User, photo_id: int) -> BullionPhoto:
    p = db.get(BullionPhoto, photo_id)
    if p is None or p.item.user_id != user.id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Photo not found")
    return p


@router.get("/photos/{photo_id}")
def get_photo(photo_id: int, size: Literal["full", "thumb"] = Query("full"), db: Session = Depends(get_db),
              user: User = Depends(current_user)):
    p = _owned_photo(db, user, photo_id)
    key = _photo_key(p.item_id)
    path = store.photo_path(key, p.file_name)
    if size == "thumb":
        thumb = store.thumb_path(key, p.file_name)
        if thumb.exists() or store.make_thumb(key, p.file_name):
            path = thumb
    if not path.exists():
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Photo file missing")
    return FileResponse(path, media_type="image/jpeg" if size == "thumb" else p.content_type,
                        headers={"Cache-Control": "private, max-age=2592000, immutable"})


@router.delete("/photos/{photo_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_photo(photo_id: int, db: Session = Depends(get_db), user: User = Depends(current_user)):
    p = _owned_photo(db, user, photo_id)
    key, name = _photo_key(p.item_id), p.file_name
    db.delete(p)
    db.commit()
    store.delete_photo_file(key, name)


# ---- Receipts & documents -----------------------------------------------------------------------------------

def _doc_out(a: BullionAttachment) -> dict:
    return {"id": a.id, "name": a.original_name, "content_type": a.content_type, "size": a.size_bytes,
            "created_at": a.created_at, "url": f"/api/bullion/attachments/{a.id}"}


def _docs(db: Session, item_id: int) -> list[dict]:
    rows = db.scalars(select(BullionAttachment).where(BullionAttachment.item_id == item_id).order_by(BullionAttachment.created_at))
    return [_doc_out(a) for a in rows]


def _owned_doc(db: Session, user: User, attachment_id: int) -> BullionAttachment:
    a = db.get(BullionAttachment, attachment_id)
    item = db.get(BullionItem, a.item_id) if a else None
    if item is None or item.user_id != user.id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "File not found")
    return a


@router.get("/items/{inv}/attachments")
def list_docs(inv: str, db: Session = Depends(get_db), user: User = Depends(current_user)):
    return _docs(db, _item(db, user, inv).id)


@router.post("/items/{inv}/attachments")
async def upload_docs(inv: str, files: list[UploadFile], db: Session = Depends(get_db), user: User = Depends(current_user)):
    item = _item(db, user, inv)
    have = len(_docs(db, item.id))
    if have + len(files) > settings.max_attachments_per_coin:
        raise HTTPException(status.HTTP_400_BAD_REQUEST,
                            f"An item can have at most {settings.max_attachments_per_coin} files (it has {have}).")
    for f in files:
        data = await f.read(settings.max_attachment_bytes + 1)
        try:
            stored, name, ctype, size = docs.save(_photo_key(item.id), data, f.content_type or "", f.filename)
        except docs.AttachmentError as e:
            raise HTTPException(status.HTTP_400_BAD_REQUEST, f"{f.filename}: {e}")
        db.add(BullionAttachment(item_id=item.id, file_name=stored, original_name=name, content_type=ctype, size_bytes=size))
    db.commit()
    return _docs(db, item.id)


@router.get("/attachments/{attachment_id}")
def get_doc(attachment_id: int, db: Session = Depends(get_db), user: User = Depends(current_user)):
    a = _owned_doc(db, user, attachment_id)
    path = docs.path_for(_photo_key(a.item_id), a.file_name)
    if not path.exists():
        raise HTTPException(status.HTTP_404_NOT_FOUND, "File missing")
    return FileResponse(path, media_type=a.content_type, headers={
        "Content-Disposition": f"inline; filename*=UTF-8''{quote(a.original_name)}",
        "Cache-Control": "private, max-age=86400", "X-Content-Type-Options": "nosniff"})


@router.delete("/attachments/{attachment_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_doc(attachment_id: int, db: Session = Depends(get_db), user: User = Depends(current_user)):
    a = _owned_doc(db, user, attachment_id)
    docs.delete_file(_photo_key(a.item_id), a.file_name)
    db.delete(a)
    db.commit()
