"""Bulk import: preview a spreadsheet or a list of PCGS certs, then create the coins the user keeps."""

import httpx
from fastapi import APIRouter, Depends, Form, HTTPException, UploadFile, status
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from ..auth import current_user
from ..db import get_db
from ..models import Coin, Collection, CoinPhoto, User
from ..schemas import CoinFields
from ..series import BY_SLUG
from ..services import importer, lookups
from ..services import photos as store
from ..services.coins import _cert_key, find_duplicate_cert, next_inventory_number
from .coins import _validate
from .collections import get_owned_collection

router = APIRouter(prefix="/api/import", tags=["import"])

MAX_CERTS = 50  # each PCGS cert costs a lookup call (1,000 a day)


class ImportRow(BaseModel):
    row: int
    sheet: str = ""
    fields: dict
    valuation: dict = {}
    errors: list[str] = []
    description: str = ""
    lookup_raw: dict | None = None
    photo_urls: list[str] = []


class PreviewOut(BaseModel):
    collection_id: int
    rows: list[ImportRow]
    ok_count: int
    error_count: int


class CertsIn(BaseModel):
    collection_id: int
    certs: str = Field(max_length=20000)


class CommitIn(BaseModel):
    collection_id: int
    rows: list[ImportRow] = Field(max_length=importer.MAX_ROWS)
    import_photos: bool = True


def _collection(db: Session, user: User, collection_id: int) -> Collection:
    col = get_owned_collection(db, user, collection_id)
    series = BY_SLUG.get(col.coin_type.slug)
    if series and series.is_type_set:
        raise HTTPException(
            status.HTTP_422_UNPROCESSABLE_CONTENT,
            "Importing into a type set isn't supported yet, because each coin needs its series. Add these one at a time.",
        )
    return col


def _describe(f: dict) -> str:
    date = f"{f.get('year') or '?'}" + (f"-{f['mint_mark']}" if f.get("mint_mark") not in (None, "P") else "")
    grade = f"{f.get('grade_prefix') or ''}{f.get('grade') or ''}{'+' if f.get('grade_plus') else ''}"
    if f.get("strike_designation"):
        grade += f" {f['strike_designation']}"
    svc = "Raw" if f.get("grading_service") == "RAW" else f"{f.get('grading_service')} #{f.get('cert_number') or '?'}"
    return " ".join(x for x in (date, f.get("variety") or "", grade.strip(), "·", svc) if x)


def _check(db: Session, user: User, col: Collection, rows: list[ImportRow]) -> list[ImportRow]:
    """Same rules as adding a coin by hand, plus duplicate certs within the file."""
    seen: dict[tuple[str, str], int] = {}
    for r in rows:
        r.description = r.description or _describe(r.fields)
        if r.errors:
            continue
        try:
            data = _validate(CoinFields(**r.fields), col, col.coin_type)
        except HTTPException as e:
            r.errors.append(str(e.detail))
            continue
        except Exception as e:  # pydantic validation of edited fields
            r.errors.append(str(e))
            continue
        on_hand = data["sale_price"] is None and data["sale_date"] is None
        key = (data["grading_service"], _cert_key(data["cert_number"]))
        if on_hand and key[1] and data["grading_service"] != "RAW":
            dup = find_duplicate_cert(db, user.id, data["grading_service"], data["cert_number"])
            if dup:
                r.errors.append(f"Already in your collection as {dup.inventory_number}")
            elif key in seen:
                r.errors.append(f"Same cert as row {seen[key]}")
            else:
                seen[key] = r.row
    return rows


def _preview(db, user, col, rows: list[ImportRow]) -> PreviewOut:
    rows = _check(db, user, col, rows)
    bad = sum(1 for r in rows if r.errors)
    return PreviewOut(collection_id=col.id, rows=rows, ok_count=len(rows) - bad, error_count=bad)


