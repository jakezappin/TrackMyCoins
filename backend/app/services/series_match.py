"""Which series a coin belongs to, from what a spreadsheet row or a PCGS lookup tells us.

Used by bulk import to sort a mixed spreadsheet into collections, and to catch coins that don't belong in the
collection being imported into (a 1921 Peace Dollar in a Morgan collection, say).
"""

import json
import re
from dataclasses import dataclass
from datetime import date
from functools import cache
from pathlib import Path

from ..series import BY_SLUG, SERIES, Series

# Checked against Greysheet's full catalog (2026-10-17); its one omission, the 1802/"1" $2.50, is real and kept.
# Years each series was struck (any mint, business strikes or proofs), gaps included: no Buffalo Nickels or
# Mercury Dimes were made in 1922, no Peace Dollars 1929-1933, and so on. Open-ended ranges are still being made.
YEARS: dict[str, tuple[tuple[int, int | None], ...]] = {
    "half-cents": ((1793, 1797), (1800, 1800), (1802, 1811), (1825, 1826), (1828, 1829), (1831, 1836), (1840, 1857)),
    "large-cents": ((1793, 1814), (1816, 1857)),
    "flying-eagle-cents": ((1856, 1858),),
    "indian-head-cents": ((1859, 1909),),
    "lincoln-cents": ((1909, None),),
    "three-cent-silver": ((1851, 1873),),
    "three-cent-nickels": ((1865, 1889),),
    "shield-nickels": ((1866, 1883),),
    "liberty-head-nickels": ((1883, 1913),),
    "buffalo-nickels": ((1913, 1921), (1923, 1931), (1934, 1938)),
    "jefferson-nickels": ((1938, None),),
    "seated-liberty-half-dimes": ((1837, 1873),),
    "seated-liberty-dimes": ((1837, 1891),),
    "barber-dimes": ((1892, 1916),),
    "mercury-dimes": ((1916, 1921), (1923, 1931), (1934, 1945), (2016, 2016)),
    "roosevelt-dimes": ((1946, None),),
    "barber-quarters": ((1892, 1916),),
    "standing-liberty-quarters": ((1916, 1921), (1923, 1930), (2016, 2016)),
    "washington-quarters": ((1932, 1932), (1934, 1974), (1976, None)),  # none dated 1933 or 1975
    "atb-5oz-silver": ((2010, 2021),),
    "america-250": ((2026, 2026),),
    "modern-commemorative-halves": ((1982, 1982), (1986, 1986), (1989, 1989), (1991, 1996), (2001, 2001),
                                    (2003, 2003), (2008, 2008), (2011, 2011), (2013, 2022), (2024, None)),
    "modern-commemorative-dollars": ((1983, 1984), (1986, 2022), (2024, None)),
    "seated-liberty-half-dollars": ((1839, 1891),),
    "barber-half-dollars": ((1892, 1915),),
    "kennedy-half-dollars": ((1964, 1974), (1976, None)),  # 1975: all dated 1776-1976
    "seated-liberty-dollars": ((1840, 1873),),
    "trade-dollars": ((1873, 1885),),
    "morgan-dollars": ((1878, 1904), (1921, 1921)),
    "peace-dollars": ((1921, 1928), (1934, 1935)),
    # The U.S. Mint's modern issues (none in 2022).
    "modern-morgan-dollars": ((2021, 2021), (2023, None)),
    "modern-peace-dollars": ((2021, 2021), (2023, None)),
    "ike-dollars": ((1971, 1974), (1976, 1978)),
    "sacagawea-dollars": ((2000, None),),
    "early-quarter-eagles": ((1796, 1798), (1802, 1802), (1804, 1808), (1821, 1821), (1824, 1827), (1829, 1834)),
    "classic-head-quarter-eagles": ((1834, 1839),),
    "early-half-eagles": ((1795, 1800), (1802, 1815), (1818, 1834)),
    "classic-head-half-eagles": ((1834, 1838),),
    "early-eagles": ((1795, 1801), (1803, 1804)),
    "gold-dollars": ((1849, 1889),),
    "liberty-quarter-eagles": ((1840, 1907),),
    "four-dollar-stella": ((1879, 1880),),
    "indian-quarter-eagles": ((1908, 1915), (1925, 1929)),
    "three-dollar-gold": ((1854, 1889),),
    "liberty-half-eagles": ((1839, 1908),),
    "indian-half-eagles": ((1908, 1916), (1929, 1929)),
    "liberty-eagles": ((1838, 1907),),
    "indian-eagles": ((1907, 1916), (1920, 1920), (1926, 1926), (1930, 1930), (1932, 1933)),
    "liberty-double-eagles": ((1849, 1907),),
    "saint-gaudens-double-eagles": ((1907, 1916), (1920, 1933), (2009, 2009)),
    "american-silver-eagles": ((1986, None),),
    "gold-eagles-5": ((1986, None),),
    "gold-eagles-10": ((1986, None),),
    "gold-eagles-25": ((1986, None),),
    "gold-eagles-50": ((1986, None),),
    "gold-buffalos": ((2006, None),),
    # Silver commemoratives (the gold-only years 1903-1905 and 1916-1917 aren't part of this series).
    "classic-commemoratives": ((1892, 1893), (1900, 1900), (1915, 1915), (1918, 1918), (1920, 1928), (1933, 1939),
                               (1946, 1954)),
}

