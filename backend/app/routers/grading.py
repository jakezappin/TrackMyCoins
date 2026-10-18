"""Grading Tracker: submissions of coins to NGC, PCGS, CAC and the rest, their turnaround, costs, documents and
results."""

from datetime import date
from decimal import Decimal
from typing import Literal
from urllib.parse import quote

from fastapi import APIRouter, Depends, Form, HTTPException, UploadFile, status
from fastapi.responses import FileResponse
from pydantic import BaseModel, Field, field_validator, model_validator
from sqlalchemy import func, select
from sqlalchemy.orm import Session, selectinload

from ..auth import current_user
from ..config import get_settings
from ..db import get_db
from ..models import Coin, GradingAttachment, GradingSubmission, GradingSubmissionCoin, User
from ..schemas import CoinFields
from ..services import attachments as docs
from ..services import grading
from ..services.coins import photo_url
from .coins import _validate, get_owned_coin

router = APIRouter(prefix="/api/grading", tags=["grading"])
settings = get_settings()

Company = Literal["NGC", "PCGS", "CACG", "CAC", "ANACS", "ICG"]
Kind = Literal["grading", "crossover", "regrade", "reholder", "sticker"]
Outcome = Literal["graded", "details", "no_grade", "not_crossed", "sticker_green", "sticker_gold", "no_sticker", "returned"]
DocKind = Literal["invoice", "shipping", "insurance", "registered", "other"]
Money = Field(default=None, ge=0, max_digits=12, decimal_places=2)


class Addon(BaseModel):
    key: str = Field(max_length=60)
    name: str = Field(max_length=100)
    fee: Decimal | None = Field(default=None, ge=0, max_digits=10, decimal_places=2)
    per: Literal["coin", "order"] = "coin"


class SubmissionIn(BaseModel):
    name: str | None = Field(default=None, max_length=100)
    company: Company
    kind: Kind = "grading"
    tier_key: str | None = Field(default=None, max_length=60)
    tier_name: str | None = Field(default=None, max_length=100)
    tier_fee: Decimal | None = Money
    tier_max_value: Decimal | None = Money
    turnaround_days: int | None = Field(default=None, ge=1, le=730)
    business_days: bool = True
    addons: list[Addon] = Field(default=[], max_length=20)
    order_number: str | None = Field(default=None, max_length=60)
    tracking_out: str | None = Field(default=None, max_length=60)
    tracking_back: str | None = Field(default=None, max_length=60)
    date_sent: date | None = None
    date_received: date | None = None
    date_shipped_back: date | None = None
    date_returned: date | None = None
    grading_paid: Decimal | None = Money
    shipping_paid: Decimal | None = Money
    notes: str | None = Field(default=None, max_length=5000)

    @field_validator("name", "tier_key", "tier_name", "order_number", "tracking_out", "tracking_back", "notes", mode="before")
    @classmethod
    def _blank(cls, v):
        return (v.strip() or None) if isinstance(v, str) else v

    @model_validator(mode="after")
    def _dates_in_order(self):
        steps = [("sent", self.date_sent), ("received by the grader", self.date_received),
                 ("shipped back", self.date_shipped_back), ("returned", self.date_returned)]
        known = [(n, d) for n, d in steps if d]
        for (n1, d1), (n2, d2) in zip(known, known[1:]):
            if d2 < d1:
                raise ValueError(f"The date {n2} is before the date {n1}.")
        if known and known[-1][1] > date.today():
            raise ValueError(f"The date {known[-1][0]} is in the future.")
        if self.company == "CAC":
            self.kind = "sticker"
        return self


class CoinAdd(BaseModel):
    inventory_number: str = Field(max_length=20)
    expected_grade: str | None = Field(default=None, max_length=20)
    declared_value: Decimal | None = Money


class CoinEdit(BaseModel):
    expected_grade: str | None = Field(default=None, max_length=20)
    declared_value: Decimal | None = Money


class Result(BaseModel):
    link_id: int
    outcome: Outcome
    grading_service: str | None = None
    cert_number: str | None = Field(default=None, max_length=30)
    grade_prefix: str | None = None
    grade: int | None = Field(default=None, ge=1, le=70)
    grade_plus: bool = False
    grade_star: bool = False
    strike_designation: str | None = Field(default=None, max_length=20)
    details_problem: str | None = Field(default=None, max_length=40)


class ResultsIn(BaseModel):
    date_returned: date | None = None
    results: list[Result] = Field(max_length=500)


# ---- Helpers -------------------------------------------------------------------------------------------------

def _owned(db: Session, user: User, sub_id: int) -> GradingSubmission:
    s = db.get(GradingSubmission, sub_id)
    if s is None or s.user_id != user.id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Submission not found")
    return s


