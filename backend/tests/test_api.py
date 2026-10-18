import itertools
from datetime import date
from decimal import Decimal

import pytest

from conftest import signup

def _png() -> bytes:
    import io

    from PIL import Image

    b = io.BytesIO()
    Image.new("RGBA", (40, 30), (180, 180, 190, 255)).save(b, "PNG")
    return b.getvalue()


PNG = _png()


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
    assert img.status_code == 200 and img.headers["content-type"] == "image/jpeg"  # stored compressed
    thumb = authed.get(d["photos"][0]["thumb_url"])
    assert thumb.status_code == 200 and thumb.headers["content-type"] == "image/jpeg"
    assert d["thumbnail_url"].endswith("?size=thumb")  # lists use the thumbnail
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

    assert len(types) == len(SERIES) == 61
    assert types[0]["slug"] == "half-cents"  # catalog order
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
    assert authed.get("/api/public/stats").json() == {"series": 61, "collection_types": 118, "categories": 11}
    stella = _type(authed, "four-dollar-stella")
    assert [f["code"] for f in stella["finishes"]] == ["PR"]  # proof-only
    gts = _type(authed, "gold-type-set")
    assert gts["is_type_set"] and len(gts["member_ids"]) == 15
    assert types[-1]["slug"] == "gold-type-set"


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


def test_estimated_value(authed, morgan_collection):
    cid = morgan_collection["id"]
    a = authed.post("/api/coins", json=coin_payload(cid, price_paid="100.00", toning_rainbow=True)).json()
    b = authed.post("/api/coins", json=coin_payload(cid, price_paid="50.00")).json()
    ia, ib = a["inventory_number"], b["inventory_number"]
    # A toner premium needs a CPG price to add to
    assert authed.put(f"/api/coins/{ia}/valuation", json={"source": "cpg", "toner_premium": "150"}).status_code == 400
    authed.post(f"/api/coins/{ia}/price-quotes", json={"value": "200.00"})

    # CPG + toner premium + holder premium (e.g. a toned coin in a Rattler)
    d = authed.put(f"/api/coins/{ia}/valuation", json={"source": "cpg", "toner_premium": "150.00", "holder_premium": "40.00"}).json()
    assert (d["value_source"], d["toner_premium"], d["holder_premium"], d["value_estimate"]) == ("cpg", "150.00", "40.00", "390.00")
    est = next(q for q in d["price_quotes"] if q["source"] == "PREMIUM")
    assert est["value"] == "390.00"
    assert est["description"] == "Estimate: CPG $200.00 + toner premium $150.00 + holder premium $40.00"
    assert d["latest_cpg"]["value"] == "200.00"  # CPG itself unchanged

    # Your own value (no CPG needed)
    d = authed.put(f"/api/coins/{ib}/valuation", json={"source": "custom", "custom_value": "75.00"}).json()
    assert (d["value_source"], d["value_estimate"]) == ("custom", "75.00")
    assert next(q for q in d["price_quotes"] if q["source"] == "CUSTOM")["value"] == "75.00"
    assert authed.put(f"/api/coins/{ib}/valuation", json={"source": "custom"}).status_code == 422

    s = authed.get(f"/api/collections/{cid}").json()["summary"]
    assert s["total_estimated_value"] == "465.00" and s["total_cpg_value"] == "200.00"
    assert (s["toner_count"], s["toner_premium_total"], s["holder_count"], s["holder_premium_total"]) == (1, "150.00", 1, "40.00")
    assert (s["custom_count"], s["unpriced_count"]) == (1, 0)
    assert s["est_wholesale_value"] == "418.50"  # 90% of estimated value
    assert authed.get("/api/dashboard").json()["totals"]["total_estimated_value"] == "465.00"

    # A lowball premium too (a low grade the lowball registry sets want)
    d = authed.put(f"/api/coins/{ia}/valuation", json={"source": "cpg", "toner_premium": "150.00", "holder_premium": "40.00",
                                                        "lowball_premium": "25.00"}).json()
    assert (d["lowball_premium"], d["value_estimate"]) == ("25.00", "415.00")
    assert next(q for q in d["price_quotes"] if q["source"] == "PREMIUM")["description"].endswith("+ lowball premium $25.00")
    s = authed.get(f"/api/collections/{cid}").json()["summary"]
    assert (s["lowball_count"], s["lowball_premium_total"], s["total_estimated_value"]) == (1, "25.00", "490.00")

    # Back to plain CPG
    d = authed.put(f"/api/coins/{ia}/valuation", json={"source": "cpg"}).json()
    assert d["toner_premium"] is None and d["holder_premium"] is None and d["lowball_premium"] is None
    assert d["value_estimate"] == "200.00"


