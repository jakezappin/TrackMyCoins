"""Fixes from the October 2026 bug review: PDF text, grade rules, CAC pages, refresh resilience, Greysheet rows,
type-set Sold pages, sessions, movers, spot prices and more."""

from datetime import datetime, timedelta, timezone
from decimal import Decimal
from types import SimpleNamespace

from fastapi.testclient import TestClient
from test_api import coin_payload
from test_reports import _collection

from app.db import SessionLocal
from app.main import app
from app.models import Coin, PriceQuote, User
from app.services import catalog, greysheet, jobs, metals, price_refresh
from app.services.lookups import cac


# ---- Insurance PDF: special characters ----------------------------------------------------------------------

def test_insurance_pdf_with_markup_characters(authed):
    col = _collection(authed, "morgan-dollars", name="Mine & <Yours>")
    for body in (
        coin_payload(col["id"], variety="VAM 1A <B", purchased_from="<i>Dealer & Sons", price_paid="100"),
        coin_payload(col["id"], vam="VAM-3 </b>", grade=65, grade_star=True),
        coin_payload(col["id"], grade_prefix="AU", grade=None, details=True, details_problem="cleaned"),
    ):
        r = authed.post("/api/coins", json=body)
        assert r.status_code == 201, r.text
    r = authed.get("/api/reports/insurance")
    assert r.status_code == 200, r.text
    assert r.content.startswith(b"%PDF")


# ---- Grade combinations and designations -----------------------------------------------------------------------

def test_grade_combinations(authed):
    morgan = _collection(authed, "morgan-dollars")
    bad = [
        dict(grade_prefix="MS", grade=45),
        dict(grade_prefix="AU", grade=65),
        dict(grade_prefix="MS", grade=70, grade_plus=True),
        dict(grade_prefix="MS", grade=64, strike_designation="RD"),  # copper color on a silver Morgan
        dict(grade_prefix="MS", grade=64, strike_designation="DCAM"),  # proof designation on a business strike
        dict(grade_prefix="SP", grade=64),  # an 1881-S isn't a specimen
        dict(grade_prefix="MS", grade=64, strike_designation="FT"),  # Full Torch is a Roosevelt dime's
        dict(grade_prefix="MS", grade=64, strike_designation="Shiny"),  # not a designation at all
    ]
    for kw in bad:
        r = authed.post("/api/coins", json=coin_payload(morgan["id"], **kw))
        assert r.status_code == 422, (kw, r.text)
    for kw in (dict(grade_prefix="MS", grade=64, grade_plus=True), dict(grade_prefix="AU", grade=58),
               dict(grade_prefix="VF", grade=35), dict(grade_prefix="MS", grade=64, strike_designation="Deep Mirror Prooflike")):
        r = authed.post("/api/coins", json=coin_payload(morgan["id"], **kw))
        assert r.status_code == 201, (kw, r.text)
    assert r.json()["strike_designation"] == "DMPL"

    # Spelled-out designations are understood, and FT is known.
    rosie = _collection(authed, "roosevelt-dimes")
    r = authed.post("/api/coins", json=coin_payload(rosie["id"], year=1950, mint_mark="D", grade=66, strike_designation="Full Torch"))
    assert r.status_code == 201 and r.json()["strike_designation"] == "FT", r.text
    lincoln = _collection(authed, "lincoln-cents")
    r = authed.post("/api/coins", json=coin_payload(lincoln["id"], year=1944, mint_mark="D", grade=66, strike_designation="Red"))
    assert r.status_code == 201 and r.json()["strike_designation"] == "RD", r.text
    kennedy_pr = _collection(authed, "kennedy-half-dollars", finish="PR")
    r = authed.post("/api/coins", json=coin_payload(kennedy_pr["id"], year=1971, mint_mark="S", grade_prefix="PR", grade=68,
                                                    strike_designation="Cameo"))
    assert r.status_code == 201 and r.json()["strike_designation"] == "CAM", r.text
    # SP is fine for a Special Mint Set year.
    kennedy = _collection(authed, "kennedy-half-dollars")
    r = authed.post("/api/coins", json=coin_payload(kennedy["id"], year=1966, mint_mark="P", grade_prefix="SP", grade=67))
    assert r.status_code == 201, r.text


