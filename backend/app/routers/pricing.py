import httpx
from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session

from ..auth import current_user
from ..db import get_db
from ..models import PriceQuote, User
from ..schemas import CoinDetail, LookupResult, ManualQuoteIn, ValuationIn
from ..services import details, greysheet, lookups, price_refresh, purchase_value
from ..services import ebay, grade_prices
from ..services import ngc_images as ngc_images_service
from ..services.history import value_history
from ..services.coins import CUSTOM, coin_detail, duplicate_info, find_duplicate_cert, latest_quote
from .coins import get_owned_coin

router = APIRouter(prefix="/api", tags=["pricing", "lookups"])


@router.get("/lookup", response_model=LookupResult)
def cert_lookup(
    service: str = Query(..., description="PCGS, NGC, ANACS or CACG"),
    cert: str = Query(..., min_length=1, max_length=30),
    user: User = Depends(current_user),
):
    try:
        return lookups.lookup(service, cert, user_id=user.id)
    except lookups.LookupError as e:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, str(e))
    except httpx.HTTPError as e:
        raise HTTPException(status.HTTP_502_BAD_GATEWAY, f"Lookup service error: {e}")


@router.get("/coins/{inventory_number}/grade-prices")
def grade_price_table(inventory_number: str, db: Session = Depends(get_db), user: User = Depends(current_user)):
    """CPG and est. wholesale for every grade of this coin's issue (saved whenever the issue is priced)."""
    coin = get_owned_coin(db, user, inventory_number)
    return grade_prices.table_for(db, coin) or {"rows": None}


@router.get("/coins/{inventory_number}/ebay")
def ebay_listings(inventory_number: str, db: Session = Depends(get_db), user: User = Depends(current_user)):
    """Current eBay listings for this coin's date, mint, service and grade (asking prices, not sales)."""
    coin = get_owned_coin(db, user, inventory_number)
    if not ebay.configured():
        return {"configured": False, "search_url": ebay.search_url(ebay.query_for(coin))}
    try:
        return {"configured": True, **ebay.listings_for(coin)}
    except ebay.EbayError as e:
        raise HTTPException(status.HTTP_502_BAD_GATEWAY, str(e))
    except httpx.HTTPError as e:
        raise HTTPException(status.HTTP_502_BAD_GATEWAY, f"Couldn't reach eBay: {e}")


@router.get("/ngc-images")
def ngc_images(link: str = Query(..., max_length=500), _: User = Depends(current_user)):
    """Full-size obverse and reverse photo URLs from one NGC photo link the user pasted."""
    try:
        return ngc_images_service.resolve(link)
    except ngc_images_service.NgcImageError as e:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, str(e))


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


@router.get("/coins/{inventory_number}/history")
def coin_history(inventory_number: str, db: Session = Depends(get_db), user: User = Depends(current_user)):
    """This coin's estimated value over time (see services/history.py), from purchase to today."""
    coin = get_owned_coin(db, user, inventory_number)
    return value_history(db, user.id, coin_id=coin.id)


@router.post("/coins/{inventory_number}/purchase-value", response_model=CoinDetail)
def fill_purchase_value(inventory_number: str, db: Session = Depends(get_db), user: User = Depends(current_user)):
    """Work out the estimated value at purchase from PCGS auction sales, if the coin needs it (one PCGS call,
    shared for a day by coins of the same issue and grade). Quota errors come back as 429."""
    coin = get_owned_coin(db, user, inventory_number)
    if purchase_value.needs_auctions(db, coin):
        try:
            purchase_value.fill_auctions(coin, user.id)
        except lookups.LookupError as e:
            raise HTTPException(status.HTTP_400_BAD_REQUEST, str(e))
        except httpx.HTTPError as e:
            raise HTTPException(status.HTTP_502_BAD_GATEWAY, f"PCGS error: {e}")
        db.commit()
    return coin_detail(coin)


@router.post("/coins/{inventory_number}/cpg", response_model=CoinDetail)
def get_cpg_price(inventory_number: str, db: Session = Depends(get_db), user: User = Depends(current_user)):
    """Fetch the current CPG value from Greysheet and add it to the coin's price history."""
    coin = get_owned_coin(db, user, inventory_number)
    try:
        price_refresh.refresh_cpg(db, coin)
    except greysheet.PricingError as e:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, str(e))
    except httpx.HTTPError as e:
        raise HTTPException(status.HTTP_502_BAD_GATEWAY, f"Greysheet error: {e}")
    db.commit()
    db.refresh(coin)
    return coin_detail(coin)


@router.post("/coins/{inventory_number}/pcgs", response_model=CoinDetail)
def get_pcgs_market(inventory_number: str, db: Session = Depends(get_db), user: User = Depends(current_user)):
    """PCGS Price Guide value, population and the last 10 auction sales for the coin's PCGS # and grade."""
    coin = get_owned_coin(db, user, inventory_number)
    try:
        price_refresh.refresh_pcgs(db, coin)
    except (greysheet.PricingError, lookups.LookupError) as e:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, str(e))
    except httpx.HTTPError as e:
        raise HTTPException(status.HTTP_502_BAD_GATEWAY, f"PCGS error: {e}")
    db.commit()
    db.refresh(coin)
    return coin_detail(coin)


@router.put("/coins/{inventory_number}/valuation", response_model=CoinDetail)
def set_valuation(
    inventory_number: str, body: ValuationIn, db: Session = Depends(get_db), user: User = Depends(current_user)
):
    """Choose how the coin's estimated value is set: from CPG (plus optional toner and holder premiums) or your own
    value. Each change is recorded in the price history.
    """
    coin = get_owned_coin(db, user, inventory_number)
    if body.source == "custom":
        if body.custom_value is None:
            raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, "Enter your estimated value")
        coin.value_source, coin.custom_value = "custom", body.custom_value
        db.add(PriceQuote(coin_id=coin.id, source=CUSTOM, value=body.custom_value,
                          grade_used=details.label(coin), description="Your own estimate"))
    else:
        coin.value_source = "cpg"
        coin.toner_premium = body.toner_premium or None
        coin.holder_premium = body.holder_premium or None
        if coin.toner_premium or coin.holder_premium:
            cpg = latest_quote(coin)
            if cpg is None or cpg.value is None:
                raise HTTPException(status.HTTP_400_BAD_REQUEST, "Get a CPG price first; premiums are added on top of CPG.")
            db.add(price_refresh.premium_quote(coin, cpg.value))
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
            grade_used=f"{coin.grade_prefix or ''}{details.price_grade(coin) or ''}",
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
