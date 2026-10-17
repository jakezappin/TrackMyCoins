"""Reading slab labels from photos (Claude call faked)."""

import io

import zxingcpp
from types import SimpleNamespace

from PIL import Image

from app.config import get_settings
from app.schemas import LookupResult
from app.services import label_reader


def _jpeg(size=(3000, 2000)):
    b = io.BytesIO()
    Image.new("RGB", size, (200, 200, 200)).save(b, "JPEG")
    return b.getvalue()


class FakeMessages:
    def __init__(self, text, stop="end_turn"):
        self.text, self.stop, self.kwargs = text, stop, None

    def create(self, **kwargs):
        self.kwargs = kwargs
        return SimpleNamespace(stop_reason=self.stop, content=[SimpleNamespace(type="text", text=self.text)])


def _fake(monkeypatch, text, stop="end_turn"):
    msgs = FakeMessages(text, stop)
    monkeypatch.setattr(get_settings(), "anthropic_api_key", "test-key")
    monkeypatch.setattr(label_reader.anthropic, "Anthropic", lambda **kw: SimpleNamespace(beta=SimpleNamespace(messages=msgs)))
    return msgs


RESULT = """{"found_label": true, "grading_service": "PCGS", "cert_number": " 4321 5678 ", "year": 1881, "mint_mark": "s",
"coin_type": "Morgan Dollar", "denomination": "$1", "grade_prefix": "MS", "grade": 65, "grade_plus": true, "grade_star": false,
"strike_designation": "DMPL", "variety": null, "vam": "", "cac_sticker": "gold", "confidence": "high", "notes": null}"""


def test_read_label(authed, monkeypatch):
    msgs = _fake(monkeypatch, RESULT)
    r = authed.post("/api/read-label", files={"file": ("label.jpg", _jpeg(), "image/jpeg")})
    assert r.status_code == 200, r.text
    d = r.json()
    assert (d["grading_service"], d["cert_number"], d["year"], d["mint_mark"], d["grade"], d["grade_plus"]) == (
        "PCGS", "43215678", 1881, "S", 65, True)
    assert d["cac_sticker"] == "gold" and d["vam"] is None and d["source"] == "claude"
    # The image is shrunk and sent as JPEG, with structured output and the server-side fallback
    img = msgs.kwargs["messages"][0]["content"][0]["source"]
    assert img["media_type"] == "image/jpeg"
    import base64
    w, h = Image.open(io.BytesIO(base64.b64decode(img["data"]))).size
    assert max(w, h) <= label_reader.MAX_SIDE
    assert msgs.kwargs["output_config"]["format"]["type"] == "json_schema"
    assert msgs.kwargs["fallbacks"] == "default"


def test_read_label_errors(authed, monkeypatch):
    monkeypatch.setattr(get_settings(), "anthropic_api_key", "")
    r = authed.post("/api/read-label", files={"file": ("label.jpg", _jpeg((10, 10)), "image/jpeg")})
    assert r.status_code == 422 and "Couldn't find a barcode" in r.json()["detail"]

    _fake(monkeypatch, RESULT)
    r = authed.post("/api/read-label", files={"file": ("x.jpg", b"not an image", "image/jpeg")})
    assert r.status_code == 422 and "isn't a photo" in r.json()["detail"]

    _fake(monkeypatch, "", stop="refusal")
    r = authed.post("/api/read-label", files={"file": ("label.jpg", _jpeg((10, 10)), "image/jpeg")})
    assert r.status_code == 422 and "declined" in r.json()["detail"]


def test_read_label_requires_login(client):
    assert client.post("/api/read-label", files={"file": ("l.jpg", b"x", "image/jpeg")}).status_code == 401


def _barcode_photo(text):
    z = zxingcpp.write_barcode_to_image(zxingcpp.create_barcode(text, zxingcpp.BarcodeFormat.Code128), scale=4)
    h, w = z.shape[:2]
    canvas = Image.new("RGB", (1600, 1000), (230, 230, 225))
    canvas.paste(Image.frombytes("L", (w, h), bytes(memoryview(z))).convert("RGB"), (300, 400))
    b = io.BytesIO()
    canvas.save(b, "PNG")
    return b.getvalue()