# Face value in cents (what "$1", "25C" or "quarter" in a description means).
FACE: dict[str, int] = {
    "half-cents": 0, "large-cents": 1, "flying-eagle-cents": 1, "indian-head-cents": 1, "lincoln-cents": 1,
    "three-cent-silver": 3, "three-cent-nickels": 3,
    "shield-nickels": 5, "liberty-head-nickels": 5, "buffalo-nickels": 5, "jefferson-nickels": 5,
    "seated-liberty-half-dimes": 5,
    "seated-liberty-dimes": 10, "barber-dimes": 10, "mercury-dimes": 10, "roosevelt-dimes": 10,
    "barber-quarters": 25, "standing-liberty-quarters": 25, "washington-quarters": 25, "atb-5oz-silver": 25,
    "seated-liberty-half-dollars": 50, "barber-half-dollars": 50, "kennedy-half-dollars": 50,
    "modern-commemorative-halves": 50, "modern-commemorative-dollars": 100,
    "seated-liberty-dollars": 100, "trade-dollars": 100, "morgan-dollars": 100, "peace-dollars": 100,
    "ike-dollars": 100, "sacagawea-dollars": 100, "modern-morgan-dollars": 100, "modern-peace-dollars": 100, "american-silver-eagles": 100, "gold-dollars": 100,
    "early-quarter-eagles": 250, "classic-head-quarter-eagles": 250, "liberty-quarter-eagles": 250,
    "indian-quarter-eagles": 250, "three-dollar-gold": 300, "four-dollar-stella": 400,
    "early-half-eagles": 500, "classic-head-half-eagles": 500, "liberty-half-eagles": 500, "indian-half-eagles": 500,
    "gold-eagles-5": 500,
    "early-eagles": 1000, "liberty-eagles": 1000, "indian-eagles": 1000, "gold-eagles-10": 1000,
    "liberty-double-eagles": 2000, "saint-gaudens-double-eagles": 2000,
    "gold-eagles-25": 2500, "gold-eagles-50": 5000, "gold-buffalos": 5000,
}

