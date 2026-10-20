"""The Sales Tracker: sales (one or more items to one buyer) and trades (items out, items in, cash either way).

Each item keeps its own sale price (what it went out for) and price paid (what came in cost), so every page that
works out profit and loss keeps working. A Sale row groups them and remembers who and where.

Trades: what goes out is sold at its trade value. What comes in cost what was given for it, the trade values
going out plus any cash paid, less any cash received, split across the incoming items by their trade values.
"""

from dataclasses import dataclass
from datetime import date
from decimal import ROUND_HALF_UP, Decimal

from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from ..models import BullionItem, Coin, Dealer, Sale, User
from . import bullion as bsvc
from .coins import coin_out, value_estimate

CENTS = Decimal("0.01")
Item = Coin | BullionItem


class SaleError(ValueError):
    """Something the user should fix (shown as is)."""


# ---- Items -------------------------------------------------------------------------------------------------------


def parse_ref(ref: str) -> tuple[str, str]:
    kind, _, inv = ref.partition(":")
    if kind not in ("coin", "bullion") or not inv:
        raise SaleError(f"Unknown item {ref!r}")
    return kind, inv


def get_item(db: Session, user: User, ref: str) -> Item:
    kind, inv = parse_ref(ref)
    model = Coin if kind == "coin" else BullionItem
    item = db.scalar(select(model).where(model.user_id == user.id, model.inventory_number == inv))
    if item is None:
        raise SaleError(f"{inv} isn't in your collection")
    return item


def ref_of(item: Item) -> str:
    return f"{'coin' if isinstance(item, Coin) else 'bullion'}:{item.inventory_number}"


def is_sold(item: Item) -> bool:
    return item.sale_date is not None or item.sale_price is not None


def title(item: Item) -> str:
    if isinstance(item, Coin):
        from ..routers.dealers import _coin_title

        return _coin_title(item) + (f" · {item.variety}" if item.variety else "")
    qty = f"{item.quantity} × " if (item.quantity or 1) > 1 else ""
    return f"{qty}{item.description}"


def est_value(item: Item) -> Decimal | None:
    """What it's worth now: a coin's estimated value, bullion's melt."""
    if isinstance(item, Coin):
        return value_estimate(item)
    return bsvc.value(item, item.collection.metal).value_now


def _money(v) -> str | None:
    return None if v is None else str(Decimal(str(v)).quantize(CENTS))


def item_out(item: Item) -> dict:
    coin = isinstance(item, Coin)
    thumb = None
    if coin:
        thumb = coin_out(item).thumbnail_url
    elif item.photos:
        thumb = f"/api/bullion/photos/{item.photos[0].id}?size=thumb"
    return {
        "ref": ref_of(item), "kind": "coin" if coin else "bullion", "inventory_number": item.inventory_number,
        "title": title(item), "thumb_url": thumb,
        "collection_id": item.collection_id, "collection_name": item.collection.name,
        "series": item.coin_type.slug if coin else "bullion",
        "path": f"/coins/{item.inventory_number}" if coin else f"/bullion/items/{item.inventory_number}",
        "price_paid": _money(item.price_paid), "purchase_date": item.purchase_date,
        "est_value": _money(est_value(item)),
        "sale_price": _money(item.sale_price), "sale_date": item.sale_date, "sold_to": item.sold_to,
        "sold_via": item.sold_via, "sold_via_other": item.sold_via_other, "is_sold": is_sold(item),
    }


def _all_items(db: Session, user: User) -> list[Item]:
    coins = db.scalars(select(Coin).where(Coin.user_id == user.id)
                       .options(selectinload(Coin.coin_type), selectinload(Coin.collection),
                                selectinload(Coin.photos), selectinload(Coin.price_quotes))).all()
    bullion = db.scalars(select(BullionItem).where(BullionItem.user_id == user.id)
                         .options(selectinload(BullionItem.collection), selectinload(BullionItem.photos))).all()
    return [*coins, *bullion]


def search(db: Session, user: User, q: str, held: bool = True, limit: int = 30) -> list[dict]:
    """Items matching every word of `q` (inventory #, date, series, variety, grade, cert, description...)."""
    words = q.lower().split()
    out = []
    for item in _all_items(db, user):
        if held and is_sold(item):
            continue
        hay = " ".join(str(x) for x in (
            item.inventory_number, title(item), item.collection.name, getattr(item, "cert_number", None),
            getattr(item, "notes", None)) if x).lower()
        if all(w in hay for w in words):
            out.append(item)
    out.sort(key=lambda i: i.inventory_number)
    return [item_out(i) for i in out[:limit]]


