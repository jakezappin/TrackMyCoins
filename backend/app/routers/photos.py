from typing import Literal

from fastapi import APIRouter, Depends, HTTPException, UploadFile, status
from fastapi.responses import FileResponse
from sqlalchemy.orm import Session

from ..auth import current_user
from ..config import get_settings
from ..db import get_db
from ..models import CoinPhoto, User
from ..schemas import CoinDetail, PhotoImportIn, PhotoReorderIn
from ..services import lookups, pcgs_cache
from ..services import photos as store
from ..services.quota import QuotaExceeded
from ..services.coins import coin_detail
from .coins import get_owned_coin

router = APIRouter(prefix="/api", tags=["photos"])
settings = get_settings()


def _check_room(current: int, adding: int) -> None:
    if current + adding > settings.max_photos_per_coin:
        raise HTTPException(
            status.HTTP_400_BAD_REQUEST,
            f"A coin can have at most {settings.max_photos_per_coin} photos (it has {current}).",
        )


def _get_owned_photo(db: Session, user: User, photo_id: int) -> CoinPhoto:
    photo = db.get(CoinPhoto, photo_id)
    if photo is None or photo.coin.user_id != user.id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Photo not found")
    return photo


@router.post("/coins/{inventory_number}/photos", response_model=CoinDetail)
async def upload_photos(
    inventory_number: str, files: list[UploadFile], db: Session = Depends(get_db), user: User = Depends(current_user)
):
    coin = get_owned_coin(db, user, inventory_number)
    _check_room(len(coin.photos), len(files))
    order = len(coin.photos)
    saved: list[str] = []
    limit = get_settings().max_photo_bytes
    for f in files:
        data = await f.read(limit + 1)  # never more than the limit in memory; save_bytes refuses the extra byte
        try:
            name, ctype = store.save_bytes(coin.id, data, f.content_type or "")
        except store.PhotoError as e:
            for done in saved:  # nothing is kept from a failed upload
                store.delete_photo_file(coin.id, done)
            raise HTTPException(status.HTTP_400_BAD_REQUEST, f"{f.filename}: {e}")
        saved.append(name)
        db.add(CoinPhoto(coin_id=coin.id, file_name=name, content_type=ctype, sort_order=order))
        order += 1
    db.commit()
    db.refresh(coin)
    return coin_detail(coin)


@router.post("/coins/{inventory_number}/photos/import", response_model=CoinDetail)
def import_photos(
    inventory_number: str, body: PhotoImportIn, db: Session = Depends(get_db), user: User = Depends(current_user)
):
    """Download images found by a cert lookup and attach them to the coin."""
    coin = get_owned_coin(db, user, inventory_number)
    urls = body.urls[: settings.max_photos_per_coin - len(coin.photos)]
    order = len(coin.photos)
    errors = []
    for url in urls:
        try:
            data, ctype = store.download_image(url)
            name, ctype = store.save_bytes(coin.id, data, ctype)
        except Exception as e:  # keep going; one bad image shouldn't block the rest
            errors.append(str(e))
            continue
        db.add(CoinPhoto(coin_id=coin.id, file_name=name, content_type=ctype, sort_order=order, source="lookup"))
        order += 1
    db.commit()
    db.refresh(coin)
    if errors and len(errors) == len(urls):
        raise HTTPException(status.HTTP_502_BAD_GATEWAY, "Could not import photos: " + "; ".join(errors))
    return coin_detail(coin)


