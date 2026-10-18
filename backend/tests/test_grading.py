"""Grading Tracker: submissions, turnaround days and colors, coins at grading, results and documents."""

import io
from datetime import date, timedelta

from PIL import Image
from test_api import coin_payload

from app.services import grading


def test_business_days_skip_weekends_and_holidays():
    # Mon Nov 23 2026 -> Mon Nov 30: Thanksgiving (Thu 26) and the weekend don't count.
    assert grading.days_between(date(2026, 11, 23), date(2026, 11, 30), business=True) == 4
    assert grading.days_between(date(2026, 11, 23), date(2026, 11, 30), business=False) == 7
    assert date(2026, 7, 3) in grading.holidays(2026)  # July 4 is a Saturday: observed Friday
    assert grading.add_days(date(2026, 12, 23), 2, business=True) == date(2026, 12, 28)  # Christmas Friday


def test_colors():
    assert [grading.color(p) for p in (1, 60, 61, 90, 91, 100, 101)] == \
        ["green", "green", "yellow", "yellow", "orange", "orange", "red"]


def _sub(authed, **kw):
    r = authed.post("/api/grading/submissions", json={"company": "NGC", **kw})
    assert r.status_code == 201, r.text
    return r.json()


def test_submission_lifecycle(authed, morgan_collection):
    raw = authed.post("/api/coins", json=coin_payload(morgan_collection["id"], grading_service="RAW", cert_number=None,
                                                      grade_prefix=None, grade=None, price_paid="80")).json()
    s = _sub(authed, name="Morgans", tier_name="Economy", tier_fee="25.00", tier_max_value="300.00", turnaround_days=20,
             business_days=True, addons=[{"key": "x", "name": "Photo", "fee": "5.00", "per": "coin"},
                                        {"key": "h", "name": "Handling", "fee": "10.00", "per": "order"}])
    assert s["number"] == 1 and s["progress"]["status"] == "preparing" and s["progress"]["color"] is None

    r = authed.post(f"/api/grading/submissions/{s['id']}/coins",
                    json={"inventory_number": raw["inventory_number"], "expected_grade": "MS64", "declared_value": "400"})
    assert r.status_code == 200, r.text
    d = r.json()
    assert d["fees"] == {"per_coin": "30.00", "estimate": "40.00"}
    assert d["over_max_value"] == [raw["inventory_number"]]  # $400 is over Economy's $300 limit
    coin = authed.get(f"/api/coins/{raw['inventory_number']}").json()
    assert coin["location"] == "grading" and coin["grading"]["number"] == 1

    # Can't be in two submissions at once, or sold while away.
    other = _sub(authed, company="PCGS")
    r = authed.post(f"/api/grading/submissions/{other['id']}/coins", json={"inventory_number": raw["inventory_number"]})
    assert r.status_code == 409
    body = coin_payload(morgan_collection["id"], grading_service="RAW", cert_number=None, grade_prefix=None, grade=None,
                        location="grading", sale_price="100", sale_date=date.today().isoformat())
    assert authed.put(f"/api/coins/{raw['inventory_number']}", json=body).status_code == 422

    # Sent 30 business days ago with a 20-day tier: overdue (red).
    sent = date.today()
    for _ in range(30):
        sent -= timedelta(days=1)
        while not grading.is_business_day(sent):
            sent -= timedelta(days=1)
    upd = {**{k: d[k] for k in ("name", "company", "kind", "tier_name", "tier_fee", "tier_max_value", "turnaround_days",
                                 "business_days", "addons")}, "date_sent": sent.isoformat()}
    d = authed.put(f"/api/grading/submissions/{s['id']}", json=upd).json()
    assert d["progress"]["elapsed"] == grading.days_between(sent, date.today(), True) >= 29 and d["progress"]["color"] == "red" and d["progress"]["clock_from"] == "sent"

    # Back: graded NGC MS64 with a cert; the coin is updated and back in inventory, and remembers its trip.
    link = d["coins"][0]["id"]
    r = authed.post(f"/api/grading/submissions/{s['id']}/results", json={"results": [
        {"link_id": link, "outcome": "graded", "grade_prefix": "MS", "grade": 64, "cert_number": "7654321-001"}]})
    assert r.status_code == 200, r.text
    d = r.json()
    assert d["progress"]["status"] == "returned" and d["coins"][0]["outcome"] == "graded"
    coin = authed.get(f"/api/coins/{raw['inventory_number']}").json()
    assert (coin["grading_service"], coin["grade"], coin["cert_number"], coin["location"]) == ("NGC", 64, "7654321-001", "inventory")
    h = coin["grading_history"][0]
    assert (h["before"], h["after"], h["expected_grade"]) == ("Raw", "NGC MS64 #7654321-001", "MS64")
    assert coin["price_paid"] == "80.00"  # grading costs aren't added to the coin's cost


