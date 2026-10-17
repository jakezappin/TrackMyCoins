"""Want list."""

from test_api import coin_payload
from test_catalog import calls, fake_greysheet  # noqa: F401  (autouse fixture)
from test_reports import _collection


def test_want_list(client, authed):
    col = _collection(authed, "morgan-dollars", name="My Morgans")
    w = authed.post("/api/wants", json={"collection_id": col["id"], "year": 1881, "mint_mark": "s", "grade": 65,
                                        "grade_prefix": "MS", "max_price": "1200"}).json()
    assert (w["label"], w["target_label"], w["max_price"], w["cpg"], w["owned"]) == (
        "1881-S Morgan Dollar", "MS65", "1200.00", None, None)
    assert w["priceable"]  # not priced yet; a "Get price" button can fetch it

    again = authed.post("/api/wants", json={"collection_id": col["id"], "year": 1881, "mint_mark": "S", "grade": 66}).json()
    assert again["id"] == w["id"] and len(authed.get("/api/wants").json()) == 1  # same coin: updated, not duplicated

    n = len(calls)
    p = authed.post(f"/api/wants/{w['id']}/price").json()
    assert len([c for c in calls[n:] if c.startswith("GetPricingRequest")]) == 1
    assert p["cpg"] == "2000.00"  # MS66 in the fake price sheet

    authed.post("/api/coins", json=coin_payload(col["id"], year=1881, mint_mark="S", grade=66))
    owned = authed.get("/api/wants").json()[0]["owned"]
    assert owned["grade"] == 66 and owned["meets_target"]

    edited = authed.put(f"/api/wants/{w['id']}", json={"collection_id": col["id"], "year": 1881, "mint_mark": "S",
                                                        "grade": 67, "notes": "  wait for a toner "}).json()
    assert edited["grade"] == 67 and edited["notes"] == "wait for a toner" and not edited["owned"]["meets_target"]

    client.post("/api/auth/logout")
    client.post("/api/auth/signup", json={"email": "z@example.com", "first_name": "Z", "last_name": "Y", "password": "long enough pw"})
    assert client.get("/api/wants").json() == []
    assert client.delete(f"/api/wants/{w['id']}").status_code == 404


def test_want_validation_and_delete(authed):
    col = _collection(authed, "morgan-dollars")
    assert authed.post("/api/wants", json={"year": 1881, "mint_mark": "S"}).status_code == 422  # no series
    assert authed.post("/api/wants", json={"collection_id": col["id"], "year": 1881, "mint_mark": "S",
                                           "grade_prefix": "ZZ"}).status_code == 422
    w = authed.post("/api/wants", json={"collection_id": col["id"], "year": 1880, "mint_mark": "CC"}).json()
    assert authed.delete(f"/api/wants/{w['id']}").status_code == 204
    assert authed.get("/api/wants").json() == []


def test_want_with_invalid_year_refused(authed):
    ct = next(t for t in authed.get("/api/coin-types").json() if t["slug"] == "peace-dollars")
    r = authed.post("/api/wants", json={"coin_type_id": ct["id"], "finish": "MS", "year": 1930, "mint_mark": "P"})
    assert r.status_code == 422 and "1930 isn't a Peace Dollar date" in r.json()["detail"]
