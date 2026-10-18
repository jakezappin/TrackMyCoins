"""Bulk import: preview a spreadsheet or a list of PCGS certs, then create the coins the user keeps."""

import json
import re
from datetime import date

import httpx
from fastapi import APIRouter, Depends, Form, HTTPException, UploadFile, status
from fastapi.responses import Response
from pydantic import BaseModel, Field, ValidationError, field_validator
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..auth import current_user
from ..db import get_db
from ..models import (CatalogEntry, Coin, CoinPhoto, CoinType, Collection, CollectionCounter, GradingSubmission,
                      StorageSpot, User)
from ..schemas import CoinFields, ImportValuation, small_json
from ..series import BY_SLUG, FINISHES, Series
from ..services import cleanup, import_columns, importer, lookups, quota, series_match
from ..services import photos as store
from ..services.coins import _cert_key, find_duplicate_cert, next_collection_number, next_inventory_number
from .coins import _validate
from .collections import get_owned_collection

router = APIRouter(prefix="/api/import", tags=["import"])
XLSX = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"

MAX_CERTS = 50  # each PCGS cert costs a lookup call (1,000 a day)


class ImportRow(BaseModel):
    row: int
    sheet: str = ""
    fields: dict
    valuation: dict = {}
    errors: list[str] = []
    description: str = ""
    lookup_raw: dict | None = None
    photo_urls: list[str] = Field(default=[], max_length=10)
    hints: dict[str, str | None] = {}  # what says which series the coin is (Type column, words after the date, inventory #)
    target: str | None = None  # the collection it will go into (preview)
    placement: str | None = None  # where it'll be kept / which submission it's in (preview)

    @field_validator("fields", "valuation", "lookup_raw")
    @classmethod
    def _not_huge(cls, v):
        return small_json(v)
    target_new: bool = False  # ... which will be created


class PreviewOut(BaseModel):
    collection_id: int | None
    rows: list[ImportRow]
    ok_count: int
    error_count: int


class CertsIn(BaseModel):
    collection_id: int | None = None  # None: sort each coin into the collection for its series
    certs: str = Field(max_length=20000)


class CommitIn(BaseModel):
    collection_id: int | None = None
    rows: list[ImportRow] = Field(max_length=importer.MAX_ROWS)
    import_photos: bool = True


def _collection(db: Session, user: User, collection_id: int | None) -> Collection | None:
    if collection_id is None:
        return None
    col = get_owned_collection(db, user, collection_id)
    series = BY_SLUG.get(col.coin_type.slug)
    if series and series.is_type_set:
        raise HTTPException(
            status.HTTP_422_UNPROCESSABLE_CONTENT,
            "Importing into a type set isn't supported yet, because each coin needs its series. Add these one at a time.",
        )
    return col


def _messages(e: ValidationError) -> list[str]:
    """Readable messages, e.g. 'purchase_date: Purchase date 0017-12-31 looks mistyped...'."""
    out = []
    for err in e.errors():
        where = ".".join(str(p) for p in err["loc"])
        msg = err["msg"].removeprefix("Value error, ")
        out.append(f"{where}: {msg}" if where else msg)
    return out


def _describe(f: dict, series_name: str | None = None) -> str:
    date = f"{f.get('year') or '?'}" + (f"-{f['mint_mark']}" if f.get("mint_mark") not in (None, "P") else "")
    if series_name:
        date += f" {series_name}"
    grade = f"{f.get('grade_prefix') or ''}{f.get('grade') or ''}{'+' if f.get('grade_plus') else ''}"
    if f.get("strike_designation"):
        grade += f" {f['strike_designation']}"
    svc = "Raw" if f.get("grading_service") == "RAW" else f"{f.get('grading_service')} #{f.get('cert_number') or '?'}"
    return " ".join(x for x in (date, f.get("variety") or "", grade.strip(), "·", svc) if x)


