"""Price by grade: CPG for every grade of a coin's issue, saved whenever the coin is priced (no extra calls)."""

from datetime import datetime, timezone
from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.orm import Session

from ..config import get_settings
from ..models import Coin, GradePriceSheet
from .coins import CPG, latest_quote


def save_sheet(db: Session, sheet: dict) -> None:
    row = db.scalar(select(GradePriceSheet).where(GradePriceSheet.key == sheet["key"]))
    if row is None:
        row = GradePriceSheet(key=sheet["key"])
        db.add(row)
    row.gsid, row.name, row.rows = sheet.get("gsid"), sheet.get("name"), sheet["rows"]
    row.fetched_at = datetime.now(timezone.utc)


def _key_for(coin: Coin) -> list[str]:
    keys = []
    if coin.pcgs_number:
        keys.append(f"pcgs:{coin.pcgs_number}")
    q = latest_quote(coin, CPG)
    gsid = (q.raw or {}).get("gsid") if q is not None else None
    if gsid:
        keys.append(f"gsid:{gsid}")
    return keys


def table_for(db: Session, coin: Coin) -> dict | None:
    """Rows of grade / CPG / est. wholesale (and the CAC versions), or None if the issue hasn't been priced yet."""
    sheet = None
    for key in _key_for(coin):
        sheet = db.scalar(select(GradePriceSheet).where(GradePriceSheet.key == key))
        if sheet:
            break
    if sheet is None:
        return None
    keep = Decimal(1) - Decimal(str(get_settings().wholesale_discount))
    by_label: dict[str, dict] = {}
    for r in sheet.rows:
        if r.get("cpg") is None:
            continue
        cpg = Decimal(r["cpg"]).quantize(Decimal("0.01"))
        row = by_label.setdefault(r["label"], {"grade": r["grade"], "label": r["label"]})
        prefix = "cac_" if r.get("cac") else ""
        row[f"{prefix}cpg"] = str(cpg)
        row[f"{prefix}wholesale"] = str((cpg * keep).quantize(Decimal("0.01")))
    rows = sorted(by_label.values(), key=lambda r: (int(r["grade"] or 0), "+" in r["label"]))
    return {
        "name": sheet.name,
        "fetched_at": sheet.fetched_at,
        "wholesale_discount": get_settings().wholesale_discount,
        "has_cac": any("cac_cpg" in r for r in rows),
        "rows": rows,
    }
