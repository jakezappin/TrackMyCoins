"""NGC photo links (S3) and photo downscaling."""

import io

import pytest
from PIL import Image

from app.services import ngc_images, photos

LINK = ("https://ccg-imaging-ngc-coins-production.s3.amazonaws.com/1ba8ddce-270b-4b4a-b00e-0561b256781a/"
        "NGC6521048-002_REV@500x722.jpg")


def test_parse_any_side_or_size():
    info = ngc_images.parse(LINK)
    base = "https://ccg-imaging-ngc-coins-production.s3.amazonaws.com/1ba8ddce-270b-4b4a-b00e-0561b256781a/NGC6521048-002"
    assert info["cert_number"] == "6521048-002"
    assert info["urls"] == [f"{base}_OBV.jpg", f"{base}_REV.jpg"]
    assert ngc_images.parse(LINK.replace("@500x722", "").replace("REV", "OBV"))["urls"] == info["urls"]


@pytest.mark.parametrize("bad", [
    "", "https://www.ngccoin.com/certlookup/6521048-002/62/",
    "https://evil.example.com/1ba8ddce-270b-4b4a-b00e-0561b256781a/NGC6521048-002_OBV.jpg",
    "https://ccg-imaging-ngc-coins-production.s3.amazonaws.com/../NGC6521048-002_OBV.jpg",
])
def test_parse_rejects(bad):
    with pytest.raises(ngc_images.NgcImageError):
        ngc_images.parse(bad)


def test_endpoint(authed, monkeypatch):
    monkeypatch.setattr(ngc_images, "resolve", lambda link: {**ngc_images.parse(link)})
    import app.routers.pricing as pr
    monkeypatch.setattr(pr.ngc_images_service, "resolve", lambda link: {**ngc_images.parse(link)})
    d = authed.get("/api/ngc-images", params={"link": LINK}).json()
    assert d["cert_number"] == "6521048-002" and len(d["urls"]) == 2
    assert authed.get("/api/ngc-images", params={"link": "nope"}).status_code == 400


def test_big_photos_are_shrunk(tmp_path, monkeypatch):
    monkeypatch.setattr(photos.settings, "photo_dir", tmp_path)
    big, small = io.BytesIO(), io.BytesIO()
    Image.new("RGB", (4000, 3000), (120, 130, 140)).save(big, "PNG")
    Image.new("RGB", (800, 600), (120, 130, 140)).save(small, "PNG")
    name, ctype = photos.save_bytes(1, big.getvalue(), "image/png")
    assert ctype == "image/jpeg" and name.endswith(".jpg")
    assert max(Image.open(photos.photo_path(1, name)).size) == photos.MAX_SIDE
    name, ctype = photos.save_bytes(1, small.getvalue(), "image/png")
    assert ctype == "image/png"  # small photos are kept as they are
