"""MyCoinWorx inventory exports: each row turned into the columns our importer reads.

A MyCoinWorx export names the series exactly ("Morgan Dollar (1878 - 1921)", "Boone Half Dollar" in Classic
Commemoratives), with the grading company, cert, PCGS #, holder and CAC flags, cost and photos in columns of their
own. Its "Coin Type" ("Dollar") is too vague to sort by, so it isn't used.
"""

import re

# Headers only a MyCoinWorx export has together.
SIGNATURE = {"Coin Series", "Grading Company", "Cert Number", "Catalog PCGS #"}
MINTS = {"P", "D", "S", "O", "CC", "W", "C"}
NOTE_KEY = "__note"  # a note for the import preview, not a column
# Special Designations that are strike designations (as we write them).
DESIGNATIONS = {"FBL": "FBL", "FB": "FB", "FT": "FT", "FS": "FS", "FH": "FH", "PL": "PL", "DMPL": "DMPL",
                "CAMEO": "CAM", "CAM": "CAM", "DCAM": "DCAM", "ULTRA CAMEO": "DCAM", "DEEP CAMEO": "DCAM",
                "BN": "BN", "RB": "RB", "RD": "RD"}
_IGNORE = {"PROOF", "W", "WHITE"}
_GRADED = {"NGC", "PCGS", "ANACS", "CACG", "ICG"}


def is_coinworx(headers) -> bool:
    return SIGNATURE <= {str(h or "").strip() for h in headers}


def _t(v) -> str:
    return " ".join(str(v or "").split())


def _yes(v) -> bool:
    return _t(v).lower() in ("yes", "y", "true", "1")


def _series(raw: dict) -> str:
    """Our series name: the export's Coin Series without its years, or the commemorative group by category."""
    cat, name, kind = _t(raw.get("Category")), _t(raw.get("Coin Series")), _t(raw.get("Coin Type"))
    name = re.sub(r"\s*\((?:\d{4}|\d{4}\s*-\s*(?:\d{4}|date)|\d{4}\s+to\s+date)\)\s*$", "", name, flags=re.I)
    if cat.lower().startswith("classic commemorative"):
        gold = _t(raw.get("Metal")).lower() == "gold" or "gold" in name.lower()
        return "Classic Gold Commemorative" if gold else "Classic Commemorative"
    if cat.lower().startswith("modern commemorative"):
        face = f"{kind} {_t(raw.get('Notes'))}".lower()
        if "$10" in face:
            return "$10 Modern Commemorative"
        if "$5" in face:
            return "$5 Modern Commemorative"
        if "half" in face or "50c" in face:
            return "Modern Commemorative Half Dollar"
        return "Modern Commemorative Dollar"
    return name or kind


def _mint(raw: dict) -> str:
    for col in ("Mint Mark", "Mint Province"):
        m = _t(raw.get(col)).upper()
        if m in MINTS:
            return m
    return ""


# NGC's label: "1922 $1", "1936-S 50C", "1849 G$1". Its denomination is the grader's; MyCoinWorx's series is a guess
# from it, and "$1" alone has been guessed wrong (a 1922 Peace Dollar listed as a Grant gold dollar).
_NGC_LABEL = re.compile(r"^NGC:\s*(\d{4})(?:-([A-Z]{1,2}))?\s+(G?\$\d+(?:\.\d+)?|\d+C[SN]?|H10C)\b", re.I)
_NGC_FACE = {"1C": 1, "2C": 2, "3CS": 3, "3CN": 3, "H10C": 5, "5C": 5, "10C": 10, "20C": 20, "25C": 25, "50C": 50,
             "$1": 100, "G$1": 100, "$2.50": 250, "$3": 300, "$5": 500, "$10": 1000, "$20": 2000}


def _label_conflict(raw: dict, series_name: str) -> tuple[str, str | None] | None:
    """(NGC's denomination, its mint) when NGC's label contradicts the series MyCoinWorx gave, else None."""
    from . import series_match as sm

    m = _NGC_LABEL.match(_t(raw.get("Notes")))
    if not m or not _t(raw.get("Year")).isdigit():
        return None
    den = m.group(3).upper()
    face = _NGC_FACE.get(den)
    if face is None:
        return None
    ser = sm.from_text(series_name, int(_t(raw.get("Year")))).series
    if ser is None:
        return None
    gold_label = den.startswith("G$") or face >= 250
    gold_series = ser.category == "Gold" or "gold" in ser.slug
    series_face = sm.FACE.get(ser.slug)
    commem = ser.slug == "classic-commemoratives"  # 25c, 50c and $1 issues: NGC's label names it separately
    if gold_label != gold_series or (series_face is not None and not commem and series_face != face):
        return den, (m.group(2) or "").upper() or None
    return None


