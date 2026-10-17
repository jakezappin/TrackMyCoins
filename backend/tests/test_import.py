"""Bulk import from CSV / Excel and from pasted PCGS certs."""

from test_api import coin_payload
from test_catalog import fake_greysheet, type_id  # noqa: F401  (autouse fixture)
from test_reports import _collection

from app.schemas import LookupResult
from app.services import importer, lookups

CSV = """Date,Grade,Service,Cert #,CAC,Variety,Price paid,Date purchased,Seller,Toning,Notes
1881-S,MS65+ DMPL,PCGS,11112222,gold,,"$1,250.00",03/15/2025,Heritage,Obverse rainbow,nice
1878 8TF,MS63,NGC,3333444-001,,,200,2025-04-01,,,
1884-CC,Raw AU55,,,,,80,,,,
1893-S,MS62,PCGS,,,,,,,,
1921,MS64,PCGS,11112222,,,,,,,
1899-Q,MS64,PCGS,55556666,,,,,,,
"""


def _preview_csv(c, col, text=CSV, name="coins.csv"):
    return c.post("/api/import/preview", data={"collection_id": str(col["id"])},
                  files={"file": (name, text.encode(), "text/csv")})


def test_csv_preview_and_commit(authed):
    col = _collection(authed, "morgan-dollars", name="Morgans")
    r = _preview_csv(authed, col)
    assert r.status_code == 200, r.text
    d = r.json()
    rows = {x["row"]: x for x in d["rows"]}
    a = rows[2]["fields"]
    assert (a["year"], a["mint_mark"], a["grade_prefix"], a["grade"], a["grade_plus"], a["strike_designation"]) == (
        1881, "S", "MS", 65, True, "DMPL")
    assert (a["cac"], a["cac_sticker"], a["price_paid"], a["purchase_date"], a["purchased_from"]) == (
        True, "gold", "1250.00", "2025-03-15", "Heritage")
    assert a["toning_obverse"] and a["toning_rainbow"]
    assert rows[3]["fields"]["variety"] == "8TF" and rows[3]["fields"]["grading_service"] == "NGC"
    assert rows[4]["fields"]["grading_service"] == "RAW" and rows[4]["fields"]["grade_prefix"] == "AU"
    assert rows[5]["errors"] == ["PCGS coin without a cert number"]
    assert rows[6]["errors"] == ["Same cert as row 2"]
    assert any("Mint mark" in e for e in rows[7]["errors"])
    assert (d["ok_count"], d["error_count"]) == (3, 3)

    r = authed.post("/api/import/commit", json={"collection_id": col["id"], "rows": d["rows"]})
    assert r.status_code == 200, r.text
    out = r.json()
    assert len(out["created"]) == 3 and len(out["skipped"]) == 3
    coins = authed.get(f"/api/collections/{col['id']}/coins").json()
    assert sorted(c["year"] for c in coins) == [1878, 1881, 1884]

    # Importing the same file again: the certs are now duplicates
    again = _preview_csv(authed, col).json()
    assert any("Already in your collection" in e for e in {x["row"]: x for x in again["rows"]}[2]["errors"])


def test_export_round_trip(authed):
    src = _collection(authed, "morgan-dollars", name="Source")
    authed.post("/api/coins", json=coin_payload(src["id"], year=1881, mint_mark="S", price_paid="100.00",
                                                cac_sticker="green", slab_rattler=True, variety="VAM-3"))
    sold = coin_payload(src["id"], year=1880, mint_mark="O", sale_price="300", sale_date="2026-01-02")
    authed.post("/api/coins", json=sold)
    xlsx = authed.get(f"/api/collections/{src['id']}/export").content

    dst = _collection(authed, "morgan-dollars", name="Copy")
    d = authed.post("/api/import/preview", data={"collection_id": str(dst["id"])},
                    files={"file": ("export.xlsx", xlsx, "application/octet-stream")}).json()
    rows = d["rows"]
    assert len(rows) == 2
    on_hand = next(r for r in rows if r["sheet"] == "Coins")
    # Same cert is still on hand in the source collection
    assert on_hand["errors"] and "Already in your collection" in on_hand["errors"][0]
    f = on_hand["fields"]
    assert (f["year"], f["mint_mark"], f["cac_sticker"], f["slab_rattler"], f["variety"], f["price_paid"]) == (
        1881, "S", "green", True, "VAM-3", "100.00")
    sold_row = next(r for r in rows if r["sheet"] == "Sold")
    assert not sold_row["errors"] and sold_row["fields"]["sale_price"] == "300.00"


def test_paste_pcgs_certs(authed, monkeypatch):
    col = _collection(authed, "morgan-dollars", name="Morgans")

    def fake(service, cert, check_cac=True, user_id=None):
        if cert == "999":
            raise lookups.LookupError("PCGS cert 999 not found")
        return LookupResult(grading_service="PCGS", cert_number=cert, year=1881, mint_mark="S", grade_prefix="MS",
                            grade=66, pcgs_number="7170", description="1881-S $1 MS66", image_urls=[])

    monkeypatch.setattr(lookups, "lookup", fake)
    import app.routers.importer as r_imp
    monkeypatch.setattr(r_imp.lookups, "lookup", fake)
    d = authed.post("/api/import/certs", json={"collection_id": col["id"], "certs": "111, 222\n999\n111"}).json()
    assert [r["fields"]["cert_number"] for r in d["rows"]] == ["111", "222", "999"]
    assert d["ok_count"] == 2 and "not found" in d["rows"][2]["errors"][0]
    out = authed.post("/api/import/commit", json={"collection_id": col["id"], "rows": d["rows"]}).json()
    assert len(out["created"]) == 2
    assert importer.split_certs(" 1,2 ;3\n\n2 ") == ["1", "2", "3"]


def test_import_rules(client, authed):
    col = _collection(authed, "morgan-dollars")
    assert _preview_csv(authed, col, name="coins.pdf").status_code == 400
    assert _preview_csv(authed, col, text="Date,Grade\n").status_code == 400
    gold = _collection(authed, "gold-type-set")
    r = _preview_csv(authed, gold)
    assert r.status_code == 422 and "type set" in r.json()["detail"]
    client.post("/api/auth/logout")
    client.post("/api/auth/signup", json={"email": "x@example.com", "first_name": "X", "last_name": "Y", "password": "long enough pw"})
    assert _preview_csv(client, col).status_code == 404


def test_overdates_and_overmintmarks():
    cases = {
        "1880/79-CC Reverse of 1878": (1880, "CC", "1880/79, Reverse of 1878"),
        "1887/6-O": (1887, "O", "1887/6"),
        "1882-O/S": (1882, "O", "O/S"),
        "1900-o/cc": (1900, "O", "O/CC"),
        "1878 7/8TF Strong": (1878, "P", "7/8TF Strong"),  # tail-feather variety, not an overdate
    }
    for date, want in cases.items():
        f, _, errors = importer.row_to_fields({"Date": date, "Grade": "MS63", "Service": "PCGS", "Cert": "1"})
        assert not errors and (f["year"], f["mint_mark"], f["variety"]) == want, date
