"""Receipts and documents stored with a coin, next to the photos (data/attachments/<coin_id>/)."""

import re
import shutil
import uuid
from pathlib import Path

from ..config import get_settings
from . import photos

settings = get_settings()

IMAGE_TYPES = {"image/jpeg", "image/png", "image/webp", "image/heic", "image/heif"}
PDF = "application/pdf"


class AttachmentError(ValueError):
    pass


def base_dir() -> Path:
    return settings.photo_dir.parent / "attachments"


def coin_dir(coin_id: int) -> Path:
    return base_dir() / str(coin_id)


def path_for(coin_id: int, file_name: str) -> Path:
    return coin_dir(coin_id) / Path(file_name).name


def clean_name(name: str | None, ext: str) -> str:
    """A safe display/download name: no folders or odd characters, sensible extension."""
    base = Path(name or "document").stem
    base = re.sub(r"[^\w .()-]+", "_", base).strip(" ._") or "document"
    return f"{base[:120]}{ext}"


def save(coin_id: int, data: bytes, content_type: str, original_name: str | None) -> tuple[str, str, str, int]:
    """Store a document; returns (stored name, display name, content type, size). Photos of receipts are compressed
    like coin photos (and lose their location data); PDFs are kept as they are."""
    content_type = (content_type or "").split(";")[0].strip().lower()
    if len(data) > settings.max_attachment_bytes:
        raise AttachmentError(f"That file is too large ({settings.max_attachment_bytes // (1024 * 1024)} MB max).")
    if content_type == PDF or (original_name or "").lower().endswith(".pdf"):
        if not data.startswith(b"%PDF"):
            raise AttachmentError("That doesn't look like a PDF.")
        content_type, ext = PDF, ".pdf"
    elif content_type in IMAGE_TYPES:
        try:
            data, content_type = photos._compress(data, "image/heic" if content_type == "image/heif" else content_type)
        except photos.PhotoError as e:
            raise AttachmentError(str(e)) from e
        ext = ".jpg"
    else:
        raise AttachmentError("Upload a PDF or a photo (JPEG, PNG, HEIC).")
    d = coin_dir(coin_id)
    d.mkdir(parents=True, exist_ok=True)
    stored = f"{uuid.uuid4().hex}{ext}"
    (d / stored).write_bytes(data)
    return stored, clean_name(original_name, ext), content_type, len(data)


def delete_file(coin_id: int, file_name: str) -> None:
    path_for(coin_id, file_name).unlink(missing_ok=True)


def delete_coin_files(coin_id: int) -> None:
    shutil.rmtree(coin_dir(coin_id), ignore_errors=True)
