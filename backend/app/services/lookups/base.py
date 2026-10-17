import re

from ...designations import canonical
from ...schemas import LookupResult


class LookupError(Exception):
    """A lookup failed in a way the user should see (bad cert, missing token, service down)."""


_GRADE_RE = re.compile(
    r"(?P<prefix>MS|PR|PF|SP|AU|XF|EF|VF|F|VG|G|AG|FR|P)?\s*-?\s*(?P<num>\d{1,2})\s*(?P<plus>\+)?\s*(?P<star>\*|★)?",
    re.IGNORECASE,
)


def parse_grade(text: str | None, result: LookupResult) -> None:
    """Fill grade_prefix/grade/plus/star/strike_designation from a string like 'MS64+ DMPL' or 'MS65RD'."""
    if not text:
        return
    upper = text.upper()
    m = _GRADE_RE.search(upper)
    if m:
        num = int(m.group("num"))
        if 1 <= num <= 70:
            result.grade = num
            prefix = (m.group("prefix") or "").upper()
            result.grade_prefix = {"PF": "PR", "EF": "XF"}.get(prefix, prefix) or None
            result.grade_plus = result.grade_plus or bool(m.group("plus"))
            result.grade_star = result.grade_star or bool(m.group("star"))
    # Designations may be glued to the number ("MS65RD"), so split letters from digits first.
    set_designation(re.sub(r"(\d)([A-Z])", r"\1 \2", upper), result)


def set_designation(text: str | None, result: LookupResult) -> None:
    """Merge any designations found in `text` (e.g. 'RD', 'FB', 'DMPL', 'DCAM') into the result."""
    if not text:
        return
    upper = text.upper()
    if "DEEP MIRROR" in upper:
        upper += " DMPL"
    elif "PROOFLIKE" in upper or "PROOF LIKE" in upper:
        upper += " PL"
    merged = canonical(f"{result.strike_designation or ''} {upper}")
    if merged:
        result.strike_designation = merged


def normalize_mint_mark(mm: str | None) -> str:
    """'S', '-S', 'O/S' (over-mintmark: the top letter is the mint) -> 'S', 'S', 'O'; blank -> 'P'."""
    mm = (mm or "").strip().upper().replace("-", "").split("/")[0].strip()
    return mm or "P"


def clean_cert(cert: str) -> str:
    """Keep only letters, digits and dashes (NGC certs look like 1234567-001)."""
    return re.sub(r"[^0-9A-Za-z-]", "", cert or "")


# "1880/79-CC $1 Reverse of 1878" -> "1880/79"; "1882-O/S $1 Strong" -> "O/S"; "1887/6-O" -> "1887/6".
_OVERDATE = re.compile(r"\b(\d{4}/\d{1,2})\b")
_OVERMINT = re.compile(r"\b\d{4}-([A-Z]{1,2}/[A-Z]{1,2})\b")


def over_variety(text: str | None) -> str | None:
    """The overdate or over-mintmark in a coin's name, if any."""
    if not text:
        return None
    found = [m.group(1) for r in (_OVERDATE, _OVERMINT) for m in [r.search(text)] if m]
    return ", ".join(found) or None


def year_of(value) -> int | None:
    """1880 from 1880, "1880" or "1880/79"."""
    m = re.match(r"\s*(\d{4})", str(value or ""))
    return int(m.group(1)) if m else None

