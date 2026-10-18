"""Catalog sync, matching and auto-resolved CPG pricing against a fake Greysheet API."""

import httpx
import pytest

from app.services import greysheet
from app.services.catalog import parse_collectible
from test_api import coin_payload

ADV = "[requires apiLevel=advanced]"


def item(gsid, pcgs, date, desg="", variety=None, strike="MS", parent=0, denom="$1", **kw):
    """Shaped like a real Basic-tier CollectibleDto: mint is in CoinDate, designation only in Name."""
    name = f"{date} {denom} {variety + ' ' if variety else ''}{strike}{' ' + desg if desg else ''}"
    return {
        "Gsid": gsid, "PcgsNumber": pcgs, "CoinDate": date, "Desg": strike, "Variety": variety,
        "Variety2": kw.pop("variety2", None), "MintMark": ADV, "StrikeType": ADV, "UiParentId": parent,
        "Name": name, **kw,
    }


MORGANS = [
    item(1, "7130", "1881-S"),
    item(2, "7131", "1881-S", "PL"),
    item(3, "97131", "1881-S", "DMPL"),
    item(10, "521814", "1881-S", variety="GSA Hoard"),
    item(4, "7072", "1878 8TF"),
    item(5, "7074", "1878 7TF", variety="Reverse of 1878"),
    item(17, "7078", "1878 7/8TF", variety="Strong"),
    item(18, "7070", "1878 7/8TF", variety="Weak"),
    item(11, "133784", "1878 8TF", variety="Spear Point", variety2="VAM-1", parent=4),  # VAM child: skipped
    item(6, "7184", "1888-O"),
    item(7, "7308", "1888-O", variety="Hot Lips"),
    item(12, "7108", "1880/79-CC", variety="Reverse of 1878"),
    item(82, "7100", "1880-CC"),
    item(83, "518851", "1880-CC", variety="GSA Hoard, Hard package"),
    item(80, "518922", "1880/79-CC", variety="Reverse of 1878", variety2="GSA Hoard, Hard package"),
    item(81, "518999", "1880/79-CC", variety="Reverse of 1878", variety2="GSA Hoard, Soft Package"),
    item(13, "7296", "1921", variety="Morgan"),
    item(19, "7138", "1882-O/S", variety="Strong"),
    item(20, "7136", "1882-O"),
    item(21, "7268", "1900-O/CC"),
    item(22, "7264", "1900-O"),
    item(23, "7178", "1887/6-O"),
    item(24, "7176", "1887-O"),
    {"Gsid": 9, "PcgsNumber": "7068", "CoinDate": "Morgan", "Desg": "MS", "Name": "Morgan $1 Pre-1921 MS [Type]"},
]

MORGAN_PROOFS = [item(8, "7315", "1880", strike="PR"), item(16, "87315", "1880", "CAM", strike="PR")]
KENNEDY_PROOFS = [
    item(20, "6801", "1992-S", "DCAM", variety="Clad", strike="PR", denom="50c"),
    item(21, "96805", "1992-S", "DCAM", variety="Silver", strike="PR", denom="50c"),
    item(22, "6400", "1964", "DCAM", strike="PR", denom="50c"),
]
LINCOLN_PROOFS = [
    item(30, "3300", "1936", "RD", strike="PR", denom="1c"),
    item(31, "3301", "1936", "RD CAM", strike="PR", denom="1c"),
    item(32, "3299", "1936", "RB", strike="PR", denom="1c"),
]
COMMEMS = [
    item(40, "9300", "1936", variety="Arkansas", denom="50c"),
    item(41, "9301", "1936", variety="Boone", denom="50c"),
    item(42, "9302", "1936-D", variety="Boone", denom="50c"),
    item(43, "9303", "1935/34", variety="Boone", denom="50c"),  # overdate
    item(44, "9304", "1922", variety="Grant Memorial", variety2="with Star", denom="50c"),
    item(45, "9305", "1922", variety="Grant Memorial", variety2="without Star", denom="50c"),
]
WASHINGTON_EARLY = [
    item(50, "5500", "1998-P", denom="25c"),
    item(51, "5501", "1934", variety="Light Motto", denom="25c"),
    item(52, "5502", "1934", variety="Medium Motto", denom="25c"),
]
STATES = [
    item(60, "9601", "1999-P", variety="Delaware", denom="25c"),
    item(61, "9602", "1999-D", variety="Delaware", denom="25c"),
    item(62, "9603", "1999-P", variety="Pennsylvania", denom="25c"),
    item(63, "9604", "1999-P", variety="Pennsylvania, Satin Finish", denom="25c"),
]
STATE_PROOFS = [
    item(70, "9700", "1999-S", "DCAM", variety="Delaware, Clad", strike="PR", denom="25c"),
    item(71, "9701", "1999-S", "DCAM", variety="Delaware, Silver", strike="PR", denom="25c"),
    item(72, "9702", "1999-S", "DCAM", variety="Pennsylvania, Clad", strike="PR", denom="25c"),
    item(73, "9703", "1999-S", "DCAM", variety="Pennsylvania, Silver", strike="PR", denom="25c"),
]
NODES = {
    8971: MORGANS, 8972: MORGAN_PROOFS, 8964: KENNEDY_PROOFS, 8913: LINCOLN_PROOFS, 9003: COMMEMS,
    8949: WASHINGTON_EARLY, 8950: STATES, 8952: STATE_PROOFS,
}