FINISH_WORD = {"MS": "", "PR": " Proof", "SPR": " Silver Proof"}
NO_SERIES = ("Couldn't tell which series this coin is. Add a Type column (e.g. Morgan Dollar) or put it after "
             "the date (e.g. 1881-S Morgan Dollar).")


class _Router:
    """Decides which collection each row goes into: the one picked, or (sorting) the user's first collection for
    the coin's series and finish, creating one at commit if there isn't one."""

    def __init__(self, db: Session, user: User, fixed: Collection | None, rows: list[ImportRow]):
        self.db, self.user, self.fixed = db, user, fixed
        self.types = {t.slug: t for t in db.scalars(select(CoinType))}
        self.existing: dict[tuple[int, str], Collection] = {}
        for c in db.scalars(select(Collection).where(Collection.user_id == user.id).order_by(Collection.number)):
            self.existing.setdefault((c.coin_type_id, c.finish), c)  # first by number
        self.planned: dict[tuple[int, str], Collection] = {}  # sorting: collections still to be created
        # PCGS numbers we've already catalogued name their series exactly.
        numbers = {str(r.fields.get("pcgs_number")) for r in rows if r.fields.get("pcgs_number")}
        self.by_pcgs: dict[str, int] = {}
        if numbers:
            for num, type_id in db.execute(
                select(CatalogEntry.pcgs_number, CatalogEntry.coin_type_id).where(CatalogEntry.pcgs_number.in_(numbers))
            ):
                self.by_pcgs.setdefault(num, type_id)
        self.slug_by_type_id = {t.id: slug for slug, t in self.types.items()}

    def series_of(self, r: ImportRow) -> tuple[Series | None, str | None]:
        year = r.fields.get("year")
        s = series_match.from_inventory_number(r.hints.get("inventory"))
        if s:
            return s, None
        type_id = self.by_pcgs.get(str(r.fields.get("pcgs_number") or ""))
        if type_id and (s := BY_SLUG.get(self.slug_by_type_id.get(type_id, ""))) and not s.is_type_set:
            return s, None
        reasons = []
        if r.lookup_raw:
            m = series_match.from_pcgs_facts(r.lookup_raw, year)
            if m.series:
                return m.series, None
            reasons.append(m.reason)
        text = r.hints.get("text")
        m = series_match.from_text(text, year)
        if m.series:
            return m.series, None
        reasons.append(m.reason)
        if text and not r.lookup_raw:
            reasons.append(f"Didn't recognize '{text}' as a series TrackMyCoins tracks. Use a name like Morgan Dollar.")
        return None, next((x for x in reasons if x), None)

    def target(self, r: ImportRow) -> tuple[Collection, CoinType] | str:
        """(collection, its coin type) for a row, or why it can't be placed."""
        try:
            CoinFields(**r.fields)  # a sent-back row with a year of "abc" is refused here, not a server error
        except ValidationError as e:
            return "; ".join(err["msg"].removeprefix("Value error, ") for err in e.errors())
        series, why = self.series_of(r)
        year = r.fields.get("year")
        if self.fixed is not None:
            mine = BY_SLUG.get(self.fixed.coin_type.slug)
            if series and mine and series.slug != mine.slug:
                return f"This looks like a {series.name}, not a {mine.name}."
            if mine and (problem := series_match.date_problem(mine, year, r.fields.get("mint_mark"), r.fields.get("grade_prefix"))):
                return problem
            return self.fixed, self.fixed.coin_type
        if series is None:
            return why or NO_SERIES
        if problem := series_match.date_problem(series, year, r.fields.get("mint_mark"), r.fields.get("grade_prefix")):
            return problem
        ct = self.types.get(series.slug)
        if ct is None:
            return NO_SERIES
        finish = "MS"
        if (r.fields.get("grade_prefix") or "") in ("PR", "PF"):
            silver = "silver" in f"{r.hints.get('text', '')} {r.fields.get('variety') or ''}".lower()
            finish = "SPR" if silver and "SPR" in (ct.finishes or []) else "PR"
        if finish not in (ct.finishes or ["MS"]):
            return f"TrackMyCoins doesn't have {FINISHES[finish][1]} collections for {series.plural}."
        key = (ct.id, finish)
        col = self.existing.get(key) or self.planned.get(key)
        if col is None:  # not saved until commit
            col = Collection(user_id=self.user.id, coin_type_id=ct.id, finish=finish, name=self._new_name(ct, finish))
            self.planned[key] = col
        return col, ct

    def _new_name(self, ct: CoinType, finish: str) -> str:
        counter = self.db.get(CollectionCounter, (self.user.id, ct.id, finish))
        n = counter.next_number if counter else 1
        taken = set(self.db.scalars(select(Collection.name).where(Collection.user_id == self.user.id)))
        taken |= {c.name for c in self.planned.values()}
        while (name := f"{ct.name}{FINISH_WORD[finish]} Collection {n}") in taken:
            n += 1
        return name

    def create_planned(self, used: set[tuple[int, str]]) -> None:
        """Save the new collections that coins are actually going into."""
        for key, col in self.planned.items():
            if key in used:
                col.number = next_collection_number(self.db, self.user.id, self.types[self.slug_by_type_id[key[0]]], key[1])
                self.db.add(col)
        self.db.flush()


