"""Photo storage on local disk under data/photos/<coin_id>/."""

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


def save_bytes(coin_id: int, data: bytes, content_type: str) -> str:
    content_type = content_type.split(";")[0].strip().lower()
    ext = ALLOWED_TYPES.get(content_type)
    if ext is None:
        raise PhotoError(f"Unsupported image type: {content_type or 'unknown'}")
    if len(data) > settings.max_photo_bytes:
        raise PhotoError("Image is too large")
    d = coin_dir(coin_id)
    d.mkdir(parents=True, exist_ok=True)
    name = f"{uuid.uuid4().hex}{ext}"
    (d / name).write_bytes(data)
    return name


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