calls: list[str] = []
GREY_VAL = ""  # Basic tier: empty


def handler(request: httpx.Request) -> httpx.Response:
    path = request.url.path.rsplit("/", 1)[-1]
    q = request.url.params
    calls.append(f"{path}?{q}")
    if q.get("ApiLevel") != "basic":
        return httpx.Response(400)
    node = int(q["NodeId"]) if "NodeId" in q else None
    if path == "GetCollectibleByNodeRequest":
        return httpx.Response(200, json={"Data": NODES.get(node, [])})
    if path == "GetPricingRequest":
        ident = q.get("PcgsNumber") or f"gs{q.get('Gsid')}"
        return httpx.Response(200, json={"Data": [{
            "GsId": 3, "Name": "1881-S $1 MS PL" if ident == "7131" else f"item {ident}",
            "PricingData": [
                {"Grade": 64, "GradeLabel": "MS64", "IsCac": False, "CpgVal": "$900", "GreyVal": ""},
                {"Grade": 65, "GradeLabel": "65", "IsCac": False, "CpgVal": "$1,150", "GreyVal": ""},
                {"Grade": 65, "GradeLabel": "65", "IsCac": True, "CpgVal": "$1,400", "GreyVal": GREY_VAL},
                {"Grade": 66, "GradeLabel": "MS66", "IsCac": False, "CpgVal": "$2,000", "GreyVal": ""},
                {"Grade": 67, "GradeLabel": "MS67", "IsCac": False, "CpgVal": "", "GreyVal": ""},
            ],
        }]})
    return httpx.Response(404)


@pytest.fixture(autouse=True)
def fake_greysheet(monkeypatch):
    calls.clear()
    monkeypatch.setattr(
        greysheet, "client",
        lambda: httpx.Client(base_url="https://greysheet.test/api", transport=httpx.MockTransport(handler)),
    )


def type_id(c, slug="morgan-dollars"):
    return next(t["id"] for t in c.get("/api/coin-types").json() if t["slug"] == slug)


morgan_type_id = type_id


def test_parse_collectible():
    p = parse_collectible(item(3, "97131", "1881-S", "DMPL"))
    assert (p["year"], p["mint_mark"], p["designation"], p["strike"], p["variety"]) == (1881, "S", "DMPL", "MS", None)
    p = parse_collectible(item(4, "7072", "1878 8TF"))
    assert (p["mint_mark"], p["designation"], p["variety"]) == ("P", None, "8TF")
    assert parse_collectible(item(8, "7315", "1880", strike="PR"))["strike"] == "PR"
    assert parse_collectible(item(31, "3301", "1936", "CAM RD", strike="PR", denom="1c"))["designation"] == "RD CAM"
    assert parse_collectible(item(1, "1", "1793 Chain", "BN", denom="1c"))["year"] == 1793
    # Charlotte gold, and bullion struck at a branch mint without a mint mark
    p = parse_collectible(item(90, "7718", "1840-C", denom="$2 1/2"))
    assert (p["year"], p["mint_mark"]) == (1840, "C")
    p = parse_collectible(item(91, "1", "2011-(W)", variety="Silver Eagle", denom="$1"))
    assert (p["mint_mark"], p["variety"]) == ("P", "(W)")
    p = parse_collectible(item(92, "2", "2011-W", variety="Silver Eagle", denom="$1"))
    assert (p["mint_mark"], p["variety"]) == ("W", None)  # "Silver Eagle" alone isn't a variety
    p = parse_collectible(item(12, "7108", "1880/79-CC", variety="Reverse of 1878"))
    assert (p["year"], p["mint_mark"], p["variety"]) == (1880, "CC", "1880/79, Reverse of 1878")
    p = parse_collectible(item(14, "7999", "1882-O/S"))
    assert (p["mint_mark"], p["variety"]) == ("O", "O/S")
    assert parse_collectible(item(13, "7296", "1921", variety="Morgan"))["variety"] is None
    assert parse_collectible(item(15, "x", "1880-S", "DCAM", strike="PR"))["designation"] == "DCAM"
    assert parse_collectible(MORGANS[-1]) is None  # [Type] entry
    assert parse_collectible(next(m for m in MORGANS if m["UiParentId"])) is None  # VAM child


