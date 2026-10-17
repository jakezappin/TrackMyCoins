"""Read-only shared collection links."""

from test_api import PNG, coin_payload
from test_catalog import fake_greysheet  # noqa: F401  (autouse fixture)
from test_reports import _collection


def _setup(c):
    col = _collection(c, "morgan-dollars", name="My Morgans")
    coin = c.post("/api/coins", json=coin_payload(col["id"], year=1881, mint_mark="S", price_paid="100.00",
                                                  purchased_from="Secret Dealer", notes="private note")).json()
    c.put(f"/api/coins/{coin['inventory_number']}/valuation", json={"source": "custom", "custom_value": "250.00"})
    sold = c.post("/api/coins", json=coin_payload(col["id"], year=1878, mint_mark="P", sale_price="200", sale_date="2026-10-01")).json()
    coin = c.post(f"/api/coins/{coin['inventory_number']}/photos", files=[("files", ("a.png", PNG, "image/png"))]).json()
    sold = c.post(f"/api/coins/{sold['inventory_number']}/photos", files=[("files", ("b.png", PNG, "image/png"))]).json()
    return col, coin, sold


def test_share_hides_private_fields(client, authed):
    col, coin, sold = _setup(authed)
    assert authed.get(f"/api/collections/{col['id']}").json()["share_token"] is None

    r = authed.put(f"/api/collections/{col['id']}/share", json={"show_values": False})
    token = r.json()["share_token"]
    assert token and len(token) >= 30

    client.post("/api/auth/logout")
    d = client.get(f"/api/shared/{token}").json()
    assert d["name"] == "My Morgans" and d["owner"] == "Test U." and d["coin_count"] == 1
    assert d["total_estimated_value"] is None and d["coins"][0]["value_estimate"] is None
    body = str(d)
    for secret in ("Secret Dealer", "private note", "100.00", "price_paid", "inventory_number", "me@example.com"):
        assert secret not in body
    # Photos: only this collection's coins on hand
    assert client.get(d["coins"][0]["photo_urls"][0]).status_code == 200
    assert client.get(f"/api/shared/{token}/photos/{sold['photos'][0]['id']}").status_code == 404
    assert client.get(f"/api/photos/{coin['photos'][0]['id']}").status_code == 401


def test_share_values_and_revoke(client, authed):
    col, coin, _ = _setup(authed)
    token = authed.put(f"/api/collections/{col['id']}/share", json={"show_values": True}).json()["share_token"]
    d = authed.get(f"/api/shared/{token}").json()
    assert d["total_estimated_value"] == "250.00" and d["coins"][0]["value_estimate"] == "250.00"

    # Changing options keeps the same link
    assert authed.put(f"/api/collections/{col['id']}/share", json={"show_values": False}).json()["share_token"] == token

    assert authed.delete(f"/api/collections/{col['id']}/share").json()["share_token"] is None
    assert authed.get(f"/api/shared/{token}").status_code == 404
    assert authed.get(f"/api/shared/{token}/photos/{coin['photos'][0]['id']}").status_code == 404
    # A new share gets a new link
    assert authed.put(f"/api/collections/{col['id']}/share", json={}).json()["share_token"] != token


def test_share_requires_owner(client, authed):
    col = _collection(authed, "morgan-dollars")
    client.post("/api/auth/logout")
    client.post("/api/auth/signup", json={"email": "x@example.com", "first_name": "X", "last_name": "Y", "password": "long enough pw"})
    assert client.put(f"/api/collections/{col['id']}/share", json={}).status_code == 404
    assert client.get("/api/shared/not-a-real-token").status_code == 404