@router.post("/preview", response_model=PreviewOut)
async def preview_file(
    file: UploadFile, collection_id: int = Form(...), db: Session = Depends(get_db), user: User = Depends(current_user)
):
    col = _collection(db, user, collection_id)
    data = await file.read(10 * 1024 * 1024 + 1)
    if len(data) > 10 * 1024 * 1024:
        raise HTTPException(status.HTTP_413_REQUEST_ENTITY_TOO_LARGE, "That file is too large (10 MB max).")
    try:
        raw_rows = importer.read_rows(file.filename or "", data)
    except importer.ImportError_ as e:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, str(e))
    if not raw_rows:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "No rows found. The first row should be column headings.")
    if len(raw_rows) > importer.MAX_ROWS:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, f"Import at most {importer.MAX_ROWS} rows at a time.")
    rows = []
    for sheet, n, raw in raw_rows:
        fields, valuation, errors = importer.row_to_fields(raw, sold_sheet=sheet == "Sold")
        rows.append(ImportRow(row=n, sheet=sheet, fields=fields, valuation=valuation, errors=errors))
    return _preview(db, user, col, rows)


@router.post("/certs", response_model=PreviewOut)
def preview_certs(body: CertsIn, db: Session = Depends(get_db), user: User = Depends(current_user)):
    """Look up a pasted list of PCGS certs."""
    col = _collection(db, user, body.collection_id)
    certs = importer.split_certs(body.certs)
    if not certs:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Paste one or more PCGS cert numbers.")
    if len(certs) > MAX_CERTS:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, f"Paste at most {MAX_CERTS} certs at a time (PCGS limits lookups).")
    rows = []
    for i, cert in enumerate(certs, start=1):
        try:
            r = lookups.lookup("PCGS", cert)
        except lookups.LookupError as e:
            rows.append(ImportRow(row=i, fields={"grading_service": "PCGS", "cert_number": cert}, errors=[str(e)],
                                  description=f"PCGS #{cert}"))
            if "limit" in str(e).lower():
                break
            continue
        except httpx.HTTPError as e:
            rows.append(ImportRow(row=i, fields={"grading_service": "PCGS", "cert_number": cert},
                                  errors=[f"PCGS lookup failed: {e}"], description=f"PCGS #{cert}"))
            continue
        fields = {
            "year": r.year, "mint_mark": r.mint_mark or "P", "grading_service": "PCGS", "cert_number": r.cert_number,
            "grade_prefix": r.grade_prefix, "grade": r.grade, "grade_plus": r.grade_plus, "grade_star": r.grade_star,
            "strike_designation": r.strike_designation, "vam": r.vam, "pcgs_number": r.pcgs_number,
            "cac": bool(r.cac), "cac_sticker": r.cac_sticker,
        }
        errors = [] if r.year else ["PCGS didn't return a date for this cert"]
        if not errors:
            try:
                fields = CoinFields(**fields).model_dump(mode="json")
            except Exception as e:
                errors.append(str(e))
        rows.append(ImportRow(row=i, fields=fields, errors=errors, lookup_raw=r.raw, photo_urls=r.image_urls[:4],
                              description=r.description or ""))
    return _preview(db, user, col, rows)


@router.post("/commit")
def commit(body: CommitIn, db: Session = Depends(get_db), user: User = Depends(current_user)):
    col = _collection(db, user, body.collection_id)
    # Rows that had problems in the preview stay skipped; the rest are checked again here.
    rows = _check(db, user, col, body.rows)
    created: list[Coin] = []
    for r in rows:
        if r.errors:
            continue
        data = _validate(CoinFields(**r.fields), col, col.coin_type)
        coin = Coin(**data, user_id=user.id, coin_type_id=col.coin_type_id, collection_id=col.id,
                    inventory_number=next_inventory_number(db, user.id, col.coin_type), lookup_raw=r.lookup_raw)
        v = r.valuation
        if v.get("value_source") == "custom" and v.get("custom_value") is not None:
            coin.value_source, coin.custom_value = "custom", v["custom_value"]
        coin.toner_premium = v.get("toner_premium")
        coin.holder_premium = v.get("holder_premium")
        db.add(coin)
        db.flush()
        created.append(coin)
        if body.import_photos:
            for order, url in enumerate(r.photo_urls[:4]):
                try:
                    data_, ctype = store.download_image(url)
                    name, ctype = store.save_bytes(coin.id, data_, ctype)
                except Exception:
                    continue
                db.add(CoinPhoto(coin_id=coin.id, file_name=name, content_type=ctype, sort_order=order, source="lookup"))
    db.commit()
    return {
        "created": [c.inventory_number for c in created],
        "skipped": [{"row": r.row, "description": r.description, "errors": r.errors} for r in rows if r.errors],
    }
