"""Dealer contacts: the list, each dealer's page (contact details, card photo, what you've bought from and sold to
them), reading a card or banner photo, a vCard, and linking coins typed before the dealer was added."""

import re
from decimal import Decimal

from fastapi import APIRouter, Depends, HTTPException, UploadFile, status
from fastapi.concurrency import run_in_threadpool
from fastapi.responses import FileResponse, Response
from pydantic import BaseModel, Field, field_validator
from sqlalchemy import or_, select, update
from sqlalchemy.orm import Session, selectinload

from ..auth import current_user
from ..config import get_settings
from ..db import get_db
from ..models import BullionItem, Coin, Dealer, User
from ..services import dealers as svc
from ..services.coins import value_estimate
from ..services.labels import grade_text
from ..services.label_reader import LabelError
from ..services.quota import QuotaExceeded
from .storage import _melt, _spots_now

router = APIRouter(prefix="/api/dealers", tags=["dealers"])


class DealerIn(BaseModel):
    business: str | None = Field(default=None, max_length=200)
    contact_name: str | None = Field(default=None, max_length=200)
    phone: str | None = Field(default=None, max_length=60)
    email: str | None = Field(default=None, max_length=200)
    website: str | None = Field(default=None, max_length=300)
    address: str | None = Field(default=None, max_length=300)
    social: str | None = Field(default=None, max_length=200)
    specialties: list[str] = Field(default_factory=list, max_length=20)
    notes: str | None = Field(default=None, max_length=5000)

    @field_validator("business", "contact_name", "phone", "email", "website", "address", "social", "notes", mode="before")
    @classmethod
    def _blank(cls, v):
        return (v.strip() or None) if isinstance(v, str) else v

    @field_validator("website")
    @classmethod
    def _site(cls, v):
        return re.sub(r"^https?://", "", v, flags=re.I).rstrip("/") if v else v

    @field_validator("specialties")
    @classmethod
    def _tags(cls, v):
        out: list[str] = []
        for t in v:
            t = " ".join(str(t).split())[:40]
            if t and t.lower() not in (x.lower() for x in out):
                out.append(t)
        return out


def owned_dealer(db: Session, user: User, dealer_id: int) -> Dealer:
    d = db.get(Dealer, dealer_id)
    if d is None or d.user_id != user.id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Dealer not found")
    return d


def apply_dealer_links(db: Session, user: User, obj: Coin | BullionItem) -> None:
    """A coin or bullion item linked to a dealer: the dealer must be the user's, and its "Purchased from" / "Sold to"
    text is the dealer's name (so lists, exports and labels show it)."""
    for id_attr, text_attr in (("purchased_from_dealer_id", "purchased_from"), ("sold_to_dealer_id", "sold_to")):
        dealer_id = getattr(obj, id_attr)
        if dealer_id is not None:
            setattr(obj, text_attr, owned_dealer(db, user, dealer_id).display_name)


# ---- Items bought from / sold to a dealer ---------------------------------------------------------------------------


def _coin_title(c: Coin) -> str:
    g = grade_text(c)
    grade = f"Raw {g}".strip() if c.grading_service == "RAW" else f"{g} {c.service_name}".strip()
    return f"{c.year}{'' if c.mint_mark == 'P' else '-' + c.mint_mark} {c.coin_type.name} {grade}".strip()


def _money(v) -> str | None:
    return str(Decimal(str(v)).quantize(Decimal("0.01"))) if v is not None else None


def _history(db: Session, user: User, dealer_ids: list[int]) -> tuple[list[Coin], list[BullionItem]]:
    coin_q = (select(Coin).where(Coin.user_id == user.id, or_(Coin.purchased_from_dealer_id.in_(dealer_ids),
                                                               Coin.sold_to_dealer_id.in_(dealer_ids)))
              .options(selectinload(Coin.coin_type), selectinload(Coin.price_quotes)))
    item_q = (select(BullionItem).where(BullionItem.user_id == user.id,
                                        or_(BullionItem.purchased_from_dealer_id.in_(dealer_ids),
                                            BullionItem.sold_to_dealer_id.in_(dealer_ids)))
              .options(selectinload(BullionItem.collection)))
    return list(db.scalars(coin_q)), list(db.scalars(item_q))


def _sold(x) -> bool:
    return x.sale_date is not None or x.sale_price is not None


def _summary(d: Dealer, coins: list[Coin], items: list[BullionItem]) -> dict:
    bought = [x for x in [*coins, *items] if x.purchased_from_dealer_id == d.id]
    sold = [x for x in [*coins, *items] if x.sold_to_dealer_id == d.id]
    return {
        "bought_count": len(bought),
        "bought_total": _money(sum((x.price_paid or Decimal(0) for x in bought), Decimal(0))),
        "sold_count": len(sold),
        "sold_total": _money(sum((x.sale_price or Decimal(0) for x in sold), Decimal(0))),
    }


