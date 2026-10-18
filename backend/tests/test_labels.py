"""Labels: price codes, label layout (nothing cut off), the print queue, preview and PDF, and each coin's own link."""

from datetime import date
from decimal import Decimal

import pytest

from app.services import labels, price_code
from conftest import signup
from test_api import coin_payload

PHRASE = "I LOVE FRANK"


def test_price_code_both_starts():
    assert price_code.letters(PHRASE) == list("ILOVEFRANK")
    # Starting at 0: I=0 ... K=9. Starting at 1: I=1 ... N=9, K=0.
    assert price_code.encode_price(145, PHRASE, 0, 3) == "LEF"
    assert price_code.encode_price(145, PHRASE, 1, 3) == "IVE"
    assert price_code.encode_price(1000, PHRASE, 1, 3) == "IKKK"
    # No cents: rounded to the nearest dollar.
    assert price_code.encode_price(Decimal("145.60"), PHRASE, 0, 3) == "LER"
    assert price_code.encode_price(Decimal("145.49"), PHRASE, 0, 3) == "LEF"
    # Filled out to the code length with letters not in the phrase; the same coin always gets the same code.
    code = price_code.encode_price(145, PHRASE, 0, 7, seed="42")
    assert len(code) == 7 and price_code.decode(code, PHRASE, 0) == "145"
    assert code == price_code.encode_price(145, PHRASE, 0, 7, seed="42")
    assert sum(ch in "ILOVEFRANK" for ch in code) == 3
    # The real letters stay together, with filler on both sides.
    assert "LEF" in code and code[0] not in "ILOVEFRANK" and code[-1] not in "ILOVEFRANK"
    code = price_code.encode_price(215, PHRASE, 0, 6, seed="7")
    assert "OLF" in code and len(code) == 6 and code[0] not in "ILOVEFRANK" and code[-1] not in "ILOVEFRANK"
    assert price_code.encode_price(215, PHRASE, 0, 3) == "OLF"  # no room: no filler
    # Dates: month, day, 2-digit year.
    assert price_code.encode_date(date(2025, 3, 15), PHRASE, 0) == "IV LF OF"
    assert price_code.decode("IV LF OF", PHRASE, 0) == "03 15 25"
    with pytest.raises(price_code.PriceCodeError, match="9 different letters"):
        price_code.check_phrase("I LOVE FRAN")


def test_long_text_wraps_and_shrinks_but_is_never_cut():
    lines = [labels.Text("1880/79-CC Morgan Dollar VAM-4 Reverse of 1879 Hot Lips", bold=True, scale=1.2),
             labels.Text("VAM-4 · Top 100 · Error: Struck 10% off center"), labels.Text("MS64 DMPL NGC · CAC Gold"),
             labels.Text("#6012345-004", "MOR-00123"), labels.Text("PLTEXN · IV LF OF", "$12,450", mono=True, right_bold=True)]
    for size in labels.SIZES:
        sheet = labels.sheet_for(size)
        placed, _mode, fs = labels.fit(lines, *sheet.label, sheet.pad, sheet.qr, sheet.max_font, sheet.modes)
        printed = " ".join(p.text for p in placed).split()
        for t in lines:  # every word of every line is on the label
            for word in f"{t.left} {t.right}".split():
                assert word in printed, (size, word)
        w, h = sheet.label
        for p in placed:  # and inside it
            width = labels.stringWidth(p.text, p.font, p.size)
            left = p.x - width if p.anchor == "end" else p.x
            assert left >= sheet.pad[0] - 0.01 and left + width <= w - sheet.pad[0] + 0.01, (size, p.text)
            assert sheet.pad[1] - 0.5 <= p.y <= h, (size, p.text)
        assert fs >= labels.MIN_FONT, size


def _job(items, **opts):
    return {"options": {"size": "2x2", **opts}, "items": [{"inventory_number": i, "asking_price": a} for i, a in items],
            "site": "http://localhost:5174"}


def test_price_code_settings(authed):
    r = authed.put("/api/auth/price-code", json={"phrase": "I LOVE FRAN", "start": 0, "length": 6})
    assert r.status_code == 422 and "exactly 10" in r.json()["detail"]
    # Which digit the phrase starts on has to be chosen.
    r = authed.put("/api/auth/price-code", json={"phrase": PHRASE, "length": 6})
    assert r.status_code == 422 and "0 or 1" in r.json()["detail"]
    me = authed.put("/api/auth/price-code", json={"phrase": "i  love frank", "start": 1, "length": 6}).json()
    assert (me["price_code_phrase"], me["price_code_start"], me["price_code_length"]) == (PHRASE, 1, 6)
    me = authed.put("/api/auth/preferences", json={"asking_price_on": True}).json()
    assert me["asking_price_on"] is True and me["details_pct"] == 70


