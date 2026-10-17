import itertools
from decimal import Decimal

from conftest import signup

PNG = (
    b"\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR\x00\x00\x00\x01\x00\x00\x00\x01\x08\x06\x00\x00\x00\x1f\x15\xc4\x89"
    b"\x00\x00\x00\rIDATx\x9cc\xf8\x0f\x00\x00\x01\x01\x00\x05\x18\xd8N\x00\x00\x00\x00IEND\xaeB`\x82"
)


_certs = itertools.count(10000001)


def coin_payload(collection_id, **kw):
    base = {
        "collection_id": collection_id,
        "year": 1881,
        "mint_mark": "s",
        "grading_service": "PCGS",
        "cert_number": str(next(_certs)),  # unique unless a test sets one
        "grade_prefix": "MS",
        "grade": 65,
        "price_paid": "250.00",
    }
    base.update(kw)
    return base


def test_requires_login(client):
    assert client.get("/api/collections").status_code == 401


def test_signup_login_logout(client):
    signup(client)
    assert client.get("/api/auth/me").json()["email"] == "me@example.com"
    client.post("/api/auth/logout")
    assert client.get("/api/auth/me").status_code == 401
    bad = client.post("/api/auth/login", json={"email": "me@example.com", "password": "nope"})
    assert bad.status_code == 401
    ok = client.post("/api/auth/login", json={"email": "ME@example.com", "password": "correct horse battery"})
    assert ok.status_code == 200
    assert client.get("/api/auth/me").status_code == 200


def test_duplicate_signup(client):
    signup(client)
    r = client.post(
        "/api/auth/signup",
        json={"email": "Me@Example.com", "first_name": "A", "last_name": "B", "password": "another long pw"},
    )
    assert r.status_code == 409


def test_inventory_numbers_and_normalization(authed, morgan_collection):
    a = authed.post("/api/coins", json=coin_payload(morgan_collection["id"])).json()
    b = authed.post("/api/coins", json=coin_payload(morgan_collection["id"], year=1884, mint_mark="cc")).json()
    assert a["inventory_number"] == "MOR-00001"
    assert b["inventory_number"] == "MOR-00002"
    assert a["mint_mark"] == "S"
    assert b["mint_mark"] == "CC"


def test_invalid_mint_mark(authed, morgan_collection):
    r = authed.post("/api/coins", json=coin_payload(morgan_collection["id"], mint_mark="W"))
    assert r.status_code == 422


def test_cac_sticker_implies_cac(authed, morgan_collection):
    c = authed.post("/api/coins", json=coin_payload(morgan_collection["id"], cac_sticker="gold")).json()
    assert c["cac"] is True and c["cac_sticker"] == "gold"
    body = coin_payload(morgan_collection["id"], cac=False, cac_sticker=None)
    c = authed.put(f"/api/coins/{c['inventory_number']}", json=body).json()
    assert c["cac"] is False and c["cac_sticker"] is None


def test_summary_and_sold(authed, morgan_collection):
    cid = morgan_collection["id"]
    a = authed.post("/api/coins", json=coin_payload(cid, price_paid="100.00")).json()
    b = authed.post("/api/coins", json=coin_payload(cid, price_paid="200.00")).json()
    authed.post(f"/api/coins/{a['inventory_number']}/price-quotes", json={"value": "150.00"})
    authed.post(f"/api/coins/{a['inventory_number']}/price-quotes", json={"value": "160.00"})  # newer one wins

    s = authed.get(f"/api/collections/{cid}").json()["summary"]
    assert Decimal(s["total_price_paid"]) == Decimal("300.00")
    assert Decimal(s["total_cpg_value"]) == Decimal("160.00")
    assert Decimal(s["est_wholesale_value"]) == Decimal("144.00")
    assert s["unpriced_count"] == 1 and s["coin_count"] == 2

    detail = authed.get(f"/api/coins/{a['inventory_number']}").json()
    assert len(detail["price_quotes"]) == 2  # history kept

    # Sell coin b: it leaves the collection list/totals and appears in Sold
    authed.put(f"/api/coins/{b['inventory_number']}", json=coin_payload(cid, price_paid="200.00", sale_price="275.00", sale_date="2026-10-01"))
    coins = authed.get(f"/api/collections/{cid}/coins").json()
    assert [c["id"] for c in coins] == [a["id"]]
    sold = authed.get(f"/api/coin-types/morgan-dollars/sold").json()
    assert [c["id"] for c in sold] == [b["id"]] and sold[0]["is_sold"]
    s = authed.get(f"/api/collections/{cid}").json()["summary"]
    assert Decimal(s["total_price_paid"]) == Decimal("100.00")

    # Collection with coins (even sold) can't be deleted
    assert authed.delete(f"/api/collections/{cid}").status_code == 409


