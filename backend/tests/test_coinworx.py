"""MyCoinWorx inventory exports import with their own columns: exact series, grading company, holders, CAC,
cost, asking price and photos."""

import csv
import io

from app.services import coinworx, importer

HEADERS = ["Item ID", "Category", "Coin Type", "Coin Series", "Metal", "Year", "Mint Mark", "Mint Province", "Design",
           "Finish", "Strike", "Catalog PCGS #", "PCGS ID", "Program", "Grade", "Graded", "Grading Company",
           "Cert Number", "Special Designations", "Special Holder", "Rattler", "OGH", "Fatty", "Soapbox", "CAC Green",
           "CAC Gold", "Toned/PQ", "Mint Error", "Cost", "Asking Price", "Status", "Sold Price", "Sold Date", "Notes",
           "Received Date", "Image URL 1", "Image URL 2"]


def _csv(rows: list[dict]) -> bytes:
    buf = io.StringIO()
    w = csv.DictWriter(buf, fieldnames=HEADERS)
    w.writeheader()
    for r in rows:
        w.writerow({h: r.get(h, "No" if h in ("Rattler", "OGH", "Fatty", "Soapbox", "CAC Green", "CAC Gold",
                                               "Toned/PQ", "Mint Error") else "") for h in HEADERS})
    return buf.getvalue().encode()


ROWS = [
    {"Category": "Dollars", "Coin Type": "Dollar", "Coin Series": "Morgan Dollar (1878 - 1921)", "Year": "1888",
     "Grade": "MS 63", "Grading Company": "ANACS", "Cert Number": "1435182", "Special Designations": "VAM-11 DBL EAR TOP 100",
     "Soapbox": "Yes", "CAC Green": "Yes", "Cost": "150", "Asking Price": "175", "Status": "ON_HAND",
     "Received Date": "2026-07-28", "Image URL 1": "https://f005.backblazeb2.com/file/CoinWorX/a.jpg"},
    {"Category": "Classic Commemoratives (1892-1954)", "Coin Type": "Half Dollar", "Coin Series": "Grant Half Dollar",
     "Year": "1922", "Program": "Grant", "Grade": "AU DETAILS", "Grading Company": "NGC", "Cert Number": "8907535-005",
     "Special Designations": "GRANT W/ STAR", "Cost": "617.47", "Status": "ON_HAND"},
    {"Category": "Twenty Cents", "Coin Type": "20 Cents", "Coin Series": "Twenty Cent (1875 - 1878)", "Year": "1875",
     "Mint Mark": "S", "Grade": "VF 30", "Grading Company": "NGC", "Cert Number": "8907535-006", "Status": "ON_HAND"},
    {"Category": "Half Dollars", "Coin Type": "Half Dollar", "Coin Series": "Franklin Half Dollar (1948 - 1963)",
     "Year": "1954", "Mint Mark": "D", "Grade": "MS64FBL", "Grading Company": "PCI", "Cert Number": "224966004",
     "Special Designations": "GSA SOFT PACK", "Status": "ON_HAND"},
    {"Category": "Dollars", "Coin Type": "Dollar", "Coin Series": "Morgan Dollar (1878 - 1921)", "Year": "1878",
     "Mint Mark": "CC", "Grade": "FAIR 2", "Grading Company": "NGC", "Cert Number": "2183211-005", "Status": "ON_HAND"},
]


def test_rows_become_our_columns():
    rows = importer.read_rows("export.csv", _csv(ROWS))
    out = []
    for _, _, raw in rows:
        photos = raw.pop(importer.PHOTOS_KEY)
        f, _, errors, _ = importer.row_to_fields(raw)
        out.append((raw, f, errors, photos))
    (r0, f0, e0, p0), (r1, f1, e1, _), (r2, f2, e2, _), (r3, f3, e3, _), (r4, f4, e4, _) = out
    assert not any((e0, e1, e2, e3, e4)), (e0, e1, e2, e3, e4)
    assert r0["Type"] == "Morgan Dollar" and f0["grading_service"] == "ANACS" and f0["vam"] == "11"
    assert f0["slab_soapbox"] and f0["cac"] and f0["cac_sticker"] == "green"
    assert (f0["price_paid"], f0["asking_price"], str(f0["purchase_date"])) == ("150.00", "175.00", "2026-07-28")
    assert p0 == ["https://f005.backblazeb2.com/file/CoinWorX/a.jpg"]
    assert r1["Type"] == "Classic Commemorative" and f1["variety"] == "Grant, With Star" and f1["details"]
    assert r2["Type"] == "Twenty Cent" and (f2["year"], f2["mint_mark"]) == (1875, "S")
    assert (f3["grading_service"], f3["other_service"], f3["strike_designation"], f3["gsa_soft_pack"]) == (
        "OTHER", "PCI", "FBL", True)
    assert (f4["grade_prefix"], f4["grade"]) == ("FR", 2)


def test_preview_sorts_into_series(authed):
    r = authed.post("/api/import/preview", files={"file": ("coinworx.csv", _csv(ROWS), "text/csv")})
    assert r.status_code == 200, r.text
    rows = r.json()["rows"]
    assert all(not row["errors"] for row in rows), [row["errors"] for row in rows]
    targets = [row["target"] for row in rows]
    assert any("Twenty Cent" in (t or "") for t in targets) and any("Morgan" in (t or "") for t in targets)
    assert rows[0]["photo_urls"] == ["https://f005.backblazeb2.com/file/CoinWorX/a.jpg"]


def test_detects_only_coinworx():
    assert coinworx.is_coinworx(HEADERS)
    assert not coinworx.is_coinworx(["Date", "Grade", "Cert", "Grading service"])
