"""Which series a coin belongs to, from what a spreadsheet row or a PCGS lookup tells us.

Used by bulk import to sort a mixed spreadsheet into collections, and to catch coins that don't belong in the
collection being imported into (a 1921 Peace Dollar in a Morgan collection, say).
"""

import re
from dataclasses import dataclass

from ..series import BY_SLUG, SERIES, Series

# Years each series was struck (business strikes and proofs). Open-ended ranges are still being made.
YEARS: dict[str, tuple[tuple[int, int | None], ...]] = {
    "half-cents": ((1793, 1857),),
    "large-cents": ((1793, 1857),),
    "flying-eagle-cents": ((1856, 1858),),
    "indian-head-cents": ((1859, 1909),),
    "lincoln-cents": ((1909, None),),
    "three-cent-silver": ((1851, 1873),),
    "three-cent-nickels": ((1865, 1889),),
    "shield-nickels": ((1866, 1883),),
    "liberty-head-nickels": ((1883, 1913),),
    "buffalo-nickels": ((1913, 1938),),
    "jefferson-nickels": ((1938, None),),
    "seated-liberty-half-dimes": ((1837, 1873),),
    "seated-liberty-dimes": ((1837, 1891),),
    "barber-dimes": ((1892, 1916),),
    "mercury-dimes": ((1916, 1945), (2016, 2016)),
    "roosevelt-dimes": ((1946, None),),
    "barber-quarters": ((1892, 1916),),
    "standing-liberty-quarters": ((1916, 1930), (2016, 2016)),
    "washington-quarters": ((1932, None),),
    "seated-liberty-half-dollars": ((1839, 1891),),
    "barber-half-dollars": ((1892, 1915),),
    "kennedy-half-dollars": ((1964, None),),
    "seated-liberty-dollars": ((1840, 1873),),
    "trade-dollars": ((1873, 1885),),
    "morgan-dollars": ((1878, 1904), (1921, 1921), (2021, None)),
    "peace-dollars": ((1921, 1935), (2021, None)),
    "ike-dollars": ((1971, 1978),),
    "sacagawea-dollars": ((2000, None),),
    "early-quarter-eagles": ((1796, 1834),),
    "classic-head-quarter-eagles": ((1834, 1839),),
    "early-half-eagles": ((1795, 1834),),
    "classic-head-half-eagles": ((1834, 1838),),
    "early-eagles": ((1795, 1804),),
    "gold-dollars": ((1849, 1889),),
    "liberty-quarter-eagles": ((1840, 1907),),
    "four-dollar-stella": ((1879, 1880),),
    "indian-quarter-eagles": ((1908, 1929),),
    "three-dollar-gold": ((1854, 1889),),
    "liberty-half-eagles": ((1839, 1908),),
    "indian-half-eagles": ((1908, 1929),),
    "liberty-eagles": ((1838, 1907),),
    "indian-eagles": ((1907, 1933),),
    "liberty-double-eagles": ((1849, 1907),),
    "saint-gaudens-double-eagles": ((1907, 1933), (2009, 2009)),
    "american-silver-eagles": ((1986, None),),
    "gold-eagles-5": ((1986, None),),
    "gold-eagles-10": ((1986, None),),
    "gold-eagles-25": ((1986, None),),
    "gold-eagles-50": ((1986, None),),
    "gold-buffalos": ((2006, None),),
    "classic-commemoratives": ((1892, 1954),),
}

# Face value in cents (what "$1", "25C" or "quarter" in a description means).
FACE: dict[str, int] = {
    "half-cents": 0, "large-cents": 1, "flying-eagle-cents": 1, "indian-head-cents": 1, "lincoln-cents": 1,
    "three-cent-silver": 3, "three-cent-nickels": 3,
    "shield-nickels": 5, "liberty-head-nickels": 5, "buffalo-nickels": 5, "jefferson-nickels": 5,
    "seated-liberty-half-dimes": 5,
    "seated-liberty-dimes": 10, "barber-dimes": 10, "mercury-dimes": 10, "roosevelt-dimes": 10,
    "barber-quarters": 25, "standing-liberty-quarters": 25, "washington-quarters": 25,
    "seated-liberty-half-dollars": 50, "barber-half-dollars": 50, "kennedy-half-dollars": 50,
    "seated-liberty-dollars": 100, "trade-dollars": 100, "morgan-dollars": 100, "peace-dollars": 100,
    "ike-dollars": 100, "sacagawea-dollars": 100, "american-silver-eagles": 100, "gold-dollars": 100,
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
    "seated-liberty-half-dollars": ("seated",),
    "barber-half-dollars": ("barber",),
    "kennedy-half-dollars": ("kennedy",),
    "seated-liberty-dollars": ("seated",),
    "trade-dollars": ("trade", "t$1"),
    "morgan-dollars": ("morgan",),
    "peace-dollars": ("peace",),
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
    (re.compile(r"\bhalfdollar\b|\b50\s*c\b"), 50),
    (re.compile(r"\$\s*1(?![0-9])|\bdollar\b"), 100),
    (re.compile(r"\b25\s*c\b|\bquarter\b"), 25),
    (re.compile(r"\b10\s*c\b|\bdime\b"), 10),
    (re.compile(r"\b5\s*c\b|\bnickel\b"), 5),
    (re.compile(r"\b3\s*c[ns]?\b|\b3cs\b|\b3cn\b"), 3),
    (re.compile(r"\b1\s*c\b|\bcent\b|\bpenny\b"), 1),
]

BY_PREFIX: dict[str, Series] = {s.prefix: s for s in SERIES}


def year_ok(slug: str, year: int | None) -> bool:
    """Was this series struck in that year? Unknown series or years aren't flagged."""
    ranges = YEARS.get(slug)
    if not ranges or year is None:
        return True
    return any(lo <= year <= (hi or 9999) for lo, hi in ranges)


def years_label(slug: str) -> str:
    return ", ".join(f"{lo}–{hi}" if hi and hi != lo else (str(lo) if hi else f"{lo} on") for lo, hi in YEARS.get(slug, ()))


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
            named = [s for s in named if FACE.get(s.slug) == face]  # none left: a design we don't track
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
    for s in SERIES:
        if s.is_type_set:
            continue
        if t.strip() in (_norm(s.name).strip(), _norm(s.plural).strip(), s.slug.replace("-", " ")):
            return Match(s) if year_ok(s.slug, year) else Match(None, _wrong_year(s, year))
    found = _candidates(text, year)
    if len(found) == 1:
        return Match(found[0])
    if len(found) > 1:
        names = ", ".join(s.name for s in found[:4])
        return Match(None, f"'{text.strip()}' could be {names}. Add a Type column naming the series.")
    # Named a series, but not one struck that year?
    loose = [s for s in SERIES if not s.is_type_set and any(_has(t, k) for k in KEYWORDS.get(s.slug, ()))]
    if len(loose) == 1:
        return Match(None, _wrong_year(loose[0], year))
    return Match(None)


def _wrong_year(s: Series, year: int | None) -> str:
    return f"{year} isn't a {s.name} date ({s.plural} were struck {years_label(s.slug)})."


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
