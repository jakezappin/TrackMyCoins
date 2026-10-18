"""Strike designations, normalized so the coin form, PCGS lookups and the Greysheet catalog agree.

A designation is an optional copper color (RD/RB/BN) followed by strike/surface designations, e.g.
"RD", "FB", "DMPL", "DCAM", "RD CAM". Token order is canonical, so "CAM RD" == "RD CAM".
"""

import re

COLORS = ("RD", "RB", "BN")
OTHERS = ("DMPL", "DPL", "PL", "DCAM", "UCAM", "CAM", "FBL", "FB", "FS", "FH", "FT", "BM")
# PCGS's API writes Cameo, Deep Cameo and Deep Mirror Prooflike as "CA", "DC" and "DM".
_ALIASES = {"UCAM": "DCAM", "CA": "CAM", "DC": "DCAM", "DM": "DMPL", "DPL": "DMPL", "5FS": "FS", "6FS": "FS", "CAMEO": "CAM", "RED": "RD", "BROWN": "BN"}
# Spelled-out designations, longest first so "Deep Cameo" isn't read as "Cameo".
_PHRASES = [
    (r"DEEP\s*MIRROR\s*PROOF\s*-?\s*LIKE", "DMPL"), (r"PROOF\s*-?\s*LIKE", "PL"),
    (r"(?:DEEP|ULTRA)\s*CAMEO", "DCAM"), (r"RED\s*(?:AND|&|/|-)?\s*BROWN", "RB"),
    (r"FULL\s*BANDS?\s*LINES?|FULL\s*BELL\s*LINES?", "FBL"), (r"FULL\s*BANDS?", "FB"), (r"FULL\s*STEPS?", "FS"),
    (r"FULL\s*HEAD", "FH"), (r"FULL\s*TORCH", "FT"),
]


def _words(text: str) -> list[str]:
    up = text.upper()
    for pattern, code in _PHRASES:
        up = re.sub(pattern, f" {code} ", up)
    return [_ALIASES.get(w, w) for w in re.findall(r"[0-9A-Z]+", up)]


def unknown(text: str | None) -> list[str]:
    """Words in a typed designation that aren't one (so they're reported, not silently dropped)."""
    return [w for w in _words(text or "") if w not in COLORS + OTHERS]


def canonical(text: str | None) -> str | None:
    if not text:
        return None
    words = _words(text)
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