def test_labels_queue_preview_and_print(authed, morgan_collection):
    c1 = authed.post("/api/coins", json=coin_payload(morgan_collection["id"], purchase_date="2025-03-15",
                                                      price_paid="145.60", asking_price="325")).json()
    c2 = authed.post("/api/coins", json=coin_payload(morgan_collection["id"], year=1882)).json()
    authed.post("/api/coins", json=coin_payload(morgan_collection["id"], year=1883, sale_price="10"))  # sold: skipped
    assert c1["asking_price"] == "325.00"

    q = authed.post("/api/labels/queue", json={"collection_id": morgan_collection["id"]}).json()
    assert [i["inventory_number"] for i in q["items"]] == [c1["inventory_number"], c2["inventory_number"]]
    assert q["items"][0]["asking_price"] == "325.00" and q["price_code_ready"] is False
    q = authed.patch(f"/api/labels/queue/{c2['inventory_number']}", json={"asking_price": "99"}).json()
    assert q["items"][1]["asking_price"] == "99.00"

    items = [(i["inventory_number"], i["asking_price"]) for i in q["items"]]
    # Coded prices need a price code first.
    r = authed.post("/api/labels/preview", json=_job(items, price="code"))
    assert r.status_code == 400 and "Account settings" in r.json()["detail"]
    assert authed.post("/api/labels/pdf", json=_job(items, purchase_date="code")).status_code == 400
    authed.put("/api/auth/price-code", json={"phrase": PHRASE, "start": 0, "length": 3})

    for size in ("avery5160", "thermal2x1"):
        r = authed.post("/api/labels/preview", json=_job(items, size=size, price="code", purchase_date="code", start=3))
        assert r.status_code == 200, r.text
        p = r.json()
        assert p["label_count"] == 2 and p["page_count"] == (2 if size == "thermal2x1" else 1) and not p["two_sided"]
        assert p["labels"][0].startswith("<?xml") and "LER" in p["labels"][0] and "IV LF OF" in p["labels"][0]
        assert "$325" in p["labels"][0] and not p["warnings"]
    # 2x2 flip inserts are for raw coins: slabs are left off (and with only slabs, there's nothing to print).
    r = authed.post("/api/labels/preview", json=_job(items, size="2x2"))
    assert r.status_code == 400 and "raw coins" in r.json()["detail"]
    # Previewing doesn't make links; printing does, and remembers the options.
    assert authed.get(f"/api/labels/coins/{c1['inventory_number']}/public").json()["path"] is None
    r = authed.post("/api/labels/pdf", json=_job(items, size="avery5160", price="plain"))
    assert r.status_code == 200 and r.content.startswith(b"%PDF")
    assert authed.get("/api/labels/queue").json()["options"]["size"] == "avery5160"
    state = authed.get(f"/api/labels/coins/{c1['inventory_number']}/public").json()
    assert state["public_page"] is False and state["path"].startswith("/c/")
    # One coin from its own page, without the queue.
    one = authed.get(f"/api/labels/queue?only={c2['inventory_number']}").json()
    assert [i["inventory_number"] for i in one["items"]] == [c2["inventory_number"]]

    assert authed.get(f"/api/labels/coins/{c1['inventory_number']}/public").json()["queued"] is True
    q = authed.post("/api/labels/queue/clear", json={"inventory_numbers": [c1["inventory_number"]]}).json()
    assert authed.get(f"/api/labels/coins/{c1['inventory_number']}/public").json()["queued"] is False
    assert [i["inventory_number"] for i in q["items"]] == [c2["inventory_number"]]
    assert authed.post("/api/labels/queue/clear", json={}).json()["items"] == []


