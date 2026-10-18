"""Coin labels (print queue, preview, PDF) and each coin's own link: the QR code on its label."""

import re
import secrets
from datetime import date
from decimal import Decimal
from typing import Literal

from fastapi import APIRouter, Depends, HTTPException, Request, Response, status
from fastapi.responses import FileResponse
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from ..auth import current_user
from ..config import get_settings
from ..db import get_db
from ..models import Coin, CoinPhoto, Collection, LabelQueueItem, User
from ..schemas import SharedCoin
from ..services import labels as svc
from ..services import photos as store
from ..services import price_code
from ..services.coins import on_hand
from .coins import get_owned_coin
from .storage import owned_spot

router = APIRouter(prefix="/api/labels", tags=["labels"])
public_router = APIRouter(prefix="/api/c", tags=["labels"])

MAX_JOB = 600
NEEDS_CODE = "Set up your price code in Account settings before printing coded prices or dates."


# ---- Options ----------------------------------------------------------------------------------------------------


class LabelOptions(BaseModel):
    size: Literal["2x2", "avery5160", "thermal2x1"] = "2x2"
    square: Literal[2.0, 1.875] = 2.0
    cut_lines: bool = True
    start: int = Field(1, ge=1, le=30)
    inventory: bool = True
    variety: bool = True
    grade: bool = True
    cert: bool = True
    cac: bool = True
    storage: bool = False
    qr: bool = True
    price: Literal["off", "plain", "code"] = "off"
    purchase_date: Literal["off", "plain", "code"] = "off"
    asking: bool = True


class JobItem(BaseModel):
    inventory_number: str = Field(max_length=20)
    asking_price: Decimal | None = Field(default=None, ge=0, max_digits=12, decimal_places=2)


class JobIn(BaseModel):
    options: LabelOptions
    items: list[JobItem] = Field(min_length=1, max_length=MAX_JOB)
    # Turn on the public page for these coins (it's never turned off from here).
    public_page: bool = False
    # The site's address as the browser sees it, for the QR codes when no canonical host is set (local use).
    site: str | None = Field(default=None, max_length=200)


def price_code_ready(user: User) -> bool:
    return len(price_code.letters(user.price_code_phrase)) == 10 and user.price_code_start in (0, 1)


def _site(request: Request, given: str | None) -> str:
    host = get_settings().canonical_host
    if host:
        return f"https://{host}"
    if given and re.fullmatch(r"https?://[A-Za-z0-9.\-]+(:\d+)?", given.rstrip("/")):
        return given.rstrip("/")
    return str(request.base_url).rstrip("/")


def ensure_token(db: Session, coin: Coin) -> str:
    if not coin.public_token:
        while True:
            token = secrets.token_urlsafe(9)  # 12 characters: short, so the QR code stays small
            if db.scalar(select(Coin.id).where(Coin.public_token == token)) is None:
                break
        coin.public_token = token
    return coin.public_token


def coin_link(site: str, coin: Coin) -> str:
    return f"{site}/c/{coin.public_token}"


# ---- Queue ------------------------------------------------------------------------------------------------------


def _title(c: Coin) -> str:
    return f"{c.year}{'' if c.mint_mark == 'P' else '-' + c.mint_mark} {c.coin_type.name}"


def _item(c: Coin, asking: Decimal | None) -> dict:
    g = svc.grade_text(c)
    grade = f"Raw {g}".strip() if c.grading_service == "RAW" else f"{g} {c.grading_service}".strip()
    return {"inventory_number": c.inventory_number, "title": _title(c), "grade": grade,
            "asking_price": str(asking) if asking is not None else None,
            "price_paid": str(c.price_paid) if c.price_paid is not None else None, "purchase_date": c.purchase_date, "public_page": c.public_page,
            "is_sold": c.sale_date is not None or c.sale_price is not None}


def _queue(db: Session, user: User) -> list[LabelQueueItem]:
    return list(db.scalars(select(LabelQueueItem).where(LabelQueueItem.user_id == user.id)
                           .options(selectinload(LabelQueueItem.coin).selectinload(Coin.coin_type))
                           .order_by(LabelQueueItem.added_at, LabelQueueItem.id)))


def _queue_out(db: Session, user: User) -> dict:
    return {
        "items": [_item(q.coin, q.asking_price) for q in _queue(db, user)],
        "options": LabelOptions(**(user.label_options or {})).model_dump() if _valid_saved(user) else LabelOptions().model_dump(),
        "price_code_ready": price_code_ready(user),
        "asking_price_on": user.asking_price_on,
    }


def _valid_saved(user: User) -> bool:
    try:
        LabelOptions(**(user.label_options or {}))
        return True
    except ValueError:
        return False