def tidy(item: Item) -> None:
    """After an edit: an item that isn't sold has no channel or sale; "other" is only described for Other."""
    if not is_sold(item):
        item.sold_via = item.sold_via_other = item.sale_id = None
    elif item.sold_via != "other":
        item.sold_via_other = None


# ---- Recording ---------------------------------------------------------------------------------------------------


@dataclass
class Party:
    sale_date: date
    sold_via: str | None
    sold_via_other: str | None
    counterparty: str | None
    dealer_id: int | None
    notes: str | None


def _party(db: Session, user: User, p: Party) -> tuple[str | None, int | None]:
    """(who it was with, as text; the dealer's id). A dealer picked: their name."""
    if p.dealer_id is not None:
        d = db.get(Dealer, p.dealer_id)
        if d is None or d.user_id != user.id:
            raise SaleError("That dealer isn't one of yours")
        return d.display_name, d.id
    return (p.counterparty or "").strip() or None, None


def _check_out(items: list[Item], when: date) -> None:
    seen = set()
    for it in items:
        if it.id is not None and (type(it), it.id) in seen:
            raise SaleError(f"{it.inventory_number} is listed twice")
        seen.add((type(it), it.id))
        if is_sold(it):
            raise SaleError(f"{it.inventory_number} is already sold")
        if it.purchase_date and when < it.purchase_date:
            raise SaleError(f"{it.inventory_number} was bought after {when:%b %d, %Y}. Check the date.")
        if isinstance(it, Coin) and it.location == "grading":
            raise SaleError(f"{it.inventory_number} is at grading. Mark it returned first.")


def _sell(item: Item, sale: Sale, price: Decimal, who: str | None, dealer_id: int | None) -> None:
    item.sale_price, item.sale_date, item.sold_to, item.sold_to_dealer_id = price, sale.sale_date, who, dealer_id
    item.sold_via, item.sold_via_other, item.sale_id = sale.sold_via, sale.sold_via_other, sale.id


def record_sale(db: Session, user: User, p: Party, lines: list[tuple[str, Decimal]]) -> Sale:
    """Sell items (refs with their prices) to one buyer."""
    if not lines:
        raise SaleError("Pick at least one item to sell")
    items = [get_item(db, user, ref) for ref, _ in lines]
    _check_out(items, p.sale_date)
    who, dealer_id = _party(db, user, p)
    via = p.sold_via or ("dealer" if dealer_id else None)
    sale = Sale(user_id=user.id, kind="sale", sale_date=p.sale_date, sold_via=via,
                sold_via_other=(p.sold_via_other or None) if via == "other" else None,
                counterparty=who, dealer_id=dealer_id, notes=p.notes)
    db.add(sale)
    db.flush()
    for item, (_, price) in zip(items, lines):
        _sell(item, sale, price, who, dealer_id)
    return sale


def split(total: Decimal, weights: list[Decimal]) -> list[Decimal]:
    """`total` in cents across items in proportion to `weights` (equally if they're all 0); the last item takes
    the rounding so the parts add up exactly."""
    total = max(total, Decimal(0)).quantize(CENTS)
    n = len(weights)
    w_sum = sum(weights)
    shares = [Decimal(1) / n] * n if w_sum <= 0 else [w / w_sum for w in weights]
    parts = [(total * s).quantize(CENTS, ROUND_HALF_UP) for s in shares[:-1]]
    return [*parts, total - sum(parts, Decimal(0))]