# Compound names folded into one token before matching, so "liberty" (Liberty gold) doesn't also hit
# "Seated Liberty" or "Liberty Head Nickel", and "eagle" doesn't hit "Flying Eagle".
_FOLD: list[tuple[str, str]] = [
    (r"liberty seated|seated liberty", "seated"),
    (r"standing liberty", "slq"),
    (r"walking liberty", "walkinglib"),
    (r"winged liberty", "mercury"),
    (r"liberty head nickel|liberty head 5c|liberty nickel|liberty 5c|v nickel", "vnickel"),
    (r"indian head cent|indian head 1c|indian cent|indian 1c", "indiancent"),
    (r"indian head nickel|indian nickel", "buffalo nickel"),
    (r"flying eagle", "flyingeagle"),
    (r"saint gaudens|st\.? gaudens", "saint"),
    (r"draped bust|capped bust", "bust"),
    (r"silver eagle", "silvereagle"),
    (r"gold eagle", "goldeagle"),
    (r"gold buffalo|american buffalo", "goldbuffalo"),
    (r"three cent silver|3 cent silver", "3cs"),
    (r"three cent nickel|3 cent nickel", "3cn"),
    (r"half cent", "halfcent"),
    (r"large cent", "largecent"),
    (r"half dime", "halfdime"),
    (r"half dollar", "halfdollar"),
]

# Words that name a design (any one is enough), matched as whole words after folding.
KEYWORDS: dict[str, tuple[str, ...]] = {
    "half-cents": ("halfcent", "1/2c"),
    "large-cents": ("largecent",),
    "flying-eagle-cents": ("flyingeagle",),
    "indian-head-cents": ("indiancent",),
    "lincoln-cents": ("lincoln", "wheat cent", "memorial cent", "wheatie"),
    "three-cent-silver": ("trime", "3cs"),
    "three-cent-nickels": ("3cn",),
    "shield-nickels": ("shield nickel", "shield 5c"),
    "liberty-head-nickels": ("vnickel",),
    "buffalo-nickels": ("buffalo nickel", "buffalo 5c"),
    "jefferson-nickels": ("jefferson",),
    "seated-liberty-half-dimes": ("halfdime", "h10c"),
    "seated-liberty-dimes": ("seated",),
    "barber-dimes": ("barber",),
    "mercury-dimes": ("mercury",),
    "roosevelt-dimes": ("roosevelt",),
    "barber-quarters": ("barber",),
    "standing-liberty-quarters": ("slq",),
    "washington-quarters": ("washington", "state quarter", "statehood"),
    "atb-5oz-silver": ("5oz", "5 oz", "five ounce", "atb5"),
    "america-250": ("semiquincentennial", "semiq", "america 250", "250th", "1776 2026", "1776~2026"),
    "seated-liberty-half-dollars": ("seated",),
    "barber-half-dollars": ("barber",),
    "kennedy-half-dollars": ("kennedy",),
    "seated-liberty-dollars": ("seated",),
    "trade-dollars": ("trade", "t$1"),
    "morgan-dollars": ("morgan",),
    "peace-dollars": ("peace",),
    "modern-morgan-dollars": ("morgan",),
    "modern-peace-dollars": ("peace",),
    "ike-dollars": ("ike", "eisenhower"),
    "sacagawea-dollars": ("sacagawea", "native american"),
    "early-quarter-eagles": ("bust",),
    "classic-head-quarter-eagles": ("classic head",),
    "early-half-eagles": ("bust",),
    "classic-head-half-eagles": ("classic head",),
    "early-eagles": ("bust",),
    "gold-dollars": ("gold dollar", "g$1", "gold"),
    "liberty-quarter-eagles": ("liberty", "coronet"),
    "four-dollar-stella": ("stella",),
    "indian-quarter-eagles": ("indian",),
    "three-dollar-gold": ("princess", "three dollar"),
    "liberty-half-eagles": ("liberty", "coronet"),
    "indian-half-eagles": ("indian",),
    "liberty-eagles": ("liberty", "coronet"),
    "indian-eagles": ("indian",),
    "liberty-double-eagles": ("liberty", "coronet"),
    "saint-gaudens-double-eagles": ("saint",),
    "american-silver-eagles": ("silvereagle", "ase", "s$1"),
    "gold-eagles-5": ("goldeagle",),
    "gold-eagles-10": ("goldeagle",),
    "gold-eagles-25": ("goldeagle",),
    "gold-eagles-50": ("goldeagle",),
    "gold-buffalos": ("goldbuffalo",),
    "classic-commemoratives": ("commemorative", "commem"),
    "modern-commemorative-halves": ("commemorative", "commem"),
    "modern-commemorative-dollars": ("commemorative", "commem"),
}