def test_sync_pulls_series_nodes(authed):
    r = authed.post(f"/api/coin-types/{morgan_type_id(authed)}/catalog/sync")
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["nodes"] == [8971, 8972]
    assert body["count"] == 24  # 23 business strikes + 2 proofs - [Type] entry - VAM child
    assert {c.split("NodeId=")[1].split("&")[0] for c in calls if "NodeId=" in c} == {"8971", "8972"}


def test_match_endpoint(authed):
    tid = morgan_type_id(authed)

    def best(**kw):
        m = authed.get("/api/catalog/match", params={"coin_type_id": tid, **kw}).json()
        return m, (m["best"] or {}).get("pcgs_number")

    assert best(year=1881, mint_mark="S", designation="DMPL")[1] == "97131"
    assert best(year=1881, mint_mark="S", designation="PL")[1] == "7131"
    assert best(year=1881, mint_mark="S")[1] == "7130"  # plain wins over GSA Hoard
    assert best(year=1888, mint_mark="O")[1] == "7184"  # plain wins over Hot Lips
    assert best(year=1921, mint_mark="P")[1] == "7296"
    assert best(year=1880, mint_mark="P", finish="PR")[1] == "7315"
    assert best(year=1880, mint_mark="P", finish="PR", designation="CAM")[1] == "87315"
    assert best(year=1880, mint_mark="CC")[1] == "7100"  # plain wins; GSA versions left out unless asked for
    assert best(year=1880, mint_mark="CC", gsa="hard")[1] == "518851"  # plain GSA hard beats the 1880/79 one
    assert best(year=1880, mint_mark="CC", gsa="soft")[1] == "518999"  # only soft pack entry
    m, pcgs = best(year=1881, mint_mark="S", gsa="hard")  # 1881-S only has a plain "GSA Hoard" entry
    assert pcgs == "521814"
    m, pcgs = best(year=1888, mint_mark="O", gsa="soft")  # no GSA listing at all
    assert pcgs is None and "no GSA Soft Pack listing" in m["message"]
    assert best(year=1880, mint_mark="CC", variety="1880/79")[1] == "7108"
    # Overdates however they're typed
    for typed in ("80/79", "1880/79-CC", "1880/79 VAM-4", "1880-CC 80/79", "1880/79 Reverse of 1878"):
        assert best(year=1880, mint_mark="CC", variety=typed)[1] == "7108", typed
    for typed in ("1887/6", "7/6", "87/6", "1887/6-O"):
        assert best(year=1887, mint_mark="O", variety=typed)[1] == "7178", typed
    # Over-mintmarks: the top letter is the mint mark, the over-mintmark is the variety
    for typed in ("O/S", "o/s", "1882-O/S", "O/S Strong"):
        assert best(year=1882, mint_mark="O", variety=typed)[1] == "7138", typed
    assert best(year=1900, mint_mark="O", variety="O/CC")[1] == "7268"
    assert best(year=1900, mint_mark="O")[1] == "7264"  # without the variety it's the regular date
    # An overdate the catalog doesn't list never falls back to the regular date's price
    m, pcgs = best(year=1880, mint_mark="CC", variety="80/78")
    assert pcgs is None and "doesn't list" in m["message"]
    assert {c["pcgs_number"] for c in m["candidates"]} == {"7108"}

    # 1878 has only date varieties: user must pick (VAM child is not offered)
    m, pcgs = best(year=1878, mint_mark="P")
    assert pcgs is None and sorted(c["pcgs_number"] for c in m["candidates"]) == ["7070", "7072", "7074", "7078"]

    m, pcgs = best(year=1895, mint_mark="P")
    assert pcgs is None and m["candidates"] == [] and "No Greysheet" in m["message"]

    # Second lookup reuses the cache (no new catalog calls)
    n = len([c for c in calls if "Collectible" in c])
    best(year=1881, mint_mark="S")
    assert len([c for c in calls if "Collectible" in c]) == n


