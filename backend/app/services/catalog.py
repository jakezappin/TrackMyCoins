"""Greysheet catalog cache: find a coin's PCGS number from date, mint, designation and variety.

Each series in app/series.py lists the Greysheet catalog sections (nodes) for its business strikes and
proofs. We pull every collectible in them, cache them in `catalog_entries`, and match locally.
"""

import gzip
import json
import re
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from pathlib import Path

import httpx
from sqlalchemy import and_, delete, func, or_, select
from sqlalchemy.orm import Session

from ..config import get_settings
from ..designations import canonical
from ..models import CatalogEntry, Coin, CoinType
from ..series import BY_SLUG, FINISHES
from . import greysheet, quota
from .greysheet import AmbiguousMatch, PricingError

_GSA_RE = re.compile(r"GSA Hoard(?:,\s*(?:Hard|Soft) Package)?", re.I)


@dataclass
class SyncResult:
    nodes: list[int]
    count: int
    synced_at: datetime


@dataclass
class Candidate:
    pcgs_number: str | None
    gsid: int | None  # None: not a Greysheet listing (a Cameo PCGS number worked out from the plain proof's)
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


# Die-marriage and attribution numbers: sub-listings carrying one are varieties for specialists, not separate issues.
# Any "letters-number" code: VAM-3, FS-101, JD-1, BD-2, HM-8, O-101 (Overton), B-3 (Bolender), S-189, C-1, N-10...
_ATTRIBUTION = re.compile(r"\b[A-Z]{1,4}-\s*\d")
# Morgan and Peace VAM sub-listings are kept, though: Greysheet prices them on their own ("Doubled Ear, VAM-11").
_VAM = re.compile(r"\bVAM[\s-]*(\d+(?:\.\d+)?[A-Z]?)\b", re.I)


# Cherrypickers' Guide numbers: "FS-101", "FS-101/803", "FS-1.5" (older numbering), "FS-901" ...
_FS = re.compile(r"\bFS[\s-]*(\d{1,3}(?:\.\d+)?[A-Z]?(?:\s*/\s*\d{1,3}[A-Z]?)?)\b", re.I)


def fs_key(text: str | None) -> str | None:
    """'Doubled Die Obverse, FS-101' -> '101'; 'FS-101/803' -> '101/803'; None without an FS number."""
    m = _FS.search(text or "")
    return re.sub(r"\s+", "", m.group(1)).upper() if m else None


def vam_key(text: str | None) -> str | None:
    """'VAM-11', 'vam 2a', '11', '14.1' -> '11', '2A', '14.1' (how VAM listings are keyed)."""
    t = (text or "").strip()
    m = _VAM.search(t) or re.fullmatch(r"\s*(\d+(?:\.\d+)?[A-Z]?)\s*", t, re.I)
    return m.group(1).upper() if m else None


def _designation_of(d: dict) -> str | None:
    name = (_clean(d.get("Name")) or "").upper()
    strike = (_clean(d.get("Desg")) or "MS").upper()
    tail = re.search(rf"\b{re.escape(strike)}((?:\s+[A-Z0-9]+)*)\s*$", name)
    return canonical(tail.group(1)) if tail else None


def designation_child(d: dict, top: dict | None) -> bool:
    """Greysheet files many priced listings under another coin: designations (PL, DMPL, CAM, DCAM, FB, FH, RD...),
    sometimes several levels deep (DCAM under CAM under PR), the plain proof under a modern DCAM listing (1969-S
    10c PR under PR DCAM), named varieties (1964 "Blunt 9" PR) and the odd misfiled date. Those are kept. Sub-listings
    for attributions (VAMs, FS numbers, Sheldon / Cohen / JD die marriages) aren't. `top` is the top-level ancestor."""
    if top is None:
        return False
    if (_clean(d.get("Variety2")) or "") != (_clean(top.get("Variety2")) or ""):
        return False  # ATB 5 oz keep the park in Variety2 on parent and child alike; elsewhere it's an attribution
    if _ATTRIBUTION.search(" ".join(x for x in (_clean(d.get("Variety")), _clean(d.get("Name"))) if x)):
        return False
    same = (_designation_of(d) == _designation_of(top)
            and (_clean(d.get("Variety")) or "") == (_clean(top.get("Variety")) or "")
            and (_clean(d.get("CoinDate")) or "") == (_clean(top.get("CoinDate")) or ""))
    return not same


