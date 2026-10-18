"""Bullion: pure metal content, values from spot prices (live and daily history), value over time, and selling
part of a roll or tube. Separate from the numismatic side: no grades, catalog or price guides.

Spot history (USD per troy ounce, one price a day) is kept in SpotPrice. It ships with the app (a bundled file of
daily prices since 2000), today's live price is recorded every day, and with a gold-api.com key (GOLD_API_KEY)
any missing days are filled in from its price history API.
"""

import bisect
import csv
import gzip
import logging
from dataclasses import dataclass
from datetime import date, datetime, timedelta, timezone
from decimal import ROUND_HALF_UP, Decimal
from pathlib import Path

import httpx
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from ..config import get_settings
from ..models import BullionCounter, BullionItem, SpotPrice
from . import metals

log = logging.getLogger(__name__)

METALS = ("silver", "gold", "platinum", "palladium")
PREFIX = {"silver": "AG", "gold": "AU", "platinum": "PT", "palladium": "PD"}
# Purities offered per metal (the form's choices); the server accepts any share between 0 and 1.
PURITIES = {
    "silver": ["0.9999", "0.999", "0.925", "0.9", "0.8", "0.4", "0.35"],
    "gold": ["0.9999", "0.999", "0.9167", "0.9"],
    "platinum": ["0.9995", "0.999"],
    "palladium": ["0.9995", "0.999"],
}
UNITS = {"ozt": Decimal(1), "g": Decimal(1) / Decimal("31.1034768"), "kg": Decimal(1000) / Decimal("31.1034768")}
# Junk silver bought by face value: pure troy ounces per $1 face (circulated-wear standards).
FACE_OZ = {Decimal("0.9"): Decimal("0.715"), Decimal("0.4"): Decimal("0.2958"), Decimal("0.35"): Decimal("1.1252")}
PACKAGING = ("single", "roll", "tube", "box")
SPOT_GAP_DAYS = 7  # a history price this old still stands in (weekends, holidays)
HISTORY_URL = "https://api.gold-api.com/history"
HISTORY_START = date(2000, 1, 1)

CENTS = Decimal("0.01")


def _d(v) -> Decimal | None:
    return None if v is None else Decimal(str(v))


def pure_oz(item: BullionItem) -> Decimal:
    """Troy ounces of pure metal in the item (all pieces)."""
    purity = _d(item.purity) or Decimal(0)
    metal = item.collection.metal if getattr(item, "collection", None) is not None else "silver"
    if item.face_value is not None and metal == "silver":
        per_dollar = FACE_OZ.get(purity.normalize()) or FACE_OZ.get(purity)
        if per_dollar is not None:
            return (_d(item.face_value) * per_dollar).quantize(Decimal("0.0001"))
    weight = _d(item.weight) or Decimal(0)
    oz = weight * UNITS.get(item.weight_unit, Decimal(1)) * purity * (item.quantity or 1)
    return oz.quantize(Decimal("0.0001"))


def started(item: BullionItem) -> date:
    if item.purchase_date:
        return item.purchase_date
    created = item.created_at if item.created_at.tzinfo else item.created_at.replace(tzinfo=timezone.utc)
    return created.date()


def long_term(bought: date, sold: date) -> bool:
    """Held more than a year (U.S. tax): sold after the purchase's one-year anniversary. Selling on the
    anniversary itself is still short-term. Bought on Feb 29: the anniversary is Feb 28."""
    try:
        anniversary = bought.replace(year=bought.year + 1)
    except ValueError:
        anniversary = date(bought.year + 1, 2, 28)
    return sold > anniversary


def is_sold(item: BullionItem) -> bool:
    return item.sale_price is not None or item.sale_date is not None


def next_inventory_number(db: Session, user_id: int, metal: str) -> str:
    counter = db.get(BullionCounter, (user_id, metal))
    if counter is None:
        counter = BullionCounter(user_id=user_id, metal=metal, next_seq=1)
        db.add(counter)
    seq = counter.next_seq
    counter.next_seq = seq + 1
    return f"{PREFIX[metal]}-{seq:05d}"


# ---- Spot prices --------------------------------------------------------------------------------------------

