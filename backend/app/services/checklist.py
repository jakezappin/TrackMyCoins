"""Collection status: every date/mint in a series (for the collection's finish) and the coins owned for each.

The list of date/mints comes from the cached Greysheet catalog. Most series are checked off by year and
mint. Where one year has several designs or major varieties collected separately, they're checked off by
issue instead: commemoratives (e.g. "1936 Boone"), Washington quarters from 1999 on (State, Territories, ATB,
American Women), ATB 5 oz silver designs, the America 250 coins, Silver Eagle special issues, modern Morgan and
Peace dollar issues and the 1878 Philadelphia Morgan tail-feather varieties.
"""

import re
from dataclasses import dataclass, field

from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from ..models import CatalogEntry, Coin, CoinType, Collection
from ..series import BY_SLUG, FINISHES, SERIES_BY_NODE, type_set_members
from . import catalog
from .coins import on_hand


# Overdate / over-mintmark parts the catalog puts first in a variety, e.g. "1935/34" or "O/S".
_OVER = re.compile(r"^(\d{4}/\d{1,2}|[A-Z]{1,2}/[A-Z]{1,2})$")


def _parts(variety: str) -> tuple[str, list[str]]:
    parts = [p.strip() for p in variety.split(",") if p.strip()]
    over = [p for p in parts if _OVER.match(p)]
    rest = [p for p in parts if not _OVER.match(p)]
    return (rest[0] if rest else parts[0]), over


def _design(variety: str) -> str:
    """Design name only: 'Delaware' from 'Delaware, Clad'; 'Boone' from '1935/34, Boone'."""
    return _parts(variety)[0]


def _variety_with_overdate(variety: str) -> str:
    """The full variety, overdate last: 'Boone (1935/34)', 'Grant Memorial, with Star', 'Alabama, 2x2'."""
    parts = [p.strip() for p in variety.split(",") if p.strip()]
    over = [p for p in parts if _OVER.match(p)]
    rest = [p for p in parts if not _OVER.match(p)] or parts
    name = ", ".join(rest)
    return f"{name} ({', '.join(over)})" if over else name


def _full(variety: str) -> str:
    return variety.strip()


def _silver_eagle_issue(variety: str) -> str | None:
    """Silver Eagle issues collected on their own line: Burnished, Reverse Proof, Enhanced, privies, Type 1 / 2,
    anniversaries. The "struck at" bullion varieties (no mint mark; emergency strikes) go on the date's line."""
    parts = [p.strip() for p in variety.split(",") if p.strip()]
    if any(re.match(r"(Struck at|Emergency)", p, re.I) for p in parts):
        kept = [p for p in parts if re.fullmatch(r"Type \d", p)]
    else:
        kept = [p for p in parts if not re.fullmatch(r"(\$1 )?SILVER EAGLE|\([PSW]\)", p, re.I)]
    return ", ".join(kept) or None


# Mint & proof sets: the year's main set is the line ("1992-S"); variations keep their name ("1955 Box
# Packaging", "1936 Brilliant Finish"). Specialty sets (Prestige, Premier, quarters-only...) are listed under
# "Other sets", outside the count.
_SET_BASE = re.compile(r"^(?:\d+c |\$\d+ )?(?:Clad |Silver )?(?:Proof Set|Uncirculated Set|Special Mint Set)(?:,\s*|$)", re.I)
EXTRA_SETS = {
    "us-proof-sets": re.compile(r"Prestige|Quarters|Presidential|Innovation|Limited Edition|Bicentennial", re.I),
    "us-silver-proof-sets": re.compile(r"Premier|Limited Edition|Quarters|Silver Reverse Proof Set|Innovation", re.I),
    "us-mint-sets": re.compile(r"Presidential|America the Beautiful|\(ATB\)|40% Silver|Enhanced", re.I),
}


def _set_issue(variety: str) -> str | None:
    return _SET_BASE.sub("", variety).strip(" ,") or None


