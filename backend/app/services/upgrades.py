"""Upgrade finder: for each line of a collection's checklist, the best coin owned, the next grade up and what it
would cost, from saved all-grades CPG prices (no API calls)."""

from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.orm import Session

from ..designations import from_greysheet_name, with_designation
from ..models import Coin, Collection, GradePriceSheet
from . import checklist, details
from .coins import CENTS, value_estimate


def _sheet(db: Session, keys: list[str]) -> GradePriceSheet | None:
    for key in keys:
        sheet = db.scalar(select(GradePriceSheet).where(GradePriceSheet.key == key))
        if sheet is not None:
            return sheet
    return None


def _cpg_rows(sheet: GradePriceSheet, cac: bool) -> list[dict]:
    """Plain (or CAC, for CAC coins) priced rows in grade order."""
    plain = [r for r in sheet.rows if r.get("cpg") and not r.get("cac")]
    rows = plain
    if cac:
        # CAC prices where the sheet has them, plain ones for the grades it doesn't.
        cac_rows = [r for r in sheet.rows if r.get("cpg") and r.get("cac")]
        have = {(r["grade"], "+" in str(r["label"])) for r in cac_rows}
        rows = cac_rows + [r for r in plain if (r["grade"], "+" in str(r["label"])) not in have]
    return sorted(rows, key=lambda r: (int(r["grade"] or 0), "+" in str(r["label"])))


def find(db: Session, col: Collection, mode: str = "full") -> dict:
    cl = checklist.build(db, col, mode)
    items, unpriced, top = [], [], []
    for row in cl.rows:
        if not row.coins:
            continue
        # Coins come best grade first; a problem-free coin beats a Details one.
        best: Coin = next((c for c in row.coins if not c.details), row.coins[0])
        grade = details.price_grade(best)
        if not grade:
            continue
        keys = ([f"pcgs:{best.pcgs_number}"] if best.pcgs_number else []) + [f"pcgs:{n}" for n in sorted(row.pcgs_numbers)]
        sheet = _sheet(db, keys)
        if sheet is None:
            unpriced.append(row.label)
            continue
        rows = _cpg_rows(sheet, cac=best.cac)
        current = value_estimate(best)
        # Grades in order with their plus: a 65+ is priced as a 65+, and its next step up is 66.
        mine = (grade, bool(best.grade_plus) and not best.details)
        rank = lambda r: (int(r["grade"] or 0), "+" in str(r["label"]))  # noqa: E731
        here = next((r for r in rows if rank(r) == mine), None)
        if current is None and here is not None:
            current = details.adjust(best, Decimal(here["cpg"]))
        # A Details coin's next step is a problem-free coin of its grade; otherwise the next grade up.
        nxt = next((r for r in rows if rank(r) == mine), None) if best.details else None
        nxt = nxt or next((r for r in rows if rank(r)[0] > grade), None)
        if nxt is None:
            top.append(row.label)  # already at the top priced grade
            continue
        designation = from_greysheet_name(sheet.name)
        next_cpg = Decimal(nxt["cpg"]).quantize(CENTS)
        cost = (next_cpg - current).quantize(CENTS) if current is not None else None
        items.append({
            "label": row.label,
            "year": row.year,
            "mint_mark": row.mint_mark,
            "variety": row.variety,
            "coin": {"inventory_number": best.inventory_number, "grade": best.grade, "grade_prefix": best.grade_prefix,
                     "grade_plus": best.grade_plus, "grade_star": best.grade_star,
                     "strike_designation": best.strike_designation, "cac": best.cac,
                     "details": best.details, "details_problem": best.details_problem},
            "current_value": str(current.quantize(CENTS)) if current is not None else None,
            "next_grade": int(nxt["grade"]),
            "next_label": with_designation(str(nxt["label"]), designation) + (" CAC" if nxt.get("cac") else ""),
            "next_cpg": str(next_cpg),
            "cost": str(cost) if cost is not None else None,
            "pct": round(float(cost / current) * 100) if cost is not None and current else None,
        })
    items.sort(key=lambda i: (i["cost"] is None, Decimal(i["cost"] or 0)))
    return {"items": items, "unpriced": unpriced, "at_top": top}