def test_users_are_isolated(client, morgan_collection):
    coin = client.post("/api/coins", json=coin_payload(morgan_collection["id"])).json()
    client.post("/api/auth/logout")
    signup(client, "other@example.com")
    assert client.get(f"/api/coins/{coin['inventory_number']}").status_code == 404
    assert client.get(f"/api/collections/{morgan_collection['id']}").status_code == 404
    assert client.get("/api/collections").json() == []
    r = client.post("/api/coins", json=coin_payload(morgan_collection["id"]))
    assert r.status_code == 404


def test_photo_upload_limit_and_delete(authed, morgan_collection):
    coin = authed.post("/api/coins", json=coin_payload(morgan_collection["id"])).json()
    files = [("files", (f"p{i}.png", PNG, "image/png")) for i in range(10)]
    d = authed.post(f"/api/coins/{coin['inventory_number']}/photos", files=files).json()
    assert len(d["photos"]) == 10
    r = authed.post(f"/api/coins/{coin['inventory_number']}/photos", files=[("files", ("x.png", PNG, "image/png"))])
    assert r.status_code == 400
    img = authed.get(d["photos"][0]["url"])
    assert img.status_code == 200 and img.content == PNG
    assert authed.delete(d["photos"][0]["url"]).status_code == 204
    assert len(authed.get(f"/api/coins/{coin['inventory_number']}").json()["photos"]) == 9
    bad = authed.post(f"/api/coins/{coin['inventory_number']}/photos", files=[("files", ("x.txt", b"hi", "text/plain"))])
    assert bad.status_code == 400


def test_cpg_without_credentials(authed, morgan_collection):
    coin = authed.post("/api/coins", json=coin_payload(morgan_collection["id"])).json()
    r = authed.post(f"/api/coins/{coin['inventory_number']}/cpg")
    assert r.status_code == 400 and "GREYSHEET_API_KEY" in r.json()["detail"]


def test_collection_numbers_and_lookup(authed):
    ct = next(t for t in authed.get("/api/coin-types").json() if t["slug"] == "morgan-dollars")
    a = authed.post("/api/collections", json={"name": "A", "coin_type_id": ct["id"]}).json()
    b = authed.post("/api/collections", json={"name": "B", "coin_type_id": ct["id"]}).json()
    assert (a["number"], b["number"]) == (1, 2)
    assert a["coin_type_slug"] == "morgan-dollars"

    got = authed.get("/api/collections/by-number/morgan-dollars/2").json()
    assert got["id"] == b["id"] and got["name"] == "B"
    assert authed.get("/api/collections/by-number/morgan-dollars/9").status_code == 404
    assert authed.get("/api/collections/by-number/peace-dollars/1").status_code == 404

    # Numbers are never reused after a delete
    authed.delete(f"/api/collections/{b['id']}")
    c = authed.post("/api/collections", json={"name": "C", "coin_type_id": ct["id"]}).json()
    assert c["number"] == 3

    # Existing id routes still work alongside the by-number route
    assert authed.get(f"/api/collections/{a['id']}/coins").status_code == 200


def test_coin_addressed_by_inventory_number(authed, morgan_collection):
    coin = authed.post("/api/coins", json=coin_payload(morgan_collection["id"])).json()
    assert coin["collection_number"] == 1 and coin["coin_type_slug"] == "morgan-dollars"
    assert authed.get("/api/coins/mor-00001").json()["id"] == coin["id"]  # case-insensitive
    assert authed.get("/api/coins/MOR-00099").status_code == 404
    assert authed.delete("/api/coins/MOR-00001").status_code == 204
    assert authed.get("/api/coins/MOR-00001").status_code == 404


