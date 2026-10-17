"""Photo storage on local disk under data/photos/<coin_id>/."""

import io
import shutil
import uuid
from pathlib import Path
from urllib.parse import urlparse

import httpx

from ..config import get_settings
from ..images import ImageTooLarge, open_image

settings = get_settings()

ALLOWED_TYPES = {
    "image/jpeg": ".jpg",
    "image/png": ".png",
    "image/webp": ".webp",
    "image/heic": ".heic",
    "image/gif": ".gif",
}

# Hosts we will download lookup images from. Only grading-service image hosts.
IMPORT_HOST_SUFFIXES = (
    "pcgs.com",
    "ngccoin.com",
    "ngc.com",
    "anacs.com",
    "caccoin.com",
    "cacgrading.com",
    "collectors.com",
    "cloudfront.net",  # PCGS image CDN
    "ccg-imaging-ngc-coins-production.s3.amazonaws.com",  # NGC's photos (only this bucket)
)


class PhotoError(ValueError):
    pass


def coin_dir(coin_id: int) -> Path:
    return settings.photo_dir / str(coin_id)


MAX_SIDE = 2000  # plenty for a coin; phone and NGC full-size photos (2-5 MB) come out at a few hundred KB
THUMB_SIDE = 360  # list and grid thumbnails (sharp at 2x on the 40-190px spots they're shown)
JPEG_QUALITY = 84
THUMB_QUALITY = 76


def _open(data: bytes, side: int):
    return open_image(data, max_side=side)


def _to_jpeg(im, side: int, quality: int) -> bytes:
    """Upright, at most `side` px, flattened onto white if transparent, saved without metadata (no GPS)."""
    from PIL import Image, ImageOps

    im = ImageOps.exif_transpose(im)
    if im.mode in ("RGBA", "LA", "P"):
        im = im.convert("RGBA")
        bg = Image.new("RGB", im.size, (255, 255, 255))
        bg.paste(im, mask=im.getchannel("A"))
        im = bg
    else:
        im = im.convert("RGB")
    im.thumbnail((side, side))
    out = io.BytesIO()
    im.save(out, "JPEG", quality=quality, optimize=True, progressive=True)
    return out.getvalue()


def _compress(data: bytes, content_type: str) -> tuple[bytes, str]:
    """Every photo is stored as an optimized JPEG (animated GIFs are kept as they are)."""
    try:
        with _open(data, MAX_SIDE) as im:
            if content_type == "image/gif" and getattr(im, "is_animated", False):
                return data, content_type
            return _to_jpeg(im, MAX_SIDE, JPEG_QUALITY), "image/jpeg"
    except ImageTooLarge as e:
        raise PhotoError(str(e)) from e
    except Exception as e:
        raise PhotoError("That file isn't a photo we can read. Try a JPEG, PNG or HEIC.") from e


def save_bytes(coin_id: int, data: bytes, content_type: str) -> tuple[str, str]:
    """Store a photo (compressed) and its thumbnail; returns (file name, content type actually stored)."""
    content_type = content_type.split(";")[0].strip().lower()
    if content_type == "image/heif":
        content_type = "image/heic"
    if content_type not in ALLOWED_TYPES:
        raise PhotoError(f"Unsupported image type: {content_type or 'unknown'}")
    if len(data) > settings.max_photo_bytes:
        raise PhotoError("Image is too large")
    data, content_type = _compress(data, content_type)
    d = coin_dir(coin_id)
    d.mkdir(parents=True, exist_ok=True)
    name = f"{uuid.uuid4().hex}{ALLOWED_TYPES[content_type]}"
    (d / name).write_bytes(data)
    make_thumb(coin_id, name)
    return name, content_type


def file_for(photo, size: str) -> tuple[Path, str] | None:
    """(path, content type) of a stored photo or its thumbnail (made on first request for older photos)."""
    if size == "thumb":
        t = thumb_path(photo.coin_id, photo.file_name)
        if t.exists() or make_thumb(photo.coin_id, photo.file_name):
            return t, "image/jpeg"
    path = photo_path(photo.coin_id, photo.file_name)
    return (path, photo.content_type) if path.exists() else None


def thumb_path(coin_id: int, file_name: str) -> Path:
    return coin_dir(coin_id) / f"{Path(file_name).stem}.thumb.jpg"


def make_thumb(coin_id: int, file_name: str) -> Path | None:
    """Create (or recreate) the thumbnail; None if the photo can't be read."""
    src, dst = photo_path(coin_id, file_name), thumb_path(coin_id, file_name)
    try:
        with _open(src.read_bytes(), THUMB_SIDE) as im:
            dst.write_bytes(_to_jpeg(im, THUMB_SIDE, THUMB_QUALITY))
    except Exception:
        return None
    return dst


def photo_path(coin_id: int, file_name: str) -> Path:
    return coin_dir(coin_id) / Path(file_name).name


def delete_photo_file(coin_id: int, file_name: str) -> None:
    photo_path(coin_id, file_name).unlink(missing_ok=True)
    thumb_path(coin_id, file_name).unlink(missing_ok=True)


def delete_coin_photo_files(coin_id: int) -> None:
    shutil.rmtree(coin_dir(coin_id), ignore_errors=True)


def _host_allowed(url: str) -> bool:
    parsed = urlparse(url)
    host = (parsed.hostname or "").lower()
    return parsed.scheme == "https" and any(host == s or host.endswith("." + s) for s in IMPORT_HOST_SUFFIXES)


def download_image(url: str) -> tuple[bytes, str]:
    if not _host_allowed(url):
        raise PhotoError(f"Not an allowed image host: {url}")
    limit = settings.max_photo_bytes
    with httpx.Client(timeout=20, follow_redirects=False) as client:
        with client.stream("GET", url, headers={"User-Agent": "coin-app/0.1"}) as r:
            if r.status_code != 200:
                raise PhotoError(f"Could not download image ({r.status_code}): {url}")
            if int(r.headers.get("content-length") or 0) > limit:
                raise PhotoError("That image is too large to import")
            data = bytearray()
            for chunk in r.iter_bytes():  # stop early instead of reading an endless or huge body
                data += chunk
                if len(data) > limit:
                    raise PhotoError("That image is too large to import")
            return bytes(data), r.headers.get("content-type", "")