class _Places:
    """Storage spots and grading submissions named in the file: the user's own, by name (spots are created at
    commit if new) or by submission # / name."""

    def __init__(self, db: Session, user: User):
        self.db, self.user = db, user
        self.spots = {s.name.lower(): s for s in db.scalars(select(StorageSpot).where(StorageSpot.user_id == user.id))}
        self.subs = list(db.scalars(select(GradingSubmission).where(GradingSubmission.user_id == user.id)))
        self.new_spots: dict[str, StorageSpot] = {}
        self.new_subs: dict[str, GradingSubmission] = {}

    def submission(self, ref: str) -> GradingSubmission | str:
        m = re.fullmatch(r"#?\s*(\d+)", ref.strip())
        hit = next((s for s in self.subs if (m and s.number == int(m.group(1))) or
                    (s.name and s.name.strip().lower() == ref.strip().lower())), None)
        if hit is None:
            return f"No grading submission {ref!r} (use its # or name from the Grading Tracker)"
        if hit.date_returned:
            return f"Submission #{hit.number} is already back"
        return hit

    def note(self, hints: dict) -> str | None:
        parts = []
        if hints.get("storage"):
            new = hints["storage"].lower() not in self.spots
            parts.append(f"Stored in {hints['storage']}{' (new)' if new else ''}"
                         + (f" · {hints['position']}" if hints.get("position") else ""))
        if hints.get("status") == "grading":
            ref = hints.get("submission")
            sub = self.submission(ref) if ref else None
            parts.append(f"At grading: #{sub.number} {sub.company}" if isinstance(sub, GradingSubmission)
                         else f"At grading: new {hints.get('submit_company')} submission")
        return " · ".join(parts) or None

    def check(self, hints: dict) -> str | None:
        if hints.get("status") == "grading" and hints.get("submission"):
            got = self.submission(hints["submission"])
            if isinstance(got, str):
                return got
        return None

    def apply(self, coin: Coin, hints: dict) -> None:
        """Called at commit, after the coin is saved."""
        from .grading import add_coin, next_number

        name = hints.get("storage")
        if name:
            spot = self.spots.get(name.lower()) or self.new_spots.get(name.lower())
            if spot is None:
                spot = StorageSpot(user_id=self.user.id, name=name)
                self.db.add(spot)
                self.db.flush()
                self.new_spots[name.lower()] = spot
            coin.storage_id, coin.storage_position = spot.id, hints.get("position")
        if hints.get("status") == "grading":
            sub = self.submission(hints["submission"]) if hints.get("submission") else None
            if not isinstance(sub, GradingSubmission):
                company = hints.get("submit_company") or "NGC"
                sub = self.new_subs.get(company)
                if sub is None:
                    sub = GradingSubmission(user_id=self.user.id, number=next_number(self.db, self.user),
                                            company=company, kind="sticker" if company == "CAC" else "grading",
                                            name=f"Imported {date.today():%b %d, %Y}", addons=[])
                    self.db.add(sub)
                    self.db.flush()
                    self.new_subs[company] = sub
            add_coin(self.db, sub, coin)


