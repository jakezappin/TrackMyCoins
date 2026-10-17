"""One-time: compress photos stored before compression was added, strip their metadata (e.g. phone GPS location)
and make thumbnails. Every photo is re-saved, even ones already small, so no location data is left behind.

Run on the server:  python -m scripts.compress_photos   (add --dry-run to only report)
"""

import sys

from app.db import SessionLocal
from app.models import CoinPhoto
from app.services import photos


def main(dry_run: bool = False) -> None:
    db = SessionLocal()
    before = after = done = 0
    for p in db.query(CoinPhoto).all():
        path = photos.photo_path(p.coin_id, p.file_name)
        if not path.exists():
            continue
        data = path.read_bytes()
        before += len(data)
        try:
            new, ctype = photos._compress(data, p.content_type or "image/jpeg")
        except photos.PhotoError:
            after += len(data)
            continue
        after += len(new)
        if dry_run:
            continue
        name = f"{path.stem}{photos.ALLOWED_TYPES[ctype]}"
        new_path = photos.photo_path(p.coin_id, name)
        new_path.write_bytes(new)
        if new_path != path:
            path.unlink()
            photos.thumb_path(p.coin_id, p.file_name).unlink(missing_ok=True)
        p.file_name, p.content_type = name, ctype
        photos.make_thumb(p.coin_id, name)
        done += 1
    db.commit()
    mb = lambda n: f"{n / 1e6:.1f} MB"  # noqa: E731
    print(f"{'Would compress' if dry_run else 'Compressed'} {done if not dry_run else 'all'} photos: {mb(before)} -> {mb(after)}")


if __name__ == "__main__":
    main(dry_run="--dry-run" in sys.argv)