def parse_collectible(d: dict, top: dict | None = None) -> dict | None:
    """Normalize a Greysheet CollectibleDto. Returns None for entries that aren't a specific coin. `top`: a
    sub-listing's (UiParentId) top-level ancestor."""
    name = _clean(d.get("Name")) or ""
    # Sub-listings are kept only when they're the parent coin with a designation (see designation_child), or a VAM.
    vam = fs = None
    if d.get("UiParentId") and not designation_child(d, top):
        text = " ".join(x for x in (name, _clean(d.get("Variety")), _clean(d.get("Variety2"))) if x)
        m = _VAM.search(text)
        if m:
            vam = m.group(1).upper()
        elif (fs := fs_key(text)) is None:
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
        "vam": vam,
        "fs": fs,
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
    """Download the series' catalog from Greysheet (one call per section, counted against the site's daily limit)."""
    nodes = series_nodes(coin_type)
    quota.spend_site("greysheet", len(nodes))
    series = BY_SLUG.get(coin_type.slug)
    raw: list[tuple[int, dict]] = []
    with greysheet.client() as c:
        for nid in nodes:
            raw.extend((nid, d) for d in greysheet.get(c, "/GetCollectibleByNodeRequest", NodeId=nid))

    now = datetime.now(timezone.utc)
    rows: dict[int, dict] = {}
    by_gsid = {d.get("Gsid"): d for _, d in raw if d.get("Gsid") is not None}

    def top_of(d: dict) -> dict | None:
        seen = set()
        while d is not None and d.get("UiParentId") and d.get("Gsid") not in seen:
            seen.add(d.get("Gsid"))
            d = by_gsid.get(d.get("UiParentId"))
        return d

    for nid, d in raw:
        if d.get("Gsid") is None:
            continue
        parsed = parse_collectible(d, top_of(d) if d.get("UiParentId") else None)
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
    if series is not None and series.is_set:
        # Two sets the same year differing only in coin count (1942 proof: 5 or 6 coins): keep the count.
        same: dict[tuple, list[dict]] = {}
        for r in rows.values():
            same.setdefault((r["year"], r["mint_mark"], r["variety"]), []).append(r)
        for group in same.values():
            if len(group) > 1:
                for r in group:
                    m = re.search(r"(\d+) Coins", r["name"])
                    if m:
                        r["variety"] = ", ".join(x for x in (r["variety"], f"{m.group(1)} Coins") if x)

    db.execute(delete(CatalogEntry).where(CatalogEntry.coin_type_id == coin_type.id))
    db.add_all(CatalogEntry(coin_type_id=coin_type.id, synced_at=now, **r) for r in rows.values())
    db.commit()
    return SyncResult(nodes=nodes, count=len(rows), synced_at=now)


# ---- Bundled catalog -------------------------------------------------------------------------------------------
# Every supported series' catalog, downloaded once (scripts/build_catalog.py) and shipped with the app, so searching
# and matching never wait on Greysheet. A series missing from the bundle is still downloaded the first time it's
# needed.

BUNDLE = Path(__file__).resolve().parent.parent / "catalog_bundle.json.gz"
_FIELDS = ("gsid", "node_id", "pcgs_number", "ngc_id", "year", "mint_mark", "designation", "strike", "variety", "name",
           "vam", "fs")


def regular():
    """Catalog rows that are dates' own listings: not VAM or FS die-variety listings (priced only when asked for)."""
    return and_(CatalogEntry.vam.is_(None), CatalogEntry.fs.is_(None))


def export_bundle(db: Session, path: Path = BUNDLE) -> int:
    rows = db.execute(select(CatalogEntry, CoinType.slug).join(CoinType, CoinType.id == CatalogEntry.coin_type_id)
                      .order_by(CoinType.slug, CatalogEntry.gsid)).all()
    data = {"built": datetime.now(timezone.utc).isoformat(), "entries": [
        {"series": slug, **{k: getattr(e, k) for k in _FIELDS}} for e, slug in rows]}
    with gzip.open(path, "wt") as f:
        json.dump(data, f, separators=(",", ":"))
    return len(rows)


def seed_from_bundle(db: Session, path: Path = BUNDLE) -> int:
    """Load the bundled catalog for series that have none yet (or an older one). Returns entries added."""
    if not path.exists():
        return 0
    with gzip.open(path, "rt") as f:
        data = json.load(f)
    built = datetime.fromisoformat(data["built"])
    types = {t.slug: t.id for t in db.scalars(select(CoinType))}
    by_series: dict[str, list[dict]] = {}
    for e in data["entries"]:
        by_series.setdefault(e.pop("series"), []).append(e)
    added = 0
    for slug, entries in by_series.items():
        type_id = types.get(slug)
        if type_id is None:
            continue
        count, last = status(db, type_id)
        if last is not None and last.tzinfo is None:
            last = last.replace(tzinfo=timezone.utc)
        if count and last is not None and last >= built:
            continue  # what we have is as new as the bundle
        db.execute(delete(CatalogEntry).where(CatalogEntry.coin_type_id == type_id))
        gsids = [e["gsid"] for e in entries]
        db.execute(delete(CatalogEntry).where(CatalogEntry.gsid.in_(gsids)))  # e.g. moved to another series
        db.add_all(CatalogEntry(coin_type_id=type_id, synced_at=built, **e) for e in entries)
        added += len(entries)
    db.commit()
    return added


