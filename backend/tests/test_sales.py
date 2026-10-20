"""Sales Tracker: a lot sold to one buyer, a trade (what came in costs what was given), undoing them, and the
history with items sold on their own pages."""

from datetime import date

from test_api import coin_payload


def _coin(authed, col, **kw):
    return authed.post("/api/coins", json=coin_payload(col, **kw)).json()["inventory_number"]


def test_sell_a_lot_and_undo(authed, morgan_collection):
    col = morgan_collection["id"]
    a, b = _coin(authed, col, price_paid="100"), _coin(authed, col, year=1882, price_paid="50")
    found = authed.get("/api/sales/items", params={"q": "1882"}).json()
    assert [i["inventory_number"] for i in found] == [b]

    r = authed.post("/api/sales/sale", json={"sale_date": date.today().isoformat(), "sold_via": "ebay",
                                             "counterparty": "buyer123",
                                             "items": [{"ref": f"coin:{a}", "price": "150"}, {"ref": f"coin:{b}", "price": "40"}]})
    assert r.status_code == 201, r.text
    c = authed.get(f"/api/coins/{a}").json()
    assert (c["sale_price"], c["sold_via"], c["sold_to"]) == ("150.00", "ebay", "buyer123")
    entry = authed.get("/api/sales").json()[0]
    assert (entry["kind"], entry["total"], entry["profit"], len(entry["out"])) == ("sale", "190.00", "40.00", 2)

    # Already sold: can't be sold again.
    again = authed.post("/api/sales/sale", json={"sale_date": date.today().isoformat(),
                                                 "items": [{"ref": f"coin:{a}", "price": "1"}]})
    assert again.status_code == 422 and "already sold" in again.text

    assert authed.delete(f"/api/sales/{entry['id']}").status_code == 204
    c = authed.get(f"/api/coins/{a}").json()
    assert (c["sale_price"], c["sale_date"], c["sold_via"]) == (None, None, None)


def test_trade_costs_what_was_given(authed, morgan_collection):
    col = morgan_collection["id"]
    out = _coin(authed, col, price_paid="300")
    in1 = _coin(authed, col, year=1883, price_paid=None)
    in2 = _coin(authed, col, year=1884, price_paid=None)
    r = authed.post("/api/sales/trade", json={
        "sale_date": date.today().isoformat(), "counterparty": "Show buddy",
        "out": [{"ref": f"coin:{out}", "price": "400"}],
        "came_in": [{"ref": f"coin:{in1}", "price": "300"}, {"ref": f"coin:{in2}", "price": "100"}],
        "cash_paid": "50"})
    assert r.status_code == 201, r.text
    gone = authed.get(f"/api/coins/{out}").json()
    assert (gone["sale_price"], gone["sold_via"]) == ("400.00", "trade")
    got1, got2 = authed.get(f"/api/coins/{in1}").json(), authed.get(f"/api/coins/{in2}").json()
    # Gave $400 of coin + $50 cash = $450, split 3:1.
    assert (got1["price_paid"], got2["price_paid"]) == ("337.50", "112.50")
    assert got1["purchased_from"] == "Show buddy" and got1["purchase_date"] == date.today().isoformat()
    entry = authed.get("/api/sales").json()[0]
    assert entry["kind"] == "trade" and len(entry["in"]) == 2 and entry["cash_paid"] == "50.00"

    assert authed.delete(f"/api/sales/{entry['id']}?delete_received=true").status_code == 204
    assert authed.get(f"/api/coins/{in1}").status_code == 404
    assert authed.get(f"/api/coins/{out}").json()["sale_price"] is None


def test_single_sales_show_in_history(authed, morgan_collection):
    col = morgan_collection["id"]
    _coin(authed, col, price_paid="10", sale_price="25", sale_date="2026-01-05", sold_via="coin_show",
          sold_to="Table 12")
    e = authed.get("/api/sales").json()[0]
    assert (e["id"], e["sold_via"], e["counterparty"], e["profit"]) == (None, "coin_show", "Table 12", "15.00")


def test_split_adds_up():
    from decimal import Decimal

    from app.services.sales import split

    parts = split(Decimal("100"), [Decimal(1), Decimal(1), Decimal(1)])
    assert sum(parts) == Decimal("100.00") and parts[0] == Decimal("33.33")
    assert split(Decimal("10"), [Decimal(0), Decimal(0)]) == [Decimal("5.00"), Decimal("5.00")]
