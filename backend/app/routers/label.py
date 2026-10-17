from fastapi import APIRouter, Depends, HTTPException, UploadFile, status
from fastapi.concurrency import run_in_threadpool

from ..auth import current_user
from ..config import get_settings
from ..models import User
from ..services import label_reader

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