def status(db: Session, coin_type_id: int) -> tuple[int, datetime | None]:
    count, last = db.execute(
        select(func.count(CatalogEntry.id), func.max(CatalogEntry.synced_at)).where(
            CatalogEntry.coin_type_id == coin_type_id
        )
    ).one()
    return count, last


# A series whose catalog just failed to download isn't tried again for an hour (a want list with many wants
# in it, say, would otherwise download it once per want).
RETRY_AFTER = timedelta(hours=1)
_failed: dict[int, tuple[datetime, str]] = {}


def ensure_synced(db: Session, coin_type: CoinType) -> None:
    count, last = status(db, coin_type.id)
    if last is not None and last.tzinfo is None:
        last = last.replace(tzinfo=timezone.utc)
    if count == 0 or last is None:
        failed = _failed.get(coin_type.id)
        if failed and datetime.now(timezone.utc) - failed[0] < RETRY_AFTER:
            if count:
                return  # use the catalog we have
            raise PricingError(failed[1])
        try:
            sync(db, coin_type)
            _failed.pop(coin_type.id, None)
        except (PricingError, httpx.HTTPError, quota.QuotaExceeded) as e:
            _failed[coin_type.id] = (datetime.now(timezone.utc), str(e) or "Greysheet catalog unavailable")
            if count:
                return
            raise


# What graders call a designation vs Greysheet's (and PCGS's) name for it, per series: NGC's Full Torch Roosevelt
# dime is PCGS's and Greysheet's Full Bands.
SERIES_DESIGNATIONS = {"roosevelt-dimes": {"FT": "FB"}}


def catalog_designation(slug: str | None, designation: str | None) -> str | None:
    """A designation in the catalog's words: "FT" -> "FB" on a Roosevelt dime, "FT PL" -> "PL FB"."""
    d = canonical(designation)
    aliases = SERIES_DESIGNATIONS.get(slug or "")
    if not d or not aliases:
        return d
    return canonical(" ".join(aliases.get(w, w) for w in d.split()))


_CAMEO = ("CAM", "DCAM")
_MIRROR = ("PL", "DMPL")


def designations(db: Session, coin_type_id: int, finish: str) -> list[str]:
    """Distinct designations in the catalog for a series and finish, e.g. ['BN', 'RB', 'RD']."""
    strike = FINISHES[finish][2]
    rows = db.scalars(
        select(CatalogEntry.designation)
        .where(CatalogEntry.coin_type_id == coin_type_id, CatalogEntry.strike == strike, regular())
        .distinct()
    ).all()
    found = {r for r in rows if r}
    ct = db.get(CoinType, coin_type_id)
    for alias, name in SERIES_DESIGNATIONS.get(ct.slug if ct else "", {}).items():
        # Both graders' words: NGC's "FT" and PCGS's "FB" Roosevelts are the same coin (priced as FB).
        found |= {canonical(d.replace(name, alias)) for d in found if name in d.split()}
    colors = sorted({w for d in found for w in d.split() if w in ("RD", "RB", "BN")})
    if strike == "PR":
        # Every proof can be Cameo or Deep/Ultra Cameo, whether or not the catalog lists it. Copper proofs carry
        # their color too (RD CAM, RD DCAM...).
        found |= {f"{c} {cam}" for c in colors for cam in _CAMEO} if colors else set(_CAMEO)
    elif strike == "MS" and not _is_set_series(db, coin_type_id):
        # Any business strike can be graded Prooflike or Deep Mirror Prooflike (NGC designates any series).
        found |= {f"{c} PL" for c in colors} if colors else set(_MIRROR)
    return sorted(found)


def _is_set_series(db: Session, coin_type_id: int) -> bool:
    ct = db.get(CoinType, coin_type_id)
    s = BY_SLUG.get(ct.slug) if ct else None
    return bool(s and s.is_set)



def _without_cameo(designation: str | None) -> str | None:
    return " ".join(w for w in (designation or "").split() if w not in _CAMEO) or None


