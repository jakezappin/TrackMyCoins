"""Refresh-all-prices background job."""

import time

import pytest

from app.services import jobs
from test_api import coin_payload
from test_catalog import fake_greysheet  # noqa: F401  (autouse: fake Greysheet API)


@pytest.fixture(autouse=True)
def fast(monkeypatch):
    monkeypatch.setattr(jobs, "PAUSE_SECONDS", 0)


def wait(c, job_id):
    for _ in range(200):
        j = c.get(f"/api/jobs/{job_id}").json()
        if j["status"] != "running":
            return j
        time.sleep(0.02)
    raise AssertionError("job didn't finish")


def test_refresh_collection(authed, morgan_collection):
    cid = morgan_collection["id"]
    a = authed.post("/api/coins", json=coin_payload(cid, strike_designation="DMPL", cac=True)).json()  # 1881-S: priced
    authed.post("/api/coins", json=coin_payload(cid, year=1878, mint_mark="P"))  # ambiguous 1878: fails
    authed.post("/api/coins", json=coin_payload(cid, grading_service="RAW", grade=None, grade_prefix="AU"))  # skipped
    authed.post("/api/coins", json=coin_payload(cid, sale_price="10"))  # sold: not included

    job = authed.post("/api/refresh-prices", json={"collection_id": cid}).json()
    assert job["scope"] == "Morgan Dollar Collection 1"
    j = wait(authed, job["id"])
    assert (j["status"], j["total"], j["done"], j["updated"], j["failed"], j["skipped"]) == ("finished", 3, 3, 1, 1, 1)
    assert any("More than one catalog match" in m for m in j["messages"])
    coin = authed.get(f"/api/coins/{a['inventory_number']}").json()
    assert coin["latest_cpg"]["value"] == "1400.00"


def test_refresh_all_and_ownership(client, authed, morgan_collection):
    authed.post("/api/coins", json=coin_payload(morgan_collection["id"]))
    j = wait(authed, authed.post("/api/refresh-prices", json={}).json()["id"])
    assert j["scope"] == "All collections" and j["total"] == 1
    assert authed.post("/api/refresh-prices", json={"collection_id": 99999}).status_code == 404
    # Another user can't see the job
    client.post("/api/auth/logout")
    client.post("/api/auth/signup", json={"email": "z@example.com", "first_name": "Z", "last_name": "Z", "password": "long enough pw"})
    assert client.get(f"/api/jobs/{j['id']}").status_code == 404
    assert client.get("/api/jobs/current").json() is None


def test_refresh_updates_premium_estimate(authed, morgan_collection):
    cid = morgan_collection["id"]
    coin = authed.post("/api/coins", json=coin_payload(cid, strike_designation="DMPL", cac=True)).json()
    inv = coin["inventory_number"]
    authed.post(f"/api/coins/{inv}/cpg")  # CPG 1400
    authed.put(f"/api/coins/{inv}/valuation", json={"source": "cpg", "toner_premium": "500", "holder_premium": "100"})
    wait(authed, authed.post("/api/refresh-prices", json={"collection_id": cid}).json()["id"])
    quotes = authed.get(f"/api/coins/{inv}").json()["price_quotes"]
    assert [q["value"] for q in quotes if q["source"] == "PREMIUM"] == ["2000.00", "2000.00"]  # recorded again on refresh