def _coin_brief(c: Coin) -> dict:
    return {
        "inventory_number": c.inventory_number,
        "year": c.year, "mint_mark": c.mint_mark, "variety": c.variety,
        "coin_type_name": c.coin_type.name, "collection_name": c.collection.name,
        "grade": grading.grade_label(c),
        "thumbnail_url": f"{photo_url(c.photos[0].id)}?size=thumb" if c.photos else None,
        "is_sold": c.sale_date is not None or c.sale_price is not None,
    }


def _link_out(link: GradingSubmissionCoin) -> dict:
    return {
        "id": link.id, "coin": _coin_brief(link.coin), "expected_grade": link.expected_grade,
        "declared_value": str(link.declared_value) if link.declared_value is not None else None,
        "before": link.before, "outcome": link.outcome, "outcome_label": grading.OUTCOMES.get(link.outcome, link.outcome),
        "after": link.after, "returned_on": link.returned_on,
    }


def _summary(s: GradingSubmission, today: date) -> dict:
    n = len(s.coins)
    return {
        "id": s.id, "number": s.number, "name": s.name, "company": s.company,
        "company_label": grading.COMPANIES.get(s.company, s.company), "kind": s.kind,
        "kind_label": grading.KINDS.get(s.kind, s.kind), "tier_key": s.tier_key, "tier_name": s.tier_name,
        "coin_count": n, "pending_count": sum(1 for link in s.coins if link.outcome == "pending"),
        "date_sent": s.date_sent, "date_received": s.date_received, "date_shipped_back": s.date_shipped_back,
        "date_returned": s.date_returned, "progress": grading.progress(s, today),
        "grading_paid": str(s.grading_paid) if s.grading_paid is not None else None,
        "shipping_paid": str(s.shipping_paid) if s.shipping_paid is not None else None,
        "created_at": s.created_at,
    }


def _detail(db: Session, s: GradingSubmission) -> dict:
    today = date.today()
    out = _summary(s, today)
    over = [link.coin.inventory_number for link in s.coins
            if s.tier_max_value is not None and link.declared_value is not None and link.declared_value > s.tier_max_value]
    out.update({
        "tier_fee": str(s.tier_fee) if s.tier_fee is not None else None,
        "tier_max_value": str(s.tier_max_value) if s.tier_max_value is not None else None,
        "turnaround_days": s.turnaround_days, "business_days": s.business_days, "addons": s.addons or [],
        "order_number": s.order_number, "tracking_out": s.tracking_out, "tracking_back": s.tracking_back,
        "notes": s.notes, "coins": [_link_out(link) for link in s.coins], "fees": grading.fees(s, len(s.coins)),
        "over_max_value": over, "attachments": _docs(db, s.id),
        "declared_total": str(sum((link.declared_value or Decimal(0) for link in s.coins), Decimal(0))),
    })
    return out


def _query(user: User):
    return (select(GradingSubmission).where(GradingSubmission.user_id == user.id)
            .options(selectinload(GradingSubmission.coins).selectinload(GradingSubmissionCoin.coin)))


def ordered(subs: list[GradingSubmission]) -> list[GradingSubmission]:
    """Not yet returned first, oldest first (the ones waiting longest); then returned, most recent first."""
    out_ = [s for s in subs if not s.date_returned]
    back = [s for s in subs if s.date_returned]
    out_.sort(key=lambda s: (s.date_received or s.date_sent or date.max, s.created_at, s.id))
    back.sort(key=lambda s: (s.date_returned, s.id), reverse=True)
    return out_ + back


def add_coin(db: Session, s: GradingSubmission, coin: Coin, expected: str | None = None,
             declared: Decimal | None = None) -> GradingSubmissionCoin:
    """Put a coin in a submission: it's now at grading."""
    if coin.sale_date is not None or coin.sale_price is not None:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, f"{coin.inventory_number} has been sold.")
    if s.date_returned:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "This submission is back already. Start a new one.")
    busy = db.scalar(select(GradingSubmissionCoin).where(GradingSubmissionCoin.coin_id == coin.id,
                                                         GradingSubmissionCoin.outcome == "pending"))
    if busy is not None and busy.submission_id != s.id:
        raise HTTPException(status.HTTP_409_CONFLICT,
                            f"{coin.inventory_number} is already at grading in submission #{busy.submission.number}.")
    if busy is not None:
        return busy
    link = GradingSubmissionCoin(submission_id=s.id, coin_id=coin.id, expected_grade=expected, declared_value=declared,
                                 before=grading.snapshot(coin))
    db.add(link)
    s.coins.append(link)
    coin.location = "grading"
    return link


def back_to_inventory(coin: Coin, link: GradingSubmissionCoin | None, today: date | None = None) -> None:
    """The coin is home again; a link without a recorded result is closed as just "back"."""
    coin.location = "inventory"
    if link is not None and link.outcome == "pending":
        link.outcome = "returned"
        link.returned_on = today or date.today()
        link.after = grading.snapshot(coin)


