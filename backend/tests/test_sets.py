"""U.S. Mint and proof sets: ungraded items priced in OGP, a line per year, specialty sets listed apart, melt."""

import contextlib
from types import SimpleNamespace

import pytest

from app.services import greysheet, set_melt


def _item(gsid, date, variety, variety2="", pcgs=None, desg="PR"):
    return {"Gsid": gsid, "Name": f"{date} {variety} {variety2} {desg}", "CoinDate": date, "Desg": desg,
            "Variety": variety, "Variety2": variety2, "PcgsNumber": pcgs}


PROOF_SETS = [
    _item(1, "1955", "Proof Set", "Box Packaging, 5 Coins", "904763"),
    _item(2, "1955", "Proof Set", "Flat Packaging, 5 Coins", "904764"),
    _item(3, "1992-S", "Clad Proof Set", "5 Coins", "904818"),
    _item(4, "1992-S", "Prestige Proof Set", "6 Coins", "904819"),
    _item(5, "1992-S", "Silver Proof Set", "5 Coins", "904820"),
    _item(6, "1992-S", "Silver Premier Proof Set", "5 Coins", "904821"),
    _item(7, "1776~2026-S-S", "Silver Proof Set", "7 Coins"),
]


@pytest.fixture()
def fake_sets(monkeypatch):
    monkeypatch.setattr(greysheet, "client", lambda: contextlib.nullcontext())
    monkeypatch.setattr(greysheet, "get", lambda c, path, **kw: PROOF_SETS if kw.get("NodeId") == 9020 else [])


def _collection(c, slug):
    t = next(t for t in c.get("/api/coin-types").json() if t["slug"] == slug)
    assert t["is_set"] is True and [f["code"] for f in t["finishes"]] == ["MS"]
    return c.post("/api/collections", json={"name": slug, "coin_type_id": t["id"]}).json()


def test_silver_proof_sets(authed, fake_sets):
    col = _collection(authed, "us-silver-proof-sets")
    sets = authed.get(f"/api/coin-types/{col['coin_type_id']}/sets?year=1992").json()
    assert [(s["name"], s["extra"], s["pcgs_number"]) for s in sets] == [
        ("", False, "904820"), ("Silver Premier Proof Set", True, "904821")]
    # Grading fields are ignored for a set; it's kept in OGP.
    r = authed.post("/api/coins", json={
        "collection_id": col["id"], "year": 1992, "mint_mark": "S", "variety": "Silver Proof Set", "pcgs_number": "904820",
        "grading_service": "PCGS", "cert_number": "123", "grade_prefix": "PR", "grade": 69, "cac": True, "ogp": True,
        "capital_holder": True, "toning_obverse": True, "price_paid": "40"})
    assert r.status_code == 201, r.text
    coin = r.json()
    assert (coin["grading_service"], coin["grade"], coin["cert_number"], coin["cac"]) == ("RAW", None, None, False)
    assert coin["ogp"] and coin["capital_holder"] and coin["toning_obverse"]
    detail = authed.get(f"/api/coins/{coin['inventory_number']}").json()
    assert detail["set_melt"]["oz"] == pytest.approx(0.6149, abs=1e-3)

    st = authed.get(f"/api/collections/{col['id']}/status").json()
    assert [r["label"] for r in st["rows"]] == ["1992-S", "2026-S"] and st["total"] == 2 and st["filled"] == 1
    assert [r["label"] for r in st["extras"]] == ["1992-S Silver Premier Proof Set"]


def test_proof_sets_lines(authed, fake_sets):
    col = _collection(authed, "us-proof-sets")
    st = authed.get(f"/api/collections/{col['id']}/status").json()
    assert [r["label"] for r in st["rows"]] == ["1955 Box Packaging", "1955 Flat Packaging", "1992-S"]
    assert [r["label"] for r in st["extras"]] == ["1992-S Prestige Proof Set"]


def test_ogp_price_and_silver_table():
    rows = [{"Grade": 80, "GradeLabel": "OGP*", "IsCac": True, "CpgVal": ""},
            {"Grade": 80, "GradeLabel": "OGP*", "IsCac": False, "CpgVal": "47.00"}]
    coin = SimpleNamespace(coin_type=SimpleNamespace(slug="us-silver-proof-sets"), grade=None, grade_plus=False, cac=False)
    assert greysheet._pick(rows, coin)["CpgVal"] == "47.00"
    greysheet.require_grade(coin)  # no grade needed
    assert set_melt.silver_oz("us-mint-sets", 1947, "Uncirculated Set") == pytest.approx(2.9658, abs=1e-3)
    assert set_melt.silver_oz("us-mint-sets", 1966, "Special Mint Set") == pytest.approx(0.1479, abs=1e-3)
    assert set_melt.silver_oz("us-proof-sets", 1990, "Clad Proof Set") == 0.0
    assert set_melt.silver_oz("us-silver-proof-sets", 2022, "Silver Proof Set") == pytest.approx(1.5076, abs=1e-3)
