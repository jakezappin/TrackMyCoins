"""Strike designations, normalized so the coin form, PCGS lookups and the Greysheet catalog agree.

A designation is an optional copper color (RD/RB/BN) followed by strike/surface designations, e.g.
"RD", "FB", "DMPL", "DCAM", "RD CAM". Token order is canonical, so "CAM RD" == "RD CAM".
"""

import re

COLORS = ("RD", "RB", "BN")
OTHERS = ("DMPL", "DPL", "PL", "DCAM", "UCAM", "CAM", "FBL", "FB", "FS", "FH", "BM")
_ALIASES = {"UCAM": "DCAM", "DPL": "DMPL", "5FS": "FS", "6FS": "FS"}


def canonical(text: str | None) -> str | None:
    if not text:
        return None
    words = [_ALIASES.get(w, w) for w in re.findall(r"[0-9A-Z]+", text.upper())]
    color = next((c for c in COLORS if c in words), None)
    others = [o for o in OTHERS if o in words]
    out = ([color] if color else []) + others
    return " ".join(out) or None


def from_greysheet_name(name: str | None) -> str | None:
    """The designation in a Greysheet listing name, read only after the strike ("MS", "PR", "SP"), e.g.
    "1878-S $1 MS PL" -> "PL", "1909-S VDB 1C MS RD" -> "RD". Varieties before it ("Overdate FS-301") are ignored."""
    m = re.search(r"\b(?:MS|PR|PF|SP)\b([^0-9]*)$", name or "")
    return canonical(m.group(1)) if m else None


def from_pcgs(facts: dict) -> str | None:
    """The designation of a PCGS coin number: its Designation field, else a name part that is only a
    designation ("1878-S $1, PL" -> "PL"; "1862/1 $2.50, FS-301" -> None)."""
    d = canonical(str(facts.get("Designation") or ""))
    if d:
        return d
    for part in str(facts.get("Name") or "").split(",")[1:]:
        words = re.findall(r"[0-9A-Z]+", part.upper())
        if words and all(_ALIASES.get(w, w) in COLORS + OTHERS for w in words):
            return canonical(part)
    return None


def with_designation(grade_label: str, designation: str | None) -> str:
    """"MS64" + "PL" -> "MS64 PL" (unless the label already carries it)."""
    if not designation or canonical(grade_label) == designation:
        return grade_label
    return f"{grade_label} {designation}"
