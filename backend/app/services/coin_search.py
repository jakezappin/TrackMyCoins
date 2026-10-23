"""Coin search for the Add Coin form: "1878-S Morgan", "1962-S Roosevelt Proof", "1881-CC $1 DMPL", "1878 7TF Rev of
78" -> catalog entries (date, mint, variety, designation, PCGS #), best match first, from the bundled catalog."""

import re
from dataclasses import dataclass

from sqlalchemy import select
from sqlalchemy.orm import Session

from ..designations import COLORS, OTHERS, canonical
from ..models import CatalogEntry, Collection, CoinType
from ..series import BY_SLUG, FINISHES
from . import catalog, series_match

# "1881-S", "1881 S", "1880/79-CC" (overdate), "1882-O/S" (over-mintmark).
_DATE = re.compile(r"\b(1[6-9]\d\d|20\d\d)(?:/(\d{1,2}))?(?:\s*-\s*|\s+)?(?:(CC|[PDSOW])(?:/(CC|[PDSOW]))?)?\b(?![a-z])",
                   re.I)
_PROOF = re.compile(r"\b(proof|pf|pr)\b", re.I)
_WORD = re.compile(r"[0-9a-z/]+")
_FILLER = {"the", "of", "and", "coin", "dollar", "dollars", "cent", "cents", "half", "quarter", "dime", "nickel"}


@dataclass
class Query:
    year: int | None
    mint: str | None
    proof: bool
    silver: bool
    designation: str | None
    series_ids: list[int] | None  # None: any series
    words: set[str]  # what's left: variety words ("8tf", "reverse", "1878"...)


def parse(db: Session, q: str) -> Query:
    text = " ".join(q.split())
    year = mint = None
    over: set[str] = set()
    m = _DATE.search(text)
    if m:
        year, mint = int(m.group(1)), (m.group(3) or "").upper() or None
        if m.group(2):  # the catalog writes overdates "1880/79" (and short ones "8/7")
            over |= {f"{year}/{m.group(2)}", f"{str(year)[-1]}/{m.group(2)[-1]}"}
        if m.group(4):
            over.add(f"{mint}/{m.group(4).upper()}".lower())
        rest = (text[: m.start()] + " " + text[m.end():]).strip()
    else:
        rest = text
    proof = bool(_PROOF.search(rest))
    silver = bool(re.search(r"\bsilver\b", rest, re.I))
    rest_np = _PROOF.sub(" ", rest)
    designation = canonical(" ".join(w for w in re.findall(r"[A-Za-z]+", rest_np)
                                     if canonical(w) and w.upper() not in ("S", "D", "O", "P", "W")))
    named = series_match._candidates(rest_np, year) if re.search(r"[A-Za-z$]", rest_np) else []
    ids: list[int] | None = None
    if named:
        slugs = {s.slug for s in named}
        ids = list(db.scalars(select(CoinType.id).where(CoinType.slug.in_(slugs))))
    words = set(_WORD.findall(catalog.label_variety(rest_np))) - _FILLER
    # Series and designation words aren't variety words.
    for s in named:
        for k in (*series_match.KEYWORDS.get(s.slug, ()), s.name, s.plural):
            words -= set(_WORD.findall(k.lower()))
    words -= {w.lower() for w in COLORS + OTHERS} | {"silver", "cameo", "deep", "red", "brown", "mirror", "prooflike"}
    return Query(year, mint, proof, silver, designation, ids, words | {o.lower() for o in over})


def _finish(e: CatalogEntry, ct: CoinType) -> str:
    if e.strike != "PR":
        return "MS"
    if "SPR" in (ct.finishes or []) and catalog._is_silver(e.variety):
        return "SPR"
    return "PR" if "PR" in (ct.finishes or []) else "MS"


def search(db: Session, user_id: int, q: str, limit: int = 12) -> list[dict]:
    p = parse(db, q)
    if p.year is None and p.series_ids is None:
        return []  # nothing to go on yet ("Morg" before the series is clear)
    stmt = select(CatalogEntry, CoinType).join(CoinType, CoinType.id == CatalogEntry.coin_type_id)
    if p.year is not None:
        stmt = stmt.where(CatalogEntry.year == p.year)
    if p.series_ids is not None:
        stmt = stmt.where(CatalogEntry.coin_type_id.in_(p.series_ids))
    if p.mint:
        stmt = stmt.where(CatalogEntry.mint_mark == p.mint)
    if not re.search(r"\bvam\b", q, re.I):
        stmt = stmt.where(CatalogEntry.vam.is_(None))  # VAM listings only when asked for ("1888 VAM 11")
    rows = db.execute(stmt.limit(5000)).all()  # scored below, so a match isn't cut off before it's ranked

    def score(e: CatalogEntry) -> tuple:
        variety_words = set(_WORD.findall(catalog.label_variety(e.variety))) if e.variety else set()
        hits = len(p.words & variety_words)
        return (
            -(e.strike == ("PR" if p.proof else "MS")),
            # Silver proofs: only where a series has separate silver and clad proofs (not Silver Eagles).
            -(bool(p.silver) == catalog._is_silver(e.variety)) if p.proof and "SPR" in (finishes.get(e.coin_type_id) or []) else 0,
            -hits,
            len(variety_words - p.words),  # plainest first (a Reverse Proof only when asked for)
            -(e.designation == p.designation) if p.designation else (e.designation is not None),
            e.year or 0,
            e.mint_mark != "P",
            e.name,
        )

    finishes = {ct.id: ct.finishes for _, ct in rows}
    rows.sort(key=lambda r: score(r[0]))
    cols = db.scalars(select(Collection).where(Collection.user_id == user_id).order_by(Collection.number)).all()
    out = []
    for e, ct in rows[:limit]:
        finish = _finish(e, ct)
        col = next((c for c in cols if c.coin_type_id == ct.id and c.finish == finish), None)
        series = BY_SLUG.get(ct.slug)
        # The date as labels print it: overdate "1880/79-CC", over-mintmark "1882-O/S".
        od = re.search(rf"\b{e.year}/\d{{1,2}}\b", e.variety or "")
        om = re.search(r"\b(CC|[PDSOW])/(CC|[PDSOW])\b", e.variety or "")
        year_s = od.group(0) if od else str(e.year)
        mint_s = om.group(0) if om and e.mint_mark and om.group(1) == e.mint_mark else e.mint_mark
        date = year_s if e.mint_mark in (None, "P") else f"{year_s}-{mint_s}"
        out.append({
            "gsid": e.gsid, "pcgs_number": e.pcgs_number, "name": e.name,
            "label": " ".join(x for x in (date, series.name if series else ct.name) if x),
            "detail": " · ".join(x for x in (e.variety, FINISHES[finish][1] if finish != "MS" else None,
                                             e.designation) if x),
            "year": e.year, "mint_mark": e.mint_mark or "P", "variety": e.variety, "designation": e.designation,
            "vam": e.vam, "coin_type_id": ct.id, "series_name": ct.name, "finish": finish,
            "collection_id": col.id if col else None, "collection_name": col.name if col else None,
        })
    return out