def test_purchase_and_sale_dates_must_be_sensible(authed, morgan_collection):
    r = authed.post("/api/coins", json=coin_payload(morgan_collection["id"], purchase_date="0017-12-31"))
    assert r.status_code == 422 and "mistyped" in str(r.json()["detail"]) and "2017" in str(r.json()["detail"])
    r = authed.post("/api/coins", json=coin_payload(morgan_collection["id"], sale_date="2107-01-01", sale_price="10"))
    assert r.status_code == 422 and "future" in str(r.json()["detail"])
    assert authed.post("/api/coins", json=coin_payload(morgan_collection["id"], purchase_date="1985-06-01")).status_code == 201


@pytest.mark.parametrize("changes, message", [
    ({"year": date.today().year + 2}, "in the future"),
    ({"purchase_date": "2026-02-30"}, "date"),                       # not a real day
    ({"purchase_date": "2025-06-01", "sale_date": "2025-05-01", "sale_price": "10"}, "before the purchase date"),
    ({"price_paid": "abc"}, "valid decimal"),
    ({"price_paid": "-5"}, "greater than or equal to 0"),
    ({"price_paid": "12.345"}, "decimal places"),
    ({"price_paid": "NaN"}, "finite"),
    ({"grade": 71}, "less than or equal to 70"),
    ({"grade_prefix": "ZZ"}, "Unknown grade"),
    ({"cert_number": "12 34;5"}, "letters, digits and dashes"),
    ({"pcgs_number": "71a"}, "digits only"),
    ({"notes": "x" * 5001}, "at most 5000"),
])
def test_coin_fields_rejected(authed, morgan_collection, changes, message):
    r = authed.post("/api/coins", json={**coin_payload(morgan_collection["id"]), **changes})
    assert r.status_code == 422, r.text
    assert message.lower() in r.text.lower(), r.text


def test_coin_fields_normalized(authed, morgan_collection):
    c = authed.post("/api/coins", json={**coin_payload(morgan_collection["id"]), "grade_prefix": "ef", "grade": 45}).json()
    assert c["grade_prefix"] == "XF"
    r = authed.put(f"/api/coins/{c['inventory_number']}/valuation", json={"source": "custom", "custom_value": "-1"})
    assert r.status_code == 422
    r = authed.post(f"/api/coins/{c['inventory_number']}/price-quotes", json={"source": "eBay", "value": "10"})
    assert r.status_code == 422


def test_signup_limits_and_real_client_ip(client, monkeypatch):
    from app.config import get_settings
    from app.routers import auth

    monkeypatch.setattr(get_settings(), "signup_mode", "invite")
    monkeypatch.setattr(get_settings(), "invite_code", "RIGHT")
    body = {"email": "g@example.com", "first_name": "G", "last_name": "H", "password": "long enough password"}
    for _ in range(get_settings().signup_max_failures):
        assert client.post("/api/auth/signup", json={**body, "invite_code": "WRONG"}).status_code == 403
    assert client.post("/api/auth/signup", json={**body, "invite_code": "RIGHT"}).status_code == 429  # guessing stopped
    # Another address (as Fly's proxy reports it) isn't affected, and a faked X-Forwarded-For doesn't help
    r = client.post("/api/auth/signup", json={**body, "invite_code": "RIGHT"}, headers={"Fly-Client-IP": "203.0.113.9"})
    assert r.status_code == 201
    assert auth.signup_limiter.blocked("ip:testclient")


