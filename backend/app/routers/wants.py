"""Want list: coins the user is looking for, with CPG at the target grade and whether they already own one."""

from decimal import Decimal

import httpx
from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field, field_validator
from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from ..auth import current_user
from ..db import get_db
from ..designations import from_greysheet_name, with_designation
from ..models import Coin, CoinType, GradePriceSheet, User, WantItem
from ..schemas import GRADE_PREFIXES
from ..series import BY_SLUG, type_set_members
from ..services import catalog, grade_prices, greysheet, quota, series_match
from ..services.coins import CENTS, on_hand
from .collections import get_owned_collection

router = APIRouter(prefix="/api/wants", tags=["wants"])


class WantIn(BaseModel):
    collection_id: int | None = None  # where it would go; sets the series and finish
    coin_type_id: int | None = None  # required without a collection, or for a type set
    finish: str = "MS"
    year: int = Field(ge=1700, le=2200)
    mint_mark: str = Field(min_length=1, max_length=5)
    variety: str | None = Field(default=None, max_length=150)
    grade_prefix: str | None = Field(default=None, max_length=5)
    grade: int | None = Field(default=None, ge=1, le=70)
    max_price: Decimal | None = Field(default=None, ge=0, max_digits=12, decimal_places=2)
    notes: str | None = Field(default=None, max_length=2000)

    @field_validator("mint_mark", "grade_prefix", mode="before")
    @classmethod
    def _upper(cls, v):
        return (v.strip().upper() or None) if isinstance(v, str) else v

    @field_validator("grade_prefix")
    @classmethod
    def _prefix(cls, v):
        v = {"PF": "PR", "EF": "XF"}.get(v, v)
        if v is not None and v not in GRADE_PREFIXES:
            raise ValueError(f"Unknown grade {v}")
        return v

    @field_validator("variety", "notes", mode="before")
    @classmethod
    def _blank(cls, v):
        return (v.strip() or None) if isinstance(v, str) else v


def _owned_want(db: Session, user: User, want_id: int) -> WantItem:
    w = db.get(WantItem, want_id)
    if w is None or w.user_id != user.id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Not on your want list")
    return w


def _resolve(db: Session, user: User, body: WantIn) -> tuple[int | None, int, str]:
    """(collection_id, coin_type_id, finish) for a want, after checking the year exists for the series."""
    collection_id, type_id, finish = _place(db, user, body)
    series = BY_SLUG.get(db.get(CoinType, type_id).slug)
    proof = "PR" if finish in ("PR", "SPR") else "MS"
    if series and (problem := series_match.date_problem(series, body.year, body.mint_mark, body.grade_prefix or proof)):
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, problem)
    return collection_id, type_id, finish


def _place(db: Session, user: User, body: WantIn) -> tuple[int | None, int, str]:
    if body.collection_id is not None:
        col = get_owned_collection(db, user, body.collection_id)
        series = BY_SLUG.get(col.coin_type.slug)
        if series and series.is_type_set:
            members = {m.slug for m in type_set_members(series)}
            ct = db.get(CoinType, body.coin_type_id) if body.coin_type_id else None
            if ct is None or ct.slug not in members:
                raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, "Choose which series the coin is from.")
            return col.id, ct.id, col.finish
        return col.id, col.coin_type_id, col.finish
    ct = db.get(CoinType, body.coin_type_id) if body.coin_type_id else None
    if ct is None:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, "Choose a series.")
    if body.finish not in ("MS", "PR", "SPR"):
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, "Unknown finish")
    return None, ct.id, body.finish


def _issue(db: Session, w: WantItem) -> catalog.Candidate | None:
    try:
        catalog.ensure_synced(db, w.coin_type)  # the series' catalog, downloaded at most monthly and shared
    except (greysheet.PricingError, httpx.HTTPError):
        return None
    m = catalog.match(db, w.coin_type_id, w.year, w.mint_mark, None, w.finish, w.variety)
    return m.best or (m.candidates[0] if len(m.candidates) == 1 else None)


def _finish_of(c: Coin) -> str:
    """The coin's finish: its collection's (Proof, Silver Proof), or a proof grade in a business-strike or type set."""
    if c.collection.finish != "MS":
        return c.collection.finish
    return "PR" if c.grade_prefix == "PR" else "MS"