def test_get_cpg_resolves_pcgs_number(authed, morgan_collection):
    cid = morgan_collection["id"]
    coin = authed.post("/api/coins", json=coin_payload(cid, strike_designation="DMPL", cac=True)).json()
    assert coin["pcgs_number"] is None
    d = authed.post(f"/api/coins/{coin['inventory_number']}/cpg")
    assert d.status_code == 200, d.text
    d = d.json()
    assert d["pcgs_number"] == "97131"
    assert d["latest_cpg"]["value"] == "1400.00" and d["latest_cpg"]["grade_used"] == "65 CAC"
    assert any("PcgsNumber=97131" in c for c in calls)


def test_get_cpg_ambiguous(authed, morgan_collection):
    coin = authed.post("/api/coins", json=coin_payload(morgan_collection["id"], year=1878, mint_mark="P")).json()
    r = authed.post(f"/api/coins/{coin['inventory_number']}/cpg")
    assert r.status_code == 400
    assert "More than one catalog match" in r.json()["detail"] and "7072" in r.json()["detail"]


def test_greysheet_value_saved_when_present(authed, morgan_collection, monkeypatch):
    coin = authed.post("/api/coins", json=coin_payload(morgan_collection["id"], strike_designation="DMPL", cac=True)).json()
    d = authed.post(f"/api/coins/{coin['inventory_number']}/cpg").json()
    assert d["latest_greysheet"] is None and len(d["price_quotes"]) == 1  # Basic tier: CPG only

    monkeypatch.setattr(__import__(__name__), "GREY_VAL", "$1,050.00")
    _age_sheets(days=2)  # a day later the saved all-grades result is stale, so Greysheet is asked again
    d = authed.post(f"/api/coins/{coin['inventory_number']}/cpg").json()
    assert d["latest_greysheet"]["value"] == "1050.00" and d["latest_cpg"]["value"] == "1400.00"


def test_silver_proof_matching(authed):
    tid = type_id(authed, "kennedy-half-dollars")

    def best(finish, year=1992, mint="S"):
        m = authed.get(
            "/api/catalog/match",
            params={"coin_type_id": tid, "year": year, "mint_mark": mint, "designation": "DCAM", "finish": finish},
        ).json()
        return (m["best"] or {}).get("pcgs_number")

    assert best("PR") == "6801"  # clad
    assert best("SPR") == "96805"  # silver
    # 1964 only exists in silver, so it matches in both
    assert best("PR", 1964, "P") == best("SPR", 1964, "P") == "6400"


def test_copper_designations(authed):
    tid = type_id(authed, "lincoln-cents")
    assert authed.get(f"/api/coin-types/{tid}/designations", params={"finish": "PR"}).json() == ["RB", "RD", "RD CAM"]

    def best(desg):
        m = authed.get(
            "/api/catalog/match",
            params={"coin_type_id": tid, "year": 1936, "mint_mark": "P", "designation": desg, "finish": "PR"},
        ).json()
        return (m["best"] or {}).get("pcgs_number")

    assert best("RD") == "3300"
    assert best("cam rd") == "3301"  # any order / case
    assert best("RB") == "3299"
    assert best(None) is None


def test_commemorative_variety(authed):
    tid = type_id(authed, "classic-commemoratives")

    def match(**kw):
        return authed.get("/api/catalog/match", params={"coin_type_id": tid, "year": 1936, **kw}).json()

    m = match(mint_mark="P")
    assert m["best"] is None and len(m["candidates"]) == 2  # Arkansas vs Boone: pick one
    assert match(mint_mark="P", variety="boone")["best"]["pcgs_number"] == "9301"
    assert match(mint_mark="D", variety="Boone")["best"]["pcgs_number"] == "9302"


def test_get_cpg_uses_gsa_entry(authed, morgan_collection):
    coin = authed.post("/api/coins", json=coin_payload(morgan_collection["id"], year=1880, mint_mark="CC", gsa_soft_pack=True)).json()
    d = authed.post(f"/api/coins/{coin['inventory_number']}/cpg").json()
    assert d["pcgs_number"] == "518999" and d["gsa_soft_pack"] is True
    both = coin_payload(morgan_collection["id"], year=1880, mint_mark="CC", gsa_soft_pack=True, gsa_hard_pack=True)
    assert authed.post("/api/coins", json=both).status_code == 422


