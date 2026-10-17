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
            "Mintage": 749500, "MintLocation": "Philadelphia", "MetalContent": "90% Silver, 10% Copper",
            "Weight": 26.73, "Diameter": 38.1, "Edge": "Reeded", "Designer": "George T. Morgan",
            "SeriesName": "Morgan Dollars 1878-1921",
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


def test_overdate_and_overmint_helpers():
    from app.services.lookups.base import normalize_mint_mark, over_variety, year_of

    assert year_of("1880/79") == 1880 and year_of(1887) == 1887 and year_of(None) is None
    assert over_variety("1880/79-CC $1 Reverse of 1878") == "1880/79"
    assert over_variety("1882-O/S $1 Strong") == "O/S"
    assert over_variety("1900-O/CC $1") == "O/CC"
    assert over_variety("1887/6-O $1") == "1887/6"
    assert over_variety("1881-S $1") is None
    assert normalize_mint_mark("O/S") == "O" and normalize_mint_mark("-S") == "S" and normalize_mint_mark("") == "P"


def test_coin_facts_card(authed, morgan_collection):
    coin = authed.post("/api/coins", json=coin_payload(morgan_collection["id"], year=1878, grade=62, pcgs_number="7072")).json()
    assert authed.get(f"/api/coins/{coin['inventory_number']}").json()["facts"] is None  # nothing fetched yet
    f = authed.post(f"/api/coins/{coin['inventory_number']}/pcgs").json()["facts"]
    assert (f["mintage"], f["mint_location"], f["weight_g"], f["designer"], f["population"], f["pop_higher"], f["pop_grade"]) == (
        749500, "Philadelphia", 26.73, "George T. Morgan", 1204, 312, "MS62")
    assert f["source"] == "pcgs_market" and f["as_of"]


def test_coin_facts_from_cert_lookup(authed, morgan_collection):
    raw = {"PCGSNo": 7130, "Grade": "MS65", "Mintage": 12760000, "MintLocation": "San Francisco", "Population": 60698,
           "PopHigher": 21681, "MetalContent": "90% Silver, 10% Copper", "Weight": 26.73, "Diameter": 38.1}
    coin = authed.post("/api/coins", json={**coin_payload(morgan_collection["id"], year=1881, mint_mark="S"), "lookup_raw": raw}).json()
    f = authed.get(f"/api/coins/{coin['inventory_number']}").json()["facts"]
    assert (f["mintage"], f["mint_location"], f["population"], f["pop_grade"], f["source"]) == (
        12760000, "San Francisco", 60698, "MS65", "cert_lookup")


def test_melt_value_for_silver_only(authed, morgan_collection):
    coin = authed.post("/api/coins", json=coin_payload(morgan_collection["id"], year=1878, grade=62, pcgs_number="7072")).json()
    f = authed.post(f"/api/coins/{coin['inventory_number']}/pcgs").json()["facts"]
    # 26.73 g x 90% silver = 0.7735 oz x $50 (test spot price)
    assert f["melt"]["metals"] == [{"metal": "silver", "oz": 0.7735, "spot": 50.0}] and f["melt"]["value"] == 38.67


def test_no_melt_for_base_metal():
    from app.services.metals import fineness, melt

    assert melt(5.0, "75% Copper, 25% Nickel") is None
    assert melt(11.34, "Copper-Nickel Clad Copper") is None
    assert fineness("Outer: 80% Silver, 20% Copper; Inner: 21% Silver, 79% Copper") == {}  # ambiguous: no guess
    assert fineness(".999 Silver") == {"silver": 0.999}
    g = fineness("91.67% Gold, 3% Silver, 5.33% Copper")
    assert round(g["gold"], 4) == 0.9167 and g["silver"] == 0.03


def test_pcgs_market_fetched_once_a_day_per_issue_and_grade(authed, morgan_collection):
    a = authed.post("/api/coins", json=coin_payload(morgan_collection["id"], year=1878, grade=62, pcgs_number="7072")).json()
    b = authed.post("/api/coins", json=coin_payload(morgan_collection["id"], year=1878, grade=62, pcgs_number="7072")).json()
    authed.post(f"/api/coins/{a['inventory_number']}/pcgs")
    n = len(requests)
    d = authed.post(f"/api/coins/{b['inventory_number']}/pcgs").json()
    assert len(requests) == n and d["pcgs_market"]["population"] == 1204  # same issue + grade: no PCGS calls


def test_pcgs_links_made_absolute():
    from app.schemas import PcgsMarket
    from app.urls import absolute_url

    assert absolute_url("www.pcgs.com/coinfacts/coin/detail/7130/65") == "https://www.pcgs.com/coinfacts/coin/detail/7130/65"
    assert absolute_url("https://x.test/a") == "https://x.test/a" and absolute_url("//x.test/a") == "https://x.test/a"
    assert absolute_url("") is None
    m = PcgsMarket(fetched_at="2026-10-17T00:00:00Z", pcgs_number="7130", grade="MS65",
                   coinfacts_url="www.pcgs.com/coinfacts/coin/detail/7130/65",
                   auctions=[{"date": "2026-08", "price": "170.8", "url": "www.stacksbowers.com/lot/1"}])
    assert m.coinfacts_url.startswith("https://") and m.auctions[0].url == "https://www.stacksbowers.com/lot/1"
