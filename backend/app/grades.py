"""Which grade combinations exist: the Sheldon numbers each letter grade covers, where a plus can go, and which
designations a series can carry. Catches typos like MS45, AU65, MS70+ or "RD CAM" on a silver Morgan."""

import re

# The Sheldon numbers the grading services use, by letter grade.
NUMBERS = {
    "PO": {1}, "FR": {2}, "AG": {3}, "G": {4, 6}, "VG": {8, 10}, "F": {12, 15}, "VF": {20, 25, 30, 35},
    "XF": {40, 45}, "AU": {50, 53, 55, 58}, "MS": set(range(60, 71)),
}
SHELDON = {n for ns in NUMBERS.values() for n in ns}  # PR and SP coins can carry any of these


NAMES = {"PO": "Poor", "FR": "Fair", "AG": "About Good", "G": "Good", "VG": "Very Good", "F": "Fine",
         "VF": "Very Fine", "XF": "Extremely Fine", "AU": "About Uncirculated", "MS": "Mint State"}


def _span(prefix: str) -> str:
    nums = sorted(NUMBERS[prefix])
    return f"{nums[0]}" if len(nums) == 1 else f"{nums[0]}–{nums[-1]}"


def runs(prefix: str) -> str:
    """"VG runs 8–10 (8, 10)", "AG runs 3"."""
    nums = sorted(NUMBERS[prefix])
    listed = "" if len(nums) == 1 or prefix == "MS" else f" ({', '.join(map(str, nums))})"
    return f"{prefix} runs {_span(prefix)}{listed}"


def letters_for(grade: int | None) -> str | None:
    """The letter grade a Sheldon number belongs to: 2 is FR, 3 AG, 45 XF, 63 MS."""
    return next((p for p, ns in NUMBERS.items() if grade in ns), None)

COPPER = {"half-cents", "large-cents", "flying-eagle-cents", "indian-head-cents", "lincoln-cents", "two-cent-pieces"}
# Full-detail designations and the series they belong to.
STRIKE_ONLY = {
    "FB": {"mercury-dimes", "roosevelt-dimes"},  # PCGS's Full Bands Roosevelt is NGC's Full Torch (FT)
    "FT": {"roosevelt-dimes"},
    "FBL": {"franklin-half-dollars"},
    "FS": {"jefferson-nickels"},
    "FH": {"standing-liberty-quarters"},
}
SMS_YEARS = range(1965, 1968)


def problem(slug: str | None, year: int | None, prefix: str | None, grade: int | None, plus: bool,
            designation: str | None, variety: str | None = None, details: bool = False) -> str | None:
    """Why this grade can't be right, or None."""
    if grade is not None and prefix:
        allowed = NUMBERS.get(prefix, SHELDON)
        if grade not in allowed:
            # Say what the letters cover and what the number is, so the fix is plain ("VG25": VG is 8-10, 25 is VF).
            head = f"{prefix}{grade} isn't a grade: {runs(prefix)}." if prefix in NUMBERS else f"{prefix}{grade} isn't a Sheldon grade."
            right = letters_for(grade)
            article = "An" if str(grade).startswith("8") or grade in (11, 18) else "A"
            if right:
                return f"{head} {article} {grade} is {right} ({NAMES[right]}), which runs {_span(right)}."
            if grade > 70:
                return f"{head} The Sheldon scale tops out at 70 (MS70)."
            lower = max((n for n in SHELDON if n < grade), default=None)
            higher = min((n for n in SHELDON if n > grade), default=None)
            near = " and ".join(str(n) for n in (lower, higher) if n is not None)
            return f"{head} {grade} isn't on the Sheldon scale (1–70); the nearest grades are {near}."
    if plus and grade is not None and not 45 <= grade <= 69:
        return (f"{prefix or ''}{grade}+ isn't a grade: plus grades run from 45+ to 69+ (XF45+ to MS69+), "
                f"so a {grade} can't carry a plus.")
    if prefix == "SP" and not details and year not in SMS_YEARS and not re.search(r"\b(sp|sms|specimen)\b", variety or "", re.I):
        return (f"SP (specimen) grades are for Special Mint Sets (1965–67) and specimen strikes. For a regular "
                f"{year or ''} coin use MS, or note the specimen issue in the variety.")
    words = (designation or "").split()
    colors = [w for w in words if w in ("RD", "RB", "BN")]
    if colors and slug and slug not in COPPER:
        return f"{colors[0]} (copper color: Red, Red-Brown, Brown) is only for copper coins: cents and half cents."
    if prefix and prefix != "PR" and ({"CAM", "DCAM"} & set(words)) and prefix != "SP":
        return (f"CAM and DCAM are proof designations, but this coin is graded {prefix}. For a proof use PR "
                f"(PR{grade or ''} DCAM); for a business strike with mirrors use PL or DMPL.")
    if prefix == "PR" and ({"PL", "DMPL"} & set(words)):
        return (f"PL and DMPL are for business strikes (MS{grade or ''} PL), but this coin is graded PR. On a proof use "
                f"CAM or DCAM.")
    for w in words:
        if w in STRIKE_ONLY and slug and slug not in STRIKE_ONLY[w]:
            names = {"FB": "Full Bands", "FT": "Full Torch", "FBL": "Full Bell Lines", "FS": "Full Steps", "FH": "Full Head"}
            series = ", ".join(x.replace("-", " ").title() for x in sorted(STRIKE_ONLY[w]))
            return f"{w} ({names.get(w, w)}) is only for {series}, not this coin."
    return None