def test_over_pattern_skips_fractions():
    from app.services.catalog import _OVER_RE

    for text in ("1880/79", "80/79", "1942/1", "'1/0', Overdate", "D/S", "O/CC", "S/S"):
        assert _OVER_RE.search(text), text
    for text in ("3 1/2 Legs", "7/8TF, Strong", "Large/Small 47", "Buffalo"):
        assert not _OVER_RE.search(text), text


def test_price_by_grade_comes_with_one_cpg_call(authed, morgan_collection):
    coin = authed.post("/api/coins", json=coin_payload(morgan_collection["id"], year=1881, mint_mark="S", grade=65,
                                                       pcgs_number="7130")).json()
    inv = coin["inventory_number"]
    assert authed.get(f"/api/coins/{inv}/grade-prices").json() == {"rows": None}  # not priced yet
    n = len(calls)
    d = authed.post(f"/api/coins/{inv}/cpg").json()
    assert d["latest_cpg"]["value"] == "1150.00"  # still the coin's own grade
    pricing = [c for c in calls[n:] if c.startswith("GetPricingRequest")]
    assert len(pricing) == 1 and "Grade=" not in pricing[0]  # all grades, one call

    t = authed.get(f"/api/coins/{inv}/grade-prices").json()
    assert [(r["label"], r.get("cpg"), r.get("wholesale"), r.get("cac_cpg")) for r in t["rows"]] == [
        ("MS64", "900.00", "810.00", None),
        ("65", "1150.00", "1035.00", "1400.00"),
        ("MS66", "2000.00", "1800.00", None),
    ]  # unpriced MS67 left out; wholesale is CPG - 10%
    assert t["has_cac"] and t["wholesale_discount"] == 0.1

    # Another coin of the same issue reuses the sheet: no call needed
    other = authed.post("/api/coins", json=coin_payload(morgan_collection["id"], year=1881, mint_mark="S", grade=64,
                                                        pcgs_number="7130")).json()
    assert len(authed.get(f"/api/coins/{other['inventory_number']}/grade-prices").json()["rows"]) == 3


def test_designation_shown_with_grade(authed, morgan_collection):
    coin = authed.post("/api/coins", json=coin_payload(morgan_collection["id"], year=1881, mint_mark="S", grade=65,
                                                       strike_designation="PL", pcgs_number="7131")).json()
    d = authed.post(f"/api/coins/{coin['inventory_number']}/cpg").json()
    assert d["latest_cpg"]["grade_used"] == "65 PL"
    t = authed.get(f"/api/coins/{coin['inventory_number']}/grade-prices").json()
    assert t["designation"] == "PL" and [r["label"] for r in t["rows"]] == ["MS64 PL", "65 PL", "MS66 PL"]


def _age_sheets(days: int) -> None:
    from datetime import datetime, timedelta, timezone

    from app.db import SessionLocal
    from app.models import GradePriceSheet

    with SessionLocal() as db:
        for sh in db.query(GradePriceSheet).all():
            sh.fetched_at = datetime.now(timezone.utc) - timedelta(days=days)
        db.commit()


def test_cpg_reuses_recent_sheet_and_records_changes_only(authed, morgan_collection):
    a = authed.post("/api/coins", json=coin_payload(morgan_collection["id"], year=1881, mint_mark="S", grade=65, pcgs_number="7130")).json()
    b = authed.post("/api/coins", json=coin_payload(morgan_collection["id"], year=1881, mint_mark="S", grade=64, pcgs_number="7130")).json()
    n = len(calls)
    authed.post(f"/api/coins/{a['inventory_number']}/cpg")
    d = authed.post(f"/api/coins/{b['inventory_number']}/cpg").json()  # same issue, other grade
    assert d["latest_cpg"]["value"] == "900.00"
    assert len([c for c in calls[n:] if c.startswith("GetPricingRequest")]) == 1  # second coin: no call

    again = authed.post(f"/api/coins/{a['inventory_number']}/cpg").json()  # unchanged price
    cpg = [q for q in again["price_quotes"] if q["source"] == "CPG"]
    assert len(cpg) == 1 and cpg[0]["confirmed_at"]  # re-confirmed, not duplicated


