from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import func, select
from sqlalchemy.orm import Session, selectinload

from ..auth import current_user
from ..db import get_db
from ..models import Coin, CoinType, Collection, User
from ..schemas import (
    CoinOut,
    CoinTypeOut,
    CollectionIn,
    CollectionRename,
    CollectionWithSummary,
    FinishOut,
)
from ..series import (
    BY_SLUG,
    CATEGORIES,
    FINISHES,
    collection_type_label,
    collection_type_slug,
    parse_collection_type_slug,
)
from ..services.coins import coin_out, collection_summary, next_collection_number, on_hand, sold

router = APIRouter(prefix="/api", tags=["collections"])


def get_owned_collection(db: Session, user: User, collection_id: int) -> Collection:
    col = db.get(Collection, collection_id)
    if col is None or col.user_id != user.id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Collection not found")
    return col


def _with_summary(db: Session, col: Collection) -> CollectionWithSummary:
    return CollectionWithSummary(
        id=col.id,
        number=col.number,
        name=col.name,
        coin_type_id=col.coin_type_id,
        coin_type_slug=col.coin_type.slug,
        finish=col.finish,
        collection_type_slug=collection_type_slug(col.coin_type.slug, col.finish),
        collection_type_label=_type_label(col.coin_type, col.finish),
        created_at=col.created_at,
        last_viewed_at=col.last_viewed_at,
        summary=collection_summary(db, col.id),
    )


def _type_label(ct: CoinType, finish: str) -> str:
    s = BY_SLUG.get(ct.slug)
    return collection_type_label(s, finish) if s else ct.plural or ct.name


def _type_by_slug(db: Session, slug: str) -> CoinType:
    ct = db.scalar(select(CoinType).where(CoinType.slug == slug))
    if ct is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Unknown coin type")
    return ct


def _coin_query(user: User):
    return (
        select(Coin)
        .where(Coin.user_id == user.id)
        .options(selectinload(Coin.photos), selectinload(Coin.price_quotes))
        .order_by(Coin.year, Coin.mint_mark, Coin.inventory_number)
    )


@router.get("/coin-types", response_model=list[CoinTypeOut])
def list_coin_types(db: Session = Depends(get_db), _: User = Depends(current_user)):
    """All series, in catalog order (by category, then as listed in app/series.py)."""
    order = {slug: i for i, slug in enumerate(BY_SLUG)}
    types = db.scalars(select(CoinType)).all()
    types = sorted(
        types,
        key=lambda t: (CATEGORIES.index(t.category) if t.category in CATEGORIES else 99, order.get(t.slug, 999)),
    )
    return [
        CoinTypeOut(
            id=t.id,
            name=t.name,
            plural=t.plural or t.name,
            slug=t.slug,
            category=t.category,
            inventory_prefix=t.inventory_prefix,
            mint_marks=t.mint_marks,
            metal=BY_SLUG[t.slug].metal if t.slug in BY_SLUG else "silver",
            finishes=[
                FinishOut(
                    code=f,
                    label=FINISHES[f][1],
                    collection_type_slug=collection_type_slug(t.slug, f),
                    collection_type_label=_type_label(t, f),
                )
                for f in (t.finishes or ["MS"])
            ],
        )
        for t in types
    ]


@router.get("/coin-types/{slug}/sold", response_model=list[CoinOut])
def sold_coins(slug: str, db: Session = Depends(get_db), user: User = Depends(current_user)):
    q = sold(_coin_query(user).where(Coin.coin_type_id == _type_by_slug(db, slug).id))
    return [coin_out(c) for c in db.scalars(q).all()]


@router.get("/collections", response_model=list[CollectionWithSummary])
def list_collections(db: Session = Depends(get_db), user: User = Depends(current_user)):
    cols = db.scalars(
        select(Collection).where(Collection.user_id == user.id).order_by(Collection.name)
    ).all()
    return [_with_summary(db, c) for c in cols]


@router.post("/collections", response_model=CollectionWithSummary, status_code=status.HTTP_201_CREATED)
def create_collection(body: CollectionIn, db: Session = Depends(get_db), user: User = Depends(current_user)):
    coin_type = db.get(CoinType, body.coin_type_id)
    if coin_type is None:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Unknown coin type")
    if body.finish not in (coin_type.finishes or ["MS"]):
        raise HTTPException(status.HTTP_400_BAD_REQUEST, f"{coin_type.plural} don't have a {FINISHES[body.finish][1]} collection type")
    name = body.name.strip()
    if db.scalar(select(Collection).where(Collection.user_id == user.id, Collection.name == name)):
        raise HTTPException(status.HTTP_409_CONFLICT, "You already have a collection with that name")
    col = Collection(
        user_id=user.id,
        coin_type_id=coin_type.id,
        finish=body.finish,
        name=name,
        number=next_collection_number(db, user.id, coin_type, body.finish),
    )
    db.add(col)
    db.commit()
    return _with_summary(db, col)


@router.get("/collections/by-number/{slug}/{number}", response_model=CollectionWithSummary)
def get_collection_by_number(
    slug: str, number: int, db: Session = Depends(get_db), user: User = Depends(current_user)
):
    """Resolve a URL like /collections/morgan-dollars/1 or /collections/kennedy-half-dollars-proof/2."""
    parsed = parse_collection_type_slug(slug)
    if parsed is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Unknown collection type")
    series, finish = parsed
    col = db.scalar(
        select(Collection).where(
            Collection.user_id == user.id,
            Collection.coin_type_id == _type_by_slug(db, series.slug).id,
            Collection.finish == finish,
            Collection.number == number,
        )
    )
    if col is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Collection not found")
    col.last_viewed_at = datetime.now(timezone.utc)
    db.commit()
    return _with_summary(db, col)


@router.get("/collections/{collection_id}", response_model=CollectionWithSummary)
def get_collection(collection_id: int, db: Session = Depends(get_db), user: User = Depends(current_user)):
    return _with_summary(db, get_owned_collection(db, user, collection_id))


@router.patch("/collections/{collection_id}", response_model=CollectionWithSummary)
def rename_collection(
    collection_id: int, body: CollectionRename, db: Session = Depends(get_db), user: User = Depends(current_user)
):
    col = get_owned_collection(db, user, collection_id)
    col.name = body.name.strip()
    db.commit()
    return _with_summary(db, col)


@router.delete("/collections/{collection_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_collection(collection_id: int, db: Session = Depends(get_db), user: User = Depends(current_user)):
    col = get_owned_collection(db, user, collection_id)
    count = db.scalar(select(func.count()).select_from(Coin).where(Coin.collection_id == col.id))
    if count:
        raise HTTPException(
            status.HTTP_409_CONFLICT,
            "This collection still has coins (including sold ones). Move them to another collection first.",
        )
    db.delete(col)
    db.commit()


@router.get("/collections/{collection_id}/coins", response_model=list[CoinOut])
def collection_coins(collection_id: int, db: Session = Depends(get_db), user: User = Depends(current_user)):
    col = get_owned_collection(db, user, collection_id)
    q = on_hand(_coin_query(user).where(Coin.collection_id == col.id))
    return [coin_out(c) for c in db.scalars(q).all()]