def cameo_pcgs_number(plain: str | None, designation: str | None) -> str | None:
    """PCGS numbers Cameo and Deep Cameo proofs as 8 or 9 in front of the plain proof's number (1895 $1 PR 7330,
    CAM 87330, DCAM 97330). Only for the four-digit numbers that rule holds for."""
    words = (designation or "").split()
    if not plain or not plain.isdigit() or len(plain) != 4:
        return None
    if "DCAM" in words:
        return "9" + plain
    if "CAM" in words:
        return "8" + plain
    return None


# ---- Matching ---------------------------------------------------------------------------------


def _is_silver(variety: str | None) -> bool:
    return bool(variety and re.search(r"\bsilver\b", variety, re.I))


# Overdates ("1880/79", "80/79", "1887/6", "8/7") and over-mintmarks ("O/S", "O/CC", "D/S").
# Not fractions like the 1936-D Buffalo's "3 1/2 Legs" (a digit, a space, then n/m).
_OVER_RE = re.compile(r"(?<!\d\s)\b\d{1,4}/\d{1,2}\b|\b[A-Z]{1,2}/[A-Z]{1,2}\b", re.I)


def label_variety(text: str | None) -> str:
    """A variety as labels print it, in the catalog's words: "8 TF" -> "8tf", "7TF Rev of 78" ->
    "7tf reverse of 1878", "7 Tail Feathers" -> "7tf"."""
    t = (text or "").lower()
    t = re.sub(r"tail\s*feathers?", "tf", t)
    t = re.sub(r"\b(\d(?:/\d)?)\s+tf\b", r"\1tf", t)
    t = re.sub(r"\brev\b\.?", "reverse", t)
    return re.sub(r"\bof\s*'?(\d{2})\b", r"of 18\1", t)


def _variety_hits(entries, variety: str, year: int, mint_mark: str) -> list:
    """Entries whose variety contains what the user typed. Tolerates the date and mint mark being typed too
    ("1880/79-CC", "1880-CC 80/79") and extra words ("1880/79 VAM-4")."""
    v = variety.strip().lower()
    hits = [e for e in entries if e.variety and v in e.variety.lower()]
    if hits:
        return hits
    tf = label_variety(v)
    if tf != v:
        # "7TF Rev of 78": every word in the catalog's variety ("7TF Reverse of 1878").
        words = set(re.findall(r"[0-9a-z/]+", tf))
        hits = [e for e in entries if e.variety and set(re.findall(r"[0-9a-z/]+", e.variety.lower())) <= words]
        if hits:
            hits.sort(key=lambda e: -len(e.variety))
            return [h for h in hits if len(h.variety) == len(hits[0].variety)]
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
    vam: str | None = None,  # a Morgan / Peace VAM: its own listing when Greysheet has one
    specials: bool = True,  # look for the coin's VAM / FS die-variety listing (False: the date's own listings)
) -> MatchResult:
    strike = FINISHES.get(finish, FINISHES["MS"])[2]
    ct = db.get(CoinType, coin_type_id)
    designation = catalog_designation(ct.slug if ct else None, designation)
    mint_mark = (mint_mark or "P").upper()

    entries = db.scalars(
        select(CatalogEntry).where(
            CatalogEntry.coin_type_id == coin_type_id,
            CatalogEntry.year == year,
            CatalogEntry.mint_mark == mint_mark,
            CatalogEntry.strike == strike,
        )
    ).all()
    vams = [e for e in entries if e.vam]
    fss = [e for e in entries if e.fs]
    entries = [e for e in entries if not e.vam and not e.fs]
    all_entries = entries
    entries = [e for e in entries if (e.designation or None) == designation]
    label = f"{year}{'' if mint_mark == 'P' else '-' + mint_mark} {designation or ''}".strip()
    key, kind, pool = vam_key(vam), "VAM", vams
    if not (key and vams) and (fkey := fs_key(variety)) and fss:
        key, kind, pool = fkey, "FS", fss
    if specials and key and pool:
        listed = _same_attribution(pool, kind, key)
        hit = [e for e in listed if (e.designation or None) == designation]
        if hit:
            hit.sort(key=lambda e: (e.pcgs_number is None, e.gsid))
            e = hit[0]
            best = Candidate(pcgs_number=e.pcgs_number, gsid=e.gsid, name=e.name, variety=e.variety,
                             designation=e.designation)
            best.exact = True
            return MatchResult(candidates=[best], best=best)
        if kind == "FS":  # the date's own listing: the variety without its FS number ("Doubled Die Obverse")
            variety = _FS.sub("", variety or "").strip(" ,;-") or None
        plain = match(db, coin_type_id, year, mint_mark, designation, finish, variety, gsa, specials=False)
        what = f"{kind}-{key} {designation}" if listed and designation else f"{kind}-{key}"
        note = f"Greysheet doesn't list {what} for {label.split()[0]}, so it's priced as the regular date."
        plain.message = f"{note} {plain.message}" if plain.message else note
        return plain
    if not entries and strike == "PR" and designation and set(designation.split()) & set(_CAMEO):
        # A Cameo / Deep Cameo proof the catalog doesn't list: PCGS's number for it, from the plain proof's.
        base = _without_cameo(designation)
        plain = [e for e in all_entries if (e.designation or None) == base and not e.variety]
        number = cameo_pcgs_number(plain[0].pcgs_number, designation) if len(plain) == 1 else None
        if number:
            word = "Deep Cameo" if "DCAM" in designation.split() else "Cameo"
            best = Candidate(pcgs_number=number, gsid=None, name=f"{plain[0].name} {word}", variety=None,
                             designation=designation)
            best.exact = True
            return MatchResult(candidates=[best], best=best)
    if not entries and designation and set(designation.split()) & set(_MIRROR):
        # A Prooflike coin Greysheet doesn't list as one (a PL Peace dollar): price it as the regular coin, and say so.
        base = " ".join(w for w in designation.split() if w not in _MIRROR) or None
        plain = match(db, coin_type_id, year, mint_mark, base, finish, variety, gsa)
        word = "DMPL" if "DMPL" in designation.split() else "PL"
        note = f"Greysheet doesn't list a {word} {label.split()[0]}, so it's matched to the regular coin (no {word} premium)."
        plain.message = f"{note} {plain.message}" if plain.message else note
        return plain
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
    if coin.is_error:
        raise PricingError("Error coins aren't in the catalog.")
    ensure_synced(db, coin.coin_type)
    gsa = "hard" if coin.gsa_hard_pack else "soft" if coin.gsa_soft_pack else None
    result = match(
        db, coin.coin_type_id, coin.year, coin.mint_mark, coin.strike_designation, coin.collection.finish, coin.variety, gsa,
        vam=coin.vam,
    )
    if result.best is None:
        if result.candidates:
            raise AmbiguousMatch("More than one catalog listing fits this coin. Pick the right one on the coin's page.",
                                 result.candidates)
        raise PricingError(result.message or "No catalog match")
    if result.best.pcgs_number:
        coin.pcgs_number = result.best.pcgs_number
    if result.best.variety and not coin.variety:
        coin.variety = result.best.variety
    return result.best


