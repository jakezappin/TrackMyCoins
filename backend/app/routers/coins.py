from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..auth import current_user
from ..db import get_db
from ..models import Coin, CoinType, Collection, User
from ..series import BY_SLUG, type_set_members
from ..schemas import CoinDetail, CoinFields, CoinIn, CoinUpdate
from ..services.coins import coin_detail, duplicate_info, find_duplicate_cert, next_inventory_number
from ..services import attachments, series_match
from ..services.photos import delete_coin_photo_files
from .collections import get_owned_collection

router = APIRouter(prefix="/api/coins", tags=["coins"])


def get_owned_coin(db: Session, user: User, inventory_number: str) -> Coin:
    """Coins are addressed by their inventory number (e.g. MOR-00005), unique per user."""
    coin = db.scalar(
        select(Coin).where(Coin.user_id == user.id, Coin.inventory_number == inventory_number.strip().upper())
    )
    if coin is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Coin not found")
    return coin


def coin_type_for(db: Session, collection: Collection, requested_id: int | None) -> CoinType:
    """The series a coin belongs to: the collection's own, or (in a type set) the member series chosen."""
    series = BY_SLUG.get(collection.coin_type.slug)
    if series is None or not series.is_type_set:
        return collection.coin_type
    members = {m.slug for m in type_set_members(series)}
    chosen = db.get(CoinType, requested_id) if requested_id else None
    if chosen is None or chosen.slug not in members:
        raise HTTPException(
            status.HTTP_422_UNPROCESSABLE_CONTENT,
            f"Choose which series this coin is from (one of the {len(members)} in a {series.name}).",
        )
    return chosen


def _validate(body: CoinFields, collection: Collection, coin_type: CoinType) -> dict:
    series = BY_SLUG.get(coin_type.slug)
    if series and (problem := series_match.date_problem(series, body.year, body.mint_mark, body.grade_prefix)):
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, problem)
    marks = coin_type.mint_marks
    if marks and body.mint_mark not in marks:
        raise HTTPException(
            status.HTTP_422_UNPROCESSABLE_CONTENT,
            f"Mint mark must be one of {', '.join(marks)} for {coin_type.name}",
        )
    data = body.model_dump(exclude={"collection_id", "coin_type_id", "lookup_raw"})
    if series and series.is_set:
        # Mint & proof sets aren't graded: no service, cert, grade, CAC or slab.
        data.update(grading_service="RAW", cert_number=None, grade_prefix=None, grade=None, grade_plus=False,
                    grade_star=False, strike_designation=None, cac=False, cac_sticker=None, slab_soapbox=False,
                    slab_ngc_fatty=False, slab_rattler=False, slab_ogh=False)
    # Proof collections hold proofs; business-strike collections don't.
    if collection.finish in ("PR", "SPR"):
        if data["grade_prefix"] in (None, "PF"):
            data["grade_prefix"] = "PR"
        if data["grade_prefix"] != "PR":
            raise HTTPException(
                status.HTTP_422_UNPROCESSABLE_CONTENT,
                f"{collection.name} is a proof collection, so the grade must be PR (e.g. PR69 DCAM).",
            )
    elif data["grade_prefix"] in ("PR", "PF"):
        raise HTTPException(
            status.HTTP_422_UNPROCESSABLE_CONTENT,
            f"{collection.name} is for business strikes. Put proofs in a Proof collection.",
        )
    # A sticker color implies CAC; un-checking CAC clears the color.
    if data["cac_sticker"]:
        data["cac"] = True
    if not data["cac"]:
        data["cac_sticker"] = None
    if data["gsa_hard_pack"] and data["gsa_soft_pack"]:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, "A GSA coin is either hard pack or soft pack, not both")
    if data["ike_blue_pack"] and data["ike_brown_pack"]:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, "Pick Blue Pack or Brown Pack, not both")
    if data["grading_service"] == "RAW":
        # Ungraded: no cert, no CAC sticker, no grading-service slab. The grade is optional and may be
        # just a letter grade (e.g. "AU") or a letter grade with a number (e.g. "AU55").
        data.update(cert_number=None, cac=False, cac_sticker=None, grade_plus=False, grade_star=False,
                    slab_soapbox=False, slab_ngc_fatty=False, slab_rattler=False, slab_ogh=False)
    return data


def _reject_duplicate(db: Session, user: User, data: dict, exclude_coin_id: int | None = None) -> None:
    dup = find_duplicate_cert(db, user.id, data["grading_service"], data["cert_number"], exclude_coin_id)
    if dup:
        info = duplicate_info(dup)
        raise HTTPException(
            status.HTTP_409_CONFLICT,
            {
                "message": f"{data['grading_service']} cert {data['cert_number']} is already in your collection "
                f"as {info['inventory_number']} ({info['description']}, {info['collection_name']}).",
                "duplicate": info,
            },
        )