def test_duplicate_cert_ignores_leading_zeros(authed, morgan_collection):
    assert authed.post("/api/coins", json=coin_payload(morgan_collection["id"], cert_number="012345678")).status_code == 201
    r = authed.post("/api/coins", json=coin_payload(morgan_collection["id"], cert_number="12345678"))
    assert r.status_code == 409


def test_move_into_proof_collection_sets_pr(authed):
    ms = _collection(authed, "morgan-dollars")
    pr = _collection(authed, "morgan-dollars", finish="PR")
    coin = authed.post("/api/coins", json=coin_payload(ms["id"], grading_service="RAW", cert_number=None,
                                                       grade_prefix=None, grade=None)).json()
    r = authed.post(f"/api/coins/{coin['inventory_number']}/move", json={"collection_id": pr["id"]})
    assert r.status_code == 200, r.text
    assert r.json()["grade_prefix"] == "PR"


def test_tail_feather_label_spellings():
    from app.services.checklist import _words

    assert _words("7TF Rev of 78") >= _words("7TF Reverse of 1878")
    assert _words("8 TF") == _words("8TF")
    assert _words("7 Tail Feathers, Reverse of 1879") >= _words("7TF Reverse of 1879")
    assert catalog.label_variety("7/8 TF Strong") == "7/8tf strong"


# ---- Collections ---------------------------------------------------------------------------------------------

def test_rename_to_taken_name(authed):
    a = _collection(authed, "morgan-dollars", name="Morgans")
    b = _collection(authed, "peace-dollars", name="Peace")
    r = authed.patch(f"/api/collections/{b['id']}", json={"name": "Morgans"})
    assert r.status_code == 409 and "already" in r.json()["detail"]
    assert authed.patch(f"/api/collections/{a['id']}", json={"name": "Morgans"}).status_code == 200  # its own name


def test_type_set_sold_page(authed):
    types = {t["slug"]: t for t in authed.get("/api/coin-types").json()}
    col = _collection(authed, "gold-type-set")
    sold = authed.post("/api/coins", json=coin_payload(
        col["id"], year=1870, mint_mark="CC", coin_type_id=types["liberty-double-eagles"]["id"],
        sale_price="5000", sale_date="2026-10-01", purchase_date="2025-01-01")).json()
    authed.post("/api/coins", json=coin_payload(col["id"], year=1871, mint_mark="CC", coin_type_id=types["liberty-double-eagles"]["id"]))
    got = authed.get("/api/coin-types/gold-type-set/sold").json()
    assert [c["inventory_number"] for c in got] == [sold["inventory_number"]]


# ---- CAC sticker pages -----------------------------------------------------------------------------------------

def test_cac_sticker_parsing():
    nav = '<nav><a href="/gold">Gold</a> <a href="/green">Green bean program</a></nav>'
    page = lambda body: f"<html><body>{nav}<main>{body}</main><footer>Gold coins · Green bean</footer></body></html>"  # noqa: E731
    assert cac.parse_page(page("<h1>Cert 12345678</h1><p>Green CAC sticker</p>"))["sticker"] == "green"
    assert cac.parse_page(page("<p>Sticker: Gold</p>"))["sticker"] == "gold"
    assert cac.parse_page(page('<img src="/img/gold-sticker.png" alt="">'))["sticker"] == "gold"
    # "Gold" in the menu, or describing the coin, says nothing about the sticker.
    r = cac.parse_page(page("<h1>1908 $20 Saint-Gaudens Gold</h1><p>Approved</p>"))
    assert r["sticker"] is None and r["cac"] is True
    assert cac.parse_page(page("<p>This coin has not been approved.</p>"))["cac"] is False


# ---- Greysheet rows ------------------------------------------------------------------------------------------

def _coin(**kw):
    return SimpleNamespace(**{"grade": 64, "grade_prefix": "MS", "grade_plus": False, "cac": False, "details": False,
                              "coin_type": None, **kw})