def test_barcode_pcgs_confirmed_without_claude(authed, monkeypatch):
    msgs = _fake(monkeypatch, RESULT)
    monkeypatch.setattr(get_settings(), "pcgs_api_token", "tok")
    calls = []

    def fake_lookup(service, cert, check_cac=True):
        calls.append(cert)
        if cert != "43215678":
            raise label_reader.lookups.LookupError("not found")
        return LookupResult(grading_service="PCGS", cert_number=cert, year=1884, mint_mark="CC", grade_prefix="MS",
                            grade=64, description="1884-CC $1 MS64", image_urls=["https://images.pcgs.com/x.jpg"])

    monkeypatch.setattr(label_reader.lookups, "lookup", fake_lookup)
    r = authed.post("/api/read-label", files={"file": ("label.png", _barcode_photo("43215678"), "image/png")})
    assert r.status_code == 200, r.text
    d = r.json()
    assert (d["source"], d["grading_service"], d["cert_number"], d["year"], d["mint_mark"], d["grade"]) == (
        "barcode", "PCGS", "43215678", 1884, "CC", 64)
    assert d["lookup"]["image_urls"] == ["https://images.pcgs.com/x.jpg"]
    assert calls == ["43215678"] and msgs.kwargs is None  # Claude never called


def test_barcode_ngc(authed, monkeypatch):
    msgs = _fake(monkeypatch, RESULT)
    r = authed.post("/api/read-label", files={"file": ("label.png", _barcode_photo("6543210-007"), "image/png")})
    d = r.json()
    assert (d["source"], d["grading_service"], d["cert_number"]) == ("barcode", "NGC", "6543210-007")
    assert msgs.kwargs is None


def test_unmatched_barcode_falls_back_to_claude(authed, monkeypatch):
    msgs = _fake(monkeypatch, RESULT)
    monkeypatch.setattr(get_settings(), "pcgs_api_token", "tok")

    def not_found(*a, **kw):
        raise label_reader.lookups.LookupError("not found")

    monkeypatch.setattr(label_reader.lookups, "lookup", not_found)
    d = authed.post("/api/read-label", files={"file": ("label.png", _barcode_photo("99999999"), "image/png")}).json()
    assert d["source"] == "claude" and msgs.kwargs is not None

    monkeypatch.setattr(get_settings(), "anthropic_api_key", "")
    r = authed.post("/api/read-label", files={"file": ("label.png", _barcode_photo("99999999"), "image/png")})
    assert r.status_code == 422 and "couldn't match it" in r.json()["detail"]


NGC_TEXT = """Verify NGC Certification
NGC Cert #: 6346547-009
1881 S $1 MS 62
Morgan Dollar
Pedigree: VAM-3
Grade: MS 62"""
IMG = ("https://ccg-imaging-ngc-coins-production.s3.amazonaws.com/1ba8ddce-270b-4b4a-b00e-0561b256781a/"
       "NGC6346547-009_OBV@500x722.jpg")


def test_ngc_page_without_claude(authed, monkeypatch):
    monkeypatch.setattr(get_settings(), "anthropic_api_key", "")
    other = IMG.replace("6346547-009", "1111111-001")
    r = authed.post("/api/ngc-page", json={"cert": "6346547-009", "grade": "62", "text": NGC_TEXT,
                                           "images": ["https://evil.example.com/x.jpg", other, IMG]})
    assert r.status_code == 200, r.text
    d = r.json()
    rd = d["reading"]
    assert (rd["grading_service"], rd["cert_number"], rd["year"], rd["mint_mark"], rd["grade_prefix"], rd["grade"]) == (
        "NGC", "6346547-009", 1881, "S", "MS", 62)
    assert d["photos"]["urls"][0].endswith("NGC6346547-009_OBV.jpg")  # the other coin's photo is ignored


def test_ngc_page_with_claude_keeps_url_cert(authed, monkeypatch):
    msgs = _fake(monkeypatch, RESULT)  # Claude's answer names a PCGS cert; the page address wins
    d = authed.post("/api/ngc-page", json={"cert": "6346547-009", "grade": "62", "text": NGC_TEXT}).json()
    assert (d["reading"]["grading_service"], d["reading"]["cert_number"], d["reading"]["year"]) == ("NGC", "6346547-009", 1881)
    assert "NGC certification" in msgs.kwargs["messages"][0]["content"][0]["text"]
    assert d["photos"]["urls"] == []
    assert authed.post("/api/ngc-page", json={"cert": "../x", "text": ""}).status_code == 400