def _check(db: Session, user: User, router_: _Router, rows: list[ImportRow]) -> list[tuple[ImportRow, Collection, CoinType]]:
    """Same rules as adding a coin by hand, plus the right series and duplicate certs within the file.
    Returns the rows that can be imported with where they go; the others get errors."""
    seen: dict[tuple[str, str], int] = {}
    ok = []
    places = _Places(db, user)
    for r in rows:
        made_up = not r.description or r.description == _describe(r.fields)  # ours, not PCGS's
        r.description = r.description or _describe(r.fields)
        r.target, r.target_new = None, False
        if r.errors:
            continue
        placed = router_.target(r)
        if isinstance(placed, str):
            r.errors.append(placed)
            continue
        col, ct = placed
        try:
            data = _validate(CoinFields(**r.fields), col, ct)
            ImportValuation(**r.valuation)
        except HTTPException as e:
            r.errors.append(str(e.detail))
            continue
        except ValidationError as e:
            r.errors.extend(_messages(e))
            continue
        on_hand = data["sale_price"] is None and data["sale_date"] is None
        key = (data["grading_service"], _cert_key(data["cert_number"]))
        if on_hand and key[1] and data["grading_service"] != "RAW":
            dup = find_duplicate_cert(db, user.id, data["grading_service"], data["cert_number"])
            if dup:
                r.errors.append(f"Already in your collection as {dup.inventory_number}")
                continue
            if key in seen:
                r.errors.append(f"Same cert as row {seen[key]}")
                continue
            seen[key] = r.row
        if (bad := places.check(r.hints)):
            r.errors.append(bad)
            continue
        r.placement = places.note(r.hints)
        r.target, r.target_new = col.name, col.id is None
        if made_up:
            r.description = _describe(r.fields, ct.name)
        ok.append((r, col, ct))
    return ok


def _preview(db, user, col, rows: list[ImportRow]) -> PreviewOut:
    _check(db, user, _Router(db, user, col, rows), rows)
    bad = sum(1 for r in rows if r.errors)
    return PreviewOut(collection_id=col.id if col else None, rows=rows, ok_count=len(rows) - bad, error_count=bad)


@router.get("/columns")
def columns(_: User = Depends(current_user)):
    """The import spreadsheet's columns: which are required and what goes in them (the Import page's guide)."""
    return import_columns.guide()


@router.get("/template")
def template(_: User = Depends(current_user)):
    return Response(import_columns.template_xlsx(), media_type=XLSX,
                    headers={"Content-Disposition": 'attachment; filename="TrackMyCoins_import_template.xlsx"'})


async def _read_upload(file: UploadFile) -> list[tuple[str, int, dict]]:
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
        raise HTTPException(status.HTTP_400_BAD_REQUEST, f"At most {importer.MAX_ROWS} rows at a time.")
    return raw_rows


def _mapping(text: str | None) -> dict[str, str]:
    if not text:
        return {}
    try:
        m = json.loads(text)
    except ValueError:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, "Column choices aren't valid")
    allowed = {c["field"] for c in cleanup.CHOICES}
    if not isinstance(m, dict) or any(not isinstance(k, str) or v not in allowed for k, v in m.items()):
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, "Column choices aren't valid")
    return m


@router.post("/cleanup")
async def cleanup_preview(file: UploadFile, mapping: str | None = Form(None), db: Session = Depends(get_db),
                          user: User = Depends(current_user)):
    """Spreadsheet cleanup: each column's match, and each row cleaned with what changed and what needs fixing."""
    return cleanup.clean(db, user.id, await _read_upload(file), _mapping(mapping))


