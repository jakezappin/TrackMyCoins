"""Precious Metals page: spot and changes, gold/silver ratio, melt table and the user's metal."""

from datetime import date, timedelta
from decimal import Decimal

from test_api import coin_payload
from test_reports import _collection

from app.db import SessionLocal
from app.models import SpotPrice
from app.services import melt_table


def _history(days_back_prices: dict[str, list[tuple[int, float]]]):
    today = date.today()
    with SessionLocal() as db:
        for metal, rows in days_back_prices.items():
            for back, price in rows:
                db.add(SpotPrice(metal=metal, day=today - timedelta(days=back), price=Decimal(str(price)), source="history"))
        db.commit()


def test_overview(authed, monkeypatch):
    from app.routers import metals as page

    wed = date(2026, 10, 14)
    monkeypatch.setattr(page, "_today", lambda: wed)
    with SessionLocal() as db:
        for back in range(1, 800):
            day = wed - timedelta(days=back)
            # The ratio sat around 60 for years (with a little spread); yesterday's close: gold 3900, silver 48.
            gold, silver = (3900.0, 48.0) if back == 1 else (2900.0 + (back % 3) * 100, 50.0)
            db.add_all([SpotPrice(metal="gold", day=day, price=Decimal(str(gold)), source="history"),
                        SpotPrice(metal="silver", day=day, price=Decimal(str(silver)), source="history")])
        db.commit()
    m = authed.get("/api/metals").json()
    gold = next(c for c in m["spot"] if c["metal"] == "gold")
    assert gold["price"] == 4000.0 and gold["prev_close"] == 3900.0 and gold["prev_day"] == "2026-10-13"
    assert gold["change"] == 100.0 and gold["change_pct"] == 2.56 and gold["market_closed"] is False
    assert gold["high_52w"] == 4000.0
    assert m["ratio"]["value"] == 80.0 and m["ratio"]["signal"] == "trade_gold"  # silver is cheap: trade gold for it
    assert m["copper"]["price"] == 5.0

    rows = {c["key"]: c for c in m["coins"]}
    assert rows["dollar-90"]["melt"] == round(26.73 * 0.9 / 31.1034768 * 50, 2)
    assert rows["gold-20"]["x_face"] == round(0.9675 * 4000 / 20, 2)
    assert rows["cent-95"]["unit"] == "lb" and rows["cent-95"]["melt"] < 0.05

    # Sunday: markets are closed; the change shown is Friday's close against Thursday's.
    monkeypatch.setattr(page, "_today", lambda: date(2026, 10, 18))
    with SessionLocal() as db:
        db.add_all([SpotPrice(metal="gold", day=date(2026, 10, 15), price=Decimal("3950"), source="history"),
                    SpotPrice(metal="gold", day=date(2026, 10, 16), price=Decimal("4000"), source="history"),
                    SpotPrice(metal="gold", day=date(2026, 10, 17), price=Decimal("4000"), source="live")])
        db.commit()
    gold = next(c for c in authed.get("/api/metals").json()["spot"] if c["metal"] == "gold")
    assert gold["market_closed"] and gold["prev_day"] == "2026-10-15" and gold["change"] == 50.0


def test_holdings_count_bullion_and_coins(authed):
    morgans = _collection(authed, "morgan-dollars")
    authed.post("/api/coins", json=coin_payload(morgans["id"]))
    kennedy = _collection(authed, "kennedy-half-dollars")
    authed.post("/api/coins", json=coin_payload(kennedy["id"], year=1967, mint_mark="P"))  # 40%
    authed.post("/api/coins", json=coin_payload(kennedy["id"], year=1990, mint_mark="P"))  # clad: no silver
    col = authed.post("/api/bullion/collections", json={"name": "Silver", "metal": "silver"}).json()
    r = authed.post("/api/bullion/items", json={"collection_id": col["id"], "description": "Bar", "weight": "10",
                                                "weight_unit": "ozt", "purity": "0.999", "quantity": 1})
    assert r.status_code == 201, r.text
    h = authed.get("/api/metals").json()["holdings"]
    silver = next(x for x in h["metals"] if x["metal"] == "silver")
    assert silver["bullion_oz"] == 9.99
    assert silver["coin_oz"] == round(melt_table.BY_KEY["dollar-90"].amount + melt_table.BY_KEY["kennedy-40"].amount, 4)
    assert (h["coins_counted"], h["coins_total"]) == (2, 3)


def test_entry_rules():
    e = melt_table.entry_for
    assert e("roosevelt-dimes", 1964).key == "dime-90" and e("roosevelt-dimes", 1965) is None
    assert e("roosevelt-dimes", 2005, "SPR").key == "dime-90" and e("roosevelt-dimes", 2020, "SPR").key == "silver-proof-dime"
    assert e("jefferson-nickels", 1943).key == "war-nickel" and e("jefferson-nickels", 1942, mint="D") is None
    assert e("ike-dollars", 1972, "MS", "S").key == "ike-40" and e("ike-dollars", 1972, "MS", "D") is None
    assert e("lincoln-cents", 1943) is None and e("lincoln-cents", 1958).key == "cent-95"


def test_history(authed):
    _history({"gold": [(d, 3000.0 + d) for d in range(1, 400)], "silver": [(d, 30.0) for d in range(1, 400)]})
    pts = authed.get("/api/metals/history?series=gold&range=1m").json()
    assert pts[-1] == {"date": date.today().isoformat(), "value": 4000.0} and len(pts) <= 32
    ratio = authed.get("/api/metals/history?series=ratio&range=all").json()
    assert ratio[-1]["value"] == 80.0 and len(ratio) <= 401


def test_week_range(authed):
    _history({"gold": [(d, 3000.0 + d) for d in range(1, 40)], "silver": [(d, 30.0) for d in range(1, 40)]})
    pts = authed.get("/api/metals/history?series=gold&range=1w").json()
    assert 6 <= len(pts) <= 9 and pts[-1]["value"] == 4000.0  # a week of closes, then today's live price
    assert len(authed.get("/api/metals/history?series=ratio&range=1w").json()) >= 6