def _out(db: Session, user: User, w: WantItem, held: list[Coin]) -> dict:
    label = f"{w.year}{'' if w.mint_mark == 'P' else '-' + w.mint_mark} {w.coin_type.name}"
    if w.variety:
        label += f" {w.variety}"
    target = f"{w.grade_prefix or ''}{w.grade or ''}" or None
    # CPG at the target grade, from a saved all-grades sheet (no API call).
    cpg = sheet_name = None
    issue = _issue(db, w) if w.grade else None
    if issue is not None:
        keys = [f"pcgs:{issue.pcgs_number}"] if issue.pcgs_number else [f"gsid:{issue.gsid}"]
        sheet = db.scalar(select(GradePriceSheet).where(GradePriceSheet.key == keys[0]))
        if sheet is not None:
            row = next((r for r in sheet.rows if r.get("grade") == w.grade and not r.get("cac") and r.get("cpg")), None)
            cpg = str(Decimal(row["cpg"]).quantize(CENTS)) if row else None
            sheet_name = sheet.name
            if target:
                target = with_designation(target, from_greysheet_name(sheet.name))
    # Coins already owned of this date/mint and finish (and variety, if given): an MS66 1880 doesn't fill a
    # wanted 1880 proof.
    mine = [c for c in held if c.coin_type_id == w.coin_type_id and c.year == w.year and c.mint_mark == w.mint_mark
            and _finish_of(c) == w.finish
            and (not w.variety or (c.variety or "").lower().find(w.variety.lower()) >= 0)]
    mine.sort(key=lambda c: (c.details, -(c.grade or 0), not c.grade_plus))  # problem-free first
    best = mine[0] if mine else None
    return {
        "id": w.id,
        "label": label,
        "collection_id": w.collection_id,
        "collection_name": w.collection.name if w.collection else None,
        "coin_type_id": w.coin_type_id,
        "finish": w.finish,
        "year": w.year,
        "mint_mark": w.mint_mark,
        "variety": w.variety,
        "grade_prefix": w.grade_prefix,
        "grade": w.grade,
        "target_label": target,
        "max_price": str(w.max_price) if w.max_price is not None else None,
        "notes": w.notes,
        "cpg": cpg,
        "priceable": issue is not None and cpg is None and sheet_name is None,
        "owned": {"inventory_number": best.inventory_number, "grade": best.grade, "grade_prefix": best.grade_prefix,
                  "grade_plus": best.grade_plus, "grade_star": best.grade_star,
                  "strike_designation": best.strike_designation,
                  "grading_service": best.grading_service, "details": best.details,
                  # A Details coin never meets a target grade.
                  "meets_target": bool(w.grade and best.grade and best.grade >= w.grade and not best.details)}
        if best else None,
        "created_at": w.created_at,
    }


def _held(db: Session, user: User) -> list[Coin]:
    return list(db.scalars(on_hand(select(Coin).where(Coin.user_id == user.id))).all())


@router.get("")
def list_wants(db: Session = Depends(get_db), user: User = Depends(current_user)):
    wants = db.scalars(
        select(WantItem).where(WantItem.user_id == user.id)
        .options(selectinload(WantItem.coin_type), selectinload(WantItem.collection))
        .order_by(WantItem.year, WantItem.mint_mark)
    ).all()
    held = _held(db, user)
    return [_out(db, user, w, held) for w in wants]


@router.post("", status_code=status.HTTP_201_CREATED)
def add_want(body: WantIn, db: Session = Depends(get_db), user: User = Depends(current_user)):
    collection_id, coin_type_id, finish = _resolve(db, user, body)
    # The same date/mint/variety twice just updates the existing entry.
    w = db.scalar(select(WantItem).where(
        WantItem.user_id == user.id, WantItem.coin_type_id == coin_type_id, WantItem.finish == finish,
        WantItem.year == body.year, WantItem.mint_mark == body.mint_mark,
        (WantItem.variety == body.variety) if body.variety else WantItem.variety.is_(None),
    ))
    if w is None:
        w = WantItem(user_id=user.id, coin_type_id=coin_type_id, finish=finish, year=body.year, mint_mark=body.mint_mark,
                     variety=body.variety)
        db.add(w)
    w.collection_id = collection_id
    w.grade_prefix, w.grade, w.max_price = body.grade_prefix, body.grade, body.max_price
    if body.notes is not None:
        w.notes = body.notes
    db.commit()
    db.refresh(w)
    return _out(db, user, w, _held(db, user))


@router.put("/{want_id}")
def update_want(want_id: int, body: WantIn, db: Session = Depends(get_db), user: User = Depends(current_user)):
    w = _owned_want(db, user, want_id)
    w.collection_id, w.coin_type_id, w.finish = _resolve(db, user, body)
    w.year, w.mint_mark, w.variety = body.year, body.mint_mark, body.variety
    w.grade_prefix, w.grade, w.max_price, w.notes = body.grade_prefix, body.grade, body.max_price, body.notes
    db.commit()
    db.refresh(w)
    return _out(db, user, w, _held(db, user))


@router.delete("/{want_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_want(want_id: int, db: Session = Depends(get_db), user: User = Depends(current_user)):
    db.delete(_owned_want(db, user, want_id))
    db.commit()


@router.post("/{want_id}/price")
def price_want(want_id: int, db: Session = Depends(get_db), user: User = Depends(current_user)):
    """Get CPG for every grade of this issue (one Greysheet call, saved and shared)."""
    w = _owned_want(db, user, want_id)
    issue = _issue(db, w)
    if issue is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Greysheet doesn't list this date and mint (or it's ambiguous).")
    key = f"pcgs:{issue.pcgs_number}" if issue.pcgs_number else f"gsid:{issue.gsid}"
    if grade_prices.recent_entry(db, key) is None:
        quota.spend(user.id, "greysheet")
        try:
            sheet = greysheet.fetch_sheet(issue.pcgs_number, None if issue.pcgs_number else issue.gsid)
        except (greysheet.PricingError, httpx.HTTPError) as e:
            raise HTTPException(status.HTTP_502_BAD_GATEWAY, f"Greysheet: {e}")
        grade_prices.save_sheet(db, sheet)
        db.commit()
    return _out(db, user, w, _held(db, user))