def test_parse_semiquincentennial_and_atb_5oz():
    def d(date, variety, variety2="", desg="MS", denom=None, name=""):
        return {"Gsid": 1, "Name": name or f"{date} {variety}", "CoinDate": date, "Desg": desg, "Variety": variety,
                "Variety2": variety2, "DenominationShort": denom}

    p = parse_collectible(d("1776~2026-D", "Mayflower Compact", denom="25c"))
    assert (p["year"], p["mint_mark"], p["strike"], p["variety"]) == (2026, "D", "MS", "25c Mayflower Compact")
    p = parse_collectible(d("1776~2026-S", "Emerging Liberty", "Silver", desg="PR", denom="10c"))
    assert (p["strike"], p["variety"]) == ("PR", "10c Emerging Liberty, Silver")
    # ATB 5 oz: the bullion strike, and the collector Satin Finish (specimen) filed with business strikes
    p = parse_collectible(d("2010", "5oz Silver", "Hot Springs"))
    assert (p["mint_mark"], p["strike"], p["variety"]) == ("P", "MS", "Hot Springs")
    p = parse_collectible(d("2010-P", "5oz Silver", "Hot Springs, Satin Finish", desg="SP"))
    assert (p["strike"], p["variety"]) == ("MS", "Hot Springs, Satin Finish")
    assert parse_collectible(d("1965", "", desg="SMS"))["variety"] == "SMS"


def test_new_series_dates():
    from app.series import BY_SLUG
    from app.services.series_match import date_problem

    atb, a250 = BY_SLUG["atb-5oz-silver"], BY_SLUG["america-250"]
    assert date_problem(atb, 2015, "P", "SP") is None
    assert "isn't an America the Beautiful" in date_problem(atb, 2022, "P", "MS")
    assert date_problem(a250, 2026, "D", "MS") is None
    assert "no 2026-S America 250" in date_problem(a250, 2026, "S", "MS") or "proofs" in date_problem(a250, 2026, "S", "MS")


def test_silver_eagle_and_modern_dollar_lines():
    from app.services.checklist import _silver_eagle_issue as issue

    assert issue("Silver Eagle, Burnished") == "Burnished"
    assert issue("Silver Eagle, Reverse Proof, Type 1") == "Reverse Proof, Type 1"
    assert issue("(P), Star Privy") == "Star Privy"
    assert issue("$1 Silver Eagle, Liberty Bell Privy, 250th Anniversary") == "Liberty Bell Privy, 250th Anniversary"
    # "Struck at" bullion varieties go on the date's own line (keeping Type 1 / Type 2 apart)
    assert issue("(S), Struck at San Francisco Mint") is None
    assert issue("(W), Silver Eagle, Type 2, Emergency West Point Strike") == "Type 2"

    def d(date, variety, name, desg="MS"):
        return {"Gsid": 1, "Name": name, "CoinDate": date, "Desg": desg, "Variety": variety, "DenominationShort": "S$1"}

    p = parse_collectible(d("1776~2026-(W)", "Morgan, Liberty Bell Privy, Enhanced Uncirculated",
                            "1776~2026-(W) S$1 Morgan, Liberty Bell Privy, Enhanced Uncirculated MS"))
    assert (p["year"], p["mint_mark"], p["variety"]) == (2026, "P", "(W), Liberty Bell Privy, Enhanced Uncirculated")
    p = parse_collectible(d("2023-S", "Peace, Reverse Proof", "2023-S S$1 Peace, Reverse Proof PR", desg="PR"))
    assert p["variety"] == "Reverse Proof"


def test_modern_morgans_split_from_shared_section(client, monkeypatch):
    from app.db import SessionLocal
    from app.models import CatalogEntry, CoinType
    from app.services import catalog as cat

    items = [{"Gsid": 1, "Name": "2024 S$1 Morgan MS", "CoinDate": "2024", "Desg": "MS"},
             {"Gsid": 2, "Name": "2024 S$1 Peace MS", "CoinDate": "2024", "Desg": "MS", "Variety": "Peace"},
             {"Gsid": 3, "Name": "2024-S Set S$1 Morgan & Peace Dollars, Reverse Proof, 2 Coins PR",
              "CoinDate": "2024-S", "Desg": "PR"}]
    monkeypatch.setattr(greysheet, "get", lambda c, path, **kw: items if kw["NodeId"] == 10536 else [])
    with SessionLocal() as db:
        for slug, gsids in (("modern-morgan-dollars", [1]), ("modern-peace-dollars", [2])):
            t = db.query(CoinType).filter_by(slug=slug).one()
            cat.sync(db, t)
            assert [e.gsid for e in db.query(CatalogEntry).filter_by(coin_type_id=t.id)] == gsids