def record_trade(db: Session, user: User, p: Party, out: list[tuple[str, Decimal]], came_in: list[tuple[str, Decimal]],
                 cash_received: Decimal | None, cash_paid: Decimal | None) -> Sale:
    """Items out at their trade values; items in (already entered) cost what was given, split by their values."""
    if not out:
        raise SaleError("Pick what you traded away")
    if not came_in:
        raise SaleError("Add what you got in the trade")
    gone = [get_item(db, user, ref) for ref, _ in out]
    got = [get_item(db, user, ref) for ref, _ in came_in]
    _check_out(gone, p.sale_date)
    if {ref_of(i) for i in gone} & {ref_of(i) for i in got}:
        raise SaleError("An item can't go out and come in the same trade")
    for it in got:
        if is_sold(it):
            raise SaleError(f"{it.inventory_number} is marked sold; it can't be what you got")
    who, dealer_id = _party(db, user, p)
    sale = Sale(user_id=user.id, kind="trade", sale_date=p.sale_date, sold_via="trade", counterparty=who,
                dealer_id=dealer_id, cash_received=cash_received or None, cash_paid=cash_paid or None, notes=p.notes)
    db.add(sale)
    db.flush()
    for item, (_, value) in zip(gone, out):
        _sell(item, sale, value, who, dealer_id)
    given = sum((v for _, v in out), Decimal(0)) + (cash_paid or 0) - (cash_received or 0)
    for item, cost in zip(got, split(given, [v for _, v in came_in])):
        item.price_paid, item.purchase_date = cost, p.sale_date
        item.purchased_from, item.purchased_from_dealer_id = who, dealer_id
        item.acquired_sale_id = sale.id
    return sale


def delete(db: Session, user: User, sale_id: int, delete_received: bool = False) -> None:
    """Undo a sale or trade: what went out is back on hand; what came in is deleted, or kept (unlinked)."""
    sale = db.get(Sale, sale_id)
    if sale is None or sale.user_id != user.id:
        raise SaleError("Not found")
    for model in (Coin, BullionItem):
        for it in db.scalars(select(model).where(model.sale_id == sale.id)):
            it.sale_price = it.sale_date = it.sold_to = it.sold_to_dealer_id = None
            it.sold_via = it.sold_via_other = it.sale_id = None
        for it in db.scalars(select(model).where(model.acquired_sale_id == sale.id)):
            if delete_received:
                db.delete(it)
            else:
                it.acquired_sale_id = None
    db.delete(sale)


# ---- History -----------------------------------------------------------------------------------------------------


def _pl(items: list[dict]) -> tuple[Decimal, Decimal, Decimal | None, int]:
    """(total sold, cost, profit/loss over items with both prices, items left out)."""
    total = sum((Decimal(i["sale_price"]) for i in items if i["sale_price"]), Decimal(0))
    both = [i for i in items if i["sale_price"] is not None and i["price_paid"] is not None]
    cost = sum((Decimal(i["price_paid"]) for i in both), Decimal(0))
    pl = sum((Decimal(i["sale_price"]) for i in both), Decimal(0)) - cost if both else None
    return total, cost, pl, len(items) - len(both)


def history(db: Session, user: User) -> list[dict]:
    """Every sale and trade, newest first. Items sold one at a time (on their own page) are entries of their own."""
    items = _all_items(db, user)
    by_sale: dict[int, list[dict]] = {}
    came_in: dict[int, list[dict]] = {}
    entries = []
    for it in items:
        if it.acquired_sale_id is not None:
            came_in.setdefault(it.acquired_sale_id, []).append(item_out(it))
        if not is_sold(it):
            continue
        if it.sale_id is not None:
            by_sale.setdefault(it.sale_id, []).append(item_out(it))
        else:
            entries.append({"id": None, "kind": "sale", "sale_date": it.sale_date, "sold_via": it.sold_via,
                            "sold_via_other": it.sold_via_other, "counterparty": it.sold_to,
                            "dealer_id": it.sold_to_dealer_id, "cash_received": None, "cash_paid": None,
                            "notes": None, "out": [item_out(it)], "in": []})
    for sale in db.scalars(select(Sale).where(Sale.user_id == user.id)):
        entries.append({"id": sale.id, "kind": sale.kind, "sale_date": sale.sale_date, "sold_via": sale.sold_via,
                        "sold_via_other": sale.sold_via_other, "counterparty": sale.counterparty,
                        "dealer_id": sale.dealer_id, "cash_received": _money(sale.cash_received),
                        "cash_paid": _money(sale.cash_paid), "notes": sale.notes,
                        "out": by_sale.get(sale.id, []), "in": came_in.get(sale.id, [])})
    for e in entries:
        total, cost, pl, left = _pl(e["out"])
        e.update(total=_money(total), cost=_money(cost), profit=_money(pl), without_cost=left)
    entries.sort(key=lambda e: (e["sale_date"] or date.min, e["id"] or 0), reverse=True)
    return entries
