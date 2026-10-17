"""Fetch CPG (Greysheet) and PCGS market data for a coin. Shared by the per-coin buttons and refresh-all jobs.

These add rows to the session but don't commit. They raise PricingError / LookupError for problems the user
should see (no grade, ambiguous catalog match...) and httpx.HTTPError for service failures.
"""

from datetime import datetime, timezone
from decimal import Decimal

from sqlalchemy.orm import Session

from ..models import Coin, PriceQuote
from . import catalog, grade_prices, greysheet, quota
from .coins import CPG, GREYSHEET, PCGS_GUIDE, PREMIUM, latest_quote
from .lookups import pcgs


def refresh_cpg(db: Session, coin: Coin) -> bool:
    """Record the coin's current CPG. Returns True if Greysheet was called (False: priced from a sheet saved for
    the same issue in the last day)."""
    greysheet.require_grade(coin)
    gsid = None
    if not coin.pcgs_number:
        # Find the PCGS number from date/mint/designation via the Greysheet catalog.
        match = catalog.resolve_for_coin(db, coin)
        gsid = None if match.pcgs_number else match.gsid
    cached = grade_prices.recent_entry(db, greysheet.sheet_key(coin, gsid))
    if cached is None:
        quota.spend(coin.user_id, "greysheet")
    q = greysheet.fetch_cpg(coin, gsid=gsid, cached=cached)
    sheet = q.pop("sheet")
    if cached is None:
        grade_prices.save_sheet(db, sheet)
    grey = q.pop("greysheet_value")
    record(coin, PriceQuote(source=CPG, **q))
    if grey is not None:
        record(coin, PriceQuote(source=GREYSHEET, **{**q, "value": grey}))
    if (coin.toner_premium or coin.holder_premium) and q["value"] is not None:
        record(coin, premium_quote(coin, q["value"]))
    return cached is None


def record(coin: Coin, quote: PriceQuote) -> None:
    """Add a price to the coin's history only if it changed; an unchanged price just gets re-confirmed.
    Keeps the history (and every page that totals it) from filling with identical rows."""
    last = latest_quote(coin, quote.source)
    if last is not None and last.value == quote.value and last.grade_used == quote.grade_used:
        last.confirmed_at = datetime.now(timezone.utc)
        return
    coin.price_quotes.insert(0, quote)  # the relationship is newest first


def premium_quote(coin: Coin, cpg: Decimal) -> PriceQuote:
    """A price-history row for CPG plus the coin's toner and/or holder premium."""
    toner, holder = coin.toner_premium or Decimal(0), coin.holder_premium or Decimal(0)
    parts = [f"CPG ${cpg:,.2f}"]
    if toner:
        parts.append(f"toner premium ${toner:,.2f}")
    if holder:
        parts.append(f"holder premium ${holder:,.2f}")
    return PriceQuote(
        coin_id=coin.id,
        source=PREMIUM,
        value=cpg + toner + holder,
        grade_used=f"{coin.grade_prefix or ''}{coin.grade or ''}",
        description="Estimate: " + " + ".join(parts),
    )


def refresh_pcgs(db: Session, coin: Coin) -> bool:
    """PCGS Price Guide, population and last 10 auction sales. Uses 2 of PCGS's 1,000 daily API calls."""
    greysheet.require_grade(coin)
    if not coin.pcgs_number:
        catalog.resolve_for_coin(db, coin)
    if not coin.pcgs_number:
        raise greysheet.PricingError("This coin needs a PCGS number. Use Find on the edit page.")
    data, called = pcgs.market_cached(
        coin.pcgs_number, coin.grade, coin.grade_plus, before_call=lambda: quota.spend(coin.user_id, "pcgs", 2)
    )
    coin.pcgs_market = {**data, "fetched_at": data.get("fetched_at") or datetime.now(timezone.utc).isoformat()}
    if data["price_guide"] is not None:
        record(
            coin,
            PriceQuote(
                source=PCGS_GUIDE,
                value=Decimal(data["price_guide"]),
                grade_used=data["grade"],
                description=f"PCGS Price Guide #{data['pcgs_number']}",
                raw={"population": data["population"], "pop_higher": data["pop_higher"]},
            ),
        )
    return called