def set_line_name(slug: str, variety: str | None) -> str | None:
    """The checklist name of a set: None for the year's main set, else the variation or specialty set."""
    if not variety:
        return None
    extra = EXTRA_SETS.get(slug)
    return variety if extra and extra.search(variety) else _set_issue(variety)


# Where to check off by issue instead of just year + mint: series -> [(applies(year, mint), issue name from variety)].
ISSUE_RULES = {
    "classic-commemoratives": [(lambda y, m: True, _variety_with_overdate)],
    "washington-quarters": [(lambda y, m: y >= 1999, _design)],
    "modern-commemorative-halves": [(lambda y, m: True, _variety_with_overdate)],
    "modern-commemorative-dollars": [(lambda y, m: True, _variety_with_overdate)],
    # One line per design, and the collector Satin Finish versions on lines of their own.
    "atb-5oz-silver": [(lambda y, m: True, _full)],
    # Mixed denominations and designs, all dated 2026: "25c Mayflower Compact", "50c Enduring Liberty, ... Privy".
    "america-250": [(lambda y, m: True, _full)],
    "american-silver-eagles": [(lambda y, m: True, _silver_eagle_issue)],
    # 2021 CC and O privies, Enhanced Uncirculated, Diamond Field, Reverse Proofs: lines of their own.
    "us-mint-sets": [(lambda y, m: True, lambda v: set_line_name("us-mint-sets", v))],
    "us-proof-sets": [(lambda y, m: True, lambda v: set_line_name("us-proof-sets", v))],
    "us-silver-proof-sets": [(lambda y, m: True, lambda v: set_line_name("us-silver-proof-sets", v))],
    "modern-morgan-dollars": [(lambda y, m: True, _full)],
    "modern-peace-dollars": [(lambda y, m: True, _full)],
    # 8TF, 7TF Reverse of 1878, 7TF Reverse of 1879, 7/8TF Strong, 7/8TF Weak are collected as separate coins.
    "morgan-dollars": [(lambda y, m: y == 1878 and m == "P", _full)],
}

# Series that also offer a type set: one line per design, any date or mint.
TYPE_SET_SERIES = {"classic-commemoratives", "modern-commemorative-halves", "modern-commemorative-dollars"}
MODES = ("full", "type")


def modes_for(series_slug: str) -> list[str]:
    return list(MODES) if series_slug in TYPE_SET_SERIES else ["full"]


@dataclass
class Row:
    key: tuple
    year: int
    mint_mark: str
    variety: str | None
    order: int = 0  # Greysheet's catalog order (release order for issues)
    pcgs_numbers: set[str] = field(default_factory=set)
    coins: list[Coin] = field(default_factory=list)
    years: set[int] = field(default_factory=set)
    type_row: bool = False  # a type-set line: one design, any date
    label_text: str | None = None  # fixed label (mixed-series type sets)
    series_id: int | None = None  # mixed-series type sets: the series that owns this line
    extra: bool = False  # a specialty set: listed, not counted

    @property
    def label(self) -> str:
        if self.label_text:
            return self.label_text
        if self.type_row:
            lo, hi = min(self.years), max(self.years)
            return f"{self.variety} ({lo})" if lo == hi else f"{self.variety} ({lo}–{hi})"
        date = f"{self.year}" if self.mint_mark == "P" else f"{self.year}-{self.mint_mark}"
        return f"{date} {self.variety}" if self.variety else date


@dataclass
class Checklist:
    rows: list[Row]
    others: list[Coin]  # owned coins that don't match any catalog date/mint
    extras: list[Row] = field(default_factory=list)  # specialty sets: listed, not counted

    @property
    def filled(self) -> int:
        return sum(1 for r in self.rows if r.coins)


def _is_silver(v: str | None) -> bool:
    return bool(v and re.search(r"\bsilver\b", v, re.I))


def _issue(series_slug: str, year: int, mint: str, variety: str | None) -> str | None:
    """The issue name when this series/date is checked off by issue, else None."""
    if not variety:
        return None
    for applies, name in ISSUE_RULES.get(series_slug, []):
        if applies(year, mint):
            return name(variety)
    return None


