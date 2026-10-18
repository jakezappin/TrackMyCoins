"""Bullion: pure ounces, values from spot (live $50 silver / $4,000 gold in tests), history, partial sales."""

from datetime import date, timedelta
from decimal import Decimal

import pytest

from app.db import SessionLocal
from app.models import SpotPrice
from app.services import bullion as svc
from app.services import price_archive


def _col(c, metal="silver", name="Stack"):
    r = c.post("/api/bullion/collections", json={"name": name, "metal": metal})
    assert r.status_code == 201, r.text
    return r.json()


def _item(c, col, **kw):
    body = {"collection_id": col["id"], "description": "Buffalo Round", "weight": "1", "weight_unit": "ozt",
            "purity": "0.999", "quantity": 1, "price_paid": "45", **kw}
    r = c.post("/api/bullion/items", json=body)
    assert r.status_code == 201, r.text
    return r.json()


def _spot(metal, day, price):
    with SessionLocal() as db:
        db.add(SpotPrice(metal=metal, day=day, price=Decimal(price), source="history"))
        db.commit()


def test_ounces_and_values(authed):
    ag, au = _col(authed), _col(authed, "gold", "Gold")
    tube = _item(authed, ag, description="Silver Eagles", packaging="tube", quantity=20, price_paid="800")
    assert (tube["inventory_number"], tube["oz"], tube["value_now"]) == ("AG-00001", "19.9800", "999.00")
    bar = _item(authed, ag, description="Silvertown Bar", weight="1", weight_unit="kg", purity="0.999", price_paid="1500")
    assert bar["oz"] == "32.1186"  # 1 kg = 32.1507 ozt x .999
    grams = _item(authed, ag, description="Art bar", weight="31.1035", weight_unit="g", purity="0.925")
    assert grams["oz"] == "0.9250"
    junk = _item(authed, ag, description="90% dimes", face_value="10", purity="0.9", weight=None, price_paid="300")
    assert (junk["oz"], junk["value_now"], junk["weight"]) == ("7.1500", "357.50", None)  # 0.715 ozt per $1 face
    eagle = _item(authed, au, description="Gold Eagle", weight="1.0909", purity="0.9167", price_paid="4200")
    assert eagle["inventory_number"] == "AU-00001" and eagle["value_now"] == "4000.00"

    col = authed.get(f"/api/bullion/collections/{ag['id']}").json()
    s = col["summary"]
    assert (s["count"], s["value"], s["cost"]) == (4, "3008.68", "2645.00")
    assert s["change"] == "363.68" and s["change_pct"] == 13.7
    dash = authed.get("/api/bullion/summary").json()
    assert dash["value"] == "7008.68" and set(dash["by_metal"]) == {"silver", "gold"}


def test_validation(authed):
    ag = _col(authed)
    base = {"collection_id": ag["id"], "description": "x", "purity": "0.999"}
    assert authed.post("/api/bullion/items", json=base).status_code == 422  # no weight or face value
    r = authed.post("/api/bullion/items", json={**base, "face_value": "5"})
    assert r.status_code == 422 and "Face value" in r.text  # face value only for 90/40/35%
    r = authed.post("/api/bullion/items", json={**base, "weight": "1", "purchase_date": "2999-01-01"})
    assert r.status_code == 422
    assert authed.post("/api/bullion/collections", json={"name": "x", "metal": "copper"}).status_code == 422


def test_value_at_purchase_and_history(authed):
    ag = _col(authed)
    bought = date.today() - timedelta(days=90)
    # Daily prices: $30 until 40 days after the purchase, $40 since (none on the purchase day itself: the
    # price from two days before stands in, as for a weekend).
    for n in range(-2, 90):
        if n not in (-1, 0):
            _spot("silver", bought + timedelta(days=n), "30" if n <= 40 else "40")
    item = _item(authed, ag, quantity=10, price_paid="330", purchase_date=bought.isoformat())
    assert (item["spot_at_purchase"], item["value_at_purchase"], item["premium_pct"]) == ("30.00", "299.70", 10.1)
    pts = authed.get(f"/api/bullion/items/{item['inventory_number']}/history").json()
    assert pts[0]["date"] == bought.isoformat() and pts[0]["value"] == "299.70"
    assert pts[-1]["value"] == "499.50" and pts[-1]["cost"] == "330.00"  # today: live $50
    assert any(p["value"] == "399.60" for p in pts)  # the $40 month


def test_sell_part_of_a_tube_and_face_value(authed):
    ag = _col(authed)
    tube = _item(authed, ag, quantity=20, price_paid="1000", packaging="tube")
    r = authed.post(f"/api/bullion/items/{tube['inventory_number']}/sell",
                    json={"quantity": 5, "sale_price": "300", "sale_date": date.today().isoformat(), "sold_to": "LCS"})
    assert r.status_code == 200, r.text
    out = r.json()
    sold = authed.get(f"/api/bullion/items/{out['sold']}").json()
    kept = authed.get(f"/api/bullion/items/{out['kept']}").json()
    assert (sold["quantity"], sold["price_paid"], sold["is_sold"], sold["change"]) == (5, "250.00", True, "50.00")
    assert (kept["quantity"], kept["price_paid"], kept["is_sold"]) == (15, "750.00", False)
    junk = _item(authed, ag, face_value="10", purity="0.9", weight=None, price_paid="300")
    out = authed.post(f"/api/bullion/items/{junk['inventory_number']}/sell",
                      json={"face_value": "4", "sale_price": "150", "sale_date": date.today().isoformat()}).json()
    assert authed.get(f"/api/bullion/items/{out['kept']}").json()["face_value"] == "6.00"
    # Selling everything doesn't split.
    out = authed.post(f"/api/bullion/items/{out['kept']}/sell",
                      json={"sale_price": "250", "sale_date": date.today().isoformat()}).json()
    assert out["kept"] is None
    s = authed.get(f"/api/bullion/collections/{ag['id']}").json()["summary"]
    assert (s["count"], s["sold_count"]) == (1, 3)


def test_spot_history_upkeep(client, monkeypatch):
    from app.config import get_settings

    with SessionLocal() as db:
        assert svc.record_live(db) == 4  # today's live price for each metal, once a day
        assert svc.record_live(db) == 0
    monkeypatch.setattr(get_settings(), "gold_api_key", "k")
    calls = []

    def fake(metal, start, end):
        calls.append((metal, start))
        return [(start + timedelta(days=n), Decimal("20") + n) for n in range(3)]

    monkeypatch.setattr(svc, "fetch_history", fake)
    with SessionLocal() as db:
        done = svc.update_history(db)
    assert set(done) == set(svc.METALS) and all(s == svc.HISTORY_START for _, s in calls)
    assert svc.SpotSeries.load(SessionLocal(), "silver").on(svc.HISTORY_START + timedelta(days=5)) == Decimal("22")
    assert svc._history_rows([{"day": "2024-01-15T00:00:00Z", "avg_price": 23.1}]) == [(date(2024, 1, 15), Decimal("23.1"))]


def test_bullion_kept_apart_from_coins(authed):
    ag = _col(authed)
    _item(authed, ag, price_paid="45")
    dash = authed.get("/api/dashboard").json()
    assert dash["totals"]["coin_count"] == 0  # the numismatic totals don't include bullion


@pytest.fixture(autouse=True)
def _no_upkeep_thread(monkeypatch):
    monkeypatch.setattr(price_archive, "PAUSE_SECONDS", 0)