def test_duplicate_cert_rejected(authed, morgan_collection):
    cid = morgan_collection["id"]
    a = authed.post("/api/coins", json=coin_payload(cid, cert_number="1234567-001", grading_service="NGC")).json()

    # Same cert, ignoring dashes/case -> 409 with info about the existing coin
    r = authed.post("/api/coins", json=coin_payload(cid, cert_number="1234567001", grading_service="NGC"))
    assert r.status_code == 409
    dup = r.json()["detail"]["duplicate"]
    assert dup["inventory_number"] == a["inventory_number"] and dup["coin_type_slug"] == "morgan-dollars"

    # Same number at a different service is a different slab
    assert authed.post("/api/coins", json=coin_payload(cid, cert_number="1234567001")).status_code == 201

    # The check endpoint agrees, and excludes the coin being edited
    chk = authed.get("/api/cert-check", params={"service": "NGC", "cert": "1234567-001"}).json()
    assert chk["duplicate"]["inventory_number"] == a["inventory_number"]
    chk = authed.get("/api/cert-check", params={"service": "NGC", "cert": "1234567-001", "exclude": a["inventory_number"]}).json()
    assert chk["duplicate"] is None

    # Editing the original keeps working
    assert authed.put(f"/api/coins/{a['inventory_number']}", json=coin_payload(cid, cert_number="1234567-001", grading_service="NGC", notes="x")).status_code == 200

    # Once sold, the cert can be added again (bought back)
    authed.put(f"/api/coins/{a['inventory_number']}", json=coin_payload(cid, cert_number="1234567-001", grading_service="NGC", sale_price="10"))
    assert authed.post("/api/coins", json=coin_payload(cid, cert_number="1234567-001", grading_service="NGC")).status_code == 201

    # Raw coins have no cert, never duplicates
    for _ in range(2):
        assert authed.post("/api/coins", json=coin_payload(cid, grading_service="RAW", cert_number=None)).status_code == 201


def test_update_profile_and_password(authed):
    r = authed.put("/api/auth/me", json={"email": "me@example.com", "first_name": "Jake", "last_name": "Z"})
    assert r.status_code == 200 and r.json()["first_name"] == "Jake"

    # Email change needs the current password
    body = {"email": "new@example.com", "first_name": "Jake", "last_name": "Z"}
    assert authed.put("/api/auth/me", json=body).status_code == 403
    assert authed.put("/api/auth/me", json={**body, "current_password": "wrong"}).status_code == 403
    assert authed.put("/api/auth/me", json={**body, "current_password": "correct horse battery"}).json()["email"] == "new@example.com"

    assert authed.post("/api/auth/password", json={"current_password": "nope", "new_password": "another long one"}).status_code == 403
    assert authed.post("/api/auth/password", json={"current_password": "correct horse battery", "new_password": "short"}).status_code == 422
    assert authed.post("/api/auth/password", json={"current_password": "correct horse battery", "new_password": "another long one"}).status_code == 204
    authed.post("/api/auth/logout")
    assert authed.post("/api/auth/login", json={"email": "new@example.com", "password": "another long one"}).status_code == 200


def test_email_change_to_taken_address(client):
    signup(client, "other@example.com")
    client.post("/api/auth/logout")
    signup(client)
    r = client.put(
        "/api/auth/me",
        json={"email": "other@example.com", "first_name": "A", "last_name": "B", "current_password": "correct horse battery"},
    )
    assert r.status_code == 409


def _type(c, slug):
    return next(t for t in c.get("/api/coin-types").json() if t["slug"] == slug)


def test_coin_types_and_finishes(authed):
    types = authed.get("/api/coin-types").json()
    from app.series import SERIES

    assert len(types) == len(SERIES) == 44
    assert types[0]["slug"] == "half-cents" and types[-1]["slug"] == "classic-commemoratives"  # catalog order
    ken = _type(authed, "kennedy-half-dollars")
    assert [f["code"] for f in ken["finishes"]] == ["MS", "PR", "SPR"]
    assert ken["finishes"][2]["collection_type_slug"] == "kennedy-half-dollars-silver-proof"
    assert ken["finishes"][1]["collection_type_label"] == "Kennedy Half Dollars – Proof"
    peace = _type(authed, "peace-dollars")
    assert [f["code"] for f in peace["finishes"]] == ["MS"]
    assert peace["finishes"][0]["collection_type_label"] == "Peace Dollars"
    assert len({t["inventory_prefix"] for t in types}) == len(types)  # prefixes unique
    gold = _type(authed, "saint-gaudens-double-eagles")
    assert gold["metal"] == "gold" and "C" not in gold["mint_marks"]
    assert _type(authed, "gold-eagles-50")["metal"] == "gold"
    assert _type(authed, "american-silver-eagles")["metal"] == "silver"
    assert authed.get("/api/public/stats").json() == {"series": 44, "collection_types": 89, "categories": 9}


