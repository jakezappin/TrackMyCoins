"""Which grade combinations exist: the Sheldon numbers each letter grade covers, where a plus can go, and which
designations a series can carry. Catches typos like MS45, AU65, MS70+ or "RD CAM" on a silver Morgan."""

import re

# The Sheldon numbers the grading services use, by letter grade.
NUMBERS = {
    "PO": {1}, "FR": {2}, "AG": {3}, "G": {4, 6}, "VG": {8, 10}, "F": {12, 15}, "VF": {20, 25, 30, 35},
    "XF": {40, 45}, "AU": {50, 53, 55, 58}, "MS": set(range(60, 71)),
}
SHELDON = {n for ns in NUMBERS.values() for n in ns}  # PR and SP coins can carry any of these

COPPER = {"half-cents", "large-cents", "flying-eagle-cents", "indian-head-cents", "lincoln-cents", "two-cent-pieces"}
# Full-detail designations and the series they belong to.
STRIKE_ONLY = {
    "FB": {"mercury-dimes"},
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
            if prefix in NUMBERS:
                nums = sorted(allowed)
                span = f"{nums[0]}" if len(nums) == 1 else f"{nums[0]}–{nums[-1]}"
                return f"{prefix}{grade} isn't a grade: {prefix} runs {span} ({', '.join(map(str, nums))})."
            return f"{prefix}{grade} isn't a Sheldon grade."
    if plus and grade is not None and not 45 <= grade <= 69:
        return f"A plus grade runs from 45+ to 69+, so {prefix or ''}{grade}+ isn't one."
    if prefix == "SP" and not details and year not in SMS_YEARS and not re.search(r"\b(sp|sms|specimen)\b", variety or "", re.I):
        return (f"SP (specimen) grades are for Special Mint Sets (1965–67) and specimen strikes. For a regular "
                f"{year or ''} coin use MS, or note the specimen issue in the variety.")
    words = (designation or "").split()
    colors = [w for w in words if w in ("RD", "RB", "BN")]
    if colors and slug and slug not in COPPER:
        return f"{colors[0]} (copper color) is only for copper coins."
    if prefix and prefix != "PR" and ({"CAM", "DCAM"} & set(words)) and prefix != "SP":
        return "CAM and DCAM are proof designations; this coin isn't graded PR."
    if prefix == "PR" and ({"PL", "DMPL"} & set(words)):
        return "PL and DMPL are for business strikes; on a proof use CAM or DCAM."
    for w in words:
        if w in STRIKE_ONLY and slug and slug not in STRIKE_ONLY[w]:
            return f"{w} is a {', '.join(s.replace('-', ' ').title() for s in sorted(STRIKE_ONLY[w]))} designation."
    return None