class SpotSeries:
    """Daily prices for one metal, looked up by date (the latest price within a week before it)."""

    def __init__(self, rows: list[tuple[date, Decimal]]):
        self.days = [d for d, _ in rows]
        self.prices = [p for _, p in rows]

    @classmethod
    def load(cls, db: Session, metal: str) -> "SpotSeries":
        rows = db.execute(select(SpotPrice.day, SpotPrice.price).where(SpotPrice.metal == metal).order_by(SpotPrice.day))
        return cls([(d, Decimal(str(p))) for d, p in rows])

    def on(self, day: date) -> Decimal | None:
        i = bisect.bisect_right(self.days, day) - 1
        if i < 0 or (day - self.days[i]).days > SPOT_GAP_DAYS:
            return None
        return self.prices[i]


def live_spot(metal: str) -> Decimal | None:
    price, _ = metals.spot(metal)
    return None if price is None else Decimal(str(price))


def record_live(db: Session) -> int:
    """Store today's live price for each metal (once a day; later checks the same day update it)."""
    today = datetime.now(timezone.utc).date()
    n = 0
    for metal in METALS:
        price = live_spot(metal)
        if price is None:
            continue
        row = db.scalar(select(SpotPrice).where(SpotPrice.metal == metal, SpotPrice.day == today))
        if row is None:
            db.add(SpotPrice(metal=metal, day=today, price=price, source="live"))
            n += 1
        elif row.source == "live":
            row.price = price
    db.commit()
    return n


def _history_rows(body) -> list[tuple[date, Decimal]]:
    """Parse gold-api.com's history response: [{"day": "2024-01-15...", "avg_price": 23.1}, ...]."""
    out = []
    for r in body if isinstance(body, list) else body.get("data") or []:
        when = r.get("day") or r.get("date") or r.get("timestamp")
        price = r.get("avg_price") or r.get("max_price") or r.get("price")
        if not when or price in (None, ""):
            continue
        try:
            day = date.fromisoformat(str(when)[:10]) if not str(when).isdigit() else \
                datetime.fromtimestamp(int(when), tz=timezone.utc).date()
            value = Decimal(str(price))
        except (ValueError, ArithmeticError):
            continue
        if value > 0:
            out.append((day, value))
    return out


def fetch_history(metal: str, start: date, end: date) -> list[tuple[date, Decimal]]:
    """Daily average prices from gold-api.com (needs GOLD_API_KEY; free tier: 10 requests an hour)."""
    key = get_settings().gold_api_key
    if not key:
        return []
    params = {
        "symbol": metals.SYMBOLS[metal], "groupBy": "day", "aggregation": "avg", "orderBy": "asc",
        "startTimestamp": int(datetime(start.year, start.month, start.day, tzinfo=timezone.utc).timestamp()),
        "endTimestamp": int(datetime(end.year, end.month, end.day, 23, 59, tzinfo=timezone.utc).timestamp()),
    }
    r = httpx.get(HISTORY_URL, params=params, headers={"x-api-key": key}, timeout=60)
    r.raise_for_status()
    return _history_rows(r.json())


def save_history(db: Session, metal: str, rows: list[tuple[date, Decimal]]) -> int:
    have = {d for (d,) in db.execute(select(SpotPrice.day).where(SpotPrice.metal == metal))}
    new = [SpotPrice(metal=metal, day=d, price=p, source="history") for d, p in rows if d not in have]
    db.add_all(new)
    db.commit()
    return len(new)


def update_history(db: Session, max_requests: int = 8) -> dict:
    """Fill in past prices (once) and the last few days (daily). Uses at most `max_requests` API calls."""
    if not get_settings().gold_api_key:
        return {"skipped": "no GOLD_API_KEY"}
    today = datetime.now(timezone.utc).date()
    done: dict[str, int] = {}
    calls = 0
    for metal in METALS:
        if calls >= max_requests:
            break
        first, last = db.execute(
            select(func.min(SpotPrice.day), func.max(SpotPrice.day))
            .where(SpotPrice.metal == metal, SpotPrice.source == "history")
        ).one()
        try:
            if first is None:
                # The whole history, once (where the source starts later, e.g. palladium in 2017, that's that).
                rows = fetch_history(metal, HISTORY_START, today)
            elif last is None or (today - last).days >= 1:
                rows = fetch_history(metal, last - timedelta(days=3), today)  # top up
            else:
                continue
            calls += 1
        except (httpx.HTTPError, ValueError) as e:
            log.info("spot history for %s: %s", metal, e)
            calls += 1
            continue
        done[metal] = save_history(db, metal, rows)
    return done