def test_greysheet_blank_and_wrong_rows():
    only_plus_and_cac = [
        {"Grade": 64, "GradeLabel": "MS64", "CpgVal": None, "IsCac": False},  # blank CPG
        {"Grade": 64, "GradeLabel": "MS64+", "CpgVal": 250, "IsCac": False},
        {"Grade": 64, "GradeLabel": "MS64", "CpgVal": 240, "IsCac": True},
    ]
    assert greysheet._pick(only_plus_and_cac, _coin()) is None  # no plus or CAC price for a plain coin
    assert greysheet._pick(only_plus_and_cac, _coin(grade_plus=True))["CpgVal"] == 250
    assert greysheet._pick(only_plus_and_cac, _coin(cac=True))["CpgVal"] == 240
    full = only_plus_and_cac + [{"Grade": 64, "GradeLabel": "MS64", "CpgVal": 200, "IsCac": False}]
    assert greysheet._pick(full, _coin())["CpgVal"] == 200


# ---- Refresh jobs --------------------------------------------------------------------------------------------

def test_refresh_survives_an_error_page(authed, morgan_collection, monkeypatch):
    for year in (1880, 1881, 1882):
        authed.post("/api/coins", json=coin_payload(morgan_collection["id"], year=year, mint_mark="S", pcgs_number="7130"))
    calls = []

    def fake_cpg(db, coin):
        calls.append(coin.year)
        if coin.year == 1880:
            raise ValueError("Expecting value: line 1 column 1 (char 0)")  # a maintenance page, not JSON
        price_refresh.record(coin, PriceQuote(source="CPG", value=Decimal("100"), grade_used="MS65"))
        return False

    monkeypatch.setattr(price_refresh, "refresh_cpg", fake_cpg)
    with SessionLocal() as db:
        uid = db.query(User).one().id
    job = jobs.Job(id="t1", user_id=uid, kind="refresh-prices", scope="All", include_pcgs=False)
    jobs._run_refresh(job, None)
    assert job.status == "finished", job.messages
    assert sorted(calls) == [1880, 1881, 1882]  # the bad response skipped one coin, not the rest
    assert job.updated == 2 and any("1880" in m and "unexpected response" in m for m in job.messages)


# ---- Sessions ------------------------------------------------------------------------------------------------

def test_password_change_signs_out_other_devices(authed):
    other = TestClient(app)
    assert other.post("/api/auth/login", json={"email": "me@example.com", "password": "correct horse battery"}).status_code == 200
    assert other.get("/api/auth/me").status_code == 200
    r = authed.post("/api/auth/password", json={"current_password": "correct horse battery", "new_password": "another long password"})
    assert r.status_code == 204
    assert other.get("/api/auth/me").status_code == 401
    assert authed.get("/api/auth/me").status_code == 200  # this device carries on


def test_login_lockout_is_per_address(client):
    from conftest import signup

    signup(client, "victim@example.com")
    client.post("/api/auth/logout")
    for i in range(12):
        client.post("/api/auth/login", json={"email": "victim@example.com", "password": "wrong"},
                    headers={"fly-client-ip": f"10.0.0.{i}"})
    r = client.post("/api/auth/login", json={"email": "victim@example.com", "password": "correct horse battery"},
                    headers={"fly-client-ip": "10.9.9.9"})
    assert r.status_code == 200, r.text


# ---- Numbers -------------------------------------------------------------------------------------------------

def test_movers_ignore_regrades(authed, morgan_collection):
    a = authed.post("/api/coins", json=coin_payload(morgan_collection["id"], year=1880)).json()
    b = authed.post("/api/coins", json=coin_payload(morgan_collection["id"], year=1882)).json()
    now = datetime.now(timezone.utc)
    with SessionLocal() as db:
        ca = db.query(Coin).filter_by(inventory_number=a["inventory_number"]).one()
        cb = db.query(Coin).filter_by(inventory_number=b["inventory_number"]).one()
        db.add_all([
            PriceQuote(coin_id=ca.id, source="CPG", value=Decimal(100), grade_used="MS64", fetched_at=now - timedelta(days=9)),
            PriceQuote(coin_id=ca.id, source="CPG", value=Decimal(300), grade_used="MS65", fetched_at=now),  # regraded
            PriceQuote(coin_id=cb.id, source="CPG", value=Decimal(100), grade_used="MS65", fetched_at=now - timedelta(days=9)),
            PriceQuote(coin_id=cb.id, source="CPG", value=Decimal(120), grade_used="MS65", fetched_at=now),  # market
        ])
        db.commit()
    d = authed.get("/api/dashboard").json()
    assert [m["coin"]["inventory_number"] for m in d["gainers"]] == [b["inventory_number"]]


