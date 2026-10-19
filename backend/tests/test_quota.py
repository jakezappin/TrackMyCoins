"""Daily limits on paid / rate-limited API calls."""

from test_api import coin_payload
from test_catalog import calls, fake_greysheet, _age_sheets  # noqa: F401  (autouse fixture)
from test_pcgs_market import requests as pcgs_requests, fake_pcgs  # noqa: F401  (autouse fixture)

from app.config import get_settings
from app.services import quota


def test_greysheet_limit_per_user(authed, morgan_collection, monkeypatch):
    monkeypatch.setattr(get_settings(), "greysheet_per_user_day", 1)
    a = authed.post("/api/coins", json=coin_payload(morgan_collection["id"], pcgs_number="7130")).json()
    b = authed.post("/api/coins", json=coin_payload(morgan_collection["id"], pcgs_number="7131")).json()
    assert authed.post(f"/api/coins/{a['inventory_number']}/cpg").status_code == 200
    r = authed.post(f"/api/coins/{b['inventory_number']}/cpg")  # a different issue: a real call, over the limit
    assert r.status_code == 429 and "today's limit" in r.json()["detail"]
    # The same issue again is priced from the saved result: free, so still allowed
    assert authed.post(f"/api/coins/{a['inventory_number']}/cpg").status_code == 200


def test_pcgs_limits_per_user_and_site(client, authed, morgan_collection, monkeypatch):
    monkeypatch.setattr(get_settings(), "pcgs_per_user_day", 2)  # one coin's market data
    monkeypatch.setattr(get_settings(), "pcgs_site_day", 3)
    a = authed.post("/api/coins", json=coin_payload(morgan_collection["id"], year=1878, grade=62, pcgs_number="7072")).json()
    b = authed.post("/api/coins", json=coin_payload(morgan_collection["id"], year=1878, grade=63, pcgs_number="7072")).json()
    assert authed.post(f"/api/coins/{a['inventory_number']}/pcgs").status_code == 200
    n = len(pcgs_requests)
    r = authed.post(f"/api/coins/{b['inventory_number']}/pcgs")
    assert r.status_code == 429 and len(pcgs_requests) == n  # refused before calling PCGS
    assert quota.used_today(0, "pcgs") == 2  # site-wide count


def test_claude_limit(authed, monkeypatch):
    import io

    from PIL import Image

    from app.services import label_reader

    monkeypatch.setattr(get_settings(), "anthropic_api_key", "k")
    monkeypatch.setattr(get_settings(), "claude_per_user_day", 0)
    monkeypatch.setattr(label_reader, "_ask_claude", lambda *a, **k: (_ for _ in ()).throw(AssertionError("called")))
    b = io.BytesIO()
    Image.new("RGB", (50, 50)).save(b, "JPEG")
    r = authed.post("/api/read-label", files={"file": ("l.jpg", b.getvalue(), "image/jpeg")})
    assert r.status_code == 429 and "label reading" in r.json()["detail"]


def test_pcgs_refusal_pauses_pcgs_until_its_retry_after(authed, monkeypatch):
    """PCGS allows 100 calls a day; once it refuses, no more calls until its Retry-After, and the message says when."""
    import httpx
    import pytest as _pytest

    from app.services import quota
    from app.services.lookups import pcgs

    calls = []

    def handler(request):
        calls.append(request.url.path)
        return httpx.Response(429, headers={"retry-after": "63102"}, text='"maximum admitted 100 per Day"')

    monkeypatch.setattr(pcgs, "_client", lambda: httpx.Client(base_url="https://pcgs.test", transport=httpx.MockTransport(handler)))
    monkeypatch.setattr(pcgs.get_settings(), "pcgs_api_token", "t")
    with _pytest.raises(pcgs.LookupError, match="resets in about 18 hours"):
        pcgs.lookup("12345678")
    assert quota.paused_for("pcgs") > 60000
    with _pytest.raises(quota.QuotaExceeded, match="100 lookups a day"):
        quota.spend(1, "pcgs", 2)  # stopped before calling PCGS again
    assert len(calls) == 1