@router.post("", response_model=CoinDetail, status_code=status.HTTP_201_CREATED)
def create_coin(body: CoinIn, db: Session = Depends(get_db), user: User = Depends(current_user)):
    col = get_owned_collection(db, user, body.collection_id)
    coin_type = coin_type_for(db, col, body.coin_type_id)
    data = _validate(body, col, coin_type)
    _reject_duplicate(db, user, data)
    coin = Coin(
        **data,
        user_id=user.id,
        coin_type_id=coin_type.id,
        collection_id=col.id,
        inventory_number=next_inventory_number(db, user.id, coin_type),
        lookup_raw=body.lookup_raw,
    )
    db.add(coin)
    db.commit()
    db.refresh(coin)
    return coin_detail(coin)


@router.get("/{inventory_number}", response_model=CoinDetail)
def get_coin(inventory_number: str, db: Session = Depends(get_db), user: User = Depends(current_user)):
    return coin_detail(get_owned_coin(db, user, inventory_number))


@router.put("/{inventory_number}", response_model=CoinDetail)
def update_coin(inventory_number: str, body: CoinUpdate, db: Session = Depends(get_db), user: User = Depends(current_user)):
    coin = get_owned_coin(db, user, inventory_number)
    col = get_owned_collection(db, user, body.collection_id)
    coin_type = coin_type_for(db, col, body.coin_type_id or coin.coin_type_id)
    if coin_type.id != coin.coin_type_id:
        # Its inventory number (e.g. MOR-00005) belongs to its series, so a coin keeps its series.
        raise HTTPException(status.HTTP_400_BAD_REQUEST, f"This coin is a {coin.coin_type.name}; it can't change series")
    data = _validate(body, col, coin_type)
    # Re-check when the coin is on hand (or being returned to hand) so edits can't create a duplicate.
    if data["sale_price"] is None and data["sale_date"] is None:
        _reject_duplicate(db, user, data, exclude_coin_id=coin.id)
    for key, value in data.items():
        setattr(coin, key, value)
    coin.collection_id = col.id
    db.commit()
    db.refresh(coin)
    return coin_detail(coin)


@router.delete("/{inventory_number}", status_code=status.HTTP_204_NO_CONTENT)
def delete_coin(inventory_number: str, db: Session = Depends(get_db), user: User = Depends(current_user)):
    coin = get_owned_coin(db, user, inventory_number)
    coin_id = coin.id
    db.delete(coin)
    db.commit()
    delete_coin_photo_files(coin_id)
    attachments.delete_coin_files(coin_id)


def _move_targets(db: Session, user: User, coin: Coin) -> list[Collection]:
    """The user's other collections this coin can live in: same series, or a type set that includes its series."""
    out = []
    for col in db.scalars(select(Collection).where(Collection.user_id == user.id, Collection.id != coin.collection_id)):
        if col.coin_type_id == coin.coin_type_id:
            out.append(col)
            continue
        series = BY_SLUG.get(col.coin_type.slug)
        if series and series.is_type_set and coin.coin_type.slug in {m.slug for m in type_set_members(series)}:
            out.append(col)
    return sorted(out, key=lambda c: c.name.lower())


@router.get("/{inventory_number}/move-targets")
def move_targets(inventory_number: str, db: Session = Depends(get_db), user: User = Depends(current_user)):
    coin = get_owned_coin(db, user, inventory_number)
    return [{"id": c.id, "name": c.name, "finish": c.finish} for c in _move_targets(db, user, coin)]


class MoveIn(BaseModel):
    collection_id: int


@router.post("/{inventory_number}/move", response_model=CoinDetail)
def move_coin(inventory_number: str, body: MoveIn, db: Session = Depends(get_db), user: User = Depends(current_user)):
    """Move a coin to another collection of the same series (or a type set that includes it). Its inventory number,
    photos, prices and history come along."""
    coin = get_owned_coin(db, user, inventory_number)
    target = get_owned_collection(db, user, body.collection_id)
    if target.id not in {c.id for c in _move_targets(db, user, coin)}:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, f"A {coin.coin_type.name} can't go in {target.name}.")
    # Same rules as saving the coin there (e.g. proofs only in proof collections).
    _validate(CoinFields.model_validate(coin, from_attributes=True), target, coin.coin_type)
    coin.collection_id = target.id
    db.commit()
    db.refresh(coin)
    return coin_detail(coin)