def test_at_grading_from_the_coin_form(authed, morgan_collection):
    body = coin_payload(morgan_collection["id"], location="grading")
    assert authed.post("/api/coins", json=body).status_code == 422  # which submission?
    r = authed.post("/api/coins", json={**body, "grading": {"new_company": "PCGS", "expected_grade": "MS66"}})
    assert r.status_code == 201, r.text
    c = r.json()
    assert c["grading"]["company"] == "PCGS" and c["grading"]["expected_grade"] == "MS66"

    # Back to In Inventory from the form: closed in the submission without a result, coin unchanged.
    r = authed.put(f"/api/coins/{c['inventory_number']}", json={**coin_payload(morgan_collection["id"], cert_number=c["cert_number"]),
                                                               "location": "inventory"})
    assert r.status_code == 200 and r.json()["location"] == "inventory" and r.json()["grading"] is None
    s = authed.get(f"/api/grading/submissions/{c['grading']['id']}").json()
    assert s["coins"][0]["outcome"] == "returned"


def test_cac_sticker_and_dashboard_order(authed, morgan_collection):
    c = authed.post("/api/coins", json=coin_payload(morgan_collection["id"])).json()
    cac = _sub(authed, company="CAC", date_sent=(date.today() - timedelta(days=40)).isoformat())
    assert cac["kind"] == "sticker"
    newer = _sub(authed, company="NGC", date_sent=(date.today() - timedelta(days=3)).isoformat())
    back = _sub(authed, company="ICG", date_sent="2026-01-05", date_returned="2026-02-01")
    authed.post(f"/api/grading/submissions/{cac['id']}/coins", json={"inventory_number": c["inventory_number"]})
    link = authed.get(f"/api/grading/submissions/{cac['id']}").json()["coins"][0]["id"]
    authed.post(f"/api/grading/submissions/{cac['id']}/results", json={"results": [{"link_id": link, "outcome": "sticker_gold"}]})
    coin = authed.get(f"/api/coins/{c['inventory_number']}").json()
    assert (coin["cac"], coin["cac_sticker"], coin["grade"]) == (True, "gold", 65)

    order = [x["id"] for x in authed.get("/api/dashboard").json()["submissions"]]
    # cac came back today, so: still out (newer), then returned newest first (cac, then back).
    assert order == [newer["id"], cac["id"], back["id"]]


def test_submission_documents(authed):
    s = _sub(authed)
    buf = io.BytesIO()
    Image.new("RGB", (200, 100), (200, 200, 200)).save(buf, "JPEG")
    r = authed.post(f"/api/grading/submissions/{s['id']}/attachments", data={"kind": "invoice"},
                    files=[("files", ("invoice.jpg", buf.getvalue(), "image/jpeg"))])
    assert r.status_code == 200, r.text
    doc = r.json()[0]
    assert doc["kind"] == "invoice" and authed.get(doc["url"]).status_code == 200
    assert authed.delete(doc["url"]).status_code == 204
    # Someone else's submission isn't reachable.
    assert authed.get("/api/grading/submissions/99999").status_code == 404


def test_tier_catalog(authed):
    c = authed.get("/api/grading/tiers").json()
    assert c["checked"] and {t["company"] for t in c["tiers"]} == {"NGC", "PCGS", "CACG", "CAC", "ANACS", "ICG"}
    ngc = next(t for t in c["tiers"] if t["key"] == "ngc-economy")
    assert ngc["business_days"] is True and ngc["days"] and ngc["fee"]
    assert c["colors"] == {"green": 60, "yellow": 90, "orange": 100}