@router.get("/queue")
def get_queue(only: str | None = None, db: Session = Depends(get_db), user: User = Depends(current_user)):
    """The print queue, the options used last time and whether a price code is set up. `only`: one coin's label
    instead of the queue (printing straight from a coin's page)."""
    out = _queue_out(db, user)
    if only:
        c = get_owned_coin(db, user, only)
        out["items"] = [_item(c, c.asking_price)]
    return out


class AddIn(BaseModel):
    inventory_numbers: list[str] = Field(default_factory=list, max_length=MAX_JOB)
    collection_id: int | None = None
    storage_id: int | None = None


@router.post("/queue")
def add_to_queue(body: AddIn, db: Session = Depends(get_db), user: User = Depends(current_user)):
    """Add coins: by inventory number, a whole collection or everything in a storage spot (sold coins are skipped)."""
    coins: list[Coin] = [get_owned_coin(db, user, inv) for inv in body.inventory_numbers]
    if body.collection_id is not None:
        col = db.get(Collection, body.collection_id)
        if col is None or col.user_id != user.id:
            raise HTTPException(status.HTTP_404_NOT_FOUND, "Collection not found")
        coins += db.scalars(on_hand(select(Coin).where(Coin.collection_id == col.id)).order_by(Coin.year, Coin.id)).all()
    if body.storage_id is not None:
        spot = owned_spot(db, user, body.storage_id)
        coins += db.scalars(on_hand(select(Coin).where(Coin.user_id == user.id, Coin.storage_id == spot.id))).all()
    have = {q.coin_id for q in _queue(db, user)}
    if len(have) + len({c.id for c in coins} - have) > MAX_JOB:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, f"The queue holds up to {MAX_JOB} labels.")
    for c in coins:
        if c.id not in have:
            db.add(LabelQueueItem(user_id=user.id, coin_id=c.id, asking_price=c.asking_price))
            have.add(c.id)
    db.commit()
    return _queue_out(db, user)


class QueueEdit(BaseModel):
    asking_price: Decimal | None = Field(default=None, ge=0, max_digits=12, decimal_places=2)


def _queued(db: Session, user: User, inv: str) -> LabelQueueItem:
    c = get_owned_coin(db, user, inv)
    q = db.scalar(select(LabelQueueItem).where(LabelQueueItem.user_id == user.id, LabelQueueItem.coin_id == c.id))
    if q is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "That coin isn't in your label queue")
    return q


@router.patch("/queue/{inv}")
def edit_queued(inv: str, body: QueueEdit, db: Session = Depends(get_db), user: User = Depends(current_user)):
    _queued(db, user, inv).asking_price = body.asking_price
    db.commit()
    return _queue_out(db, user)


@router.delete("/queue/{inv}")
def remove_queued(inv: str, db: Session = Depends(get_db), user: User = Depends(current_user)):
    db.delete(_queued(db, user, inv))
    db.commit()
    return _queue_out(db, user)


class ClearIn(BaseModel):
    inventory_numbers: list[str] | None = Field(default=None, max_length=MAX_JOB)  # None: everything


@router.post("/queue/clear")
def clear_queue(body: ClearIn, db: Session = Depends(get_db), user: User = Depends(current_user)):
    wanted = {i.strip().upper() for i in body.inventory_numbers} if body.inventory_numbers is not None else None
    for q in _queue(db, user):
        if wanted is None or q.coin.inventory_number in wanted:
            db.delete(q)
    db.commit()
    return _queue_out(db, user)


# ---- Preview and print ------------------------------------------------------------------------------------------


def _build(db: Session, user: User, body: JobIn, request: Request, assign_tokens: bool):
    opts = body.options
    if (opts.price == "code" or opts.purchase_date == "code") and not price_code_ready(user):
        raise HTTPException(status.HTTP_400_BAD_REQUEST, NEEDS_CODE)
    site = _site(request, body.site)
    data = []
    for it in body.items:
        c = get_owned_coin(db, user, it.inventory_number)
        if assign_tokens:
            ensure_token(db, c)
        # The preview shows a stand-in link for coins that don't have one yet (the QR code looks the same).
        url = coin_link(site, c) if c.public_token else f"{site}/c/{'x' * 12}"
        data.append(svc.label_lines(c, c.coin_type.name, svc.Options(**opts.model_dump()), user, it.asking_price, url))
    return data


