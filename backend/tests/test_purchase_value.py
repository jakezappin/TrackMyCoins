"""Estimated value at purchase, the shared CPG history it can use, and the value chart's line from it."""

from datetime import date, datetime, timedelta, timezone
from decimal import Decimal

from test_api import coin_payload

from app.db import SessionLocal
from app.models import Coin, CpgHistory, PriceQuote
from app.services import grade_prices, purchase_value
from app.services.history import value_history


def _coin(authed, col_id, **kw):
    return authed.post("/api/coins", json=coin_payload(col_id, pcgs_number="7130", grade=64, **kw)).json()


def _detail(authed, inv):
    return authed.get(f"/api/coins/{inv}").json()["purchase_value"]


def _quote(inv, value, days_ago):
    with SessionLocal() as db:
        c = db.query(Coin).filter_by(inventory_number=inv).one()
        db.add(PriceQuote(coin_id=c.id, source="CPG", value=Decimal(value),
                          fetched_at=datetime.now(timezone.utc) - timedelta(days=days_ago)))
        db.commit()


def test_value_at_purchase_is_own_value_recent_cpg_or_price_paid(authed, morgan_collection):
    col = morgan_collection["id"]
    today = date.today()
    recent = _coin(authed, col, purchase_date=(today - timedelta(days=20)).isoformat(), price_paid="150")
    _quote(recent["inventory_number"], "175", 0)
    assert (_detail(authed, recent["inventory_number"])["value"], _detail(authed, recent["inventory_number"])["source"]) == ("175.00", "cpg")

    # Bought 2 years ago: no auction or history lookups (off for now), so the price paid.
    old = _coin(authed, col, purchase_date=(today - timedelta(days=730)).isoformat(), price_paid="120")
    _quote(old["inventory_number"], "175", 0)
    pv = _detail(authed, old["inventory_number"])
    assert (pv["value"], pv["source"], pv["pending"]) == ("120.00", "paid", False)

    # Set from the coin page, and cleared back to the worked-out value.
    r = authed.put(f"/api/coins/{old['inventory_number']}/purchase-value", json={"value": "140"})
    assert (r.json()["purchase_value"]["value"], r.json()["purchase_value"]["source"]) == ("140.00", "custom")
    r = authed.put(f"/api/coins/{old['inventory_number']}/purchase-value", json={"value": None})
    assert r.json()["purchase_value"]["source"] == "paid"


def test_dormant_sources_when_switched_on(authed, morgan_collection, monkeypatch):
    """History and PCGS auctions are off for now; they still work when switched back on."""
    monkeypatch.setattr(purchase_value, "USE_HISTORY", True)
    monkeypatch.setattr(purchase_value, "USE_AUCTIONS", True)
    col = morgan_collection["id"]
    today = date.today()

    # Recent purchase priced now: that CPG.
    recent = _coin(authed, col, purchase_date=(today - timedelta(days=20)).isoformat(), price_paid="150")
    _quote(recent["inventory_number"], "175", 0)
    pv = _detail(authed, recent["inventory_number"])
    assert (pv["value"], pv["source"]) == ("175.00", "cpg")

    # Bought 2 years ago, added and priced today: not today's CPG. Price paid until auctions are looked up...
    old = _coin(authed, col, purchase_date=(today - timedelta(days=730)).isoformat(), price_paid="120")
    _quote(old["inventory_number"], "175", 0)
    pv = _detail(authed, old["inventory_number"])
    assert (pv["value"], pv["source"], pv["pending"]) == ("120.00", "paid", True)

    # ... then the average of the sales nearest the purchase month (within a year).
    def ym(months_from_purchase):
        d = today - timedelta(days=730) + timedelta(days=30 * months_from_purchase)
        return f"{d.year}-{d.month:02d}"

    sales = [(ym(0), Decimal(100)), (ym(-1), Decimal(110)), (ym(2), Decimal(90)), (ym(20), Decimal(500))]
    monkeypatch.setattr(purchase_value, "_sales", lambda *a, **k: sales)
    pv = authed.post(f"/api/coins/{old['inventory_number']}/purchase-value").json()["purchase_value"]
    assert (pv["value"], pv["source"], pv["pending"]) == ("100.00", "auctions", False)
    assert pv["detail"].startswith("Average of 3 PCGS auction sales")

    # The app's own CPG history covering the purchase date beats auctions.
    with SessionLocal() as db:
        when = datetime.now(timezone.utc) - timedelta(days=760)
        db.add(CpgHistory(key="pcgs:7130", grade=64, label="MS64", cac=False, value=Decimal("130"),
                          first_seen=when, last_seen=when + timedelta(days=40)))
        db.commit()
    pv = _detail(authed, old["inventory_number"])
    assert (pv["value"], pv["source"]) == ("130.00", "cpg_history")

    # The owner's own figure beats everything.
    authed.put(f"/api/coins/{old['inventory_number']}", json=coin_payload(
        col, pcgs_number="7130", grade=64, cert_number=old["cert_number"],
        purchase_date=(today - timedelta(days=730)).isoformat(), price_paid="120", purchase_value_custom="140"))
    pv = _detail(authed, old["inventory_number"])
    assert (pv["value"], pv["source"]) == ("140.00", "custom")


