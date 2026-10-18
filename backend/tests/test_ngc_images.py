"""NGC photo links (S3) and photo downscaling."""

import io

import pytest
from PIL import Image

from app.services import ngc_images, photos

LINK = ("https://ccg-imaging-ngc-coins-production.s3.amazonaws.com/1ba8ddce-270b-4b4a-b00e-0561b256781a/"
        "NGC6521048-002_REV@500x722.jpg")


def test_parse_keeps_lowercase_names_and_any_preview_size():
    link = ("https://ccg-imaging-ngc-coins-production.s3.amazonaws.com/d414aff8-0d7b-4a44-abb7-bfdddd6678e8/"
            "NGC6573699-002_obv@500x715.jpg")
    info = ngc_images.parse(link)
    base = "https://ccg-imaging-ngc-coins-production.s3.amazonaws.com/d414aff8-0d7b-4a44-abb7-bfdddd6678e8/NGC6573699-002"
    assert info["cert_number"] == "6573699-002"
    assert info["urls"] == [f"{base}_obv.jpg", f"{base}_rev.jpg"]
    assert info["previews"] == [link, f"{base}_rev.jpg"]


def test_parse_any_side_or_size():
    info = ngc_images.parse(LINK)
    base = "https://ccg-imaging-ngc-coins-production.s3.amazonaws.com/1ba8ddce-270b-4b4a-b00e-0561b256781a/NGC6521048-002"
    assert info["cert_number"] == "6521048-002"
    assert info["urls"] == [f"{base}_OBV.jpg", f"{base}_REV.jpg"]
    assert ngc_images.parse(LINK.replace("@500x722", "").replace("REV", "OBV"))["urls"] == info["urls"]


def test_parse_newer_folder_ids_and_uppercase_jpg():
    """Newer photos sit in 40-character folders, with .JPG and an @200X300 preview size."""
    link = ("https://ccg-imaging-ngc-coins-production.s3.amazonaws.com/d7d9afcb81fdf5faaebc316e7e0b934fc1a0db03/"
            "NGC3871027-001_OBV@200X300.JPG")
    info = ngc_images.parse(link)
    base = "https://ccg-imaging-ngc-coins-production.s3.amazonaws.com/d7d9afcb81fdf5faaebc316e7e0b934fc1a0db03/NGC3871027-001"
    assert info["cert_number"] == "3871027-001"
    assert info["urls"] == [f"{base}_OBV.JPG", f"{base}_REV.JPG"]


@pytest.mark.parametrize("bad", [
    "", "https://www.ngccoin.com/certlookup/6521048-002/62/",
    "https://evil.example.com/1ba8ddce-270b-4b4a-b00e-0561b256781a/NGC6521048-002_OBV.jpg",
    "https://ccg-imaging-ngc-coins-production.s3.amazonaws.com/../NGC6521048-002_OBV.jpg",
])
def test_parse_rejects(bad):
    with pytest.raises(ngc_images.NgcImageError):
        ngc_images.parse(bad)


def test_endpoint(authed, monkeypatch):
    import app.routers.pricing as pr
    monkeypatch.setattr(pr.ngc_images_service, "resolve", lambda link: {**ngc_images.parse(link)})
    d = authed.get("/api/ngc-images", params={"link": LINK}).json()
    assert d["cert_number"] == "6521048-002" and len(d["urls"]) == 2
    assert authed.get("/api/ngc-images", params={"link": "nope"}).status_code == 400


def test_photos_compressed_with_thumbnail_and_no_gps(tmp_path, monkeypatch):
    monkeypatch.setattr(photos.settings, "photo_dir", tmp_path)
    exif = Image.Exif()
    exif[0x8825] = {2: (40.0, 26.0, 46.0), 1: "N"}  # GPS info, as phones add
    big, small = io.BytesIO(), io.BytesIO()
    Image.new("RGB", (4000, 3000), (120, 130, 140)).save(big, "JPEG", quality=98, exif=exif)
    Image.new("RGBA", (800, 600), (120, 130, 140, 128)).save(small, "PNG")

    name, ctype = photos.save_bytes(1, big.getvalue(), "image/jpeg")
    stored = Image.open(photos.photo_path(1, name))
    assert ctype == "image/jpeg" and max(stored.size) == photos.MAX_SIDE
    assert 0x8825 not in stored.getexif()  # location stripped
    assert photos.photo_path(1, name).stat().st_size < len(big.getvalue())
    assert max(Image.open(photos.thumb_path(1, name)).size) == photos.THUMB_SIDE

    name, ctype = photos.save_bytes(1, small.getvalue(), "image/png")  # transparent PNG -> JPEG on white
    assert ctype == "image/jpeg" and name.endswith(".jpg") and Image.open(photos.photo_path(1, name)).size == (800, 600)

    photos.delete_photo_file(1, name)
    assert not photos.thumb_path(1, name).exists()


def test_huge_images_refused_before_decoding(tmp_path, monkeypatch):
    import pytest as _pytest

    from app.images import ImageTooLarge, open_image
    from app.services import label_reader

    monkeypatch.setattr(photos.settings, "photo_dir", tmp_path)
    b = io.BytesIO()
    Image.new("L", (13000, 13000)).save(b, "PNG")  # tiny file, ~500 MB if decoded in color
    with _pytest.raises(ImageTooLarge):
        open_image(b.getvalue())
    with _pytest.raises(photos.PhotoError, match="too large"):
        photos.save_bytes(1, b.getvalue(), "image/png")
    with _pytest.raises(label_reader.LabelError, match="too large"):
        label_reader.read_label(b.getvalue())


def test_downloads_capped(monkeypatch):
    import httpx
    import pytest as _pytest

    big = b"\xff" * (photos.settings.max_photo_bytes + 10)
    real = httpx.Client
    monkeypatch.setattr(photos.httpx, "Client", lambda **kw: real(transport=httpx.MockTransport(
        lambda req: httpx.Response(200, content=big, headers={"content-type": "image/jpeg"})), **kw))
    with _pytest.raises(photos.PhotoError, match="too large"):
        photos.download_image("https://ccg-imaging-ngc-coins-production.s3.amazonaws.com/x/NGC1-001_OBV.jpg")