@router.post("/cleanup/file")
async def cleanup_file(file: UploadFile, mapping: str | None = Form(None), db: Session = Depends(get_db),
                       user: User = Depends(current_user)):
    """The cleaned spreadsheet (Coins, plus Changes and Problems sheets), ready to import."""
    result = cleanup.clean(db, user.id, await _read_upload(file), _mapping(mapping))
    stem = re.sub(r"[^A-Za-z0-9]+", "_", (file.filename or "spreadsheet").rsplit(".", 1)[0]).strip("_") or "spreadsheet"
    return Response(cleanup.to_xlsx(result), media_type=XLSX,
                    headers={"Content-Disposition": f'attachment; filename="{stem}_cleaned.xlsx"'})


@router.post("/preview", response_model=PreviewOut)
async def preview_file(
    file: UploadFile, collection_id: int | None = Form(None), db: Session = Depends(get_db), user: User = Depends(current_user)
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
        fields, valuation, errors, hints = importer.row_to_fields(raw, sold_sheet=sheet == "Sold")
        rows.append(ImportRow(row=n, sheet=sheet, fields=fields, valuation=valuation, errors=errors, hints=hints))
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
            r = lookups.lookup("PCGS", cert, user_id=user.id)
        except quota.QuotaExceeded as e:  # keep what was looked up; the rest can be pasted again tomorrow
            for later in certs[i - 1:]:
                rows.append(ImportRow(row=len(rows) + 1, fields={"grading_service": "PCGS", "cert_number": later},
                                      errors=[str(e)], description=f"PCGS #{later}"))
            break
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
    # Rows that had problems in the preview stay skipped; the rest are checked (and placed) again here.
    router_ = _Router(db, user, col, body.rows)
    placed = _check(db, user, router_, body.rows)
    router_.create_planned({(c.coin_type_id, c.finish) for _, c, _ in placed})
    rows = body.rows
    places = _Places(db, user)
    created: list[tuple[Coin, list[str]]] = []
    per_collection: dict[int, dict] = {}
    for r, target, ct in placed:
        data = _validate(CoinFields(**r.fields), target, ct)
        # Storage and At Grading aren't import columns (yet); never trust them from the rows sent back.
        data.update(storage_id=None, storage_position=None, location="inventory")
        coin = Coin(**data, user_id=user.id, coin_type_id=ct.id, collection_id=target.id,
                    inventory_number=next_inventory_number(db, user.id, ct), lookup_raw=r.lookup_raw)
        v = ImportValuation(**r.valuation)
        if v.value_source == "custom" and v.custom_value is not None:
            coin.value_source, coin.custom_value = "custom", v.custom_value
        coin.toner_premium = v.toner_premium
        coin.holder_premium = v.holder_premium
        db.add(coin)
        db.flush()
        places.apply(coin, r.hints)  # Stored in / At Grading, only if the file had those columns
        created.append((coin, r.photo_urls[:4] if body.import_photos else []))
        entry = per_collection.setdefault(target.id, {"id": target.id, "name": target.name, "count": 0,
                                                       "new": (target.coin_type_id, target.finish) in router_.planned})
        entry["count"] += 1
    db.commit()  # the coins are saved before any slow photo downloads

    # Photos are downloaded outside any database transaction (downloads can take a while, and holding SQLite's
    # write lock meanwhile made other saves and price refreshes fail with "database is locked").
    for coin, urls in created:
        saved = []
        for order, url in enumerate(urls):
            try:
                data_, ctype = store.download_image(url)
                name, ctype = store.save_bytes(coin.id, data_, ctype)
            except Exception:
                continue
            saved.append(CoinPhoto(coin_id=coin.id, file_name=name, content_type=ctype, sort_order=order, source="lookup"))
        if saved:
            db.add_all(saved)
            db.commit()
    return {
        "created": [c.inventory_number for c, _ in created],
        "collections": list(per_collection.values()),
        "skipped": [{"row": r.row, "sheet": r.sheet, "description": r.description, "errors": r.errors}
                    for r in rows if r.errors],
    }
