import re

from fastapi import APIRouter, Depends, HTTPException, UploadFile, status
from fastapi.concurrency import run_in_threadpool
from pydantic import BaseModel, Field

from ..auth import current_user
from ..config import get_settings
from ..models import User
from ..services import label_reader, ngc_images

router = APIRouter(prefix="/api", tags=["label"])


@router.post("/read-label")
async def read_label(file: UploadFile, _: User = Depends(current_user)):
    """Read a slab label from a photo: service, cert number, date, grade, designation, variety, CAC."""
    data = await file.read(get_settings().max_photo_bytes + 1)
    if len(data) > get_settings().max_photo_bytes:
        raise HTTPException(status.HTTP_413_REQUEST_ENTITY_TOO_LARGE, "That photo is too large (15 MB max).")
    try:
        return await run_in_threadpool(label_reader.read_label, data)
    except label_reader.LabelError as e:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, str(e)) from e


class NgcPageIn(BaseModel):
    cert: str = Field(max_length=20)
    grade: str | None = Field(None, max_length=10)
    text: str = Field("", max_length=6000)
    images: list[str] = Field([], max_length=20)


@router.post("/ngc-page")
def ngc_page(body: NgcPageIn, _: User = Depends(current_user)):
    """Details and photos from an NGC cert page, sent by the "Add to TrackMyCoins" bookmark that runs in the
    collector's own browser while they view the page."""
    cert = body.cert.strip()
    if not re.fullmatch(r"\d{5,10}-\d{3}", cert):
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "That doesn't look like an NGC cert page.")
    reading = label_reader.read_ngc_page(cert, body.grade, body.text)
    photos = {"urls": [], "previews": []}
    for link in body.images:
        try:
            info = ngc_images.parse(link)
        except ngc_images.NgcImageError:
            continue
        if info["cert_number"] == cert:  # only this coin's photos
            photos = {"urls": info["urls"], "previews": info["previews"]}
            break
    return {"reading": reading, "photos": photos}
