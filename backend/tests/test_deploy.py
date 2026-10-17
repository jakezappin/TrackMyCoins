"""Production features: sign-up modes, failed-login limiting, serving the built frontend."""

import pytest

from app.routers import auth as auth_router


def body(**kw):
    return {"email": "new@example.com", "first_name": "N", "last_name": "U", "password": "long enough pw", **kw}


def test_signup_modes(client, monkeypatch):
    s = auth_router.settings
    monkeypatch.setattr(s, "signup_mode", "closed")
    assert client.get("/api/auth/config").json() == {"signup": "closed"}
    assert client.post("/api/auth/signup", json=body()).status_code == 403

    monkeypatch.setattr(s, "signup_mode", "invite")
    monkeypatch.setattr(s, "invite_code", "morgan-1878")
    assert client.post("/api/auth/signup", json=body()).status_code == 403
    assert client.post("/api/auth/signup", json=body(invite_code="wrong")).status_code == 403
    assert client.post("/api/auth/signup", json=body(invite_code=" morgan-1878 ")).status_code == 201

    # Invite mode with no code configured lets nobody in
    monkeypatch.setattr(s, "invite_code", "")
    assert client.post("/api/auth/signup", json=body(email="x@example.com", invite_code="")).status_code == 403


@pytest.fixture()
def fresh_limiter(monkeypatch):
    monkeypatch.setattr(auth_router, "login_limiter", auth_router.FailureLimiter(3, 900))


def test_login_lockout(client, fresh_limiter):
    client.post("/api/auth/signup", json=body())
    client.post("/api/auth/logout")
    bad = {"email": "new@example.com", "password": "nope"}
    assert [client.post("/api/auth/login", json=bad).status_code for _ in range(3)] == [401, 401, 401]
    assert client.post("/api/auth/login", json=bad).status_code == 429
    # Even the right password is refused while locked out
    assert client.post("/api/auth/login", json={"email": "new@example.com", "password": "long enough pw"}).status_code == 429


def test_successful_login_resets_email_count(client, fresh_limiter):
    client.post("/api/auth/signup", json=body())
    client.post("/api/auth/logout")
    bad = {"email": "new@example.com", "password": "nope"}
    good = {"email": "new@example.com", "password": "long enough pw"}
    client.post("/api/auth/login", json=bad)
    client.post("/api/auth/login", json=bad)
    assert client.post("/api/auth/login", json=good).status_code == 200


def test_serves_frontend(client, tmp_path, monkeypatch):
    import importlib

    from app import config, main

    dist = tmp_path / "dist"
    (dist / "assets").mkdir(parents=True)
    (dist / "index.html").write_text("<html>app</html>")
    (dist / "assets" / "app.js").write_text("console.log(1)")
    (dist / "favicon.svg").write_text("<svg/>")
    monkeypatch.setattr(config.get_settings(), "frontend_dist", dist)
    importlib.reload(main)
    from fastapi.testclient import TestClient

    with TestClient(main.app) as c:
        assert c.get("/").text == "<html>app</html>"
        assert c.get("/coins/MOR-00005").text == "<html>app</html>"  # client-side route
        assert c.get("/assets/app.js").text == "console.log(1)"
        assert c.get("/favicon.svg").text == "<svg/>"
        assert c.get("/../../etc/passwd").text == "<html>app</html>"  # no escaping the folder
        assert c.get("/api/nope").status_code == 404
        assert c.get("/api/health").json() == {"ok": True}
    importlib.reload(main)


def test_invite_is_the_default(monkeypatch):
    from app.config import Settings

    monkeypatch.delenv("SIGNUP_MODE", raising=False)
    assert Settings(_env_file=None).signup_mode == "invite"