# Face value written out: (pattern, cents), checked in order on folded text; the first hit wins.
_FACE_PATTERNS: list[tuple[re.Pattern, int]] = [
    (re.compile(r"\bhalfcent\b|\b1/2\s*c\b"), 0),
    (re.compile(r"\bhalfdime\b|\bh10\s*c\b"), 5),
    (re.compile(r"\$\s*2(?:\.50?|\s*1/2)(?![0-9])|\bquarter eagle\b"), 250),
    (re.compile(r"\bhalf eagle\b"), 500),
    (re.compile(r"\bdouble eagle\b"), 2000),
    (re.compile(r"\$\s*50(?![0-9])"), 5000),
    (re.compile(r"\$\s*25(?![0-9])"), 2500),
    (re.compile(r"\$\s*20(?![0-9])"), 2000),
    (re.compile(r"\$\s*10(?![0-9])|\beagle\b"), 1000),
    (re.compile(r"\$\s*5(?![0-9])"), 500),
    (re.compile(r"\$\s*4(?![0-9])"), 400),
    (re.compile(r"\$\s*3(?![0-9])"), 300),
    (re.compile(r"\bhalfdollar\b|\b50\s*c\b|\bhalf\b"), 50),  # half cents and dimes are folded already
    (re.compile(r"\$\s*1(?![0-9])|\bdollar\b"), 100),
    (re.compile(r"\b25\s*c\b|\bquarter\b"), 25),
    (re.compile(r"\b10\s*c\b|\bdime\b"), 10),
    (re.compile(r"\b5\s*c\b|\bnickel\b"), 5),
    (re.compile(r"\b3\s*c[ns]?\b|\b3cs\b|\b3cn\b"), 3),
    (re.compile(r"\b1\s*c\b|\bcent\b|\bpenny\b"), 1),
]

BY_PREFIX: dict[str, Series] = {s.prefix: s for s in SERIES}


def _this_year() -> int:
    return date.today().year


def _latest_year() -> int:
    """The newest date a coin can carry: the Mint sells some next-year-dated coins before the year starts."""
    return _this_year() + 1


def year_ok(slug: str, year: int | None) -> bool:
    """Was this series struck in that year? (Series without a list, or no year, aren't flagged.)"""
    ranges = YEARS.get(slug)
    if not ranges or year is None:
        return True
    return any(lo <= year <= (hi or _latest_year()) for lo, hi in ranges)


def years_label(slug: str) -> str:
    """'1878–1904, 1921, 2021, 2023 on'."""
    return ", ".join(f"{lo}–{hi}" if hi and hi != lo else (str(lo) if hi else f"{lo} on") for lo, hi in YEARS.get(slug, ()))


# Real dates Greysheet's catalog leaves out: {slug: {year: {"MS"|"PR": mints}}}.
MISSING_FROM_CATALOG = {
    "early-quarter-eagles": {1802: {"MS": "P"}},  # the 1802/"1"
}
MINT_NAMES = {"P": "Philadelphia (no mint mark)", "D": "D", "S": "S", "O": "O", "CC": "CC", "C": "C", "W": "W"}


@cache
def _issues() -> dict:
    """Every date and mint each series was struck at (app/series_issues.json, built by scripts/build_issues.py)."""
    path = Path(__file__).resolve().parents[1] / "series_issues.json"
    data = json.loads(path.read_text())
    out = {slug: {int(y): {k: set(v.split()) for k, v in s.items()} for y, s in years.items()} for slug, years in data.items()}
    for slug, years in MISSING_FROM_CATALOG.items():
        for y, s in years.items():
            for k, v in s.items():
                out.setdefault(slug, {}).setdefault(y, {}).setdefault(k, set()).update(v.split())
    return out


