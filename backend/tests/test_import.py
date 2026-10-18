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
        f, _, errors, _ = importer.row_to_fields({"Date": date, "Grade": "MS63", "Service": "PCGS", "Cert": "1"})
        assert not errors and (f["year"], f["mint_mark"], f["variety"]) == want, date


MIXED = """Type,Date,Grade,Service,Cert #
,1881-S Morgan Dollar,MS64,PCGS,90000001
Peace Dollar,1922,MS63,PCGS,90000002
Barber Dime,1900-O,MS62,NGC,90000003
,1895 Morgan,PR64 CAM,PCGS,90000004
Morgan,1910,MS63,PCGS,90000005
Franklin Half,1955,MS64,PCGS,90000006
,1881 $1,MS63,PCGS,90000007
,1882-S,MS64,PCGS,90000008
,1922-S Peace,MS63,PCGS,90000009
"""


def test_sort_mixed_file_into_collections(authed):
    first = _collection(authed, "morgan-dollars", name="Morgans A")
    _collection(authed, "morgan-dollars", name="Morgans B")
    r = authed.post("/api/import/preview", files={"file": ("mixed.csv", MIXED.encode(), "text/csv")})
    assert r.status_code == 200, r.text
    rows = {x["row"]: x for x in r.json()["rows"]}
    assert (rows[2]["target"], rows[2]["target_new"], rows[2]["fields"]["variety"]) == ("Morgans A", False, None)
    assert (rows[3]["target"], rows[3]["target_new"]) == ("Peace Dollar Collection 1", True)
    assert rows[4]["target"] == "Barber Dime Collection 1"
    assert rows[5]["target"] == "Morgan Dollar Proof Collection 1"
    assert "Morgan Dollars (1878–1904, 1921)" in rows[6]["errors"][0] and "1910" in rows[6]["errors"][0]
    assert rows[7]["errors"] and rows[8]["errors"]  # a series we don't track; "$1" alone is ambiguous
    assert "Type column" in rows[9]["errors"][0]  # nothing says what it is
    assert rows[10]["target"] == "Peace Dollar Collection 1"

    out = authed.post("/api/import/commit", json={"collection_id": None, "rows": r.json()["rows"]}).json()
    assert len(out["created"]) == 5 and len(out["skipped"]) == 4
    made = {c["name"]: c for c in out["collections"]}
    assert made["Morgans A"]["count"] == 1 and not made["Morgans A"]["new"]
    assert made["Peace Dollar Collection 1"]["count"] == 2 and made["Peace Dollar Collection 1"]["new"]
    assert made["Morgan Dollar Proof Collection 1"]["new"]
    cols = {c["name"]: c for c in authed.get("/api/collections").json()}
    assert cols["Peace Dollar Collection 1"]["number"] == 1 and cols["Morgan Dollar Proof Collection 1"]["finish"] == "PR"
    assert [c["inventory_number"][:3] for c in authed.get(f"/api/collections/{first['id']}/coins").json()] == ["MOR"]
    peace = authed.get(f"/api/collections/{made['Peace Dollar Collection 1']['id']}/coins").json()
    assert sorted(c["year"] for c in peace) == [1922, 1922]


def test_import_into_one_collection_flags_other_series(authed):
    col = _collection(authed, "morgan-dollars", name="Morgans")
    text = "Date,Grade,Service,Cert #\n1921 Peace Dollar,MS63,PCGS,91000001\n1910,MS63,PCGS,91000002\n1921,MS63,PCGS,91000003\n"
    rows = {x["row"]: x for x in _preview_csv(authed, col, text).json()["rows"]}
    assert rows[2]["errors"] == ["This looks like a Peace Dollar, not a Morgan Dollar."]
    assert "1910 isn't a Morgan Dollar date" in rows[3]["errors"][0]
    assert rows[4]["errors"] == [] and rows[4]["target"] == "Morgans"


def test_export_inventory_numbers_sort_themselves(authed):
    text = "Inventory #,Date,Grade,Grading service,Cert #\nPEA-00007,1923-S,MS64,PCGS,92000001\n"
    r = authed.post("/api/import/preview", files={"file": ("x.csv", text.encode(), "text/csv")}).json()
    assert r["rows"][0]["target"] == "Peace Dollar Collection 1"