# ---- Values -------------------------------------------------------------------------------------------------

@dataclass
class ItemValue:
    oz: Decimal
    spot_now: Decimal | None
    value_now: Decimal | None
    spot_at_purchase: Decimal | None
    value_at_purchase: Decimal | None
    premium_pct: float | None  # paid over melt on the purchase date


def value(item: BullionItem, metal: str, series: SpotSeries | None = None, spot_now: Decimal | None = None) -> ItemValue:
    oz = pure_oz(item)
    now = spot_now if spot_now is not None else live_spot(metal)
    at = series.on(started(item)) if series else None
    v_at = (oz * at).quantize(CENTS, ROUND_HALF_UP) if at is not None else None
    premium = None
    if v_at and item.price_paid is not None and v_at > 0:
        premium = round(float(_d(item.price_paid) / v_at - 1) * 100, 1)
    return ItemValue(oz=oz, spot_now=now, value_now=(oz * now).quantize(CENTS, ROUND_HALF_UP) if now is not None else None,
                     spot_at_purchase=at, value_at_purchase=v_at, premium_pct=premium)


def summary(items: list[BullionItem], metal_of, spots_now: dict[str, Decimal | None]) -> dict:
    """Totals over the items on hand: pure ounces per metal and value now for everything; cost basis, change and
    average cost per ounce only over items with a price paid (one without isn't free: it's left out and counted
    in `no_cost`). Realized gains only count sales with both prices."""
    held = [i for i in items if not is_sold(i)]
    oz: dict[str, Decimal] = {}
    oz_costed: dict[str, Decimal] = {}
    cost_by: dict[str, Decimal] = {}
    value_now = value_costed = cost = cost_priced = Decimal(0)
    unpriced = no_cost = 0
    for i in held:
        m = metal_of(i)
        o = pure_oz(i)
        oz[m] = oz.get(m, Decimal(0)) + o
        price = spots_now.get(m)
        v = o * price if price is not None else None
        if v is not None:
            value_now += v
        else:
            unpriced += 1
        paid = _d(i.price_paid)
        if paid is None:
            no_cost += 1
            continue
        cost += paid
        cost_by[m] = cost_by.get(m, Decimal(0)) + paid
        oz_costed[m] = oz_costed.get(m, Decimal(0)) + o
        if v is not None:
            value_costed += v
            cost_priced += paid  # the change compares like with like: items with both a cost and a value
    sold = [i for i in items if is_sold(i)]
    realized_items = [i for i in sold if i.sale_price is not None and i.price_paid is not None]
    realized = sum((_d(i.sale_price) - _d(i.price_paid) for i in realized_items), Decimal(0))
    change = value_costed - cost_priced
    return {
        "count": len(held),
        "oz": {m: str(v.quantize(Decimal("0.0001"))) for m, v in oz.items()},
        # What was paid per pure ounce: also the spot price where the stack breaks even.
        "avg_cost_oz": {m: str((cost_by[m] / v).quantize(CENTS)) for m, v in oz_costed.items() if v > 0 and m in cost_by},
        "value": str(value_now.quantize(CENTS)),
        "cost": str(cost.quantize(CENTS)),
        "change": str(change.quantize(CENTS)),
        "change_pct": round(float(change / cost_priced) * 100, 1) if cost_priced else None,
        "unpriced": unpriced,
        "no_cost": no_cost,
        "sold_count": len(sold),
        "realized": str(realized.quantize(CENTS)),
        "realized_count": len(realized_items),
        "spot": {m: (str(p) if p is not None else None) for m, p in spots_now.items()},
    }