@router.post("/coins/{inventory_number}/pcgs-check")
def pcgs_check(inventory_number: str, db: Session = Depends(get_db), user: User = Depends(current_user)):
    """Look up a PCGS coin's cert at PCGS (for coins imported or added without one): save PCGS's photos, and fill in
    what the coin is missing (PCGS #, designation, VAM, variety). Says what it did, and if PCGS's grade differs."""
    coin = get_owned_coin(db, user, inventory_number)
    if coin.grading_service != "PCGS" or not coin.cert_number:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "This needs a PCGS coin with a cert number.")
    try:
        # A stored lookup without photos is asked again: PCGS may have imaged the coin since.
        stored = pcgs_cache.get(pcgs_cache.cert_key(lookups.clean_cert(coin.cert_number)))
        r = lookups.lookup("PCGS", coin.cert_number, user_id=user.id, fresh=stored is not None and not stored.get("image_urls"))
    except QuotaExceeded as e:
        raise HTTPException(status.HTTP_429_TOO_MANY_REQUESTS, str(e)) from e
    except lookups.LookupError as e:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, str(e)) from e
    except Exception as e:  # network trouble
        raise HTTPException(status.HTTP_502_BAD_GATEWAY, f"Couldn't reach PCGS: {e}") from e

    notes: list[str] = []
    filled = []
    for field, label in (("pcgs_number", "PCGS #"), ("strike_designation", "designation"), ("vam", "VAM"), ("variety", "variety")):
        value = getattr(r, field, None)
        if value and not getattr(coin, field):
            setattr(coin, field, value)
            filled.append(f"{label} {value}")
    if r.raw and not coin.lookup_raw:
        coin.lookup_raw = r.raw
    if filled:
        notes.append("Filled in " + ", ".join(filled) + ".")
    theirs = f"{r.grade_prefix or ''}{r.grade or ''}"
    mine = f"{coin.grade_prefix or ''}{coin.grade or ''}"
    if r.grade and theirs != mine:
        notes.append(f"PCGS has this cert as {theirs}; this coin says {mine or 'no grade'}. Check it.")

    added = 0
    if any(p.source == "pcgs" for p in coin.photos):
        notes.append("PCGS's photos were already saved.")
    elif not r.image_urls:
        notes.append("PCGS has no photos for this cert.")
    else:
        order = len(coin.photos)
        for url in r.image_urls[: max(0, settings.max_photos_per_coin - len(coin.photos))]:
            try:
                data, ctype = store.download_image(url)
                name, ctype = store.save_bytes(coin.id, data, ctype)
            except Exception:  # keep going; one bad image shouldn't block the rest
                continue
            db.add(CoinPhoto(coin_id=coin.id, file_name=name, content_type=ctype, sort_order=order, source="pcgs"))
            order += 1
            added += 1
        notes.insert(0, f"Saved {added} photo{'' if added == 1 else 's'} from PCGS." if added else
                     "Couldn't save PCGS's photos.")
    db.commit()
    db.refresh(coin)
    return {"coin": coin_detail(coin), "message": " ".join(notes) or "Nothing new from PCGS.", "added": added}


@router.put("/coins/{inventory_number}/photos/order", response_model=CoinDetail)
def reorder_photos(
    inventory_number: str, body: PhotoReorderIn, db: Session = Depends(get_db), user: User = Depends(current_user)
):
    coin = get_owned_coin(db, user, inventory_number)
    by_id = {p.id: p for p in coin.photos}
    if set(body.photo_ids) != set(by_id):
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "photo_ids must list every photo of this coin")
    for i, pid in enumerate(body.photo_ids):
        by_id[pid].sort_order = i
    db.commit()
    db.refresh(coin)
    return coin_detail(coin)


@router.get("/photos/{photo_id}")
def get_photo(
    photo_id: int,
    size: Literal["full", "thumb"] = "full",
    db: Session = Depends(get_db),
    user: User = Depends(current_user),
):
    photo = _get_owned_photo(db, user, photo_id)
    found = store.file_for(photo, size)
    if found is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Photo file missing")
    # A photo id's file never changes (edits make new photos), so browsers can keep it.
    return FileResponse(found[0], media_type=found[1], headers={"Cache-Control": "private, max-age=2592000, immutable"})


@router.delete("/photos/{photo_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_photo(photo_id: int, db: Session = Depends(get_db), user: User = Depends(current_user)):
    photo = _get_owned_photo(db, user, photo_id)
    coin_id, file_name = photo.coin_id, photo.file_name
    db.delete(photo)
    db.commit()
    store.delete_photo_file(coin_id, file_name)