def date_problem(series: Series, year: int | None, mint: str | None, grade_prefix: str | None = None) -> str | None:
    """Why a date can't be right for a series (wrong year, no such mint that year, or a proof-only date with a
    business-strike grade), or None. Years newer than the catalog (e.g. the 2021+ Morgans) only get the year check."""
    if problem := year_problem(series, year):
        return problem
    strikes = _issues().get(series.slug, {}).get(year) if year is not None else None
    if not strikes or not mint or mint not in series.mint_marks:  # unknown letters: the mint-mark check says so
        return None
    every = set().union(*strikes.values())
    if mint not in every:
        made = ", ".join(MINT_NAMES.get(m, m) for m in sorted(every, key=_mint_order))
        return f"There's no {year}-{mint} {series.name}. {year} {series.plural} were struck at: {made}."
    prefix = (grade_prefix or "").upper()
    if prefix and prefix not in ("PR", "PF", "SP") and mint not in strikes.get("MS", set()):
        label = f"{year}-{mint}" if mint != "P" else str(year)
        return f"{label} {series.plural} were only struck as proofs, so the grade should be PR (e.g. PR63)."
    return None


def _mint_order(m: str) -> int:
    return ["P", "C", "CC", "D", "O", "S", "W"].index(m) if m in ("P", "C", "CC", "D", "O", "S", "W") else 9


def year_problem(series: Series, year: int | None) -> str | None:
    """Why a year can't be right for a series, or None."""
    if year_ok(series.slug, year):
        return None
    if year is not None and year > _latest_year():
        return f"{year} is in the future."
    article = "an" if series.name[:1].upper() in "AEIOU" else "a"
    return f"{year} isn't {article} {series.name} date ({series.plural} were struck {years_label(series.slug)})."


def _norm(text: str) -> str:
    t = " " + re.sub(r"[^a-z0-9$/.]+", " ", text.lower()).strip() + " "
    t = re.sub(r"\s+", " ", re.sub(r"(?<![0-9])\.|\.(?![0-9])", " ", t))  # keep "$2.50", drop other dots
    for pat, token in _FOLD:
        t = re.sub(rf"(?<![a-z0-9]){pat}(?![a-z0-9])", token, t)
    return re.sub(r"\s+", " ", t)


def face_value(text: str) -> int | None:
    t = _norm(text)
    for pat, cents in _FACE_PATTERNS:
        if pat.search(t):
            return cents
    return None


def _has(t: str, word: str) -> bool:
    w = _norm(word).strip()
    return re.search(rf"(?<![a-z0-9]){re.escape(w)}(?![a-z0-9])", t) is not None


@dataclass
class Match:
    series: Series | None
    reason: str | None = None  # why it couldn't be matched, for the import's error message


def _candidates(text: str, year: int | None) -> list[Series]:
    t = _norm(text)
    usable = [s for s in SERIES if not s.is_type_set and year_ok(s.slug, year)]
    named = [s for s in usable if any(_has(t, k) for k in KEYWORDS.get(s.slug, ()))]
    face = face_value(text)
    if named:
        # "Indian $5" or "Seated Liberty dime": the face value picks among designs used on several coins.
        if face is not None:
            # none left: a design we don't track. Mixed-denomination sets (no FACE) take any.
            named = [s for s in named if FACE.get(s.slug, face) == face]
        # A longer keyword is a better hit ("gold buffalo" over "buffalo", "indian head cent" over "indian").
        if len(named) > 1:
            def best(s: Series) -> int:
                return max((len(k) for k in KEYWORDS[s.slug] if _has(t, k)), default=0)
            top = max(best(s) for s in named)
            named = [s for s in named if best(s) == top]
        return named
    if face is not None:
        return [s for s in usable if FACE.get(s.slug) == face]
    return []