def _same_attribution(pool: list, kind: str, key: str) -> list:
    """Listings with this VAM / FS number. An FS number typed alone ("FS-101") also finds a combined listing
    ("FS-101/803") when it's the only one."""
    attr = (lambda e: e.vam) if kind == "VAM" else (lambda e: e.fs)
    exact = [e for e in pool if attr(e) == key]
    if exact or kind == "VAM" or "/" in key:
        return exact
    part = [e for e in pool if key in (attr(e) or "").split("/")]
    return part if len({attr(e) for e in part}) == 1 else []


def vam_listing(db: Session, coin: Coin, sync: bool = True) -> CatalogEntry | None:
    """The coin's own die-variety listing, if Greysheet has one: its VAM's (Morgan / Peace), else the FS number in its
    variety ("Doubled Die Obverse, FS-101"). Same date, mint, strike and designation. `sync`: download the series'
    catalog first if there's none (not while a coin is being saved)."""
    vkey, fkey = vam_key(coin.vam), fs_key(coin.variety)
    if not (vkey or fkey) or coin.is_error:
        return None
    if sync:
        try:
            ensure_synced(db, coin.coin_type)
        except (PricingError, httpx.HTTPError, quota.QuotaExceeded):
            return None  # no catalog to hand: priced as the date
    strike = FINISHES.get(coin.collection.finish, FINISHES["MS"])[2]
    rows = db.scalars(select(CatalogEntry).where(
        CatalogEntry.coin_type_id == coin.coin_type_id, CatalogEntry.year == coin.year,
        CatalogEntry.mint_mark == (coin.mint_mark or "P").upper(), CatalogEntry.strike == strike,
        or_(CatalogEntry.vam.isnot(None), CatalogEntry.fs.isnot(None)))).all()
    designation = catalog_designation(coin.coin_type.slug, coin.strike_designation)
    rows = [e for e in rows if (e.designation or None) == designation]
    hits = _same_attribution([e for e in rows if e.vam], "VAM", vkey) if vkey else []
    if not hits and fkey:
        hits = _same_attribution([e for e in rows if e.fs], "FS", fkey)
    hits.sort(key=lambda e: (e.pcgs_number is None, e.gsid))
    return hits[0] if hits else None