@router.post("/preview")
def preview(body: JobIn, request: Request, db: Session = Depends(get_db), user: User = Depends(current_user)):
    """The labels as they'll print: the first pages (SVG), with any warnings."""
    data = _build(db, user, body, request, assign_tokens=False)
    opts = svc.Options(**body.options.model_dump())
    pages, smallest = svc.pages(data, opts, preview=True)
    # Sheets: close-ups of the first few labels, and the first pages to show where they fall.
    shown = [] if body.options.size == "thermal2x1" else pages[:2]
    closeups = [svc.closeup(d, opts) for d in data[:4]]
    warnings = []
    if smallest < svc.MIN_FONT:
        warnings.append(f"Some text prints very small ({smallest:.1f} pt) to fit everything. Turning off a field or "
                        "two, or a bigger label size, makes it easier to read.")
    return {"labels": [svc.svg(p) for p in closeups], "pages": [svc.svg(p) for p in shown],
            "page_count": len(pages), "label_count": len(data),
            "smallest_font": round(smallest, 1), "warnings": warnings}


@router.post("/pdf")
def print_pdf(body: JobIn, request: Request, db: Session = Depends(get_db), user: User = Depends(current_user)):
    data = _build(db, user, body, request, assign_tokens=True)
    if body.public_page:
        for it in body.items:
            get_owned_coin(db, user, it.inventory_number).public_page = True
    user.label_options = body.options.model_dump()
    db.commit()
    pages, _ = svc.pages(data, svc.Options(**body.options.model_dump()))
    name = "Label" if len(data) == 1 else "Labels"
    return Response(svc.pdf(pages, "Coin labels"), media_type="application/pdf", headers={
        "Content-Disposition": f'attachment; filename="Coin_{name}_{date.today():%Y-%m-%d}.pdf"'})


# ---- A coin's own link ------------------------------------------------------------------------------------------


class PublicIn(BaseModel):
    public_page: bool


def _public_state(request: Request, c: Coin) -> dict:
    return {"public_page": c.public_page, "url": coin_link(_site(request, None), c) if c.public_token else None,
            "path": f"/c/{c.public_token}" if c.public_token else None}


@router.get("/coins/{inv}/public")
def public_state(inv: str, request: Request, db: Session = Depends(get_db), user: User = Depends(current_user)):
    return _public_state(request, get_owned_coin(db, user, inv))


@router.put("/coins/{inv}/public")
def set_public(inv: str, body: PublicIn, request: Request, db: Session = Depends(get_db), user: User = Depends(current_user)):
    c = get_owned_coin(db, user, inv)
    ensure_token(db, c)
    c.public_page = body.public_page
    db.commit()
    return _public_state(request, c)


@router.post("/coins/{inv}/public/new-link")
def new_link(inv: str, request: Request, db: Session = Depends(get_db), user: User = Depends(current_user)):
    """Retire the old link (labels already printed stop working) and make a new one."""
    c = get_owned_coin(db, user, inv)
    c.public_token = None
    db.flush()
    ensure_token(db, c)
    db.commit()
    return _public_state(request, c)


def _viewer(request: Request, db: Session) -> User | None:
    try:
        return current_user(request, db)
    except HTTPException:
        return None


NOT_FOUND = "This label's link doesn't work any more. The owner may have made a new one."


def _by_token(db: Session, token: str) -> Coin:
    c = db.scalar(select(Coin).where(Coin.public_token == token)) if token else None
    if c is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, NOT_FOUND)
    return c


@public_router.get("/{token}")
def public_coin(token: str, request: Request, db: Session = Depends(get_db)):
    """What a scanned label opens. The owner: where their coin is. Anyone else: the public page if it's on (never
    prices, purchase details, storage or notes), otherwise just that the coin is private."""
    c = _by_token(db, token)
    viewer = _viewer(request, db)
    if viewer is not None and viewer.id == c.user_id:
        return {"owner": True, "inventory_number": c.inventory_number}
    sold = c.sale_date is not None or c.sale_price is not None
    if not c.public_page or sold:
        return {"owner": False, "private": True}
    fields = {k: getattr(c, k) for k in SharedCoin.model_fields if k not in ("value_estimate", "photo_urls", "thumb_url")}
    coin = SharedCoin(**fields, photo_urls=[f"/api/c/{token}/photos/{p.id}" for p in c.photos],
                      thumb_url=f"/api/c/{token}/photos/{c.photos[0].id}?size=thumb" if c.photos else None)
    return {"owner": False, "private": False, "title": _title(c), "coin_type_name": c.coin_type.name, "coin": coin}


@public_router.get("/{token}/photos/{photo_id}")
def public_photo(token: str, photo_id: int, size: Literal["full", "thumb"] = "full", db: Session = Depends(get_db)):
    c = _by_token(db, token)
    photo = db.get(CoinPhoto, photo_id)
    sold = c.sale_date is not None or c.sale_price is not None
    if photo is None or photo.coin_id != c.id or not c.public_page or sold:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Photo not found")
    found = store.file_for(photo, size)
    if found is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Photo file missing")
    return FileResponse(found[0], media_type=found[1], headers={"Cache-Control": "private, max-age=600"})
