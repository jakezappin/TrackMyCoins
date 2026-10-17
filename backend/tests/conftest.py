import os
import tempfile
from pathlib import Path

import pytest

_tmp = Path(tempfile.mkdtemp(prefix="coinapp-test-"))
os.environ["DATABASE_URL"] = f"sqlite:///{_tmp / 'test.db'}"
os.environ["PHOTO_DIR"] = str(_tmp / "photos")
os.environ["SESSION_SECRET"] = "test-secret"
os.environ["PCGS_API_TOKEN"] = ""
os.environ["GREYSHEET_API_KEY"] = ""
os.environ["GREYSHEET_API_TOKEN"] = ""

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