def convert(raw: dict) -> tuple[dict, list[str]]:
    """(the row with our column names, its photo URLs)."""
    program = _t(raw.get("Program"))
    design = _t(raw.get("Design"))
    grade = _t(raw.get("Grade"))
    grade = re.sub(r"^FAIR\b", "FR", grade, flags=re.I)  # "FAIR 2"
    accu = re.match(r"^A\d\s*-\s*(\d{1,2})\s*([a-z]*)$", grade, re.I)  # Accugrade's own scale: "A3-64c"
    if accu:
        from ..grades import letters_for

        n = int(accu.group(1))
        grade = f"{letters_for(n) or 'MS'}{n}"
        notes_extra = [f"Accugrade grade: {_t(raw.get('Grade'))}"]
    else:
        notes_extra = []
    company = _t(raw.get("Grading Company")).upper()
    notes = ([_t(raw.get("Notes")).replace(" | ", "\n")] if _t(raw.get("Notes")) else []) + notes_extra

    variety, vam, designation, packaging, problems = [], None, None, [], []
    if program:
        variety.append(program)
    if design and design.lower() not in ("all varieties", "west point mint mark") and design.lower() not in program.lower():
        variety.append(design)
    if _t(raw.get("Mint Mark")).upper() == "REV":  # a reverse variety noted in the mint mark (1956 FS-701)
        variety.append("Reverse")
    for part in re.split(r"\s{2,}|,|;", _t(raw.get("Special Designations")).replace("  ", ",")):
        p = part.strip()
        up = p.upper()
        if program and up.startswith(program.upper() + " "):  # "GRANT W/ STAR" with Program "Grant": "With Star"
            p = re.sub(r"\bW/\s*", "With ", p[len(program) + 1:].strip(), flags=re.I).title()
            up = p.upper()
        if not p or up in _IGNORE or (program and up.replace("-", " ") in program.upper().replace("-", " ")):
            continue
        if up in DESIGNATIONS:
            designation = DESIGNATIONS[up]
        elif up.startswith("GSA"):
            packaging.append("GSA Soft Pack" if "SOFT" in up else "GSA Hard Pack")
        elif (m := re.match(r"VAM[\s-]*(\d+[A-Z]?)\s*(.*)$", up)):
            vam = m.group(1)
            if m.group(2).strip():
                variety.append(m.group(2).strip().title())
        elif up == "CLEANED":
            problems.append("Cleaned")
        elif up.endswith(" CLEANED"):
            problems.append("Cleaned")
        elif up not in (program.upper(), _series(raw).upper()):
            variety.append(p if not p.isupper() else p.title() if not re.search(r"\d", p) else p)
    proof = bool(re.match(r"^\s*(PR|PF)", grade, re.I)) or _t(raw.get("Strike")).upper() == "PR"
    if proof and designation in ("PL", "DMPL"):  # some graders (PCI) call a proof's mirrors PL / DMPL
        notes.append(f"Holder designation: {designation}")
        designation = "CAM" if designation == "PL" else "DCAM"
    if re.search(r"\bFS-\d+\b", _t(raw.get("Special Holder"))):  # "Superbird FS-901": a variety
        variety.append(_t(raw.get("Special Holder")))
    holder = [n for col, n in (("Rattler", "Rattler"), ("OGH", "OGH"), ("Fatty", "Fatty"), ("Soapbox", "Soapbox"))
              if _yes(raw.get(col))]
    if _t(raw.get("Special Holder")):
        notes.append(f"Holder: {_t(raw.get('Special Holder'))}")
    if problems and "DETAILS" in grade.upper():
        grade = f"{grade} {' '.join(problems)}"
    elif problems:
        notes.append(", ".join(problems))

    service = company if company in _GRADED or len(company) <= 4 else ("" if company == "OTHER" else company.title())
    if company == "OTHER":
        from .importer import service_from_cert

        guessed, _ = service_from_cert(_t(raw.get("Cert Number")))
        service = guessed or "Other"
    status = _t(raw.get("Status")).upper()
    sold = status == "SOLD" or bool(_t(raw.get("Sold Date")) or _t(raw.get("Sold Price")))
    year = _t(raw.get("Year"))
    if year == "1776" and re.search(r"washington quarter|kennedy|eisenhower|ike", _series(raw), re.I):
        year = "1976"  # the Bicentennial quarter, half and dollar are dated 1776-1976
    row = {
        "Type": _series(raw),
        "Date": f"{year}{'-' + _mint(raw) if _mint(raw) else ''}",
        "Variety": ", ".join(dict.fromkeys(variety)) or None,
        "VAM": vam,
        "Grading service": service or None,
        "Cert number": _t(raw.get("Cert Number")) or None,
        "Grade": grade or None,
        "Designation": designation,
        "PCGS #": _t(raw.get("PCGS ID")) or _t(raw.get("Catalog PCGS #")) or None,
        "CAC": "Yes" if _yes(raw.get("CAC Green")) or _yes(raw.get("CAC Gold")) else None,
        "CAC sticker": "Gold" if _yes(raw.get("CAC Gold")) else ("Green" if _yes(raw.get("CAC Green")) else None),
        "Slab": ", ".join(holder) or None,
        "Packaging": ", ".join(packaging) or None,
        "Toning": "Yes" if _yes(raw.get("Toned/PQ")) else None,
        "Price paid": _t(raw.get("Cost")) or _t(raw.get("Total Cost")) or None,
        "Purchase date": _t(raw.get("Received Date")) or None,
        "Asking price": _t(raw.get("Asking Price")) or None,
        "Sale price": _t(raw.get("Sold Price")) or None,
        "Sale date": _t(raw.get("Sold Date")) or None,
        "Notes": "\n".join(n for n in notes if n) or None,
    }
    if not sold and status in ("", "ON_HAND"):
        row["Status"] = "In Inventory"
    conflict = _label_conflict(raw, row["Type"])
    if conflict:
        den, mint = conflict
        listed = re.sub(r"\s*\([^)]*\)\s*$", "", _t(raw.get("Coin Series"))) or row["Type"]
        row["Type"] = den  # with the year, NGC's denomination picks the series ("1922 $1": a Peace Dollar)
        if mint:
            row["Date"] = f"{year}-{mint}"
        row["PCGS #"] = row["Variety"] = None  # MyCoinWorx's catalog number and issue were for its guess
        row[NOTE_KEY] = (f"MyCoinWorx listed this as {listed}, but NGC's label says {year} {den}. "
                         "Sorted by NGC's label. Check it.")
    photos = [u for i in range(1, 9) if (u := _t(raw.get(f"Image URL {i}")))]
    return row, photos