def from_text(text: str | None, year: int | None) -> Match:
    """A series from a Type column or a description such as '1881-S Morgan Dollar' or '1908 $20 Saint'."""
    if not text or not text.strip():
        return Match(None)
    # The series' own name ("Morgan Dollars", "$2.50 Indian") first.
    t = _norm(text)
    exact_miss = None  # named exactly, but not struck that year (a 2024 "Peace Dollar" is a Modern Peace Dollar)
    for s in SERIES:
        if s.is_type_set:
            continue
        if t.strip() in (_norm(s.name).strip(), _norm(s.plural).strip(), s.slug.replace("-", " ")):
            if year_ok(s.slug, year):
                return Match(s)
            exact_miss = exact_miss or s
    found = _candidates(text, year)
    if len(found) == 1:
        return Match(found[0])
    if len(found) > 1:
        names = ", ".join(s.name for s in found[:4])
        return Match(None, f"'{text.strip()}' could be {names}. Add a Type column naming the series.")
    # Named a series, but not one struck that year?
    loose = [s for s in SERIES if not s.is_type_set and any(_has(t, k) for k in KEYWORDS.get(s.slug, ()))]
    if exact_miss is not None:
        return Match(None, _wrong_year(exact_miss, year))
    if len(loose) == 1:
        return Match(None, _wrong_year(loose[0], year))
    if loose and year is not None:
        named = " or ".join(f"{s.plural} ({years_label(s.slug)})" for s in loose[:3])
        return Match(None, f"No {named} are dated {year}.")
    return Match(None)


def _wrong_year(s: Series, year: int | None) -> str:
    return year_problem(s, year) or ""


def from_inventory_number(inv: str | None) -> Series | None:
    """Our own export: 'MOR-00012' is a Morgan Dollar."""
    m = re.match(r"^\s*([A-Z0-9]+)-\d+\s*$", str(inv or "").upper())
    return BY_PREFIX.get(m.group(1)) if m else None


def from_pcgs_facts(raw: dict | None, year: int | None) -> Match:
    """A PCGS cert lookup: SeriesName ('Morgan Dollars 1878-1921') with Name ('1878-S $1') and Denomination."""
    if not raw:
        return Match(None)
    series_name = str(raw.get("SeriesName") or "")
    text = " ".join(str(raw.get(k) or "") for k in ("SeriesName", "Denomination", "Name"))
    m = from_text(re.sub(r"\b\d{4}\s*-\s*\d{4}\b", " ", text), year)
    if m.series or m.reason:
        return m
    if series_name:
        return Match(None, f"PCGS lists this as {series_name}, which TrackMyCoins doesn't track yet.")
    return Match(None)


def by_slug(slug: str | None) -> Series | None:
    return BY_SLUG.get(slug or "")


_GENERIC = {"dollar", "dollars", "cent", "cents", "half", "quarter", "quarters", "dime", "dimes", "nickel", "nickels",
            "coin", "us", "u.s.", "type", "series"}


def strip_series_words(text: str | None, series: Series) -> str | None:
    """'Morgan Dollar 8TF' -> '8TF': what's left of a description once the series' own words are taken out."""
    if not text:
        return None
    drop = _GENERIC | {w.lower() for w in re.split(r"[\s()]+", f"{series.name} {series.plural}") if w}
    drop |= {k for k in KEYWORDS.get(series.slug, ()) if " " not in k}
    face = re.compile(r"^[gst]?\$\d+(?:\.\d+)?$|^\d+c$", re.I)  # "$1", "G$1", "25C"
    words = [w for w in text.split()
             if w.strip(",.;:-").lower() not in drop and _norm(w).strip() not in drop and not face.match(w.strip(",.;:-"))]
    left = " ".join(words).strip(" ,.;:-")
    return left or None
