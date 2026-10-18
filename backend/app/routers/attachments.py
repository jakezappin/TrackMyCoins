from urllib.parse import quote

from fastapi import APIRouter, Depends, HTTPException, UploadFile, status
from fastapi.responses import FileResponse
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..auth import current_user
from ..config import get_settings
from ..db import get_db
from ..models import Coin, CoinAttachment, User
from ..services import attachments as store
from .coins import get_owned_coin

router = APIRouter(prefix="/api", tags=["attachments"])
settings = get_settings()


def _out(a: CoinAttachment) -> dict:
    return {"id": a.id, "name": a.original_name, "content_type": a.content_type, "size": a.size_bytes,
            "created_at": a.created_at, "url": f"/api/attachments/{a.id}"}


def _owned(db: Session, user: User, attachment_id: int) -> CoinAttachment:
    a = db.get(CoinAttachment, attachment_id)
    if a is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "File not found")
    coin = db.get(Coin, a.coin_id)
    if coin is None or coin.user_id != user.id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "File not found")
    return a


def _list(db: Session, coin_id: int) -> list[dict]:
    rows = db.scalars(select(CoinAttachment).where(CoinAttachment.coin_id == coin_id).order_by(CoinAttachment.created_at))
    return [_out(a) for a in rows]


@router.get("/coins/{inventory_number}/attachments")
def list_attachments(inventory_number: str, db: Session = Depends(get_db), user: User = Depends(current_user)):
    coin = get_owned_coin(db, user, inventory_number)
    return _list(db, coin.id)


@router.post("/coins/{inventory_number}/attachments")
async def upload_attachments(
    inventory_number: str, files: list[UploadFile], db: Session = Depends(get_db), user: User = Depends(current_user)
):
    coin = get_owned_coin(db, user, inventory_number)
    have = len(_list(db, coin.id))
    if have + len(files) > settings.max_attachments_per_coin:
        raise HTTPException(status.HTTP_400_BAD_REQUEST,
                            f"A coin can have at most {settings.max_attachments_per_coin} files (it has {have}).")
    saved: list[str] = []
    for f in files:
        data = await f.read(settings.max_attachment_bytes + 1)
        try:
            stored, name, ctype, size = store.save(coin.id, data, f.content_type or "", f.filename)
        except store.AttachmentError as e:
            for done in saved:  # nothing is kept from a failed upload
                store.delete_file(coin.id, done)
            raise HTTPException(status.HTTP_400_BAD_REQUEST, f"{f.filename}: {e}")
        saved.append(stored)
        db.add(CoinAttachment(coin_id=coin.id, file_name=stored, original_name=name, content_type=ctype, size_bytes=size))
    db.commit()
    return _list(db, coin.id)


@router.get("/attachments/{attachment_id}")
def get_attachment(attachment_id: int, db: Session = Depends(get_db), user: User = Depends(current_user)):
    a = _owned(db, user, attachment_id)
    path = store.path_for(a.coin_id, a.file_name)
    if not path.exists():
        raise HTTPException(status.HTTP_404_NOT_FOUND, "File missing")
    # Shown in the browser (PDF viewer / image), saved under its original name.
    return FileResponse(
        path,
        media_type=a.content_type,
        headers={
            "Content-Disposition": f"inline; filename*=UTF-8''{quote(a.original_name)}",
            "Cache-Control": "private, max-age=86400",
            "X-Content-Type-Options": "nosniff",
        },
    )


@router.delete("/attachments/{attachment_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_attachment(attachment_id: int, db: Session = Depends(get_db), user: User = Depends(current_user)):
    a = _owned(db, user, attachment_id)
    store.delete_file(a.coin_id, a.file_name)
    db.delete(a)
    db.commit()
