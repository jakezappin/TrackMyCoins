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
