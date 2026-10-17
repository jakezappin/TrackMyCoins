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
    mm = (mm or "").strip().upper().replace("-", "")
    return mm or "P"


def clean_cert(cert: str) -> str:
    """Keep only letters, digits and dashes (NGC certs look like 1234567-001)."""
    return re.sub(r"[^0-9A-Za-z-]", "", cert or "")
