"""Fixes from the 2026-10-18 review of the new features."""

from datetime import date, timedelta

from test_api import coin_payload


def _sub(authed, **kw):
    return authed.post("/api/grading/submissions", json={"company": "NGC", **kw}).json()


def _put_in(authed, sub, inv):
    return authed.post(f"/api/grading/submissions/{sub['id']}/coins", json={"inventory_number": inv})


def test_import_ignores_storage_and_status_sent_back(authed, morgan_collection, client):
    from conftest import signup  # noqa: F401

    spot = authed.post("/api/storage/spots", json={"name": "Mine"}).json()
    row = {"row": 2, "fields": {**coin_payload(morgan_collection["id"]), "storage_id": spot["id"] + 50,
                                "storage_position": "x", "location": "grading"}, "errors": []}
    row["fields"].pop("collection_id")
    out = authed.post("/api/import/commit", json={"collection_id": morgan_collection["id"], "rows": [row]})
    assert out.status_code == 200, out.text
    c = authed.get(f"/api/coins/{out.json()['created'][0]}").json()
    assert (c["storage_id"], c["storage_name"], c["location"]) == (None, None, "inventory")


def test_result_without_cert_keeps_cert_and_sticker(authed, morgan_collection):
    c = authed.post("/api/coins", json=coin_payload(morgan_collection["id"], grading_service="NGC",
                                                   cert_number="1234567-001", cac_sticker="green")).json()
    s = _sub(authed)
    link = _put_in(authed, s, c["inventory_number"]).json()["coins"][0]["id"]
    authed.post(f"/api/grading/submissions/{s['id']}/results", json={"results": [
        {"link_id": link, "outcome": "graded", "grade_prefix": "MS", "grade": 66}]})  # an NGC regrade, no new cert
    got = authed.get(f"/api/coins/{c['inventory_number']}").json()
    assert (got["cert_number"], got["cac"], got["grade"]) == ("1234567-001", True, 66)


def test_older_result_doesnt_undo_newer_trip(authed, morgan_collection):
    c = authed.post("/api/coins", json=coin_payload(morgan_collection["id"])).json()
    inv = c["inventory_number"]
    old = _sub(authed)
    link = _put_in(authed, old, inv).json()["coins"][0]["id"]
    authed.post(f"/api/grading/submissions/{old['id']}/results", json={"results": [
        {"link_id": link, "outcome": "graded", "grade_prefix": "MS", "grade": 64, "cert_number": "1111111-001"}]})
    new = _sub(authed, company="PCGS")
    _put_in(authed, new, inv)
    # Re-recording the old submission's result: the coin stays at grading in the new one, grade untouched.
    authed.post(f"/api/grading/submissions/{old['id']}/results", json={"results": [
        {"link_id": link, "outcome": "graded", "grade_prefix": "MS", "grade": 62, "cert_number": "2222222-001"}]})
    got = authed.get(f"/api/coins/{inv}").json()
    assert (got["location"], got["grade"], got["cert_number"]) == ("grading", 64, "1111111-001")


def test_readd_after_reopening(authed, morgan_collection):
    c = authed.post("/api/coins", json=coin_payload(morgan_collection["id"])).json()
    s = _sub(authed, date_sent=(date.today() - timedelta(days=5)).isoformat())
    _put_in(authed, s, c["inventory_number"])
    body = {"company": "NGC", "date_sent": s["date_sent"], "date_returned": date.today().isoformat()}
    authed.put(f"/api/grading/submissions/{s['id']}", json=body)  # back: the coin returns to inventory
    authed.put(f"/api/grading/submissions/{s['id']}", json={**body, "date_returned": None})  # reopened
    r = _put_in(authed, s, c["inventory_number"])
    assert r.status_code == 200, r.text
    assert r.json()["coins"][0]["outcome"] == "pending"
    assert authed.get(f"/api/coins/{c['inventory_number']}").json()["location"] == "grading"


def test_account_pacing(client):
    from conftest import signup

    signup(client, "target@example.com")
    client.post("/api/auth/logout")
    for i in range(20):
        client.post("/api/auth/login", json={"email": "target@example.com", "password": "nope"},
                    headers={"fly-client-ip": f"10.1.{i}.1"})
    r1 = client.post("/api/auth/login", json={"email": "target@example.com", "password": "nope"},
                     headers={"fly-client-ip": "10.2.0.1"})
    r2 = client.post("/api/auth/login", json={"email": "target@example.com", "password": "correct horse battery"},
                     headers={"fly-client-ip": "10.2.0.2"})
    assert r1.status_code == 401 and r2.status_code == 429 and "seconds" in r2.json()["detail"]  # slowed, not locked


def test_melt_rules():
    from app.services.melt_table import entry_for

    assert entry_for("jefferson-nickels", 1942, "MS", "P", "Type 2, Silver").key == "war-nickel"
    assert entry_for("jefferson-nickels", 1942, "MS", "P", "Type 1") is None
    assert entry_for("classic-commemoratives", 1893, variety="Isabella").key == "quarter-90"
    assert entry_for("classic-commemoratives", 1900, variety="Lafayette").key == "dollar-90"
    assert entry_for("classic-commemoratives", 1936, variety="Albany").key == "half-90"


def test_search_without_year(authed):
    from app.db import SessionLocal
    from app.services import catalog

    with SessionLocal() as db:
        catalog.seed_from_bundle(db)
    hits = authed.get("/api/catalog/search", params={"q": "Lincoln Cheerios"}).json()
    assert hits and "Cheerios" in (hits[0]["variety"] or "")
