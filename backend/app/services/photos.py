"""Photo storage on local disk under data/photos/<coin_id>/."""

import io
import shutil
import uuid
from pathlib import Path
from urllib.parse import urlparse

import httpx

from ..config import get_settings

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
    "cloudfront.net",
    "amazonaws.com",
)


class PhotoError(ValueError):
    pass


def coin_dir(coin_id: int) -> Path:
    return settings.photo_dir / str(coin_id)


MAX_SIDE = 2000  # keeps phone and NGC full-size photos (~2-5 MB) to a few hundred KB


def _shrink(data: bytes, content_type: str) -> tuple[bytes, str] | None:
    """Re-encode HEIC or oversized photos as a JPEG at most MAX_SIDE px; None to keep the original."""
    import pillow_heif
    from PIL import Image, ImageOps

    pillow_heif.register_heif_opener()
    try:
        with Image.open(io.BytesIO(data)) as im:
            if content_type != "image/heic" and max(im.size) <= MAX_SIDE:
                return None
            if content_type == "image/gif" and getattr(im, "is_animated", False):
                return None
            im = ImageOps.exif_transpose(im).convert("RGB")
            im.thumbnail((MAX_SIDE, MAX_SIDE))
            out = io.BytesIO()
            im.save(out, "JPEG", quality=88)
    except Exception as e:
        if content_type == "image/heic":
            raise PhotoError("Couldn't read that HEIC photo") from e
        return None  # store as-is; the browser may still show it
    return out.getvalue(), "image/jpeg"


def save_bytes(coin_id: int, data: bytes, content_type: str) -> tuple[str, str]:
    """Store a photo; returns (file name, content type actually stored)."""
    content_type = content_type.split(";")[0].strip().lower()
    if content_type == "image/heif":
        content_type = "image/heic"
    ext = ALLOWED_TYPES.get(content_type)
    if ext is None:
        raise PhotoError(f"Unsupported image type: {content_type or 'unknown'}")
    if len(data) > settings.max_photo_bytes:
        raise PhotoError("Image is too large")
    shrunk = _shrink(data, content_type)
    if shrunk:
        data, content_type = shrunk
        ext = ".jpg"
    d = coin_dir(coin_id)
    d.mkdir(parents=True, exist_ok=True)
    name = f"{uuid.uuid4().hex}{ext}"
    (d / name).write_bytes(data)
    return name, content_type


def photo_path(coin_id: int, file_name: str) -> Path:
    return coin_dir(coin_id) / Path(file_name).name


def delete_photo_file(coin_id: int, file_name: str) -> None:
    photo_path(coin_id, file_name).unlink(missing_ok=True)


def delete_coin_photo_files(coin_id: int) -> None:
    shutil.rmtree(coin_dir(coin_id), ignore_errors=True)


def _host_allowed(url: str) -> bool:
    parsed = urlparse(url)
    host = (parsed.hostname or "").lower()
    return parsed.scheme == "https" and any(host == s or host.endswith("." + s) for s in IMPORT_HOST_SUFFIXES)


def download_image(url: str) -> tuple[bytes, str]:
    if not _host_allowed(url):
        raise PhotoError(f"Not an allowed image host: {url}")
    with httpx.Client(timeout=20, follow_redirects=False) as client:
        r = client.get(url, headers={"User-Agent": "coin-app/0.1"})
    if r.status_code != 200:
        raise PhotoError(f"Could not download image ({r.status_code}): {url}")
    return r.content, r.headers.get("content-type", "")