def _norm(text: str) -> str:
    return re.sub(r"[^0-9a-z/]", "", text.lower())


def _words(text: str | None) -> set[str]:
    return set(re.findall(r"[0-9a-z/]+", (text or "").lower()))


def _best_variety_match(rows: list["Row"], coin_variety: str | None) -> "Row | None":
    """The row whose variety words all appear in the coin's variety; the most specific one wins.

    '1935/34 Boone' -> 'Boone (1935/34)' over 'Boone'; '7/8TF Strong' -> '7/8TF, Strong' (never '8TF').
    """
    words = _words(coin_variety)
    if not words:
        return None
    hits = [r for r in rows if r.variety and _words(r.variety) <= words]
    if not hits:
        return None
    hits.sort(key=lambda r: -len(_words(r.variety)))
    if len(hits) > 1 and len(_words(hits[0].variety)) == len(_words(hits[1].variety)):
        return None  # tie: ambiguous
    return hits[0]


def _catalog_entries(db: Session, col: Collection) -> list[CatalogEntry]:
    strike = FINISHES[col.finish][2]
    entries = db.scalars(
        select(CatalogEntry).where(CatalogEntry.coin_type_id == col.coin_type_id, CatalogEntry.strike == strike)
    ).all()
    if col.finish == "SPR":
        # Silver proofs: dates struck in both silver and clad (e.g. 1992-S onward); keep the silver ones.
        dates_with_clad = {(e.year, e.mint_mark) for e in entries if not _is_silver(e.variety)}
        entries = [e for e in entries if _is_silver(e.variety) and (e.year, e.mint_mark) in dates_with_clad]
    elif col.finish == "PR" and "SPR" in (col.coin_type.finishes or []):
        # Regular proofs: leave out the optional silver issues (they belong to the Silver Proof set).
        dates_with_clad = {(e.year, e.mint_mark) for e in entries if not _is_silver(e.variety)}
        entries = [e for e in entries if not (_is_silver(e.variety) and (e.year, e.mint_mark) in dates_with_clad)]
    return entries


def _held_coins(db: Session, col: Collection) -> list[Coin]:
    return db.scalars(
        on_hand(select(Coin).where(Coin.collection_id == col.id))
        .options(selectinload(Coin.photos), selectinload(Coin.price_quotes))
        .order_by(Coin.details, Coin.grade.desc(), Coin.grade_plus.desc(), Coin.inventory_number)
    ).all()


def _build_mixed_type_set(db: Session, col: Collection, series) -> Checklist:
    """One line per design across several series (e.g. the Gold Type Set)."""
    types = {t.slug: t for t in db.scalars(select(CoinType)).all()}
    members = [types[m.slug] for m in type_set_members(series) if m.slug in types]
    for ct in members:
        catalog.ensure_synced(db, ct)
    entries = db.scalars(
        select(CatalogEntry).where(CatalogEntry.coin_type_id.in_([ct.id for ct in members]), CatalogEntry.strike == "MS")
    ).all()
    by_node: dict[int, list[CatalogEntry]] = {}
    for e in entries:
        by_node.setdefault(e.node_id, []).append(e)

    rows: list[Row] = []
    for i, (label, node) in enumerate(series.type_rows):
        es = by_node.get(node, [])
        owner = types.get(SERIES_BY_NODE[node].slug)
        rows.append(
            Row(
                key=(node,),
                year=min((e.year for e in es), default=0),
                mint_mark="P",
                variety=None,
                order=i,
                label_text=label,
                series_id=owner.id if owner else None,
                years={e.year for e in es},
                pcgs_numbers={e.pcgs_number for e in es if e.pcgs_number},
            )
        )

    others = []
    for coin in _held_coins(db, col):
        row = None
        if coin.pcgs_number:
            row = next((r for r in rows if r.series_id == coin.coin_type_id and coin.pcgs_number in r.pcgs_numbers), None)
        if row is None:
            # Same series and a year that design was struck (e.g. 1870 $20 -> Liberty Type 2).
            fits = [r for r in rows if r.series_id == coin.coin_type_id and coin.year in r.years]
            row = fits[0] if len(fits) == 1 else None
        (row.coins if row else others).append(coin)
    return Checklist(rows=rows, others=others)