def history(db: Session, items: list[BullionItem], metal_of) -> list[dict]:
    """Melt value and cost of the items held over time: a point on the first of each month, on purchase and sale
    dates, and today. Points where a metal has no spot price that day have no value."""
    if not items:
        return []
    series = {m: SpotSeries.load(db, m) for m in {metal_of(i) for i in items}}
    today = datetime.now(timezone.utc).date()
    live = {m: live_spot(m) for m in series}
    # Sold without a date: held until today (the summary already leaves it out).
    spans = [(i, started(i), i.sale_date or (today if i.sale_price is not None else None)) for i in items]
    days = {today} | {s for _, s, _ in spans} | {e for _, _, e in spans if e}
    first = min(s for _, s, _ in spans)
    m = first.replace(day=1)
    while m < today:
        if m > first:
            days.add(m)
        m = (m + timedelta(days=32)).replace(day=1)
    points = []
    for d in sorted(days):
        value_d = cost_d = Decimal(0)
        count = priced = 0
        for i, s, e in spans:
            if s > d or (e is not None and e <= d):
                continue
            count += 1
            cost_d += _d(i.price_paid) or Decimal(0)
            metal = metal_of(i)
            price = live[metal] if d == today and live[metal] is not None else series[metal].on(d)
            if price is not None:
                value_d += pure_oz(i) * price
                priced += 1
        if count == 0:
            continue
        points.append({
            "date": d.isoformat(), "coin_count": count, "priced_count": priced, "cost": str(cost_d.quantize(CENTS)),
            "value": str(value_d.quantize(CENTS)) if priced == count else None, "backfilled": False,
        })
    return points


# ---- Selling part of a roll or tube -------------------------------------------------------------------------

def split_for_sale(db: Session, item: BullionItem, metal: str, *, quantity: int | None = None,
                   face_value: Decimal | None = None) -> BullionItem:
    """Split off the sold part of an item: a new item with the sold pieces (or face value) and its share of the
    cost; the original keeps the rest. Returns the new (sold) item, not yet given sale details."""
    if item.face_value is not None:
        total, part = _d(item.face_value), _d(face_value)
        if part is None or not (0 < part < total):
            raise ValueError(f"Enter a face value between $0 and ${total} (or sell it all).")
        share = part / total
    else:
        total, part = item.quantity or 1, quantity
        if part is None or not (0 < part < total):
            raise ValueError(f"Enter a quantity between 1 and {total - 1} (or sell it all).")
        share = Decimal(part) / Decimal(total)
    cost = _d(item.price_paid)
    sold_cost = (cost * share).quantize(CENTS, ROUND_HALF_UP) if cost is not None else None
    sold = BullionItem(
        user_id=item.user_id, collection_id=item.collection_id,
        inventory_number=next_inventory_number(db, item.user_id, metal),
        description=item.description, packaging=item.packaging if item.face_value is None else item.packaging,
        quantity=part if item.face_value is None else 1, weight=item.weight, weight_unit=item.weight_unit,
        purity=item.purity, face_value=part if item.face_value is not None else None, price_paid=sold_cost,
        purchase_date=item.purchase_date, purchased_from=item.purchased_from,
        notes=f"Split from {item.inventory_number}." + (f"\n{item.notes}" if item.notes else ""),
    )
    if item.face_value is not None:
        item.face_value = total - part
    else:
        item.quantity = total - part
    if cost is not None:
        item.price_paid = cost - sold_cost
    db.add(sold)
    db.flush()
    return sold


# ---- Bundled history ----------------------------------------------------------------------------------------
# Daily prices since 2000 ship with the app (app/spot_history.csv.gz, written by scripts/export_spot_history.py),
# so a new database has the whole history without calling any API; the API only adds the days since.

BUNDLED = Path(__file__).resolve().parents[1] / "spot_history.csv.gz"


def seed_from_bundle(db: Session) -> int:
    """Load bundled daily prices the database doesn't have yet. Returns how many were added."""
    if not BUNDLED.exists():
        return 0
    have = {(m, d) for m, d in db.execute(select(SpotPrice.metal, SpotPrice.day))}
    new = []
    with gzip.open(BUNDLED, "rt", newline="") as f:
        for row in csv.DictReader(f):
            day = date.fromisoformat(row["day"])
            if (row["metal"], day) not in have:
                new.append({"metal": row["metal"], "day": day, "price": Decimal(row["price"]), "source": "history"})
    if new:
        db.execute(SpotPrice.__table__.insert(), new)
        db.commit()
    return len(new)


def export_bundle(db: Session, path: Path = BUNDLED) -> int:
    rows = db.execute(select(SpotPrice.metal, SpotPrice.day, SpotPrice.price).order_by(SpotPrice.metal, SpotPrice.day)).all()
    with gzip.open(path, "wt", newline="") as f:
        w = csv.writer(f)
        w.writerow(["metal", "day", "price"])
        for m, d, p in rows:
            w.writerow([m, d.isoformat(), f"{Decimal(str(p)):.4f}"])
    return len(rows)
