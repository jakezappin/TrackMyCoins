"""Dashboard totals, recent collections and sales, and quick search."""

import time
from decimal import Decimal

from test_api import _type, coin_payload


def _col(c, name, slug="morgan-dollars"):
    return c.post("/api/collections", json={"name": name, "coin_type_id": _type(c, slug)["id"]}).json()


def test_totals_across_collections(authed):
    a, b = _col(authed, "A"), _col(authed, "B", "peace-dollars")
    x = authed.post("/api/coins", json=coin_payload(a["id"], price_paid="100.00")).json()
    authed.post("/api/coins", json=coin_payload(b["id"], year=1922, mint_mark="P", price_paid="50.00"))
    authed.post("/api/coins", json=coin_payload(a["id"], price_paid="999.00", sale_price="1200", sale_date="2026-09-01"))  # sold: excluded
    authed.post(f"/api/coins/{x['inventory_number']}/price-quotes", json={"value": "200.00"})

    t = authed.get("/api/dashboard").json()["totals"]
    assert (t["coin_count"], t["collection_count"], t["unpriced_count"]) == (2, 2, 1)
    assert Decimal(t["total_price_paid"]) == Decimal("150.00")
    assert Decimal(t["total_cpg_value"]) == Decimal("200.00")
    assert Decimal(t["est_wholesale_value"]) == Decimal("180.00")


def test_recent_collections_and_sales(authed):
    a, b, c = _col(authed, "A"), _col(authed, "B"), _col(authed, "C")
    # Open B, then A; C never opened.
    authed.get(f"/api/collections/by-number/morgan-dollars/{b['number']}")
    time.sleep(0.01)
    authed.get(f"/api/collections/by-number/morgan-dollars/{a['number']}")
    d = authed.get("/api/dashboard").json()
    assert [x["name"] for x in d["recent_collections"]] == ["A", "B", "C"]
    assert d["recent_collections"][0]["last_viewed_at"] is not None

    old = authed.post("/api/coins", json=coin_payload(a["id"], price_paid="100", sale_price="150", sale_date="2026-01-05")).json()
    new = authed.post("/api/coins", json=coin_payload(b["id"], price_paid="300", sale_price="250", sale_date="2026-09-20")).json()
    sales = authed.get("/api/dashboard").json()["recent_sales"]
    assert [s["coin"]["inventory_number"] for s in sales] == [new["inventory_number"], old["inventory_number"]]
    assert [Decimal(s["profit"]) for s in sales] == [Decimal("-50"), Decimal("50")]
    assert sales[0]["collection_name"] == "B"


def test_quick_search(authed):
    col = _col(authed, "Morgans")
    s81 = authed.post("/api/coins", json=coin_payload(col["id"], year=1881, mint_mark="S", cert_number="44556677", variety="GSA Hoard", notes="from the Smith estate")).json()
    c84 = authed.post("/api/coins", json=coin_payload(col["id"], year=1884, mint_mark="CC", cert_number="12340000", purchased_from="Heritage")).json()
    p84 = authed.post("/api/coins", json=coin_payload(col["id"], year=1884, mint_mark="P")).json()

    def hits(q):
        return [h["coin"]["inventory_number"] for h in authed.get("/api/search/coins", params={"q": q}).json()]

    assert hits(s81["inventory_number"].lower())[0] == s81["inventory_number"]  # inventory #
    assert hits("4455-6677") == [s81["inventory_number"]]  # cert, ignoring punctuation
    assert hits("1884-CC") == [c84["inventory_number"]]
    assert hits("1884 cc") == [c84["inventory_number"]]
    assert sorted(hits("1884")) == sorted([c84["inventory_number"], p84["inventory_number"]])
    assert hits("smith") == [s81["inventory_number"]]  # notes
    assert hits("gsa hoard") == [s81["inventory_number"]]  # variety, all words
    assert hits("heritage") == [c84["inventory_number"]]  # seller
    assert hits("nothing like this") == []

    first = authed.get("/api/search/coins", params={"q": "1881-S"}).json()[0]
    assert first["type_name"] == "Morgan Dollar" and first["collection_name"] == "Morgans"


def test_search_is_per_user(client):
    from conftest import signup

    signup(client, "a@example.com")
    col = _col(client, "Mine")
    coin = client.post("/api/coins", json=coin_payload(col["id"], cert_number="99887766")).json()
    client.post("/api/auth/logout")
    signup(client, "b@example.com")
    assert client.get("/api/search/coins", params={"q": "99887766"}).json() == []
    assert client.get("/api/search/coins", params={"q": coin["inventory_number"]}).json() == []
