"""Greysheet catalog cache: find a coin's PCGS number from date, mint, designation and variety.

Each series in app/series.py lists the Greysheet catalog sections (nodes) for its business strikes and
proofs. We pull every collectible in them, cache them in `catalog_entries`, and match locally.
"""

import re
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone

from sqlalchemy import delete, func, select
from sqlalchemy.orm import Session

from ..config import get_settings
from ..designations import canonical
from ..models import CatalogEntry, Coin, CoinType
from ..series import BY_SLUG, FINISHES
from . import greysheet
from .greysheet import PricingError

STALE_AFTER = timedelta(days=30)
_GSA_RE = re.compile(r"GSA Hoard(?:,\s*(?:Hard|Soft) Package)?", re.I)


@dataclass
class SyncResult:
    nodes: list[int]
    count: int
    synced_at: datetime


@dataclass
class Candidate:
    pcgs_number: str | None
    gsid: int
    name: str
    variety: str | None
    designation: str | None
    exact: bool = False


@dataclass
class MatchResult:
    candidates: list[Candidate] = field(default_factory=list)
    best: Candidate | None = None
    message: str | None = None


# ---- Parsing ----------------------------------------------------------------------------


def _clean(v) -> str | None:
    """Basic-tier responses replace advanced fields with '[requires apiLevel=advanced]'."""
    if v is None:
        return None
    v = str(v).strip()
    return None if not v or v.startswith("[requires") else v


# CoinDate looks like "1881-S", "1880/79-CC", "1882-O/S", "1887/6", "1878 8TF", "1793 Chain", "1840-C"
# (Charlotte gold), "2011-(W)" (struck at West Point but carrying no mint mark, e.g. bullion eagles) or
# "1776~2026-D" (the dual-dated Semiquincentennial coins: the year is the second one).
# "1991-95-P" (the WWII 50th Anniversary commemoratives, dated 1991-1995 and issued in 1993) is rewritten first.
_DUAL_ISSUED = {"1991-95": "1993"}
_DATE_RE = re.compile(
    r"^(?P<dual>1776~)?(?P<year>1[789]\d\d|20\d\d)(?P<over>/\d{1,2})?"
    r"(?:-(?:(?P<mint>CC|C|O|S|D|W|P)(?P<mint_over>/(?:CC|C|O|S|D))?|\((?P<struck>[A-Z]{1,2})\)))?"
    r"(?:\s+(?P<extra>.+))?$"
)
# Varieties that don't distinguish a coin (1921 "Morgan" just separates it from the Peace dollar).
_IGNORED_VARIETIES = {"MORGAN", "SILVER EAGLE", "5OZ SILVER", "PEACE", "S$1 MORGAN", "S$1 PEACE", "S$1"}