def _out(d: Dealer, summary: dict | None = None) -> dict:
    return {
        "id": d.id, "business": d.business, "contact_name": d.contact_name, "display_name": d.display_name,
        "phone": d.phone, "email": d.email, "website": d.website, "address": d.address, "social": d.social,
        "specialties": d.specialties or [], "notes": d.notes,
        "photo_url": f"/api/dealers/{d.id}/photo?v={d.photo_file}" if d.photo_file else None,
        **(summary or {}),
    }


# ---- The list and each dealer -------------------------------------------------------------------------------------


@router.get("")
def list_dealers(db: Session = Depends(get_db), user: User = Depends(current_user)):
    dealers = list(db.scalars(select(Dealer).where(Dealer.user_id == user.id)))
    coins, items = _history(db, user, [d.id for d in dealers]) if dealers else ([], [])
    out = [_out(d, _summary(d, coins, items)) for d in dealers]
    return sorted(out, key=lambda x: x["display_name"].lower())


@router.post("", status_code=status.HTTP_201_CREATED)
def create_dealer(body: DealerIn, db: Session = Depends(get_db), user: User = Depends(current_user)):
    if not (body.business or body.contact_name):
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, "Enter the business or the contact's name.")
    d = Dealer(user_id=user.id, **body.model_dump())
    db.add(d)
    db.commit()
    return _out(d, _summary(d, [], []))


@router.get("/{dealer_id}")
def get_dealer(dealer_id: int, db: Session = Depends(get_db), user: User = Depends(current_user)):
    """The dealer, with everything you've bought from and sold to them."""
    d = owned_dealer(db, user, dealer_id)
    coins, items = _history(db, user, [d.id])
    spots = _spots_now() if items else {}
    rows = []
    for c in coins:
        rows.append({"kind": "coin", "inventory_number": c.inventory_number, "title": _coin_title(c),
                     "bought": c.purchased_from_dealer_id == d.id, "sold_to_them": c.sold_to_dealer_id == d.id,
                     "purchase_date": c.purchase_date, "price_paid": _money(c.price_paid),
                     "sale_date": c.sale_date, "sale_price": _money(c.sale_price), "is_sold": _sold(c),
                     "value_now": _money(value_estimate(c)) if not _sold(c) else None})
    for i in items:
        rows.append({"kind": "bullion", "inventory_number": i.inventory_number, "title": i.description,
                     "bought": i.purchased_from_dealer_id == d.id, "sold_to_them": i.sold_to_dealer_id == d.id,
                     "purchase_date": i.purchase_date, "price_paid": _money(i.price_paid),
                     "sale_date": i.sale_date, "sale_price": _money(i.sale_price), "is_sold": _sold(i),
                     "value_now": _money(_melt(i, spots)) if not _sold(i) else None})
    rows.sort(key=lambda r: str((r["sale_date"] if r["sold_to_them"] and not r["bought"] else r["purchase_date"]) or ""),
              reverse=True)
    held = [r for r in rows if r["bought"] and not r["is_sold"]]
    valued = [r for r in held if r["value_now"] is not None]
    summary = {**_summary(d, coins, items),
               "held_count": len(held),
               "held_value": _money(sum((Decimal(r["value_now"]) for r in valued), Decimal(0))) if valued else None,
               "held_unvalued": len(held) - len(valued)}
    return {**_out(d, summary), "items": rows, "link_suggestions": len(_suggestions(db, user, d))}


@router.put("/{dealer_id}")
def update_dealer(dealer_id: int, body: DealerIn, db: Session = Depends(get_db), user: User = Depends(current_user)):
    d = owned_dealer(db, user, dealer_id)
    if not (body.business or body.contact_name):
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, "Enter the business or the contact's name.")
    for k, v in body.model_dump().items():
        setattr(d, k, v)
    # Linked coins and bullion show the dealer's (new) name.
    for model in (Coin, BullionItem):
        db.execute(update(model).where(model.user_id == user.id, model.purchased_from_dealer_id == d.id)
                   .values(purchased_from=d.display_name))
        db.execute(update(model).where(model.user_id == user.id, model.sold_to_dealer_id == d.id)
                   .values(sold_to=d.display_name))
    db.commit()
    return get_dealer(dealer_id, db, user)


@router.delete("/{dealer_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_dealer(dealer_id: int, db: Session = Depends(get_db), user: User = Depends(current_user)):
    """Coins and bullion keep the dealer's name as typed text; only the link goes."""
    d = owned_dealer(db, user, dealer_id)
    for model in (Coin, BullionItem):
        db.execute(update(model).where(model.user_id == user.id, model.purchased_from_dealer_id == d.id)
                   .values(purchased_from_dealer_id=None))
        db.execute(update(model).where(model.user_id == user.id, model.sold_to_dealer_id == d.id)
                   .values(sold_to_dealer_id=None))
    svc.delete_photo(d)
    db.delete(d)
    db.commit()


# ---- Reading a card or banner, and its photo ---------------------------------------------------------------------


async def _read_upload(file: UploadFile) -> bytes:
    data = await file.read(get_settings().max_photo_bytes + 1)
    if len(data) > get_settings().max_photo_bytes:
        raise HTTPException(status.HTTP_413_REQUEST_ENTITY_TOO_LARGE, "That photo is too large (15 MB max).")
    return data


@router.post("/read-card")
async def read_card(file: UploadFile, user: User = Depends(current_user)):
    """Contact details from a photo of a business card or show banner (nothing is saved)."""
    data = await _read_upload(file)
    try:
        return await run_in_threadpool(svc.read_card, data, user.id)
    except LabelError as e:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, str(e)) from e
    except QuotaExceeded as e:
        raise HTTPException(status.HTTP_429_TOO_MANY_REQUESTS, str(e)) from e