def test_spot_keeps_last_good_price(monkeypatch):
    answers = iter([(30.0, "t1"), (None, None)])
    monkeypatch.setattr(metals, "_fetch_spot", lambda metal: next(answers))
    metals._spot.clear()
    assert metals.spot("silver") == (30.0, "t1")
    metals._spot["silver"] = (0, 30.0, "t1")  # expired
    assert metals.spot("silver") == (30.0, "t1")  # the fetch failed: last good price, not None


def test_value_chart_follows_value_source(authed, morgan_collection):
    c = authed.post("/api/coins", json=coin_payload(morgan_collection["id"], purchase_date="2026-01-01")).json()
    with SessionLocal() as db:
        coin = db.query(Coin).filter_by(inventory_number=c["inventory_number"]).one()
        db.add(PriceQuote(coin_id=coin.id, source="CPG", value=Decimal(100), grade_used="MS65",
                          fetched_at=datetime.now(timezone.utc) - timedelta(days=5)))
        db.commit()
    inv = c["inventory_number"]
    authed.put(f"/api/coins/{inv}/valuation", json={"source": "custom", "custom_value": "500"})
    last = lambda: authed.get(f"/api/history?collection_id={morgan_collection['id']}").json()[-1]["value"]  # noqa: E731
    assert last() == "500.00"
    authed.put(f"/api/coins/{inv}/valuation", json={"source": "cpg"})
    assert last() == "100.00"  # back to CPG: the chart follows


# ---- Bullion import and summary ------------------------------------------------------------------------------

def test_bullion_import_quantity_and_purity():
    from app.services.bullion_io import parse_purity, row_to_item

    assert parse_purity("1000") == 1
    for q in ("0", "-3", "2.5"):
        _, errors = row_to_item({"Description": "Buffalo", "Weight": "1", "Purity": ".999", "Quantity": q})
        assert any("Quantity" in e for e in errors), q
    f, errors = row_to_item({"Description": "Buffalo", "Weight": "1", "Purity": ".999", "Quantity": "1,000"})
    assert not errors and f["quantity"] == 1000


def test_bullion_change_leaves_out_unpriced_metal():
    from app.services import bullion

    items = [SimpleNamespace(sale_date=None, sale_price=None, price_paid=Decimal(100), metal="silver", weight=Decimal(1),
                             weight_unit="ozt", purity=Decimal(1), quantity=1, face_value=None),
             SimpleNamespace(sale_date=None, sale_price=None, price_paid=Decimal(2000), metal="palladium", weight=Decimal(1),
                             weight_unit="ozt", purity=Decimal(1), quantity=1, face_value=None)]
    s = bullion.summary(items, lambda i: i.metal, {"silver": Decimal(50), "palladium": None})
    assert s["change"] == "-50.00" and s["cost"] == "2100.00"  # palladium has no price: not a $2,000 loss


def test_security_headers(client):
    r = client.get("/api/health")
    assert r.headers["X-Frame-Options"] == "DENY" and r.headers["X-Content-Type-Options"] == "nosniff"
    assert client.get("/api/shared/nope").headers["Referrer-Policy"] == "no-referrer"


def test_one_address(client, monkeypatch):
    from app.config import get_settings

    monkeypatch.setattr(get_settings(), "canonical_host", "trackmycoins.app")
    r = client.get("/dashboard?x=1", headers={"host": "trackmycoins.fly.dev"}, follow_redirects=False)
    assert r.status_code == 301 and r.headers["location"] == "https://trackmycoins.app/dashboard?x=1"
    r = client.post("/api/auth/login", json={}, headers={"host": "www.trackmycoins.app"}, follow_redirects=False)
    assert r.status_code == 308 and r.headers["location"] == "https://trackmycoins.app/api/auth/login"
    # The address itself, local hosts and Fly's health checks are left alone.
    assert client.get("/api/health", headers={"host": "trackmycoins.app"}).status_code == 200
    assert client.get("/api/health", headers={"host": "trackmycoins.fly.dev"}, follow_redirects=False).status_code == 200
    assert client.get("/api/health", headers={"host": "127.0.0.1:8080"}).status_code == 200