def test_paste_certs_sorted_by_pcgs_series(authed, monkeypatch):
    from app.routers import importer as r_imp

    facts = {"1": ("Morgan Dollars 1878-1921", "1881-S $1", 1881, "S"),
             "2": ("Peace Dollars 1921-1935", "1923 $1", 1923, None),
             "3": ("Franklin Half Dollars 1948-1963", "1955 50C", 1955, None)}

    def fake(service, cert, check_cac=True, user_id=None):
        series, name, year, mint = facts[cert]
        return LookupResult(grading_service="PCGS", cert_number=cert, year=year, mint_mark=mint, grade_prefix="MS",
                            grade=64, description=name, raw={"SeriesName": series, "Name": name})

    monkeypatch.setattr(r_imp.lookups, "lookup", fake)
    d = authed.post("/api/import/certs", json={"certs": "1, 2, 3"}).json()
    rows = {x["row"]: x for x in d["rows"]}
    assert rows[1]["target"] == "Morgan Dollar Collection 1" and rows[2]["target"] == "Peace Dollar Collection 1"
    assert "doesn't track yet" in rows[3]["errors"][0]


def test_year_gaps_are_invalid(authed):
    """Exact years, not spans: no 1922 Mercury Dime, 1930 Peace Dollar, 1975 Kennedy or future-dated coin."""
    from app.series import BY_SLUG
    from app.services.series_match import year_problem

    for slug, year in [("mercury-dimes", 1922), ("peace-dollars", 1930), ("kennedy-half-dollars", 1975),
                       ("morgan-dollars", 2022), ("indian-eagles", 1925), ("buffalo-nickels", 1932), ("large-cents", 1815)]:
        assert year_problem(BY_SLUG[slug], year), (slug, year)
    for slug, year in [("mercury-dimes", 1921), ("peace-dollars", 1934), ("modern-morgan-dollars", 2023),
                       ("early-quarter-eagles", 1802), ("liberty-double-eagles", 1849)]:
        assert year_problem(BY_SLUG[slug], year) is None, (slug, year)
    assert "future" in year_problem(BY_SLUG["lincoln-cents"], 2999)


def test_invalid_year_blocked_when_adding_by_hand(authed, morgan_collection):
    r = authed.post("/api/coins", json=coin_payload(morgan_collection["id"], year=1910, mint_mark="S"))
    assert r.status_code == 422 and "1910 isn't a Morgan Dollar date" in r.json()["detail"]


def test_date_and_mint_must_exist():
    from app.series import BY_SLUG
    from app.services.series_match import date_problem

    morgan, peace = BY_SLUG["morgan-dollars"], BY_SLUG["peace-dollars"]
    assert "There's no 1904-CC Morgan Dollar" in date_problem(morgan, 1904, "CC", "MS")
    assert "were struck at: Philadelphia (no mint mark), O, S" in date_problem(morgan, 1904, "CC", "MS")
    assert "only struck as proofs" in date_problem(morgan, 1895, "P", "MS")
    assert date_problem(morgan, 1895, "P", "PR") is None and date_problem(morgan, 1895, "O", "AU") is None
    assert "no 1921-S Peace" in date_problem(peace, 1921, "S", "MS")
    assert date_problem(morgan, 2023, "S", "MS")  # a 2023 Morgan is a Modern Morgan Dollar
    assert date_problem(BY_SLUG["modern-morgan-dollars"], 2023, "P", "MS") is None
    assert date_problem(BY_SLUG["early-quarter-eagles"], 1802, "P", "MS") is None  # real, missing from Greysheet
    assert date_problem(BY_SLUG["jefferson-nickels"], 2020, "W", "PR") is None
    assert date_problem(BY_SLUG["kennedy-half-dollars"], 1970, "P", "MS")  # 1970 halves: D (business), S (proof)


def test_ogp_round_trip(authed):
    from app.services import importer

    f, *_ = importer.row_to_fields({"Date": "1986-S", "Grade": "PR69 DCAM", "Service": "Raw", "Packaging": "OGP"})
    assert f["ogp"] is True
    f, *_ = importer.row_to_fields({"Date": "1973-S", "Grade": "PR68", "Packaging": "Brown Pack, OGP"})
    assert f["ogp"] and f["ike_brown_pack"]
    f, *_ = importer.row_to_fields({"Date": "1986-S", "Grade": "PR69", "OGP": "Yes"})
    assert f["ogp"] is True
    f, *_ = importer.row_to_fields({"Date": "1986-S", "Grade": "PR69"})
    assert f["ogp"] is False
