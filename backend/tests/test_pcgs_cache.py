"""PCGS allows 100 calls a day: a cert is asked once and kept, an issue and grade's market data for a week, the
bulk refresh never calls PCGS, and the value at purchase a coin page fills by itself waits while PCGS is short."""

from datetime import datetime, timedelta, timezone

from app.db import SessionLocal
from app.models import PcgsCache
from app.schemas import LookupResult
from app.services import lookups, pcgs_cache, quota
from app.services.lookups import pcgs


def test_cert_lookup_is_asked_once(client, monkeypatch):
    calls = []

    def fake(cert):
        calls.append(cert)
        return LookupResult(grading_service="PCGS", cert_number=cert, grade_prefix="MS", grade=64, pcgs_number="7130")

    monkeypatch.setattr(pcgs, "lookup", fake)
    a = lookups.lookup("PCGS", "12345678", user_id=1)
    b = lookups.lookup("PCGS", "12345678", user_id=1)
    assert calls == ["12345678"] and a == b and b.pcgs_number == "7130"
    assert quota.used_today(1, "pcgs") == 2  # charged once
    lookups.lookup("PCGS", "12345678", user_id=1, fresh=True)
    assert len(calls) == 2


def test_market_data_kept_a_week(client, monkeypatch):
    calls = []
    monkeypatch.setattr(pcgs, "market", lambda n, g, p: calls.append(n) or {"price_guide": "100", "grade": g})
    assert pcgs.market_cached("7130", 64, cache_only=True) == (None, False)
    d, called = pcgs.market_cached("7130", 64)
    assert called and d["price_guide"] == "100"
    assert pcgs.market_cached("7130", 64) == (d, False)
    with SessionLocal() as db:  # 8 days later: asked again
        db.get(PcgsCache, pcgs_cache.market_key("7130", 64, False)).fetched_at = datetime.now(timezone.utc) - timedelta(days=8)
        db.commit()
    assert pcgs.market_cached("7130", 64)[1] and len(calls) == 2


def test_automatic_pcgs_waits_when_short(client, monkeypatch):
    assert quota.room_for_automatic_pcgs()
    quota.spend_site("pcgs", 45)
    assert not quota.room_for_automatic_pcgs()
