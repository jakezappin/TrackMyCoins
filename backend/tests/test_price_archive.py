"""The price archive: auction sales and PCGS guide values kept for good, the monthly upkeep, and the chart."""

from datetime import date, datetime, timedelta, timezone
from decimal import Decimal

import pytest
from test_api import coin_payload

from app.config import get_settings
from app.db import SessionLocal
from app.models import AuctionFetch, AuctionSale, Coin, GradePriceSheet, PcgsGuideHistory, PriceQuote
from app.services import greysheet, price_archive, purchase_value, quota
from app.services.history import value_history


def _sale(ym, price, cert="1", lot="10"):
    return {"date": ym, "price": str(price), "cert_number": cert, "lot": lot, "auctioneer": "Heritage", "service": "PCGS"}


def test_sales_saved_once_and_guide_changes_only(client):
    with SessionLocal() as db:
        assert price_archive.save_sales(db, "7130", 64, False, [_sale("2024-03", 150), _sale("2024-04", 160, "2")]) == 2
        db.flush()
        # The same sales seen again (another coin, another refresh) aren't stored twice.
        assert price_archive.save_sales(db, "7130", 64, False, [_sale("2024-03", 150), _sale("2024-05", 170, "3")]) == 1
        db.flush()
        assert sorted(price_archive.sales_for(db, "7130", 64, False)) == [
            ("2024-03", Decimal("150.00")), ("2024-04", Decimal("160.00")), ("2024-05", Decimal("170.00"))]
        assert price_archive.sales_for(db, "7130", 65, False) == []

        for v in ("200", "200", "210"):
            price_archive.record_guide(db, "7130", 64, False, Decimal(v))
            db.flush()
        assert [str(h.value) for h in db.query(PcgsGuideHistory).order_by(PcgsGuideHistory.id)] == ["200.00", "210.00"]
        db.rollback()


def test_value_at_purchase_reads_archive_and_refetches_quarterly(client, monkeypatch):
    calls = []

    def fake_fetch(db, num, grade, plus):
        calls.append(num)
        price_archive.save_sales(db, num, grade, plus, [_sale("2024-03", 100), _sale("2024-02", 120, "2")])
        db.add(AuctionFetch(pcgs_number=num, grade=grade, plus=plus, fetched_at=datetime.now(timezone.utc)))

    monkeypatch.setattr(price_archive, "fetch_full", fake_fetch)
    monkeypatch.setattr(quota, "spend", lambda *a, **k: None)
    assert sorted(purchase_value._sales("9999", 64, False, 1)) == [("2024-02", Decimal("120.00")), ("2024-03", Decimal("100.00"))]
    purchase_value._sales("9999", 64, False, 1)
    assert calls == ["9999"]  # fetched within the last 3 months: the archive answers


@pytest.fixture()
def keys_on(monkeypatch):
    s = get_settings()
    monkeypatch.setattr(s, "pcgs_api_token", "x")
    monkeypatch.setattr(s, "greysheet_api_key", "x")
    monkeypatch.setattr(price_archive, "PAUSE_SECONDS", 0)
    return s


def test_monthly_upkeep(authed, morgan_collection, keys_on, monkeypatch):
    for year, mint, grade in [(1881, "S", 64), (1881, "S", 64), (1884, "O", 63)]:
        authed.post("/api/coins", json=coin_payload(morgan_collection["id"], year=year, mint_mark=mint, grade=grade,
                                                    pcgs_number="7130" if year == 1881 else "7180"))
    sheets, auctions = [], []
    monkeypatch.setattr(greysheet, "fetch_sheet", lambda pcgs_number=None, gsid=None: sheets.append(pcgs_number) or {
        "key": f"pcgs:{pcgs_number}", "gsid": 1, "name": "x", "rows": [{"grade": 64, "label": "MS64", "cac": False, "cpg": "150"}]})

    def fake_fetch(db, num, grade, plus):
        auctions.append((num, grade))
        db.add(AuctionFetch(pcgs_number=num, grade=grade, plus=plus, fetched_at=datetime.now(timezone.utc)))

    monkeypatch.setattr(price_archive, "fetch_full", fake_fetch)
    out = price_archive.run_due()
    assert (out["sheets"], out["auctions"]) == (2, 2)  # one sheet per issue, one auction list per issue and grade
    assert sorted(sheets) == ["7130", "7180"] and sorted(auctions) == [("7130", 64), ("7180", 63)]

    # Nothing due again until a month (sheets) or 3 months (auctions) have passed.
    assert price_archive.run_due() == {"sheets": 0, "auctions": 0, "stopped": None}
    with SessionLocal() as db:
        db.query(GradePriceSheet).update({"fetched_at": datetime.now(timezone.utc) - timedelta(days=31)})
        db.commit()
    assert price_archive.run_due()["sheets"] == 2

    # Its own daily allowance: stops when it's used up, and the rest waits for another day.
    monkeypatch.setattr(keys_on, "archive_greysheet_day", 0)
    with SessionLocal() as db:
        db.query(GradePriceSheet).update({"fetched_at": datetime.now(timezone.utc) - timedelta(days=31)})
        db.commit()
    assert price_archive.run_due()["stopped"] == "greysheet allowance"


def test_chart_follows_the_market(authed, morgan_collection):
    today = date.today()

    def ym(months_ago):
        d = (today.replace(day=15) - timedelta(days=30 * months_ago))
        return f"{d.year}-{d.month:02d}"

    c = authed.post("/api/coins", json=coin_payload(morgan_collection["id"], pcgs_number="7130", grade=64, price_paid="100",
                                                    purchase_date=(today - timedelta(days=365)).isoformat())).json()
    with SessionLocal() as db:
        coin = db.query(Coin).filter_by(inventory_number=c["inventory_number"]).one()
        # The market rose sharply mid-year and came back down.
        sales = [_sale(ym(m), 100 if m >= 10 else 400 if 4 <= m <= 8 else 200, cert=f"{m}-{i}")
                 for m in range(0, 13) for i in range(3)]
        price_archive.save_sales(db, "7130", 64, False, sales)
        db.add(PriceQuote(coin_id=coin.id, source="CPG", value=Decimal(200), fetched_at=datetime.now(timezone.utc)))
        db.commit()
        pts = value_history(db, coin.user_id)
    start = today - timedelta(days=365)
    mid = next(p for p in pts if p["date"] >= (start + timedelta(days=180)).isoformat())
    days = (date.fromisoformat(mid["date"]) - start).days
    straight = 100 + (200 - 100) * days / 365
    assert pts[0]["value"] == "100.00" and pts[-1]["value"] == "200.00"  # still starts and ends where it should
    assert float(mid["value"]) > straight + 50  # but follows the mid-year rise
    assert all(p["backfilled"] for p in pts[:-1])


def test_one_coins_history(authed, morgan_collection):
    a = authed.post("/api/coins", json=coin_payload(morgan_collection["id"], price_paid="100", purchase_date="2025-01-05")).json()
    authed.post("/api/coins", json=coin_payload(morgan_collection["id"], price_paid="999", purchase_date="2025-01-05"))
    pts = authed.get(f"/api/coins/{a['inventory_number']}/history").json()
    assert pts[0]["date"] == "2025-01-05" and {p["cost"] for p in pts} == {"100.00"}  # only this coin