def next_number(db: Session, user: User) -> int:
    return (db.scalar(select(func.max(GradingSubmission.number)).where(GradingSubmission.user_id == user.id)) or 0) + 1


# ---- Tiers ---------------------------------------------------------------------------------------------------

@router.get("/tiers")
def list_tiers(_: User = Depends(current_user)):
    return {**grading.tiers(), "companies": grading.COMPANIES, "kinds": grading.KINDS, "outcomes": grading.OUTCOMES,
            "colors": {"green": grading.GREEN_UPTO, "yellow": grading.YELLOW_UPTO, "orange": grading.ORANGE_UPTO}}


# ---- Submissions ---------------------------------------------------------------------------------------------

@router.get("/submissions")
def list_submissions(db: Session = Depends(get_db), user: User = Depends(current_user)):
    today = date.today()
    return [_summary(s, today) for s in ordered(list(db.scalars(_query(user)).all()))]


@router.post("/submissions", status_code=status.HTTP_201_CREATED)
def create_submission(body: SubmissionIn, db: Session = Depends(get_db), user: User = Depends(current_user)):
    s = GradingSubmission(user_id=user.id, number=next_number(db, user), **body.model_dump(exclude={"addons"}))
    s.addons = [a.model_dump(mode="json") for a in body.addons]
    db.add(s)
    db.commit()
    db.refresh(s)
    return _detail(db, s)


@router.get("/submissions/{sub_id}")
def get_submission(sub_id: int, db: Session = Depends(get_db), user: User = Depends(current_user)):
    return _detail(db, _owned(db, user, sub_id))


@router.put("/submissions/{sub_id}")
def update_submission(sub_id: int, body: SubmissionIn, db: Session = Depends(get_db), user: User = Depends(current_user)):
    s = _owned(db, user, sub_id)
    for k, v in body.model_dump(exclude={"addons"}).items():
        setattr(s, k, v)
    s.addons = [a.model_dump(mode="json") for a in body.addons]
    if s.date_returned:
        # Back home: coins without a recorded result go back to inventory unchanged.
        for link in s.coins:
            if link.outcome == "pending":
                back_to_inventory(link.coin, link, s.date_returned)
    db.commit()
    db.refresh(s)
    return _detail(db, s)


@router.delete("/submissions/{sub_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_submission(sub_id: int, db: Session = Depends(get_db), user: User = Depends(current_user)):
    s = _owned(db, user, sub_id)
    for link in s.coins:
        if link.outcome == "pending":
            link.coin.location = "inventory"
    files = [(a.file_name) for a in db.scalars(select(GradingAttachment).where(GradingAttachment.submission_id == s.id))]
    db.delete(s)
    db.commit()
    for f in files:
        docs.delete_file(_doc_key(sub_id), f)


# ---- Coins in a submission -----------------------------------------------------------------------------------

@router.post("/submissions/{sub_id}/coins")
def add_coin_endpoint(sub_id: int, body: CoinAdd, db: Session = Depends(get_db), user: User = Depends(current_user)):
    s = _owned(db, user, sub_id)
    coin = get_owned_coin(db, user, body.inventory_number)
    add_coin(db, s, coin, body.expected_grade, body.declared_value)
    db.commit()
    db.refresh(s)
    return _detail(db, s)


@router.put("/submissions/{sub_id}/coins/{link_id}")
def edit_coin(sub_id: int, link_id: int, body: CoinEdit, db: Session = Depends(get_db), user: User = Depends(current_user)):
    s = _owned(db, user, sub_id)
    link = next((x for x in s.coins if x.id == link_id), None)
    if link is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Coin not in this submission")
    link.expected_grade = (body.expected_grade or "").strip() or None
    link.declared_value = body.declared_value
    db.commit()
    return _detail(db, s)


@router.delete("/submissions/{sub_id}/coins/{link_id}")
def remove_coin(sub_id: int, link_id: int, db: Session = Depends(get_db), user: User = Depends(current_user)):
    s = _owned(db, user, sub_id)
    link = next((x for x in s.coins if x.id == link_id), None)
    if link is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Coin not in this submission")
    if link.outcome != "pending":
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "This coin's result is recorded; it stays in its history.")
    link.coin.location = "inventory"
    s.coins.remove(link)
    db.delete(link)
    db.commit()
    db.refresh(s)
    return _detail(db, s)