def test_no_sales_means_price_paid(authed, morgan_collection, monkeypatch):
    monkeypatch.setattr(purchase_value, "USE_AUCTIONS", True)
    c = _coin(authed, morgan_collection["id"], purchase_date="2015-03-01", price_paid="95")
    monkeypatch.setattr(purchase_value, "_sales", lambda *a, **k: [("2024-01", Decimal(200))])  # too far away
    pv = authed.post(f"/api/coins/{c['inventory_number']}/purchase-value").json()["purchase_value"]
    assert (pv["value"], pv["source"], pv["pending"]) == ("95.00", "paid", False)


def test_average_near_takes_ten_closest():
    start = date(2024, 6, 15)
    sales = [(f"2024-{m:02d}", Decimal(m * 10)) for m in range(1, 13)] + [("2023-06", Decimal(5))]
    avg, n, span = purchase_value.average_near(sales, start)
    # Nearest 10 to June 2024: Jun, May, Jul, Apr, Aug, Mar, Sep, Feb, Oct, Jan (earlier wins ties)
    assert (n, span) == (10, "2024-01..2024-10")
    assert avg == Decimal(sum(range(1, 11)) * 10 / 10).quantize(Decimal("0.01"))


def test_cpg_history_extends_or_adds():
    t0 = datetime(2026, 1, 1, tzinfo=timezone.utc)
    rows = [{"grade": 64, "label": "MS64", "cac": False, "cpg": "160"}]
    with SessionLocal() as db:
        grade_prices.record_history(db, "pcgs:1", rows, t0)
        db.flush()
        grade_prices.record_history(db, "pcgs:1", rows, t0 + timedelta(days=7))
        db.flush()
        grade_prices.record_history(db, "pcgs:1", [{**rows[0], "cpg": "170"}], t0 + timedelta(days=14))
        db.flush()
        h = db.query(CpgHistory).filter_by(key="pcgs:1").order_by(CpgHistory.first_seen).all()
        assert [(str(x.value), x.last_seen.day) for x in h] == [("160.00", 8), ("170.00", 15)]


def test_chart_runs_from_value_at_purchase(authed, morgan_collection):
    today = datetime.now(timezone.utc).date()  # the server's day (prices are dated in UTC)
    a = _coin(authed, morgan_collection["id"], purchase_date=(today - timedelta(days=100)).isoformat(), price_paid="100")
    # Another coin bought halfway, so the chart has a point in between.
    _coin(authed, morgan_collection["id"], purchase_date=(today - timedelta(days=50)).isoformat(), price_paid=None)
    _quote(a["inventory_number"], "200", 0)
    with SessionLocal() as db:
        user_id = db.query(Coin).filter_by(inventory_number=a["inventory_number"]).one().user_id
        pts = {p["date"]: p for p in value_history(db, user_id)}
    start = pts[(today - timedelta(days=100)).isoformat()]
    mid = pts[(today - timedelta(days=50)).isoformat()]
    assert (start["value"], start["backfilled"]) == ("100.00", True)  # price paid (no sales looked up)
    assert mid["value"] == "150.00"  # halfway along the line to today's 200
    assert pts[today.isoformat()]["value"] == "200.00"


def test_import_keeps_only_own_values():
    from app.services import importer

    base = {"Date": "1881-S", "Grade": "MS64", "Service": "PCGS", "Cert": "1", "Est. value at purchase": "$140"}
    f, *_ = importer.row_to_fields({**base, "Value at purchase from": "Your own value"})
    assert f["purchase_value_custom"] == "140.00"
    f, *_ = importer.row_to_fields({**base, "Value at purchase from": "Average of 4 PCGS auction sales"})
    assert f["purchase_value_custom"] is None  # worked out; worked out again after import
    f, *_ = importer.row_to_fields(base)  # someone else's spreadsheet: their figure
    assert f["purchase_value_custom"] == "140.00"
