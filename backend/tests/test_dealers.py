"""Dealer contacts: the list and each dealer's history, links from coins and bullion, reading a card photo, the card
photo, vCards and linking coins typed before the dealer was added."""

import io

from PIL import Image

from conftest import signup
from test_api import coin_payload

RICK = {"business": "Rick's Rare Coins", "contact_name": "Rick Alvarez", "phone": "(555) 201-7788",
        "email": "rick@ricksrare.com", "website": "https://ricksrare.com/", "specialties": ["Morgans", "CAC", "morgans"],
        "notes": "Baltimore Expo, booth 1123"}


def _jpeg() -> bytes:
    buf = io.BytesIO()
    Image.new("RGB", (60, 40), "white").save(buf, "JPEG")
    return buf.getvalue()


def test_dealers_and_their_coins(authed, morgan_collection):
    r = authed.post("/api/dealers", json={"notes": "no name"})
    assert r.status_code == 422
    d = authed.post("/api/dealers", json=RICK).json()
    assert d["website"] == "ricksrare.com" and d["specialties"] == ["Morgans", "CAC"]

    # Picked on the coin form: linked, and the coin's text shows the dealer's name.
    c1 = authed.post("/api/coins", json=coin_payload(morgan_collection["id"], price_paid="250", purchased_from="whatever",
                                                     purchased_from_dealer_id=d["id"])).json()
    assert c1["purchased_from"] == "Rick's Rare Coins" and c1["purchased_from_dealer_id"] == d["id"]
    c2 = authed.post("/api/coins", json=coin_payload(morgan_collection["id"], year=1884, price_paid="500",
                                                     sale_price="650", sale_date="2026-01-05",
                                                     sold_to_dealer_id=d["id"])).json()
    col = authed.post("/api/bullion/collections", json={"name": "Silver", "metal": "silver"}).json()
    bar = authed.post("/api/bullion/items", json={"collection_id": col["id"], "description": "10 oz bar", "weight": "10",
                                                  "weight_unit": "ozt", "purity": "0.999", "price_paid": "400",
                                                  "purchased_from_dealer_id": d["id"]})
    assert bar.status_code == 201 and bar.json()["purchased_from"] == "Rick's Rare Coins", bar.text

    lst = authed.get("/api/dealers").json()
    assert lst[0]["bought_count"] == 2 and lst[0]["bought_total"] == "650.00"
    assert lst[0]["sold_count"] == 1 and lst[0]["sold_total"] == "650.00"
    page = authed.get(f"/api/dealers/{d['id']}").json()
    assert {i["inventory_number"] for i in page["items"]} == {c1["inventory_number"], c2["inventory_number"], "AG-00001"}
    assert page["held_count"] == 2  # the coin and the bar still held (the sold coin isn't)

    # Renaming the dealer renames the linked coins' text.
    authed.put(f"/api/dealers/{d['id']}", json={**RICK, "business": "Rick's Rare Coins & Bullion"})
    assert authed.get(f"/api/coins/{c1['inventory_number']}").json()["purchased_from"] == "Rick's Rare Coins & Bullion"

    # Another user's dealer can't be linked.
    authed.post("/api/auth/logout")
    signup(authed, "other@example.com")
    col2 = authed.post("/api/collections", json={"name": "M", "coin_type_id": morgan_collection["coin_type_id"]}).json()
    r = authed.post("/api/coins", json=coin_payload(col2["id"], purchased_from_dealer_id=d["id"]))
    assert r.status_code == 404
    assert authed.get(f"/api/dealers/{d['id']}").status_code == 404
    authed.post("/api/auth/logout")
    authed.post("/api/auth/login", json={"email": "me@example.com", "password": "correct horse battery"})

    # Deleting the dealer keeps the coins' text, without the link.
    assert authed.delete(f"/api/dealers/{d['id']}").status_code == 204
    c = authed.get(f"/api/coins/{c1['inventory_number']}").json()
    assert c["purchased_from"] == "Rick's Rare Coins & Bullion" and c["purchased_from_dealer_id"] is None


def test_link_my_coins(authed, morgan_collection):
    typed = [("Ricks Rare Coins", None), ("Rick's Rare Coins, Inc.", None), ("rick alvarez", None),
             ("Heartland Numismatics", None), (None, "Rick's Rare")]
    invs = []
    for i, (bought, sold) in enumerate(typed):
        extra = {"sale_price": "10", "sale_date": "2026-01-05", "sold_to": sold} if sold else {}
        invs.append(authed.post("/api/coins", json=coin_payload(morgan_collection["id"], year=1880 + i,
                                                                 purchased_from=bought, **extra)).json()["inventory_number"])
    d = authed.post("/api/dealers", json=RICK).json()
    sugg = authed.get(f"/api/dealers/{d['id']}/link-suggestions").json()
    assert {s["inventory_number"] for s in sugg} == {invs[0], invs[1], invs[2], invs[4]}  # not Heartland
    assert authed.get(f"/api/dealers/{d['id']}").json()["link_suggestions"] == 4
    page = authed.post(f"/api/dealers/{d['id']}/link", json={"items": [f"coin:{invs[0]}", f"coin:{invs[4]}", f"coin:{invs[3]}"]}).json()
    assert {i["inventory_number"] for i in page["items"]} == {invs[0], invs[4]}  # Heartland isn't a match: not linked
    assert authed.get(f"/api/coins/{invs[4]}").json()["sold_to_dealer_id"] == d["id"]


def test_read_card_photo_and_vcard(authed, monkeypatch):
    from app.services import label_reader

    seen = {}

    def fake(content, hint, schema=None, clean=None):
        seen["schema"] = schema
        return clean({"found": True, "business": " Rick's Rare Coins ", "contact_name": "Rick Alvarez",
                      "phone": "(555) 201-7788", "email": None, "website": "https://ricksrare.com/", "address": None,
                      "social": None, "specialties": ["Morgan Dollars", " "], "notes": "Booth 1123"})

    monkeypatch.setattr(label_reader, "_ask_claude", fake)
    monkeypatch.setattr(label_reader.get_settings(), "anthropic_api_key", "test")
    r = authed.post("/api/dealers/read-card", files={"file": ("card.jpg", _jpeg(), "image/jpeg")})
    assert r.status_code == 200, r.text
    card = r.json()
    assert card["business"] == "Rick's Rare Coins" and card["website"] == "ricksrare.com"
    assert card["specialties"] == ["Morgan Dollars"] and "business" in seen["schema"]["properties"]

    d = authed.post("/api/dealers", json=RICK).json()
    r = authed.post(f"/api/dealers/{d['id']}/photo", files={"file": ("card.jpg", _jpeg(), "image/jpeg")})
    assert r.status_code == 200 and r.json()["photo_url"]
    assert authed.get(r.json()["photo_url"]).headers["content-type"] == "image/jpeg"
    v = authed.get(f"/api/dealers/{d['id']}/vcard")
    assert v.headers["content-type"].startswith("text/vcard")
    assert "ORG:Rick's Rare Coins" in v.text and "TEL;TYPE=WORK,VOICE:(555) 201-7788" in v.text
    assert "URL:https://ricksrare.com" in v.text and "N:Alvarez;Rick;;;" in v.text