def test_proof_collections(authed):
    ken = _type(authed, "kennedy-half-dollars")
    ms = authed.post("/api/collections", json={"name": "Kennedy BU", "coin_type_id": ken["id"]}).json()
    pr = authed.post("/api/collections", json={"name": "Kennedy Proofs", "coin_type_id": ken["id"], "finish": "PR"}).json()
    spr = authed.post("/api/collections", json={"name": "Kennedy Silver", "coin_type_id": ken["id"], "finish": "SPR"}).json()
    # Numbering is per collection type
    assert (ms["number"], pr["number"], spr["number"]) == (1, 1, 1)
    assert pr["collection_type_slug"] == "kennedy-half-dollars-proof"
    got = authed.get("/api/collections/by-number/kennedy-half-dollars-silver-proof/1").json()
    assert got["id"] == spr["id"] and got["finish"] == "SPR"
    assert authed.get("/api/collections/by-number/kennedy-half-dollars-proof/2").status_code == 404
    assert authed.get("/api/collections/by-number/nonsense-proof/1").status_code == 404

    # Peace dollars have no proof collection type
    peace = _type(authed, "peace-dollars")
    r = authed.post("/api/collections", json={"name": "Peace PR", "coin_type_id": peace["id"], "finish": "PR"})
    assert r.status_code == 400

    # Proof collections take PR grades (defaulting to PR); MS collections reject PR
    c = authed.post("/api/coins", json=coin_payload(pr["id"], year=1992, mint_mark="S", grade_prefix=None, grade=69, strike_designation="dcam")).json()
    assert c["grade_prefix"] == "PR" and c["strike_designation"] == "DCAM"
    assert c["inventory_number"] == "KEN-00001" and c["collection_type_slug"] == "kennedy-half-dollars-proof"
    assert authed.post("/api/coins", json=coin_payload(pr["id"], year=1992, mint_mark="S", grade_prefix="MS")).status_code == 422
    assert authed.post("/api/coins", json=coin_payload(ms["id"], year=1992, mint_mark="S", grade_prefix="PR")).status_code == 422

    # Inventory numbers are per series, shared across finishes
    c2 = authed.post("/api/coins", json=coin_payload(ms["id"], year=1964, mint_mark="D")).json()
    assert c2["inventory_number"] == "KEN-00002"


def test_designation_normalized(authed, morgan_collection):
    c = authed.post("/api/coins", json=coin_payload(morgan_collection["id"], strike_designation="dmpl ")).json()
    assert c["strike_designation"] == "DMPL"


def test_raw_coins(authed, morgan_collection):
    cid = morgan_collection["id"]
    # Letter grade only, with slab/CAC fields that don't apply to raw coins
    raw = authed.post("/api/coins", json=coin_payload(
        cid, grading_service="RAW", cert_number="999", grade_prefix="au", grade=None,
        cac=True, cac_sticker="green", slab_rattler=True, grade_plus=True, gsa_soft_pack=True,
    )).json()
    assert (raw["grading_service"], raw["grade_prefix"], raw["grade"]) == ("RAW", "AU", None)
    assert raw["cert_number"] is None and raw["cac"] is False and raw["cac_sticker"] is None
    assert raw["slab_rattler"] is False and raw["grade_plus"] is False
    assert raw["gsa_soft_pack"] is True  # GSA coins are often raw, in the GSA holder

    # Letter grade with a number, or no grade at all
    assert authed.post("/api/coins", json=coin_payload(cid, grading_service="RAW", grade_prefix="VF", grade=30)).json()["grade"] == 30
    none = authed.post("/api/coins", json=coin_payload(cid, grading_service="RAW", grade_prefix=None, grade=None)).json()
    assert none["grade_prefix"] is None and none["grade"] is None

    # CPG needs a number
    r = authed.post(f"/api/coins/{raw['inventory_number']}/cpg")
    assert r.status_code == 400 and "give this raw coin a number" in r.json()["detail"].lower()


def test_ike_packaging(authed):
    ike = _type(authed, "ike-dollars")
    col = authed.post("/api/collections", json={"name": "Ikes", "coin_type_id": ike["id"]}).json()
    c = authed.post("/api/coins", json=coin_payload(col["id"], year=1971, mint_mark="S", ike_blue_pack=True, grading_service="RAW")).json()
    assert c["ike_blue_pack"] is True
    both = coin_payload(col["id"], year=1972, mint_mark="S", ike_blue_pack=True, ike_brown_pack=True)
    assert authed.post("/api/coins", json=both).status_code == 422