def build(db: Session, col: Collection, mode: str = "full") -> Checklist:
    series = BY_SLUG.get(col.coin_type.slug)
    if series is not None and series.is_type_set:
        return _build_mixed_type_set(db, col, series)
    catalog.ensure_synced(db, col.coin_type)
    slug = col.coin_type.slug
    type_set = mode == "type" and slug in TYPE_SET_SERIES

    rows: dict[tuple, Row] = {}
    for e in _catalog_entries(db, col):
        if type_set:
            if not e.variety:
                continue
            variety = _design(e.variety)
            key = (variety.lower(),)
        else:
            variety = _issue(slug, e.year, e.mint_mark, e.variety)
            key = (e.year, e.mint_mark, (variety or "").lower())
        # Entries are stored in Greysheet's order, so the lowest id is the earliest-listed.
        row = rows.setdefault(
            key,
            Row(key=key, year=e.year, mint_mark=e.mint_mark, variety=variety, order=e.id, type_row=type_set),
        )
        if slug in EXTRA_SETS and e.variety and EXTRA_SETS[slug].search(e.variety):
            row.extra = True
        row.order = min(row.order, e.id)
        row.year = min(row.year, e.year)
        row.years.add(e.year)
        if e.pcgs_number:
            row.pcgs_numbers.add(e.pcgs_number)

    coins = db.scalars(
        on_hand(select(Coin).where(Coin.collection_id == col.id))
        .options(selectinload(Coin.photos), selectinload(Coin.price_quotes))
        .order_by(Coin.details, Coin.grade.desc(), Coin.grade_plus.desc(), Coin.inventory_number)
    ).all()

    others = []
    for coin in coins:
        row = None
        # Best: the coin's PCGS number belongs to a row. Otherwise year + mint (+ issue).
        if coin.pcgs_number:
            row = next((r for r in rows.values() if coin.pcgs_number in r.pcgs_numbers), None)
        if row is None and type_set:
            # Any date or mint of the design counts; the coin's variety names the design.
            row = _best_variety_match(list(rows.values()), coin.variety)
        elif row is None:
            candidates = [r for r in rows.values() if r.year == coin.year and r.mint_mark == coin.mint_mark]
            if any(r.variety for r in candidates):
                # Several issues that date: the coin's variety says which one (e.g. "Delaware", "8TF").
                hit = _best_variety_match(candidates, coin.variety)
                plain = [r for r in candidates if not r.variety]
                # Nothing more specific matches: the date's plain line (a year's main set, say).
                candidates = [hit] if hit else plain if len(plain) == 1 else []
            row = candidates[0] if len(candidates) == 1 else None
        (row.coins if row else others).append(coin)

    # Where each issue first appears in the catalog.
    first_of_issue: dict[tuple, int] = {}
    for r in rows.values():
        if r.variety:
            k = (r.year, r.variety.lower())
            first_of_issue[k] = min(first_of_issue.get(k, r.order), r.order)

    def sort_key(r: Row):
        # Within a year, follow Greysheet's catalog order (P before branch mints, issues in release order),
        # keeping all mints of one issue together.
        position = first_of_issue.get((r.year, r.variety.lower()), r.order) if r.variety else r.order
        return (r.year, position, MINT_ORDER.get(r.mint_mark, 9))

    ordered = sorted(rows.values(), key=sort_key)
    return Checklist(rows=[r for r in ordered if not r.extra], others=others, extras=[r for r in ordered if r.extra])


# Conventional order within a year: Philadelphia first, then branch mints.
MINT_ORDER = {"P": 0, "W": 1, "D": 2, "CC": 3, "O": 4, "S": 5}