def test_coin_link_owner_stranger_private(client, morgan_collection):
    c = client.post("/api/coins", json=coin_payload(morgan_collection["id"], notes="secret", price_paid="250")).json()
    inv = c["inventory_number"]
    path = client.put(f"/api/labels/coins/{inv}/public", json={"public_page": False}).json()["path"]
    api_path = f"/api{path}"
    assert client.get(api_path).json() == {"owner": True, "inventory_number": inv}

    client.post("/api/auth/logout")
    assert client.get(api_path).json() == {"owner": False, "private": True}
    signup(client, "other@example.com")  # someone else's account: still private to them
    assert client.get(api_path).json()["private"] is True
    client.post("/api/auth/logout")

    client.post("/api/auth/login", json={"email": "me@example.com", "password": "correct horse battery"})
    client.put(f"/api/labels/coins/{inv}/public", json={"public_page": True})
    client.post("/api/auth/logout")
    pub = client.get(api_path).json()
    assert pub["private"] is False and pub["title"] == "1881-S Morgan Dollar" and pub["coin"]["grade"] == 65
    text = str(pub)
    assert "secret" not in text and "250" not in text and "price_paid" not in text

    # A new link retires the old one.
    client.post("/api/auth/login", json={"email": "me@example.com", "password": "correct horse battery"})
    new = client.post(f"/api/labels/coins/{inv}/public/new-link").json()["path"]
    assert new != path and client.get(api_path).status_code == 404
    assert client.get(f"/api{new}").json()["owner"] is True


def test_2x2_front_and_back(authed, morgan_collection):
    from app.services.short_names import short_name

    assert short_name("morgan-dollars", "Morgan Dollar", 1878, None) == "Morgan"
    assert short_name("washington-quarters", "Washington Quarter", 1999, "Delaware, Silver") == "Delaware Quarter"
    assert short_name("washington-quarters", "Washington Quarter", 1965, "Doubled Die Obverse") == "Washington"
    assert short_name("classic-commemoratives", "Classic Commemorative", 1925, "Stone Mountain") == "Stone Mountain Comm. Half"
    assert short_name("classic-commemoratives", "Classic Commemorative", 1935, "1935/34, Boone") == "Boone Comm. Half"
    assert short_name("classic-commemoratives", "Classic Commemorative", 1893, "Isabella") == "Isabella Comm. Quarter"
    assert short_name("american-silver-eagles", "American Silver Eagle", 2021, "Type 2") == "ASE"
    assert short_name("america-250", "America 250 (2026)", 2026, "25c Mayflower Compact, Silver") == "Mayflower Compact Quarter"

    raw = authed.post("/api/coins", json=coin_payload(morgan_collection["id"], year=1878, mint_mark="CC", grading_service="RAW",
                                                       cert_number=None, grade_prefix="VF", grade=20, price_paid="145")).json()
    ungraded = authed.post("/api/coins", json=coin_payload(morgan_collection["id"], year=1880, grading_service="RAW",
                                                            cert_number=None, grade_prefix=None, grade=None)).json()
    slab = authed.post("/api/coins", json=coin_payload(morgan_collection["id"], year=1881)).json()
    items = [(c["inventory_number"], "325") for c in (raw, ungraded, slab)]
    p = authed.post("/api/labels/preview", json=_job(items, size="2x2", price="plain")).json()
    assert p["two_sided"] and p["label_count"] == 2 and p["skipped"] == [slab["inventory_number"]] and p["warnings"]
    front, back = p["labels"][0], p["labels"][1]
    assert "1878-CC" in front and "Morgan" in front and "VF20" in front and "$" not in front  # nothing private
    assert all(w in back for w in ("1878-CC", "Morgan", "Dollar", "Raw VF20", "$145", "$325"))
    assert "VF20" not in p["labels"][2]  # no grade entered: none on the front
    assert len(p["pages"]) == 2  # the first sheet's fronts and backs

    # The PDF: fronts, then backs mirrored (the first back sits in the right-hand column).
    opts = labels.Options(size="2x2")
    data = [labels.LabelData([labels.Text("x")], None, labels.Front("1878-CC", "Morgan", "VF20"))]
    pages, _ = labels.pages(data, opts)
    assert len(pages) == 2
    sheet = labels.sheet_for("2x2")
    assert labels._slot(sheet, 0, mirror=True)[0] == labels._slot(sheet, 3)[0]
    r = authed.post("/api/labels/pdf", json=_job(items, size="2x2"))
    assert r.status_code == 200 and r.content.startswith(b"%PDF")
    r = authed.get("/api/labels/alignment-test?square=1.875")
    assert r.status_code == 200 and r.content.startswith(b"%PDF")