@router.post("/{dealer_id}/photo")
async def upload_photo(dealer_id: int, file: UploadFile, db: Session = Depends(get_db), user: User = Depends(current_user)):
    d = owned_dealer(db, user, dealer_id)
    data = await _read_upload(file)
    try:
        await run_in_threadpool(svc.save_photo, d, data)
    except LabelError as e:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, str(e)) from e
    db.commit()
    return _out(d)


@router.delete("/{dealer_id}/photo")
def remove_photo(dealer_id: int, db: Session = Depends(get_db), user: User = Depends(current_user)):
    d = owned_dealer(db, user, dealer_id)
    svc.delete_photo(d)
    db.commit()
    return _out(d)


@router.get("/{dealer_id}/photo")
def get_photo(dealer_id: int, db: Session = Depends(get_db), user: User = Depends(current_user)):
    d = owned_dealer(db, user, dealer_id)
    path = svc.photo_dir() / d.photo_file if d.photo_file else None
    if path is None or not path.exists():
        raise HTTPException(status.HTTP_404_NOT_FOUND, "No photo")
    return FileResponse(path, media_type="image/jpeg", headers={"Cache-Control": "private, max-age=86400"})


@router.get("/{dealer_id}/vcard")
def get_vcard(dealer_id: int, db: Session = Depends(get_db), user: User = Depends(current_user)):
    d = owned_dealer(db, user, dealer_id)
    safe = re.sub(r"[^A-Za-z0-9]+", "_", d.display_name).strip("_") or "Dealer"
    return Response(svc.vcard(d), media_type="text/vcard",
                    headers={"Content-Disposition": f'attachment; filename="{safe}.vcf"'})


# ---- Linking coins typed before the dealer was added -------------------------------------------------------------


def _suggestions(db: Session, user: User, d: Dealer) -> list[dict]:
    """Coins and bullion whose typed "Purchased from" / "Sold to" names this dealer but aren't linked to anyone."""
    out = []
    coins = db.scalars(select(Coin).where(Coin.user_id == user.id, or_(
        Coin.purchased_from.is_not(None), Coin.sold_to.is_not(None))).options(selectinload(Coin.coin_type)))
    items = db.scalars(select(BullionItem).where(BullionItem.user_id == user.id, or_(
        BullionItem.purchased_from.is_not(None), BullionItem.sold_to.is_not(None))))
    for kind, rows in (("coin", coins), ("bullion", items)):
        for x in rows:
            fields = []
            if x.purchased_from_dealer_id is None and svc.name_matches(x.purchased_from, d):
                fields.append("purchased_from")
            if x.sold_to_dealer_id is None and svc.name_matches(x.sold_to, d):
                fields.append("sold_to")
            if fields:
                out.append({"kind": kind, "inventory_number": x.inventory_number,
                            "title": _coin_title(x) if kind == "coin" else x.description,
                            "fields": fields, "purchased_from": x.purchased_from, "sold_to": x.sold_to})
    return out


@router.get("/{dealer_id}/link-suggestions")
def link_suggestions(dealer_id: int, db: Session = Depends(get_db), user: User = Depends(current_user)):
    return _suggestions(db, user, owned_dealer(db, user, dealer_id))


class LinkIn(BaseModel):
    items: list[str] = Field(max_length=2000)  # "coin:MOR-00005", "bullion:AG-00003"


@router.post("/{dealer_id}/link")
def link_items(dealer_id: int, body: LinkIn, db: Session = Depends(get_db), user: User = Depends(current_user)):
    """Link the chosen suggestions (only ones that still match, so nothing else can be linked this way)."""
    d = owned_dealer(db, user, dealer_id)
    wanted = set(body.items)
    for s in _suggestions(db, user, d):
        if f"{s['kind']}:{s['inventory_number']}" not in wanted:
            continue
        model = Coin if s["kind"] == "coin" else BullionItem
        x = db.scalar(select(model).where(model.user_id == user.id, model.inventory_number == s["inventory_number"]))
        if "purchased_from" in s["fields"]:
            x.purchased_from_dealer_id, x.purchased_from = d.id, d.display_name
        if "sold_to" in s["fields"]:
            x.sold_to_dealer_id, x.sold_to = d.id, d.display_name
    db.commit()
    return get_dealer(dealer_id, db, user)
