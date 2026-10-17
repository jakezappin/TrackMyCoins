from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..auth import current_user
from ..db import get_db
from ..models import Coin, Collection, User
from ..schemas import CoinDetail, CoinFields, CoinIn, CoinUpdate
from ..services.coins import coin_detail, duplicate_info, find_duplicate_cert, next_inventory_number
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


def _validate(body: CoinFields, collection: Collection) -> dict:
    marks = collection.coin_type.mint_marks
    if marks and body.mint_mark not in marks:
        raise HTTPException(
            status.HTTP_422_UNPROCESSABLE_CONTENT,
            f"Mint mark must be one of {', '.join(marks)} for {collection.coin_type.name}",
        )
    data = body.model_dump(exclude={"collection_id", "lookup_raw"})
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
    data = _validate(body, col)
    _reject_duplicate(db, user, data)
    coin = Coin(
        **data,
        user_id=user.id,
        coin_type_id=col.coin_type_id,
        collection_id=col.id,
        inventory_number=next_inventory_number(db, user.id, col.coin_type),
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
    if col.coin_type_id != coin.coin_type_id:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "A coin can only move to a collection of the same coin type")
    data = _validate(body, col)
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
