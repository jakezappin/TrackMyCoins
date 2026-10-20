"""CPG from a price sheet already saved for the issue (no Greysheet call), and CPG at a grade a raw coin doesn't
have yet, kept or not."""

from test_api import coin_payload

from app.db import SessionLocal
from app.services import grade_prices

SHEET = {"key": "pcgs:7130", "gsid": 1, "name": "1881-S $1 MS",
         "rows": [{"grade": g, "label": f"MS{g}", "cac": False, "cpg": str(v), "grey": None}
                  for g, v in ((63, 90), (64, 120), (65, 210))]}


def _save_sheet():
    with SessionLocal() as db:
        grade_prices.save_sheet(db, SHEET)
        db.commit()


def test_new_coin_takes_cpg_from_saved_sheet(authed, morgan_collection):
    _save_sheet()
    c = authed.post("/api/coins", json=coin_payload(morgan_collection["id"], pcgs_number="7130", grade=64)).json()
    assert c["latest_cpg"]["value"] == "120.00"
    # A new grade on edit: priced again from the same sheet.
    r = authed.put(f"/api/coins/{c['inventory_number']}", json=coin_payload(
        morgan_collection["id"], pcgs_number="7130", grade=65, cert_number=c["cert_number"])).json()
    assert r["latest_cpg"]["value"] == "210.00"


def test_raw_coin_cpg_at_a_grade_then_kept(authed, morgan_collection):
    _save_sheet()
    c = authed.post("/api/coins", json=coin_payload(morgan_collection["id"], pcgs_number="7130", grading_service="RAW",
                                                    cert_number=None, grade=None, grade_prefix=None)).json()
    assert c["latest_cpg"] is None
    inv = c["inventory_number"]
    r = authed.post(f"/api/coins/{inv}/cpg-at-grade", json={"grade": 63})
    assert r.status_code == 200, r.text
    assert (r.json()["value"], r.json()["grade_label"]) == ("90.00", "MS63")
    assert authed.get(f"/api/coins/{inv}").json()["grade"] is None  # not saved: discarding needs nothing
    saved = authed.put(f"/api/coins/{inv}/grade", json={"grade": 63}).json()
    assert (saved["grade"], saved["grade_prefix"], saved["latest_cpg"]["value"]) == (63, "MS", "90.00")
