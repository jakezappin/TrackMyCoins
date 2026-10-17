"""Value over time, rebuilt from price history and purchase/sale dates."""

from datetime import datetime, timezone

from app.db import SessionLocal
from app.models import PriceQuote
from test_api import coin_payload


def _quote(coin_id, source, value, day):
    with SessionLocal() as db:
        db.add(PriceQuote(coin_id=coin_id, source=source, value=value, fetched_at=datetime.fromisoformat(day).replace(tzinfo=timezone.utc)))
        db.commit()


def test_value_history(authed, morgan_collection):
    cid = morgan_collection["id"]
    a = authed.post("/api/coins", json=coin_payload(cid, price_paid="100.00", purchase_date="2026-01-10")).json()
    b = authed.post("/api/coins", json=coin_payload(cid, price_paid="300.00", purchase_date="2026-03-01",
                                                     sale_price="400", sale_date="2026-06-01")).json()
    _quote(a["id"], "CPG", "150.00", "2026-02-01")
    _quote(b["id"], "CPG", "350.00", "2026-03-05")
    _quote(a["id"], "PREMIUM", "250.00", "2026-04-01")  # toner premium added

    pts = {p["date"]: p for p in authed.get("/api/history", params={"collection_id": cid}).json()}
    assert (pts["2026-01-10"]["cost"], pts["2026-01-10"]["value"]) == ("100.00", None)  # bought, not yet priced
    assert pts["2026-02-01"]["value"] == "150.00"
    assert (pts["2026-03-01"]["cost"], pts["2026-03-01"]["value"], pts["2026-03-01"]["priced_count"]) == ("400.00", "150.00", 1)
    assert pts["2026-03-05"]["value"] == "500.00"
    assert pts["2026-04-01"]["value"] == "600.00"
    assert (pts["2026-06-01"]["cost"], pts["2026-06-01"]["value"], pts["2026-06-01"]["coin_count"]) == ("100.00", "250.00", 1)  # sold
    assert list(pts) == sorted(pts)  # in date order, ending today

    assert authed.get("/api/history").json()[-1]["cost"] == "100.00"  # all collections
    assert authed.get("/api/history", params={"collection_id": 99999}).status_code == 404