def parse_collectible(d: dict) -> dict | None:
    """Normalize a Greysheet CollectibleDto. Returns None for entries that aren't a specific coin."""
    name = _clean(d.get("Name")) or ""
    # Entries with a UiParentId are sub-varieties of a parent coin (VAMs, Sheldon numbers); keep parents.
    if d.get("UiParentId"):
        return None
    if "[TYPE]" in name.upper() or d.get("IsSet") is True or d.get("IsType") is True:
        return None
    coin_date = _clean(d.get("CoinDate")) or ""
    # Sets: "1776~2026-S-S" (mint repeated) and "1976-P,D" (coins from two mints): keep the first mint.
    coin_date = re.sub(r"-([A-Z]{1,2})(?:-\1|,[A-Z]{1,2})$", r"-\1", coin_date)
    for dual, issued in _DUAL_ISSUED.items():
        if coin_date.startswith(dual):
            coin_date = issued + coin_date[len(dual):]
            d = {**d, "Variety": ", ".join(x for x in ("1991-1995", _clean(d.get("Variety"))) if x)}
    m = _DATE_RE.match(coin_date)
    if not m:
        return None

    strike = (_clean(d.get("Desg")) or "MS").upper()
    if strike == "PF":
        strike = "PR"

    # Designation = the words after the strike at the end of the name: "... MS DMPL", "... PR RD CAM".
    designation = None
    tail = re.search(rf"\b{re.escape(strike)}((?:\s+[A-Z0-9]+)*)\s*$", name.upper())
    if tail:
        designation = canonical(tail.group(1))

    parts = []
    # Specimen and Special Mint Set strikes are collected with business strikes (an ATB 5 oz Satin Finish, a 1965
    # SMS dime): file them under MS, named so they keep a checklist line of their own.
    finish_note = None
    if strike in ("SP", "SMS"):
        tags = " ".join(x for x in (_clean(d.get("Variety")), _clean(d.get("Variety2"))) if x).upper()
        if strike == "SMS" and "SMS" not in tags:
            finish_note = "SMS"
        elif strike == "SP" and not any(w in tags for w in ("SATIN", "SPECIMEN", "SMS", "SPECIAL MINT")):
            finish_note = "Specimen"
        strike = "MS"
    if m.group("over"):
        parts.append(f"{m.group('year')}{m.group('over')}")
    if m.group("mint_over"):
        parts.append(f"{m.group('mint')}{m.group('mint_over')}")
    if m.group("struck"):
        parts.append(f"({m.group('struck')})")  # no mint mark on the coin
    denom = _clean(d.get("DenominationShort"))
    with_denom = bool(m.group("dual") and denom and re.fullmatch(r"\d+c|\$\d+", denom))
    if with_denom:
        parts.append(denom)  # America 250 mixes denominations: "25c Mayflower Compact"
    for v in (m.group("extra"), _clean(d.get("Variety")), _clean(d.get("Variety2"))):
        # "Morgan, Liberty Bell Privy" (the modern dollars): the series name isn't part of the variety.
        v = re.sub(r"^(?:S\$1 )?(?:Morgan|Peace)(?:, |$)", "", v or "").strip() or None
        # Sets: the coin count isn't part of the name ("Proof Set, 5 Coins" -> "Proof Set").
        v = re.sub(r"(?:^|,\s*)\d+ Coins$", "", v or "").strip(" ,") or None
        if v and v.upper() not in _IGNORED_VARIETIES:
            parts.append(v)
    if finish_note:
        parts.append(finish_note)

    return {
        "gsid": int(d["Gsid"]),
        "pcgs_number": _clean(d.get("PcgsNumber")),
        "ngc_id": d.get("NgcId") or None,
        "year": int(m.group("year")),
        "mint_mark": m.group("mint") or "P",
        "designation": designation,
        "strike": strike[:5],
        "variety": re.sub(r"^(\S+), ", r"\1 ", ", ".join(parts))[:255] if with_denom and len(parts) > 1
        else (", ".join(parts)[:255] or None),
        "name": name[:255],
    }


# ---- Sync -----------------------------------------------------------------------------------


def series_nodes(coin_type: CoinType) -> list[int]:
    overrides = get_settings().greysheet_node_overrides.get(coin_type.slug)
    if overrides:
        return list(overrides)
    s = BY_SLUG.get(coin_type.slug)
    if s is None or s.is_type_set:
        raise PricingError(f"No Greysheet catalog sections configured for {coin_type.name}")
    return list(dict.fromkeys([*s.ms_nodes, *s.pr_nodes]))


def sync(db: Session, coin_type: CoinType) -> SyncResult:
    nodes = series_nodes(coin_type)
    series = BY_SLUG.get(coin_type.slug)
    raw: list[tuple[int, dict]] = []
    with greysheet.client() as c:
        for nid in nodes:
            raw.extend((nid, d) for d in greysheet.get(c, "/GetCollectibleByNodeRequest", NodeId=nid))

    now = datetime.now(timezone.utc)
    rows: dict[int, dict] = {}
    for nid, d in raw:
        if d.get("Gsid") is None:
            continue
        parsed = parse_collectible(d)
        if parsed and series is not None:
            name = parsed["name"]
            if (series.only and not re.search(series.only, name)) or (series.skip and re.search(series.skip, name)):
                continue
        if parsed:
            if series is not None and series.is_set:
                parsed["strike"] = "MS"  # proof sets too: a set collection has one finish
            rows.setdefault(parsed["gsid"], {**parsed, "node_id": nid})
    if not rows:
        raise PricingError(f"Greysheet returned no {coin_type.name} items")

    db.execute(delete(CatalogEntry).where(CatalogEntry.coin_type_id == coin_type.id))
    db.add_all(CatalogEntry(coin_type_id=coin_type.id, synced_at=now, **r) for r in rows.values())
    db.commit()
    return SyncResult(nodes=nodes, count=len(rows), synced_at=now)


