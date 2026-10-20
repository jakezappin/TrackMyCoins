"""Fetch CPG (Greysheet) and PCGS market data for a coin. Shared by the per-coin buttons and refresh-all jobs.

These add rows to the session but don't commit. They raise PricingError / LookupError for problems the user
should see (no grade, ambiguous catalog match...) and httpx.HTTPError for service failures.
"""

from datetime import datetime, timedelta, timezone
from decimal import Decimal

from sqlalchemy.orm import Session

from .. import grades
from ..models import Coin, PriceQuote
from . import catalog, details, grade_prices, greysheet, price_archive, quota
from .coins import CPG, GREYSHEET, PCGS_GUIDE, PREMIUM, coin_melt, latest_quote
from .lookups import pcgs


def _not_error(coin: Coin) -> None:
    if coin.is_error:
        raise greysheet.PricingError("Error coins aren't in the price guides. Enter your own estimated value.")


SAVED_FOR = timedelta(days=7)  # Greysheet updates CPG weekly: a saved sheet this old still prices a coin by itself


def _cpg(db: Session, coin: Coin, saved_only: bool = False) -> tuple[dict, bool] | None:
    """(the coin's CPG quote, whether Greysheet was called). `saved_only`: only from a price sheet saved for the
    same issue this week (None if there isn't one), never Greysheet."""
    _not_error(coin)
    greysheet.require_grade(coin)
    gsid = None
    if not coin.pcgs_number:
        # Find the PCGS number from date/mint/designation via the Greysheet catalog.
        match = catalog.resolve_for_coin(db, coin)
        gsid = None if match.pcgs_number else match.gsid
    cached = grade_prices.recent_entry(db, greysheet.sheet_key(coin, gsid), SAVED_FOR if saved_only else None)
    if cached is None:
        if saved_only:
            return None
        quota.spend(coin.user_id, "greysheet")
    q = greysheet.fetch_cpg(coin, gsid=gsid, cached=cached)
    sheet = q.pop("sheet")
    if cached is None:
        grade_prices.save_sheet(db, sheet)
    return q, cached is None


def _record_cpg(coin: Coin, q: dict) -> None:
    grey = q.pop("greysheet_value")
    record(coin, PriceQuote(source=CPG, **q))
    if grey is not None:
        record(coin, PriceQuote(source=GREYSHEET, **{**q, "value": grey}))
    if coin.value_source != "custom" and (coin.toner_premium or coin.holder_premium or coin.lowball_premium) and q["value"] is not None:
        record(coin, premium_quote(coin, q["value"]))


def refresh_cpg(db: Session, coin: Coin) -> bool:
    """Record the coin's current CPG. Returns True if Greysheet was called (False: priced from a sheet saved for
    the same issue in the last day)."""
    q, called = _cpg(db, coin)
    _record_cpg(coin, q)
    return called


def fill_cpg_from_saved(db: Session, coin: Coin) -> bool:
    """A coin with no CPG at its grade yet takes it from a price sheet already saved this week for the same issue
    (another coin's lookup): no Greysheet call. Returns True if a price was recorded. Never raises."""
    if coin.is_error or not coin.pcgs_number or greysheet.is_set(coin) or not details.price_grade(coin):
        return False
    last = latest_quote(coin, CPG)
    if last is not None and (last.raw or {}).get("row", {}).get("Grade") == details.price_grade(coin):
        return False
    try:
        got = _cpg(db, coin, saved_only=True)
    except Exception:  # no match, no price at this grade...: the button still works
        return False
    if got is None:
        return False
    _record_cpg(coin, got[0])
    return True


def cpg_at_grade(db: Session, coin: Coin, grade: int) -> dict:
    """What CPG would be if the coin had this numeric grade, without changing the coin (for a raw coin with none
    yet). The price sheet it comes from is saved, so saving the grade afterwards needs no second call."""
    before = coin.grade, coin.grade_prefix, coin.grade_plus
    coin.grade, coin.grade_prefix, coin.grade_plus = grade, prefix_for(coin, grade), False
    try:
        q, _ = _cpg(db, coin)
    finally:
        coin.grade, coin.grade_prefix, coin.grade_plus = before
    return {"value": q["value"], "grade_used": q["grade_used"], "description": q["description"]}


def prefix_for(coin: Coin, grade: int) -> str:
    """The letters a numeric grade goes with: PR in a proof collection, else MS / AU / XF... by number."""
    if coin.collection and coin.collection.finish != "MS":
        return "PR"
    return grades.letters_for(grade) or "MS"


def record(coin: Coin, quote: PriceQuote) -> None:
    """Add a price to the coin's history only if it changed; an unchanged price just gets re-confirmed.
    Keeps the history (and every page that totals it) from filling with identical rows."""
    last = latest_quote(coin, quote.source)
    if last is not None and last.value == quote.value and last.grade_used == quote.grade_used:
        last.confirmed_at = datetime.now(timezone.utc)
        return
    coin.price_quotes.insert(0, quote)  # the relationship is newest first


def premium_quote(coin: Coin, cpg: Decimal) -> PriceQuote:
    """A price-history row for CPG (a Details coin's share of it) plus the coin's toner, holder and lowball premiums."""
    toner, holder = coin.toner_premium or Decimal(0), coin.holder_premium or Decimal(0)
    lowball = coin.lowball_premium or Decimal(0)
    if coin.details:
        cpg = details.adjust(coin, cpg, coin_melt(coin))
    parts = [f"{'Details value' if coin.details else 'CPG'} ${cpg:,.2f}"]
    if toner:
        parts.append(f"toner premium ${toner:,.2f}")
    if holder:
        parts.append(f"holder premium ${holder:,.2f}")
    if lowball:
        parts.append(f"lowball premium ${lowball:,.2f}")
    return PriceQuote(
        coin_id=coin.id,
        source=PREMIUM,
        value=cpg + toner + holder + lowball,
        grade_used=details.label(coin),
        description="Estimate: " + " + ".join(parts),
    )


def refresh_pcgs(db: Session, coin: Coin, cache_only: bool = False) -> bool:
    """PCGS Price Guide, population and last 10 auction sales. Uses 2 of PCGS's 100 daily API calls, unless this
    issue and grade was fetched in the last week. `cache_only`: only what's stored (the bulk refresh), never PCGS."""
    _not_error(coin)
    greysheet.require_grade(coin)
    if not coin.pcgs_number:
        catalog.resolve_for_coin(db, coin)
    if not coin.pcgs_number:
        raise greysheet.PricingError("This coin needs a PCGS number. Use Find on the edit page.")
    grade = details.price_grade(coin)
    data, called = pcgs.market_cached(
        coin.pcgs_number, grade, coin.grade_plus and not coin.details,
        before_call=lambda: quota.spend(coin.user_id, "pcgs", 2), cache_only=cache_only,
    )
    if data is None:
        return False
    coin.pcgs_market = {**data, "fetched_at": data.get("fetched_at") or datetime.now(timezone.utc).isoformat()}
    price_archive.save_market(db, data, grade, coin.grade_plus and not coin.details)
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
