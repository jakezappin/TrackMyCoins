"""'For sale on eBay now' (Browse API), against a fake eBay."""

import httpx
import pytest

from test_api import coin_payload
from test_catalog import fake_greysheet, type_id  # noqa: F401  (autouse fixture)
from test_reports import _collection

from app.config import get_settings
from app.services import ebay

TITLES = [
    ("1881-S Morgan Silver Dollar PCGS MS65", 120.0, ["FIXED_PRICE", "BEST_OFFER"]),     # match
    ("1881 S $1 Morgan Dollar MS-65 PCGS CAC", 150.0, ["FIXED_PRICE"]),                 # match, CAC
    ("1881-S Morgan PCGS MS 65", 95.0, ["AUCTION"]),                                    # match, auction
    ("1881-S Morgan Dollar PCGS MS65 DMPL", 900.0, ["FIXED_PRICE"]),                    # DMPL: different coin
    ("1881-S Morgan Dollar PCGS MS66", 200.0, ["FIXED_PRICE"]),                         # wrong grade
    ("1881-S Morgan Dollar NGC MS65", 110.0, ["FIXED_PRICE"]),                          # wrong service
    ("1881-O Morgan Dollar PCGS MS65", 300.0, ["FIXED_PRICE"]),                         # wrong mint
    ("1881-S Morgan PCGS Genuine UNC Details Cleaned", 40.0, ["FIXED_PRICE"]),          # details
    ("Lot of 5 1881-S Morgan Dollars PCGS MS65", 600.0, ["FIXED_PRICE"]),               # lot
]


@pytest.fixture
def fake_ebay(monkeypatch):
    calls = []

    def handler(request: httpx.Request) -> httpx.Response:
        calls.append(request)
        if request.url.path.endswith("/oauth2/token"):
            return httpx.Response(200, json={"access_token": "tok", "expires_in": 7200})
        items = []
        for i, (title, price, opts) in enumerate(TITLES):
            it = {"itemId": str(i), "title": title, "buyingOptions": opts, "price": {"value": f"{price}", "currency": "USD"},
                  "itemWebUrl": f"https://www.ebay.com/itm/{i}", "image": {"imageUrl": f"https://i.ebayimg.com/{i}.jpg"}}
            if "AUCTION" in opts:
                it.update(currentBidPrice={"value": "101.50", "currency": "USD"}, bidCount=3, itemEndDate="2026-10-20T18:00:00.000Z")
            items.append(it)
        return httpx.Response(200, json={"total": len(items), "itemSummaries": items})

    real = httpx.Client
    monkeypatch.setattr(ebay.httpx, "Client", lambda **kw: real(transport=httpx.MockTransport(handler), **kw))
    monkeypatch.setattr(get_settings(), "ebay_client_id", "id")
    monkeypatch.setattr(get_settings(), "ebay_client_secret", "secret")
    ebay._cache.clear()
    ebay._token.update(value=None, expires=0)
    return calls


def test_listings_filtered_to_the_coin(authed, fake_ebay):
    col = _collection(authed, "morgan-dollars")
    coin = authed.post("/api/coins", json=coin_payload(col["id"], year=1881, mint_mark="S", grade=65)).json()
    d = authed.get(f"/api/coins/{coin['inventory_number']}/ebay").json()
    assert d["configured"] and d["query"] == "1881-S Morgan Dollar PCGS MS65"
    assert [x["title"] for x in d["items"]] == [
        "1881-S Morgan PCGS MS 65", "1881-S Morgan Silver Dollar PCGS MS65", "1881 S $1 Morgan Dollar MS-65 PCGS CAC"]
    auction = d["items"][0]
    assert (auction["kind"], auction["price"], auction["bids"]) == ("auction", 101.5, 3)
    assert d["items"][1]["best_offer"] and d["items"][2]["cac"]
    assert d["stats"] == {"count": 3, "buy_it_now_count": 2, "low": 120.0, "median": 135.0, "high": 150.0}
    assert "_sacat=253" in d["search_url"]

    search = next(r for r in fake_ebay if "item_summary" in r.url.path)
    assert search.headers["X-EBAY-C-MARKETPLACE-ID"] == "EBAY_US" and search.url.params["category_ids"] == "253"
    # Cached: a second look doesn't call eBay again
    n = len(fake_ebay)
    authed.get(f"/api/coins/{coin['inventory_number']}/ebay")
    assert len(fake_ebay) == n


def test_designation_coin_wants_its_designation(authed, fake_ebay):
    col = _collection(authed, "morgan-dollars")
    coin = authed.post("/api/coins", json=coin_payload(col["id"], year=1881, mint_mark="S", grade=65, strike_designation="DMPL")).json()
    d = authed.get(f"/api/coins/{coin['inventory_number']}/ebay").json()
    assert [x["title"] for x in d["items"]] == ["1881-S Morgan Dollar PCGS MS65 DMPL"]


def test_not_configured(authed, monkeypatch):
    monkeypatch.setattr(get_settings(), "ebay_client_id", "")
    col = _collection(authed, "morgan-dollars")
    coin = authed.post("/api/coins", json=coin_payload(col["id"], year=1881, mint_mark="S", grade=65)).json()
    d = authed.get(f"/api/coins/{coin['inventory_number']}/ebay").json()
    assert d["configured"] is False and "ebay.com/sch" in d["search_url"]
