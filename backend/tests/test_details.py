"""Details (problem) grades: recorded as such, valued at a share of straight-grade CPG, never below melt."""

from datetime import datetime, timezone
from decimal import Decimal

from test_api import coin_payload

from app.db import SessionLocal
from app.models import Coin, PriceQuote
from app.schemas import LookupResult
from app.services import details, greysheet
from app.services.importer import row_to_fields
from app.services.lookups.base import parse_grade


def _quote(inv, value, grade_used="AU50"):
    with SessionLocal() as db:
        c = db.query(Coin).filter_by(inventory_number=inv).one()
        db.add(PriceQuote(coin_id=c.id, source="CPG", value=Decimal(value), grade_used=grade_used,
                          fetched_at=datetime.now(timezone.utc)))
        db.commit()


def _details_coin(authed, col, **kw):
    body = coin_payload(col, **{"grade_prefix": "AU", "grade": None, "details": True, "details_problem": "cleaned", **kw})
    r = authed.post("/api/coins", json=body)
    assert r.status_code == 201, r.text
    return r.json()


def test_valued_at_share_of_straight_cpg(authed, morgan_collection):
    c = _details_coin(authed, morgan_collection["id"])
    assert (c["details"], c["details_problem"], c["grade"]) == (True, "cleaned", None)
    _quote(c["inventory_number"], "200")
    got = authed.get(f"/api/coins/{c['inventory_number']}").json()
    assert got["value_estimate"] == "140.00"  # 70% of AU50 CPG
    assert "70% of AU50 CPG" in got["details_basis"]
    assert "bottom of its range" in got["details_basis"]

    # The owner's default, then the coin's own percentage.
    assert authed.put("/api/auth/preferences", json={"details_pct": 50}).status_code == 200
    assert authed.get(f"/api/coins/{c['inventory_number']}").json()["value_estimate"] == "100.00"
    body = {**coin_payload(morgan_collection["id"], grade_prefix="AU", grade=None, details=True,
                           details_problem="cleaned", details_pct=60, cert_number=c["cert_number"])}
    r = authed.put(f"/api/coins/{c['inventory_number']}", json=body)
    assert r.status_code == 200, r.text
    assert r.json()["value_estimate"] == "120.00"
    summary = authed.get(f"/api/collections/{morgan_collection['id']}").json()["summary"]
    assert summary["total_estimated_value"] == "120.00"


def test_never_below_melt(authed, morgan_collection):
    c = _details_coin(authed, morgan_collection["id"])
    with SessionLocal() as db:
        coin = db.query(Coin).filter_by(inventory_number=c["inventory_number"]).one()
        coin.lookup_raw = {"PCGSNo": 7130, "Mintage": 1000, "Weight": 26.73, "MetalContent": "90% Silver"}
        db.commit()
    _quote(c["inventory_number"], "40")  # 70% = $28, but the silver is worth $38.67 at $50 spot
    got = authed.get(f"/api/coins/{c['inventory_number']}").json()
    assert got["value_estimate"] == "38.67"
    assert "Raised to melt" in got["details_basis"]


def test_rules(authed, morgan_collection):
    col = morgan_collection["id"]
    r = authed.post("/api/coins", json=coin_payload(col, grade_prefix="AU", grade=55, details=True, cac=True))
    assert r.status_code == 422 and "CAC" in r.text
    # Plus and star don't go with a Details grade.
    r = authed.post("/api/coins", json=coin_payload(col, grade_prefix="AU", grade=55, details=True, grade_plus=True))
    assert r.status_code == 201 and r.json()["grade_plus"] is False
    # Untick Details: the problem and percentage go too.
    r = authed.post("/api/coins", json=coin_payload(col, details=False, details_problem="cleaned", details_pct=40))
    assert (r.json()["details_problem"], r.json()["details_pct"]) == (None, None)


def test_price_grade_and_greysheet_row():
    coin = Coin(grade_prefix="XF", grade=None, details=True, grade_plus=False, cac=False)
    assert details.price_grade(coin) == 40
    items = [{"Grade": 40, "GradeLabel": "XF40", "CpgVal": 90, "IsCac": False},
             {"Grade": 45, "GradeLabel": "XF45", "CpgVal": 110, "IsCac": False}]
    assert greysheet._pick(items, coin)["CpgVal"] == 90
    assert details.label(Coin(grade_prefix="AU", grade=55, details=True, details_problem="environmental-damage")) \
        == "AU55 Details · Environmental Damage"


def test_lookup_text():
    for text, want in [("AU Details", ("AU", None, None)), ("Genuine - Cleaned - XF Details", ("XF", None, "cleaned")),
                       ("AU55 Details – Scratched", ("AU", 55, "scratched"))]:
        r = LookupResult(grading_service="PCGS", cert_number="1")
        parse_grade(text, r)
        assert r.details and (r.grade_prefix, r.grade, r.details_problem) == want, text
    r = LookupResult(grading_service="PCGS", cert_number="1")
    parse_grade("MS64+", r)
    assert not r.details and (r.grade, r.grade_plus) == (64, True)
    # A page heading isn't a Details grade.
    assert details.in_page("Coin Details  1881-S $1 MS 64")[0] is False


def test_import_details_grade():
    f, _, errors, _ = row_to_fields({"Date": "1881-S", "Grade": "AU55 Details - Cleaned", "Service": "ANACS", "Cert": "123"})
    assert not errors, errors
    assert (f["grade_prefix"], f["grade"], f["details"], f["details_problem"]) == ("AU", 55, True, "cleaned")
    f, _, errors, _ = row_to_fields({"Date": "1881-S", "Grade": "XF", "Problem": "Environmental damage", "Service": "Raw"})
    assert (f["details"], f["details_problem"]) == (True, "environmental-damage")
    f, _, errors, _ = row_to_fields({"Date": "1881-S", "Grade": "Proof 69", "Service": "NGC", "Cert": "1234567-001"})
    assert (f["grade_prefix"], f["grade"]) == ("PR", 69), errors


def test_wants_and_upgrades_skip_details(authed, morgan_collection):
    col = morgan_collection["id"]
    _details_coin(authed, col, grade=58, grade_prefix="AU", year=1881, mint_mark="S")
    w = authed.post("/api/wants", json={"collection_id": col, "year": 1881, "mint_mark": "S", "grade_prefix": "AU",
                                        "grade": 50}).json()
    owned = next(x for x in authed.get("/api/wants").json() if x["id"] == w["id"])["owned"]
    assert owned["details"] is True and owned["meets_target"] is False
