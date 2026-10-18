"""Error coins (owner-described, owner-valued, no catalog pricing) and rim toners."""

from test_api import coin_payload

from app.services.importer import row_to_fields


def test_error_coin(authed, morgan_collection):
    col = morgan_collection["id"]
    r = authed.post("/api/coins", json=coin_payload(col, is_error=True))
    assert r.status_code == 422 and "Describe the error" in r.text
    r = authed.post("/api/coins", json=coin_payload(col, is_error=True, error_description="Off-center 15%",
                                                    error_value="900.00", price_paid="400.00"))
    assert r.status_code == 201, r.text
    c = r.json()
    assert (c["is_error"], c["error_description"], c["value_source"], c["value_estimate"]) == \
        (True, "Off-center 15%", "custom", "900.00")
    inv = c["inventory_number"]
    # No price-guide lookups; value at purchase is what was paid.
    assert authed.post(f"/api/coins/{inv}/cpg").status_code == 400
    assert authed.post(f"/api/coins/{inv}/pcgs").status_code == 400
    detail = authed.get(f"/api/coins/{inv}").json()
    assert (detail["purchase_value"]["source"], detail["purchase_value"]["value"]) == ("paid", "400.00")
    # Unticking it drops the description.
    r = authed.put(f"/api/coins/{inv}", json=coin_payload(col, cert_number=c["cert_number"], is_error=False,
                                                          error_description="Off-center 15%"))
    assert r.json()["error_description"] is None
    # It shows in the export and the insurance PDF builds.
    assert authed.get("/api/reports/insurance").status_code == 200


def test_import_error_and_rim_toner():
    f, _, errors, _ = row_to_fields({"Date": "1881-S", "Grade": "MS64", "Service": "PCGS", "Cert": "55",
                                     "Error": "Double struck", "Toning": "Rim, Obverse"})
    assert not errors, errors
    assert (f["is_error"], f["error_description"], f["toning_rim"], f["toning_obverse"]) == (True, "Double struck", True, True)


def test_rim_toner(authed, morgan_collection):
    r = authed.post("/api/coins", json=coin_payload(morgan_collection["id"], toning_rim=True))
    assert r.status_code == 201 and r.json()["toning_rim"] is True
