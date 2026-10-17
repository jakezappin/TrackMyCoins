from datetime import datetime, timezone
from decimal import Decimal

import httpx
from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session

from ..auth import current_user
from ..db import get_db
from ..models import PriceQuote, User
from ..schemas import CoinDetail, LookupResult, ManualQuoteIn
from ..services import catalog, greysheet, lookups
from ..services.lookups import pcgs
from ..services.coins import CPG, GREYSHEET, PCGS_GUIDE, coin_detail, duplicate_info, find_duplicate_cert
from .coins import get_owned_coin

router = APIRouter(prefix="/api", tags=["pricing", "lookups"])


@router.get("/lookup", response_model=LookupResult)
def cert_lookup(
    service: str = Query(..., description="PCGS, NGC, ANACS or CACG"),
    cert: str = Query(..., min_length=1, max_length=30),
    _: User = Depends(current_user),
):
    try:
        return lookups.lookup(service, cert)
    except lookups.LookupError as e:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, str(e))
    except httpx.HTTPError as e:
        raise HTTPException(status.HTTP_502_BAD_GATEWAY, f"Lookup service error: {e}")


@router.get("/cert-check")
def cert_check(
    service: str,
    cert: str,
    exclude: str | None = Query(None, description="inventory number of the coin being edited"),
    db: Session = Depends(get_db),
    user: User = Depends(current_user),
):
    """Is this cert already on hand in one of the user's collections?"""
    exclude_id = get_owned_coin(db, user, exclude).id if exclude else None
    dup = find_duplicate_cert(db, user.id, service.upper(), cert, exclude_id)
    return {"duplicate": duplicate_info(dup) if dup else None}


@router.post("/coins/{inventory_number}/cpg", response_model=CoinDetail)
def get_cpg_price(inventory_number: str, db: Session = Depends(get_db), user: User = Depends(current_user)):
    """Fetch the current CPG value from Greysheet and add it to the coin's price history."""
    coin = get_owned_coin(db, user, inventory_number)
    try:
        greysheet.require_grade(coin)
        gsid = None
        if not coin.pcgs_number:
            # Find the PCGS number from date/mint/designation via the Greysheet catalog.
            match = catalog.resolve_for_coin(db, coin)
            gsid = None if match.pcgs_number else match.gsid
        q = greysheet.fetch_cpg(coin, gsid=gsid)
    except greysheet.PricingError as e:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, str(e))
    except httpx.HTTPError as e:
        raise HTTPException(status.HTTP_502_BAD_GATEWAY, f"Greysheet error: {e}")
    grey = q.pop("greysheet_value")
    db.add(PriceQuote(coin_id=coin.id, source=CPG, **q))
    if grey is not None:
        db.add(PriceQuote(coin_id=coin.id, source=GREYSHEET, **{**q, "value": grey}))
    db.commit()
    db.refresh(coin)
    return coin_detail(coin)


@router.post("/coins/{inventory_number}/pcgs", response_model=CoinDetail)
def get_pcgs_market(inventory_number: str, db: Session = Depends(get_db), user: User = Depends(current_user)):
    """PCGS Price Guide value, population and the last 10 auction sales for the coin's PCGS # and grade.

    Uses 2 of the PCGS API's 1,000 daily calls.
    """
    coin = get_owned_coin(db, user, inventory_number)
    try:
        greysheet.require_grade(coin)
        if not coin.pcgs_number:
            catalog.resolve_for_coin(db, coin)  # find it from date/mint/designation
        if not coin.pcgs_number:
            raise greysheet.PricingError("This coin needs a PCGS number. Use Find on the edit page.")
        data = pcgs.market(coin.pcgs_number, coin.grade, coin.grade_plus)
    except (greysheet.PricingError, lookups.LookupError) as e:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, str(e))
    except httpx.HTTPError as e:
        raise HTTPException(status.HTTP_502_BAD_GATEWAY, f"PCGS error: {e}")

    now = datetime.now(timezone.utc)
    coin.pcgs_market = {**data, "fetched_at": now.isoformat()}
    if data["price_guide"] is not None:
        db.add(
            PriceQuote(
                coin_id=coin.id,
                source=PCGS_GUIDE,
                value=Decimal(data["price_guide"]),
                grade_used=data["grade"],
                description=f"PCGS Price Guide #{data['pcgs_number']}",
                raw={"population": data["population"], "pop_higher": data["pop_higher"]},
            )
        )
    db.commit()
    db.refresh(coin)
    return coin_detail(coin)


@router.post("/coins/{inventory_number}/price-quotes", response_model=CoinDetail)
def add_manual_quote(
    inventory_number: str, body: ManualQuoteIn, db: Session = Depends(get_db), user: User = Depends(current_user)
):
    """Record a price by hand, e.g. a CPG value read from the printed guide."""
    coin = get_owned_coin(db, user, inventory_number)
    db.add(
        PriceQuote(
            coin_id=coin.id,
            source=body.source.upper(),
            value=body.value,
            description=body.description or "Entered manually",
            grade_used=f"{coin.grade_prefix or ''}{coin.grade or ''}",
        )
    )
    db.commit()
    db.refresh(coin)
    return coin_detail(coin)


@router.delete("/price-quotes/{quote_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_quote(quote_id: int, db: Session = Depends(get_db), user: User = Depends(current_user)):
    q = db.get(PriceQuote, quote_id)
    if q is None or q.coin.user_id != user.id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Price quote not found")
    db.delete(q)
    db.commit()