@router.post("/submissions/{sub_id}/results")
def record_results(sub_id: int, body: ResultsIn, db: Session = Depends(get_db), user: User = Depends(current_user)):
    """The submission is back: each coin's result updates the coin (new service, grade, cert or CAC sticker), is kept
    in its grading history, and the coin is back in inventory."""
    s = _owned(db, user, sub_id)
    by_id = {link.id: link for link in s.coins}
    returned_on = body.date_returned or s.date_returned or date.today()
    for r in body.results:
        link = by_id.get(r.link_id)
        if link is None:
            raise HTTPException(status.HTTP_404_NOT_FOUND, f"Coin {r.link_id} isn't in this submission")
        coin = link.coin
        if r.outcome in ("graded", "details"):
            fields = CoinFields.model_validate(coin, from_attributes=True).model_dump()
            fields.update(
                grading_service=r.grading_service or (s.company if s.company not in ("CAC",) else coin.grading_service),
                cert_number=r.cert_number, grade_prefix=r.grade_prefix, grade=r.grade, grade_plus=r.grade_plus,
                grade_star=r.grade_star, strike_designation=r.strike_designation,
                details=r.outcome == "details", details_problem=r.details_problem if r.outcome == "details" else None,
            )
            if fields["grading_service"] != coin.grading_service or r.cert_number != coin.cert_number:
                fields.update(cac=False, cac_sticker=None)  # a new slab has no sticker
            try:
                body_fields = CoinFields(**fields)
            except ValueError as e:
                raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, f"{coin.inventory_number}: {e}")
            data = _validate(body_fields, coin.collection, coin.coin_type)
            for k in grading.GRADE_FIELDS:
                setattr(coin, k, data[k])
        elif r.outcome in ("sticker_green", "sticker_gold"):
            coin.cac, coin.cac_sticker = True, r.outcome.removeprefix("sticker_")
        link.outcome = r.outcome
        link.returned_on = returned_on
        link.after = grading.snapshot(coin)
        coin.location = "inventory"
    if all(link.outcome != "pending" for link in s.coins):
        s.date_returned = s.date_returned or returned_on
    db.commit()
    db.refresh(s)
    return _detail(db, s)


# ---- Documents -----------------------------------------------------------------------------------------------

def _doc_key(sub_id: int) -> str:
    return f"grading-{sub_id}"


def _docs(db: Session, sub_id: int) -> list[dict]:
    rows = db.scalars(select(GradingAttachment).where(GradingAttachment.submission_id == sub_id)
                      .order_by(GradingAttachment.created_at))
    return [{"id": a.id, "kind": a.kind, "name": a.original_name, "content_type": a.content_type, "size": a.size_bytes,
             "created_at": a.created_at, "url": f"/api/grading/attachments/{a.id}"} for a in rows]


def _owned_doc(db: Session, user: User, attachment_id: int) -> GradingAttachment:
    a = db.get(GradingAttachment, attachment_id)
    s = db.get(GradingSubmission, a.submission_id) if a else None
    if s is None or s.user_id != user.id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "File not found")
    return a


@router.post("/submissions/{sub_id}/attachments")
async def upload_docs(sub_id: int, files: list[UploadFile], kind: DocKind = Form("other"),
                      db: Session = Depends(get_db), user: User = Depends(current_user)):
    s = _owned(db, user, sub_id)
    have = len(_docs(db, s.id))
    if have + len(files) > settings.max_attachments_per_coin:
        raise HTTPException(status.HTTP_400_BAD_REQUEST,
                            f"A submission can have at most {settings.max_attachments_per_coin} files (it has {have}).")
    saved: list[str] = []
    for f in files:
        data = await f.read(settings.max_attachment_bytes + 1)
        try:
            stored, name, ctype, size = docs.save(_doc_key(s.id), data, f.content_type or "", f.filename)
        except docs.AttachmentError as e:
            for done in saved:
                docs.delete_file(_doc_key(s.id), done)
            raise HTTPException(status.HTTP_400_BAD_REQUEST, f"{f.filename}: {e}")
        saved.append(stored)
        db.add(GradingAttachment(submission_id=s.id, kind=kind, file_name=stored, original_name=name,
                                 content_type=ctype, size_bytes=size))
    db.commit()
    return _docs(db, s.id)


@router.get("/attachments/{attachment_id}")
def get_doc(attachment_id: int, db: Session = Depends(get_db), user: User = Depends(current_user)):
    a = _owned_doc(db, user, attachment_id)
    path = docs.path_for(_doc_key(a.submission_id), a.file_name)
    if not path.exists():
        raise HTTPException(status.HTTP_404_NOT_FOUND, "File missing")
    return FileResponse(path, media_type=a.content_type, headers={
        "Content-Disposition": f"inline; filename*=UTF-8''{quote(a.original_name)}",
        "Cache-Control": "private, max-age=86400", "X-Content-Type-Options": "nosniff"})


@router.delete("/attachments/{attachment_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_doc(attachment_id: int, db: Session = Depends(get_db), user: User = Depends(current_user)):
    a = _owned_doc(db, user, attachment_id)
    docs.delete_file(_doc_key(a.submission_id), a.file_name)
    db.delete(a)
    db.commit()
