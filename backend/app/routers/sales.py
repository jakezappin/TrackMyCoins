"""Sales Tracker: record sales and trades of coins and bullion from one page, and see their history."""

from datetime import date, datetime, timezone
from decimal import Decimal

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel, Field, field_validator
from sqlalchemy.orm import Session

from ..auth import current_user
from ..db import get_db
from ..models import User
from ..schemas import SoldVia
from ..services import sales as svc

router = APIRouter(prefix="/api/sales", tags=["sales"])

Money = Decimal


class Line(BaseModel):
    ref: str = Field(min_length=3, max_length=40)  # "coin:MOR-00012" | "bullion:AG-00003"
    price: Decimal = Field(ge=0, max_digits=12, decimal_places=2)


class PartyIn(BaseModel):
    sale_date: date
    counterparty: str | None = Field(default=None, max_length=200)
    dealer_id: int | None = None
    notes: str | None = Field(default=None, max_length=5000)

    @field_validator("sale_date")
    @classmethod
    def _not_future(cls, v: date):
        if v > datetime.now(timezone.utc).date():
            raise ValueError("The date is in the future.")
        return v


class SaleIn(PartyIn):
    sold_via: SoldVia | None = None
    sold_via_other: str | None = Field(default=None, max_length=60)
    items: list[Line] = Field(min_length=1, max_length=200)


class TradeIn(PartyIn):
    out: list[Line] = Field(min_length=1, max_length=200)
    came_in: list[Line] = Field(min_length=1, max_length=200)
    cash_received: Decimal | None = Field(default=None, ge=0, max_digits=12, decimal_places=2)
    cash_paid: Decimal | None = Field(default=None, ge=0, max_digits=12, decimal_places=2)


def _fail(e: svc.SaleError):
    return HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, str(e))


@router.get("")
def history(db: Session = Depends(get_db), user: User = Depends(current_user)):
    return svc.history(db, user)


@router.get("/items")
def items(q: str = Query("", max_length=100), held: bool = True, db: Session = Depends(get_db),
          user: User = Depends(current_user)):
    """Coins and bullion to pick from (on hand unless `held` is false)."""
    return svc.search(db, user, q, held=held)


@router.post("/sale", status_code=status.HTTP_201_CREATED)
def record_sale(body: SaleIn, db: Session = Depends(get_db), user: User = Depends(current_user)):
    party = svc.Party(body.sale_date, body.sold_via, (body.sold_via_other or "").strip() or None, body.counterparty,
                      body.dealer_id, body.notes)
    try:
        sale = svc.record_sale(db, user, party, [(l.ref, l.price) for l in body.items])
    except svc.SaleError as e:
        raise _fail(e)
    db.commit()
    return {"id": sale.id}


@router.post("/trade", status_code=status.HTTP_201_CREATED)
def record_trade(body: TradeIn, db: Session = Depends(get_db), user: User = Depends(current_user)):
    party = svc.Party(body.sale_date, "trade", None, body.counterparty, body.dealer_id, body.notes)
    try:
        sale = svc.record_trade(db, user, party, [(l.ref, l.price) for l in body.out],
                                [(l.ref, l.price) for l in body.came_in], body.cash_received, body.cash_paid)
    except svc.SaleError as e:
        raise _fail(e)
    db.commit()
    return {"id": sale.id}


@router.delete("/{sale_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete(sale_id: int, delete_received: bool = False, db: Session = Depends(get_db),
           user: User = Depends(current_user)):
    """Undo a sale or trade. `delete_received`: also delete what came in from a trade."""
    try:
        svc.delete(db, user, sale_id, delete_received)
    except svc.SaleError:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Not found")
    db.commit()
