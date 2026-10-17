"""Get PCGS Data: price guide, population and auction sales, against a fake PCGS API."""

import httpx
import pytest

from app.services.lookups import pcgs
from test_api import coin_payload

requests: list[httpx.Request] = []


def handler(request: httpx.Request) -> httpx.Response:
    requests.append(request)
    path = request.url.path
    if path.endswith("/GetCoinFactsByGrade"):
        return httpx.Response(200, json={
            "PCGSNo": "7072", "Grade": "MS62", "PriceGuideValue": 335.0, "Population": 1204, "PopHigher": 312,
            "CoinFactsLink": "https://www.pcgs.com/coinfacts/coin/7072", "IsValidRequest": True,
        })
    if path.endswith("/GetAPRByGrade"):
        return httpx.Response(200, json={"IsValidRequest": True, "Auctions": [
            {"Service": "NGC", "Date": "04-2026", "Auctioneer": "Stack's Bowers", "LotNumV2": "99020",
             "SaleName": "Spring 2026", "CertNo": "1", "Price": 268.4, "IsCAC": False, "AuctionLotUrl": "https://x/1"},
            {"Service": "PCGS", "Date": "06-2026", "Auctioneer": "Heritage", "LotNo": 5, "SaleName": "June",
             "CertNo": "2", "Price": 317.2, "IsCAC": True, "AuctionLotUrl": "https://x/2"},
            {"Service": "PCGS", "Date": "", "Price": 100},  # no date: skipped
        ]})
    return httpx.Response(404)


@pytest.fixture(autouse=True)
def fake_pcgs(monkeypatch):
    requests.clear()
    monkeypatch.setattr(pcgs, "_client", lambda: httpx.Client(base_url="https://pcgs.test/publicapi", transport=httpx.MockTransport(handler)))


def test_get_pcgs_data(authed, morgan_collection):
    coin = authed.post("/api/coins", json=coin_payload(morgan_collection["id"], year=1878, grade=62, pcgs_number="7072", grade_plus=True)).json()
    r = authed.post(f"/api/coins/{coin['inventory_number']}/pcgs")
    assert r.status_code == 200, r.text
    d = r.json()
    m = d["pcgs_market"]
    assert (m["price_guide"], m["population"], m["pop_higher"], m["grade"]) == ("335.0", 1204, 312, "MS62")
    assert [(a["date"], a["price"], a["cac"]) for a in m["auctions"]] == [("2026-06", "317.2", True), ("2026-04", "268.4", False)]
    assert m["auctions"][0]["lot"] == "5" and m["auctions"][1]["auctioneer"] == "Stack's Bowers"
    # Saved to price history alongside CPG
    assert [(q["source"], q["value"]) for q in d["price_quotes"]] == [("PCGS", "335.00")]
    # Asked for the coin's grade (with plus) and 10 sales
    apr = next(q for q in requests if q.url.path.endswith("/GetAPRByGrade"))
    assert apr.url.params["GradeNo"] == "62" and apr.url.params["PlusGrade"] == "true" and apr.url.params["NumberOfRecords"] == "10"
    # Persisted on the coin
    assert authed.get(f"/api/coins/{coin['inventory_number']}").json()["pcgs_market"]["population"] == 1204


def test_get_pcgs_data_needs_grade(authed, morgan_collection):
    raw = authed.post("/api/coins", json=coin_payload(morgan_collection["id"], grading_service="RAW", grade_prefix="AU", grade=None, pcgs_number="7072")).json()
    r = authed.post(f"/api/coins/{raw['inventory_number']}/pcgs")
    assert r.status_code == 400 and "number" in r.json()["detail"]
    assert requests == []  # no PCGS calls spent


def test_sale_date_parsing():
    assert pcgs._sale_date("06-2026") == "2026-06"
    assert pcgs._sale_date("6/2025") == "2025-06"
    assert pcgs._sale_date("2024-11-03") == "2024-11"
    assert pcgs._sale_date("") is None
