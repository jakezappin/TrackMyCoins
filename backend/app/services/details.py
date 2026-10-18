"""Details (problem) grades: genuine coins with a problem (cleaned, damaged...), graded "AU Details" and the like.

No price source covers them: CPG, the PCGS Price Guide and CAC are all for problem-free coins. So a Details coin
is valued at a share of the straight-grade CPG (the owner's default, 70% unless changed, or the coin's own), never
below melt. With no grade number ("AU Details"), the straight grade priced is the bottom of that range (AU50).
"""

import re
from decimal import Decimal

from ..models import Coin

CENTS = Decimal("0.01")
DEFAULT_PCT = 70

PROBLEMS = {
    "cleaned": "Cleaned",
    "environmental-damage": "Environmental Damage",
    "scratched": "Scratched",
    "tooled": "Tooled",
    "altered-surfaces": "Altered Surfaces",
    "damaged": "Damaged",
    "holed": "Holed",
    "repaired": "Repaired",
    "graffiti": "Graffiti",
    "bent": "Bent",
    "rim-damage": "Rim Damage",
    "questionable-color": "Questionable Color",
    "polished": "Polished",
    "whizzed": "Whizzed",
    "other": "Other",
}

# What label text means which problem (NGC "Improperly Cleaned", PCGS "Genuine – Cleaned - AU Details"...).
_WORDS = [
    (r"clean", "cleaned"),
    (r"environment|corro|pvc|\bdamage[d]?\s*\(env", "environmental-damage"),
    (r"scratch", "scratched"),
    (r"tool", "tooled"),
    (r"altered|artificial|surface", "altered-surfaces"),
    (r"holed|\bhole\b|plugged", "holed"),
    (r"repair", "repaired"),
    (r"graffiti|engrav", "graffiti"),
    (r"bent", "bent"),
    (r"rim", "rim-damage"),
    (r"questionable (?:color|toning)|artificial (?:color|toning)|\bqt\b", "questionable-color"),
    (r"polish", "polished"),
    (r"whizz", "whizzed"),
    (r"damage", "damaged"),
]

# The straight grade a number-less Details grade is priced at: the bottom of its range.
BASE_GRADE = {"PO": 1, "FR": 2, "AG": 3, "G": 4, "VG": 8, "F": 12, "VF": 20, "XF": 40, "AU": 50, "MS": 60,
              "SP": 60, "PR": 60}


def detect(text: str | None) -> tuple[bool, str | None]:
    """(is details, problem slug) from grade or label text such as 'AU Details', 'Genuine - Cleaned'."""
    t = (text or "").lower()
    if not re.search(r"\bdetails?\b|\bgenuine\b|\bimproperly\b|\bproblem\b", t):
        return False, None
    return True, problem_of(t)


_GRADE_DETAILS = re.compile(
    r"\b(MS|PF|PR|SP|AU|XF|EF|VF|VG|AG|FR|PO|UNC|F|G)\s*-?\s*(\d{1,2})?\s*details\b", re.I)


def in_page(text: str | None) -> tuple[bool, str | None, str | None, int | None]:
    """(is details, problem, grade prefix, grade) from a cert page's text: only a grade followed by "Details"
    counts (a page heading like "Coin Details" doesn't)."""
    m = _GRADE_DETAILS.search(text or "")
    if not m:
        return False, None, None, None
    prefix = m.group(1).upper()
    prefix = {"PF": "PR", "EF": "XF", "UNC": "MS"}.get(prefix, prefix)
    after = (text or "")[m.end(): m.end() + 80]
    return True, problem_of(after), prefix, int(m.group(2)) if m.group(2) else None


def problem_of(text: str | None) -> str | None:
    t = (text or "").lower().replace("_", " ")
    if t.strip() in PROBLEMS:
        return t.strip()
    for pattern, slug in _WORDS:
        if re.search(pattern, t):
            return slug
    return None


def price_grade(coin) -> int | None:
    """The numeric straight grade CPG is looked up at."""
    if coin.grade:
        return coin.grade
    if getattr(coin, "details", False):
        return BASE_GRADE.get(coin.grade_prefix or "")
    return None


def pct(coin: Coin) -> int:
    own = getattr(coin, "details_pct", None)
    if own is not None:
        return own
    return getattr(getattr(coin, "user", None), "details_pct", None) or DEFAULT_PCT


def adjust(coin: Coin, straight: Decimal | None, melt: Decimal | None = None) -> Decimal | None:
    """A straight-grade value made into this coin's: unchanged unless it's a Details coin."""
    if straight is None or not getattr(coin, "details", False):
        return straight
    v = (straight * Decimal(pct(coin)) / 100).quantize(CENTS)
    return max(v, melt) if melt is not None else v


def label(coin) -> str:
    """'AU55 Details · Cleaned', 'AU Details'."""
    base = f"{coin.grade_prefix or ''}{coin.grade or ''}".strip()
    if not getattr(coin, "details", False):
        return base
    out = f"{base} Details".strip()
    if coin.details_problem:
        out += f" · {PROBLEMS.get(coin.details_problem, coin.details_problem)}"
    return out


def basis(coin: Coin, melt_used: bool = False) -> str | None:
    """How a Details coin's value was worked out, for the coin page and reports."""
    if not getattr(coin, "details", False):
        return None
    g = price_grade(coin)
    grade = f"{coin.grade_prefix or ''}{g or ''}"
    text = f"Valued at {pct(coin)}% of {grade} CPG, since price guides only cover problem-free coins"
    if not coin.grade and g:
        text += f". {coin.grade_prefix} Details is priced from the bottom of its range ({grade})"
    if melt_used:
        text += ". Raised to melt value, its floor"
    return text + "."