def test_production_needs_a_real_session_secret(monkeypatch):
    import pytest as _pytest

    from app.config import DEV_SECRET, Settings, check_production

    monkeypatch.setenv("FLY_APP_NAME", "trackmycoins")
    with _pytest.raises(RuntimeError):
        check_production(Settings(session_secret=DEV_SECRET))
    check_production(Settings(session_secret="x" * 64))  # fine


def test_move_between_collections(authed):
    from test_reports import _collection

    a = _collection(authed, "morgan-dollars", name="Morgans A")
    b = _collection(authed, "morgan-dollars", name="Morgans B")
    peace = _collection(authed, "peace-dollars", name="Peace")
    proofs = _collection(authed, "morgan-dollars", finish="PR", name="Morgan Proofs")
    coin = authed.post("/api/coins", json=coin_payload(a["id"], year=1881, mint_mark="S")).json()
    inv = coin["inventory_number"]

    targets = authed.get(f"/api/coins/{inv}/move-targets").json()
    assert {t["name"] for t in targets} == {"Morgans B", "Morgan Proofs"}  # same series only; not Peace
    d = authed.post(f"/api/coins/{inv}/move", json={"collection_id": b["id"]}).json()
    assert d["collection_id"] == b["id"] and d["inventory_number"] == inv  # same inventory number
    assert authed.post(f"/api/coins/{inv}/move", json={"collection_id": peace["id"]}).status_code == 400
    r = authed.post(f"/api/coins/{inv}/move", json={"collection_id": proofs["id"]})  # an MS coin isn't a proof
    assert r.status_code == 422 and "proof" in r.text


def test_attachments_upload_view_delete(authed, morgan_collection, client):
    from app.services import attachments as store

    coin = authed.post("/api/coins", json=coin_payload(morgan_collection["id"])).json()
    inv = coin["inventory_number"]
    pdf = b"%PDF-1.4\n% receipt\n%%EOF\n"
    files = [("files", ("../Heritage invoice.pdf", pdf, "application/pdf")), ("files", ("receipt.png", PNG, "image/png"))]
    got = authed.post(f"/api/coins/{inv}/attachments", files=files).json()
    assert [a["name"] for a in got] == ["Heritage invoice.pdf", "receipt.jpg"]  # photo stored compressed
    r = authed.get(got[0]["url"])
    assert r.status_code == 200 and r.content == pdf and r.headers["content-type"] == "application/pdf"
    assert "Heritage%20invoice.pdf" in r.headers["content-disposition"]
    # Not a PDF, not an image, or too many files: refused
    bad = authed.post(f"/api/coins/{inv}/attachments", files=[("files", ("x.pdf", b"hello", "application/pdf"))])
    assert bad.status_code == 400
    bad = authed.post(f"/api/coins/{inv}/attachments", files=[("files", ("x.txt", b"hi", "text/plain"))])
    assert bad.status_code == 400
    many = [("files", (f"r{i}.pdf", pdf, "application/pdf")) for i in range(9)]
    assert authed.post(f"/api/coins/{inv}/attachments", files=many).status_code == 400
    # Another user can't see them
    authed.post("/api/auth/logout")
    signup(client, "other@example.com")
    assert client.get(got[0]["url"]).status_code == 404
    assert client.delete(got[0]["url"]).status_code == 404
    client.post("/api/auth/logout")
    client.post("/api/auth/login", json={"email": "me@example.com", "password": "correct horse battery"})
    assert authed.delete(got[1]["url"]).status_code == 204
    assert len(authed.get(f"/api/coins/{inv}/attachments").json()) == 1
    # Deleting the coin removes its files
    assert store.coin_dir(coin["id"]).exists()
    authed.delete(f"/api/coins/{inv}")
    assert not store.coin_dir(coin["id"]).exists()