def status(db: Session, coin_type_id: int) -> tuple[int, datetime | None]:
    count, last = db.execute(
        select(func.count(CatalogEntry.id), func.max(CatalogEntry.synced_at)).where(
            CatalogEntry.coin_type_id == coin_type_id
        )
    ).one()
    return count, last


def ensure_synced(db: Session, coin_type: CoinType) -> None:
    count, last = status(db, coin_type.id)
    if last is not None and last.tzinfo is None:
        last = last.replace(tzinfo=timezone.utc)
    if count == 0 or last is None or datetime.now(timezone.utc) - last > STALE_AFTER:
        sync(db, coin_type)


def designations(db: Session, coin_type_id: int, finish: str) -> list[str]:
    """Distinct designations in the catalog for a series and finish, e.g. ['BN', 'RB', 'RD']."""
    strike = FINISHES[finish][2]
    rows = db.scalars(
        select(CatalogEntry.designation)
        .where(CatalogEntry.coin_type_id == coin_type_id, CatalogEntry.strike == strike)
        .distinct()
    ).all()
    return sorted({r for r in rows if r})


# ---- Matching ---------------------------------------------------------------------------------


def _is_silver(variety: str | None) -> bool:
    return bool(variety and re.search(r"\bsilver\b", variety, re.I))


# Overdates ("1880/79", "80/79", "1887/6", "8/7") and over-mintmarks ("O/S", "O/CC", "D/S").
# Not fractions like the 1936-D Buffalo's "3 1/2 Legs" (a digit, a space, then n/m).
_OVER_RE = re.compile(r"(?<!\d\s)\b\d{1,4}/\d{1,2}\b|\b[A-Z]{1,2}/[A-Z]{1,2}\b", re.I)


def _variety_hits(entries, variety: str, year: int, mint_mark: str) -> list:
    """Entries whose variety contains what the user typed. Tolerates the date and mint mark being typed too
    ("1880/79-CC", "1880-CC 80/79") and extra words ("1880/79 VAM-4")."""
    v = variety.strip().lower()
    hits = [e for e in entries if e.variety and v in e.variety.lower()]
    if hits:
        return hits
    # Drop a leading date ("1882-", "1880-CC ") and a trailing mint mark ("1880/79-CC"), then retry.
    mm = re.escape(mint_mark.lower())
    cleaned = re.sub(rf"^{year}(?:\s*-\s*{mm}(?![/a-z]))?(?=[\s,-]|$)[\s,-]*", "", v)
    cleaned = re.sub(rf"-\s*{mm}(?![/a-z])", "", cleaned).strip(" ,-")
    if cleaned and cleaned != v:
        hits = [e for e in entries if e.variety and cleaned in e.variety.lower()]
        if hits:
            return hits
    # Otherwise match on the overdate itself, comparing just the digits after the slash and the year it's on.
    for token in _OVER_RE.findall(cleaned or v):
        hits = [e for e in entries if e.variety and _same_over(token, e.variety, year)]
        if hits:
            return hits
    return []


def _same_over(token: str, catalog_variety: str, year: int) -> bool:
    """'80/79' and '1880/79' are the same overdate on an 1880 coin; so are '7/6' and '1887/6' on 1887."""
    def key(t: str) -> str | None:
        top, under = t.split("/")
        if top.isdigit() and under.isdigit():
            return under if str(year).endswith(top) else None
        return t.lower()
    k = key(token)
    return k is not None and any(key(t) == k for t in _OVER_RE.findall(catalog_variety))


