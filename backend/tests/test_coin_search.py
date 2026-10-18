"""The Add Coin search: the bundled catalog, parsing "1880/79-CC Morgan", and a collection made on save."""

from test_api import coin_payload

from app.db import SessionLocal
from app.services import catalog


def _seed():
    with SessionLocal() as db:
        return catalog.seed_from_bundle(db)


def test_bundle_seeds_once(client):
    assert _seed() > 9000
    assert _seed() == 0  # already as new as the bundle


def test_search(authed, morgan_collection):
    _seed()
    s = lambda q: authed.get("/api/catalog/search", params={"q": q}).json()  # noqa: E731
    top = s("1878-S Morgan")[0]
    assert (top["label"], top["pcgs_number"], top["collection_id"]) == ("1878-S Morgan Dollar", "7082", morgan_collection["id"])
    assert s("1878 7TF Rev of 78")[0]["variety"] == "7TF, Reverse of 1878"
    od = s("1880/79-CC Morgan")[0]
    assert od["label"] == "1880/79-CC Morgan Dollar" and od["pcgs_number"] == "7108"
    assert s("1882-O/S Morgan")[0]["label"] == "1882-O/S Morgan Dollar"
    assert s("1881-CC DMPL")[0]["designation"] == "DMPL"
    rosie = s("1962 Roosevelt Proof")[0]
    assert rosie["finish"] == "PR" and rosie["collection_id"] is None and rosie["label"].startswith("1962 Roosevelt")
    assert s("Morg") == []


def test_create_with_new_collection(authed):
    _seed()
    hit = authed.get("/api/catalog/search", params={"q": "1962 Roosevelt Proof"}).json()[0]
    body = coin_payload(0, year=1962, mint_mark=hit["mint_mark"], grade_prefix="PR", grade=67, pcgs_number=hit["pcgs_number"],
                        new_collection={"coin_type_id": hit["coin_type_id"], "finish": "PR"})
    r = authed.post("/api/coins", json=body)
    assert r.status_code == 201, r.text
    c = r.json()
    assert c["collection_type_slug"] == "roosevelt-dimes-proof"
    # The next one goes into that collection.
    assert authed.get("/api/catalog/search", params={"q": "1963 Roosevelt Proof"}).json()[0]["collection_id"] == c["collection_id"]
