import os
import tempfile
from pathlib import Path

import pytest

_tmp = Path(tempfile.mkdtemp(prefix="coinapp-test-"))
os.environ["DATABASE_URL"] = f"sqlite:///{_tmp / 'test.db'}"
os.environ["PHOTO_DIR"] = str(_tmp / "photos")
os.environ["SESSION_SECRET"] = "test-secret"
os.environ["SIGNUP_MODE"] = "open"  # most tests sign up freely; test_deploy covers invite mode
os.environ["PCGS_API_TOKEN"] = ""
os.environ["GREYSHEET_API_KEY"] = ""
os.environ["GREYSHEET_API_TOKEN"] = ""
os.environ["BACKGROUND_JOBS"] = "0"
os.environ["SEED_SPOT_HISTORY"] = "0"

from fastapi.testclient import TestClient  # noqa: E402

from app.db import Base, engine  # noqa: E402
from app.main import app  # noqa: E402


@pytest.fixture()
def client():
    Base.metadata.drop_all(engine)
    Base.metadata.create_all(engine)
    with TestClient(app) as c:
        yield c


def signup(c, email="me@example.com"):
    r = c.post(
        "/api/auth/signup",
        json={"email": email, "first_name": "Test", "last_name": "User", "password": "correct horse battery"},
    )
    assert r.status_code == 201, r.text
    return r.json()


@pytest.fixture()
def authed(client):
    signup(client)
    return client


@pytest.fixture()
def morgan_collection(authed):
    ct = next(t for t in authed.get("/api/coin-types").json() if t["slug"] == "morgan-dollars")
    r = authed.post("/api/collections", json={"name": "Morgan Dollar Collection 1", "coin_type_id": ct["id"]})
    assert r.status_code == 201, r.text
    return r.json()


@pytest.fixture(autouse=True)
def fixed_spot_prices(monkeypatch):
    """No network in tests: silver $50, gold $4,000 an ounce."""
    from app.services import metals

    prices = {"silver": 50.0, "gold": 4000.0, "platinum": 1600.0, "palladium": 1000.0, "copper": 5.0}
    monkeypatch.setattr(metals, "_fetch_spot", lambda metal: (prices[metal], "2026-10-17T12:00:00Z"))
    metals._spot.clear()


@pytest.fixture(autouse=True)
def fresh_pcgs_cache():
    from app.services.lookups import pcgs

    pcgs._market_cache.clear()


@pytest.fixture(autouse=True)
def fresh_rate_limits():
    """Every test starts with clean login/sign-up counters (tests sign up many accounts from one address)."""
    from app.routers import auth

    for lim in (auth.login_limiter, auth.signup_limiter, auth.signup_counter):
        lim._hits.clear()


@pytest.fixture(autouse=True)
def fresh_catalog_failures():
    """The catalog's back-off after a failed download is kept in memory; start each test without one."""
    from app.services import catalog

    catalog._failed.clear()