def match(
    db: Session,
    coin_type_id: int,
    year: int,
    mint_mark: str,
    designation: str | None = None,
    finish: str = "MS",
    variety: str | None = None,
    gsa: str | None = None,  # "hard" | "soft" for coins in GSA holders
) -> MatchResult:
    strike = FINISHES.get(finish, FINISHES["MS"])[2]
    designation = canonical(designation)
    mint_mark = (mint_mark or "P").upper()

    entries = db.scalars(
        select(CatalogEntry).where(
            CatalogEntry.coin_type_id == coin_type_id,
            CatalogEntry.year == year,
            CatalogEntry.mint_mark == mint_mark,
            CatalogEntry.strike == strike,
        )
    ).all()
    entries = [e for e in entries if (e.designation or None) == designation]
    label = f"{year}{'' if mint_mark == 'P' else '-' + mint_mark} {designation or ''}".strip()
    if not entries:
        return MatchResult(message=f"No Greysheet catalog entry for {label}.")

    # Silver proof collections want the silver issue; regular proof collections want clad, when a
    # date has both (e.g. 1992-S Roosevelt). Only applies to series with silver proofs.
    coin_type = db.get(CoinType, coin_type_id)
    if coin_type and "SPR" in (coin_type.finishes or []) and strike == "PR":
        silver = [e for e in entries if _is_silver(e.variety)]
        clad = [e for e in entries if not _is_silver(e.variety)]
        if silver and clad:
            entries = silver if finish == "SPR" else clad

    # GSA holders are priced separately: keep only GSA entries for GSA coins, and drop them otherwise.
    gsa_entries = [e for e in entries if e.variety and "gsa" in e.variety.lower()]
    if gsa:
        packed = [e for e in gsa_entries if f"{gsa} pack" in e.variety.lower()]
        generic = [e for e in gsa_entries if "hard pack" not in e.variety.lower() and "soft pack" not in e.variety.lower()]
        entries = packed or generic
        if not entries:
            return MatchResult(message=f"Greysheet has no GSA {gsa.title()} Pack listing for {label}.")
    elif gsa_entries and len(gsa_entries) < len(entries):
        entries = [e for e in entries if e not in gsa_entries]

    # A variety typed on the coin (e.g. "Alabama", "8TF", "1880/79") narrows the list.
    if variety:
        hits = _variety_hits(entries, variety, year, mint_mark)
        if hits:
            entries = hits
        elif _OVER_RE.search(variety):
            # An overdate / over-mintmark the catalog doesn't list under that name: never quietly price it as
            # the regular date (worth far less). Offer the listings that are overdates instead.
            overs = [e for e in entries if e.variety and _OVER_RE.search(e.variety)] or entries
            cands = [Candidate(pcgs_number=e.pcgs_number, gsid=e.gsid, name=e.name, variety=e.variety,
                               designation=e.designation) for e in overs]
            return MatchResult(
                candidates=cands,
                message=f"Greysheet doesn't list “{variety.strip()}” for {label} under that name. Pick the right one.",
            )

    # Plain entries (no variety) first.
    entries.sort(key=lambda e: (bool(_GSA_RE.sub("", e.variety or "").strip(" ,")), e.pcgs_number is None, e.gsid))
    cands = [
        Candidate(pcgs_number=e.pcgs_number, gsid=e.gsid, name=e.name, variety=e.variety, designation=e.designation)
        for e in entries
    ]

    # A single plain entry wins (e.g. 1881-S over "1881-S GSA Hoard"); otherwise the user picks.
    # For GSA coins, the GSA label itself doesn't count as a variety.
    def extra_variety(v: str | None) -> str:
        return _GSA_RE.sub("", v or "").strip(" ,") if gsa else (v or "")

    plain = [c for c in cands if not extra_variety(c.variety)]
    best = plain[0] if len(plain) == 1 else cands[0] if len(cands) == 1 else None
    if best:
        best.exact = True
    msg = None if best else f"{len(cands)} possible matches for {label}. Pick the right one."
    return MatchResult(candidates=cands, best=best, message=msg)


def resolve_for_coin(db: Session, coin: Coin) -> Candidate:
    """Find (and remember) the PCGS number for a coin. Raises PricingError if it isn't unique."""
    ensure_synced(db, coin.coin_type)
    gsa = "hard" if coin.gsa_hard_pack else "soft" if coin.gsa_soft_pack else None
    result = match(
        db, coin.coin_type_id, coin.year, coin.mint_mark, coin.strike_designation, coin.collection.finish, coin.variety, gsa
    )
    if result.best is None:
        if result.candidates:
            opts = "; ".join(
                f"#{c.pcgs_number or '—'} {c.name}" for c in result.candidates[:6]
            )
            raise PricingError(
                f"More than one catalog match. Use Find on the coin's edit page to pick one. Options: {opts}"
            )
        raise PricingError(result.message or "No catalog match")
    if result.best.pcgs_number:
        coin.pcgs_number = result.best.pcgs_number
    if result.best.variety and not coin.variety:
        coin.variety = result.best.variety
    return result.best
