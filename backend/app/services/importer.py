"""Bulk import: turn spreadsheet rows (CSV / Excel, including our own export) into coin fields.

Parsing is forgiving about column names and formats; every row is then checked with the same rules as
adding a coin by hand, and problems are reported per row so the user can fix the file or skip the row.
"""

import csv
import io
import re
from datetime import date, datetime, timedelta
from decimal import Decimal, InvalidOperation

from openpyxl import load_workbook
from pydantic import ValidationError

from ..designations import canonical, unknown
from ..schemas import CoinFields
from .. import grades
from . import details, series_match

MAX_ROWS = 2000


class ImportError_(Exception):
    pass


def _key(name) -> str:
    return re.sub(r"[^a-z0-9]", "", str(name or "").lower())


# Normalized header -> field. Our own export's headers are all here.
ALIASES = {
    "date": "date", "datemint": "date", "datemintmark": "date", "coin": "date", "description": "date",
    "year": "year",
    "mint": "mint_mark", "mintmark": "mint_mark", "mm": "mint_mark",
    "variety": "variety", "pedigree": "variety",
    "vam": "vam",
    "gradingservice": "grading_service", "service": "grading_service", "grader": "grading_service",
    "tpg": "grading_service", "company": "grading_service",
    "cert": "cert_number", "certno": "cert_number", "certnumber": "cert_number", "certification": "cert_number",
    "certificationnumber": "cert_number", "serial": "cert_number",
    "grade": "grade",
    "error": "error_description", "errortype": "error_description", "minterror": "error_description",
    "details": "details", "detailsgrade": "details", "problem": "details_problem",
    "detailsproblem": "details_problem", "detailsreason": "details_problem", "detailspercent": "details_pct",
    "details%": "details_pct",
    "designation": "strike_designation", "strikedesignation": "strike_designation",
    "cac": "cac", "caced": "cac",
    "cacsticker": "cac_sticker", "sticker": "cac_sticker",
    "collectorslab": "slab", "slab": "slab", "holder": "slab",
    "packaging": "packaging", "ogp": "ogp", "originalgovernmentpackaging": "ogp",
    "toning": "toning", "toned": "toning",
    "pcgs": "pcgs_number", "pcgsno": "pcgs_number", "pcgsnumber": "pcgs_number", "pcgscoinnumber": "pcgs_number",
    "pricepaid": "price_paid", "cost": "price_paid", "paid": "price_paid", "purchaseprice": "price_paid",
    "datepurchased": "purchase_date", "purchasedate": "purchase_date", "purchased": "purchase_date",
    "dateacquired": "purchase_date", "acquired": "purchase_date", "boughton": "purchase_date",
    "datebought": "purchase_date", "bought": "purchase_date", "purchasedon": "purchase_date", "acquiredon": "purchase_date",
    "boughtfrom": "purchased_from", "vendor": "purchased_from", "purchasedat": "purchased_from",
    "pricebought": "price_paid", "costbasis": "price_paid", "amountpaid": "price_paid",
    "purchasedfrom": "purchased_from", "seller": "purchased_from", "source": "purchased_from",
    "dealer": "purchased_from", "from": "purchased_from", "wherepurchased": "purchased_from",
    "wherebought": "purchased_from", "boughtfrom": "purchased_from", "purchasedat": "purchased_from", "vendor": "purchased_from",
    "saleprice": "sale_price", "soldfor": "sale_price",
    "askingprice": "asking_price", "asking": "asking_price", "listprice": "asking_price",
    "saledate": "sale_date", "datesold": "sale_date",
    "soldto": "sold_to", "buyer": "sold_to",
    "notes": "notes", "note": "notes", "comments": "notes",
    "tonerpremium": "toner_premium", "holderpremium": "holder_premium", "lowballpremium": "lowball_premium",
    "type": "series_hint", "series": "series_hint", "cointype": "series_hint", "seriesname": "series_hint",
    "denomination": "series_hint", "denom": "series_hint", "collectiontype": "series_hint",
    "inventory": "inventory_hint", "inventorynumber": "inventory_hint", "inventoryno": "inventory_hint",
    "estvalueatpurchase": "purchase_value", "valueatpurchase": "purchase_value",
    "estimatedvalueatpurchase": "purchase_value", "valueatpurchasefrom": "purchase_value_from",
    # Where it's kept and whether it's out at grading (only used when the spreadsheet has these columns).
    "storedin": "storage_name", "storage": "storage_name", "storagespot": "storage_name",
    "storagelocation": "storage_name", "location": "storage_name", "box": "storage_name", "album": "storage_name",
    "position": "storage_position", "storageposition": "storage_position", "slot": "storage_position",
    "hole": "storage_position",
    "status": "status", "inventorystatus": "status",
    "submission": "submission", "gradingsubmission": "submission", "submissionnumber": "submission",
    "submittedto": "submit_company", "sentto": "submit_company", "gradingcompany": "submit_company",
    "valuesource": "value_source", "estimatedvalue": "estimated_value", "myvalue": "estimated_value",
}

# "1881-S" / "1881/CC" (any letters after a dash are the mint mark, so typos get flagged), or "1881 S".
DATE_RE = re.compile(r"^\s*(\d{4})(?:\s*[-/]\s*([A-Z]{1,2})\b|\s+(CC|[PDSOW])\b)?\s*(.*)$", re.I)
OVERDATE_RE = re.compile(r"^\s*(\d{4})/(\d{1,2})(?:\s*-\s*([A-Z]{1,2})\b)?\s*(.*)$", re.I)
OVERMINT_RE = re.compile(r"^\s*(\d{4})\s*-\s*([A-Z]{1,2})/([A-Z]{1,2})\b\s*(.*)$", re.I)
GRADE_RE = re.compile(r"^(?:(raw)\s*)?(proof|unc|[A-Za-z]{1,3}(?![A-Za-z]))?[\s-]*(\d{1,2})?\s*(\+)?\s*(★|\*|star)?\s*(.*)$", re.I)
# What else people put in a Grade cell: the service, the cert and the CAC sticker ("FR02 (32611221 PCGS)",
# "MS65 PCGS #12345678 CAC Green").
_CELL_SERVICE = re.compile(r"\b(PCGS|NGC|ANACS|CACG|ICG)\b", re.I)
_CELL_CERT = re.compile(r"(?:#\s*)?\b(\d{6,8}-\d{3}|\d{6,10})\b")
_CELL_CAC = re.compile(r"\b(?:(green|gold)\s+)?CAC\b(?:\s+(green|gold))?(?:\s+(?:bean|sticker))?", re.I)


# Grading companies TrackMyCoins doesn't track: their coins come in as raw, with the holder kept in Notes.
_OTHER_GRADERS = re.compile(r"\b(PCI|TruGrade|SEGS|INB|ACG|NNC|SGS|PGA|HALLMARK|Global|NCI|IGC|CCG)\b", re.I)

_CELL_HOLDERS = [
    (re.compile(r"\brattler\b", re.I), "Rattler"), (re.compile(r"\bfatty\b", re.I), "NGC Fatty"),
    (re.compile(r"\bsoap\s?box\b", re.I), "Soapbox"), (re.compile(r"\b(?:OGH|old green holder)\b", re.I), "OGH"),
]
_CELL_PACKS = [
    (re.compile(r"\bGSA\b[\w\s,-]*?\bsoft\b(?:\s*(?:pack(?:age)?|box|holder|case))?", re.I), "GSA Soft Pack"),
    (_GSA_WORDS := re.compile(r"\bGSA\b(?:[\s,-]*(?:hoard|hard|soft|pack(?:age)?|box(?:ed)?|holder|slab|case|"
                              r"capsule|plastic|envelope|w/|with|coa|certificate|and))*", re.I), "GSA Hard Pack"),
    (re.compile(r"\bOGP\b", re.I), "OGP"),
]


def split_grade_cell(text: str | None) -> tuple[str | None, dict]:
    """The grade, and anything else written in the Grade cell: ("FR02", {"grading_service": "PCGS",
    "cert_number": "32611221"}) from "FR02 (32611221 PCGS)"; also a CAC sticker, CAC Grading ("123456789 CAC"),
    and holders ("Rattler", "NGC Fatty", "GSA Hard Pack")."""
    if not text:
        return text, {}
    found: dict = {}
    rest = text
    if (m := _CELL_SERVICE.search(rest)):
        found["grading_service"] = m.group(1).upper()
        rest = rest[: m.start()] + " " + rest[m.end():]
    elif (m := _OTHER_GRADERS.search(rest)):
        found["other_grader"] = m.group(1)
        rest = rest[: m.start()] + " " + rest[m.end():]
    # A cert is 6+ digits; a grade never is (and a grade's own digits come right after its letters).
    cert = _CELL_CERT.search(rest)
    if cert:
        found["cert_number"] = cert.group(1)
    cac = _CELL_CAC.search(rest)
    if cac:
        if cert and "grading_service" not in found and cac.start() > cert.end():
            # "(123456789 CAC)": CAC after the cert, and no other company, is CAC Grading's own slab.
            found["grading_service"] = "CACG"
        else:
            found["cac"] = (cac.group(1) or cac.group(2) or "yes").lower()
    spans = sorted((x.start(), x.end()) for x in (cert, cac) if x)
    for a, b in reversed(spans):
        rest = rest[:a] + " " + rest[b:]
    for pattern, name in _CELL_HOLDERS:
        if pattern.search(rest):
            found.setdefault("slab", []).append(name)
            rest = pattern.sub(" ", rest)
    for pattern, name in _CELL_PACKS:
        if pattern.search(rest):
            found.setdefault("packaging", []).append(name)
            rest = pattern.sub(" ", rest)
    rest = re.sub(r"[()\[\]{},;|#]", " ", rest)
    return " ".join(rest.split()) or None, found


def service_from_cert(cert: str | None) -> tuple[str | None, str | None]:
    """The grading service a cert number's format points to, and a note when that's only likely (None: certain).
    NGC: 7 digits, a dash and 3 (1234567-001). PCGS: 8 digits (or 7, like many ANACS certs). CAC Grading: 9 digits.
    ICG: 10 digits."""
    c = (cert or "").strip()
    if re.fullmatch(r"\d{6,8}-\d{3}", c):
        return "NGC", None
    if re.fullmatch(r"\d{8}", c):
        return "PCGS", "PCGS worked out from the 8-digit cert number. Check it."
    if re.fullmatch(r"\d{7}", c):
        return "PCGS", "PCGS worked out from the 7-digit cert number, but ANACS uses 7 digits too. Check it."
    if re.fullmatch(r"\d{9}", c):
        return "CACG", "CAC Grading worked out from the 9-digit cert number. Check it."
    if re.fullmatch(r"\d{10}", c):
        return "ICG", "ICG worked out from the 10-digit cert number. Check it."
    if re.fullmatch(r"\d{6}", c):
        return "ANACS", "ANACS worked out from the 6-digit cert number. Check it."
    return None, None


# A run-together description in one column: "1881-S Morgan Dollar PCGS MS65+ DMPL CAC Green #12345678".
_SERVICE = re.compile(r"\b(PCGS|NGC|ANACS|CACG|ICG)\b", re.I)
_GRADE = re.compile(r"\b(MS|PR|PF|SP|AU|XF|EF|VF|VG|AG|FR|PO|F|G)[\s-]?(\d{1,2})(\s?\+)?(\s?(?:★|\*))?(?![\d/])", re.I)
_CERT = re.compile(r"(?:#\s*)?\b(\d{7}-\d{3}|\d{6,10})\b")
_CAC = re.compile(r"\bCAC\b(?:\s+(green|gold))?|\b(green|gold)\s+(?:cac|bean|sticker)\b", re.I)
_DESIG = re.compile(r"\b(DMPL|DPL|PL|DCAM|UCAM|CAM|RD|RB|BN|FBL|FB|FS|FH|FT)\b")


def split_description(text: str) -> tuple[str, dict]:
    """("1881-S Morgan Dollar", {"grading_service": "PCGS", "grade": "MS65+ DMPL", "cac_sticker": "Green",
    "cert_number": "12345678"}) from "1881-S Morgan Dollar PCGS MS65+ DMPL CAC Green #12345678"."""
    found: dict = {}
    rest = text
    if (m := _SERVICE.search(rest)):
        found["grading_service"] = m.group(1).upper()
        rest = rest[: m.start()] + " " + rest[m.end():]
    if (m := _CAC.search(rest)):
        found["cac_sticker"] = (m.group(1) or m.group(2) or "yes").title()
        rest = rest[: m.start()] + " " + rest[m.end():]
    # The cert (6+ digits, or NGC's 1234567-001) first, so it isn't taken for part of a Details problem.
    if (m := _CERT.search(rest)):
        found["cert_number"] = m.group(1)
        rest = rest[: m.start()] + " " + rest[m.end():]
    is_details, _ = details.detect(rest)
    if (m := _GRADE.search(rest)):
        grade = f"{m.group(1).upper().replace('PF', 'PR').replace('EF', 'XF')}{m.group(2)}"
        grade += "+" if m.group(3) else ""
        grade += "★" if m.group(4) else ""
        tail = rest[m.end():]
        desig = _DESIG.findall(tail[:20])
        if desig:
            grade += " " + " ".join(desig)
            tail = _DESIG.sub(" ", tail, count=len(desig))
        if is_details:
            found_d = re.search(r"details?.*$", tail, re.I)
            grade += " Details" + ((" " + re.sub(r"^details?\W*", "", found_d.group(0), flags=re.I)) if found_d else "")
            tail = tail[: found_d.start()] if found_d else tail
        found["grade"] = grade.strip()
        rest = rest[: m.start()] + " " + tail
    return " ".join(rest.replace(" ,", ",").split()).strip(" ,-·"), found


GRADE_NAMES = {"PO": "Poor", "FR": "Fair", "AG": "About Good", "G": "Good", "VG": "Very Good", "F": "Fine",
               "VF": "Very Fine", "XF": "Extremely Fine", "AU": "About Uncirculated", "MS": "Mint State"}
SERVICES = {"PCGS": "PCGS", "NGC": "NGC", "ANACS": "ANACS", "ICG": "ICG", "CACG": "CACG", "CAC": "CACG", "CACGRADING": "CACG",
            "RAW": "RAW", "UNGRADED": "RAW", "NONE": "RAW"}
YES = {"yes", "y", "true", "1", "x", "✓", "green", "gold"}


def _yes(v) -> bool:
    return (_text(v) or "").strip().lower() in YES


PHOTOS_KEY = "__photos"  # photo links carried with a row (MyCoinWorx exports), not a column
NOTE_KEY = "__note"  # a note for the preview about the row (e.g. MyCoinWorx's series overruled), not a column


def read_rows(filename: str, data: bytes, sheets: tuple[str, ...] = ("Coins", "Sold")) -> list[tuple[str, int, dict]]:
    """[(sheet, row number, {header: value})] from a CSV or Excel file. A MyCoinWorx export is turned into our
    columns (its photo links under PHOTOS_KEY)."""
    from . import coinworx

    rows = _read_rows(filename, data, sheets)
    if rows and coinworx.is_coinworx(rows[0][2].keys()):
        out = []
        for sheet, n, raw in rows:
            row, photos = coinworx.convert(raw)
            out.append((sheet, n, {**row, PHOTOS_KEY: photos}))
        return out
    return rows


def _read_rows(filename: str, data: bytes, sheets: tuple[str, ...] = ("Coins", "Sold")) -> list[tuple[str, int, dict]]:
    """[(sheet, row number, {header: value})] from a CSV or Excel file. In a workbook, the named sheets (our own
    export's) are read if there; otherwise the first sheet."""
    name = filename.lower()
    if name.endswith((".xlsx", ".xlsm")):
        try:
            wb = load_workbook(io.BytesIO(data), read_only=True, data_only=True)
        except Exception as e:
            raise ImportError_("Couldn't open that Excel file.") from e
        # Our export: on hand in "Coins" (or "Bullion"), sold in "Sold". Otherwise the first sheet.
        wanted = [s for s in sheets if s in wb.sheetnames] or [wb.sheetnames[0]]
        out = []
        for sheet in wanted:
            rows = wb[sheet].iter_rows(values_only=True)
            header = next(rows, None)
            if not header:
                continue
            for i, values in enumerate(rows, start=2):
                if values and any(v not in (None, "") for v in values):
                    out.append((sheet, i, dict(zip(header, values))))
        return out
    if name.endswith((".csv", ".txt")):
        try:
            text = data.decode("utf-8-sig")
        except UnicodeDecodeError:
            text = data.decode("latin-1")
        reader = csv.DictReader(io.StringIO(text))
        if not reader.fieldnames:
            raise ImportError_("That CSV file has no header row.")
        return [("CSV", i, row) for i, row in enumerate(reader, start=2) if any((v or "").strip() for v in row.values())]
    raise ImportError_("Upload a .csv or .xlsx file.")


def _text(v) -> str | None:
    if v is None:
        return None
    if isinstance(v, float) and v.is_integer():
        v = int(v)
    s = str(v).strip()
    return s or None


# What people write for "don't know": treated as blank, not an error.
_UNKNOWN = {"unk", "unknown", "n/a", "na", "?", "??", "-", "--", "tbd", "none", "x"}


def _money(v, errors: list[str], label: str) -> Decimal | None:
    s = _text(v)
    if s is None or s.strip().lower() in _UNKNOWN:
        return None
    try:
        d = Decimal(re.sub(r"[$,\s]", "", s))
    except InvalidOperation:
        errors.append(f"{label} isn't a number: {s}")
        return None
    if not d.is_finite() or d < 0:
        errors.append(f"{label} must be a positive amount: {s}")
        return None
    if d >= Decimal("10000000000"):
        errors.append(f"{label} is too large: {s}")
        return None
    return d.quantize(Decimal("0.01"))


def _two_digit_year(d: date) -> date:
    """A 2-digit year read as a full one ("12/31/17" -> 2017-12-31): 00 up to this year is 20xx, later is 19xx.
    (strptime's %Y takes "17" as the year 0017.)"""
    if d.year >= 100:
        return d
    century = 2000 if d.year <= date.today().year % 100 else 1900
    try:
        return d.replace(year=century + d.year)
    except ValueError:  # Feb 29 in a year that isn't a leap year
        return d.replace(year=century + d.year, day=28)


def _date(v, errors: list[str], label: str) -> date | None:
    if v is None or v == "" or (isinstance(v, str) and v.strip().lower() in _UNKNOWN):
        return None
    if isinstance(v, datetime):
        d = v.date()
    elif isinstance(v, date):
        d = v
    else:
        s = str(v).strip()
        d = None
        for fmt in ("%Y-%m-%d", "%m/%d/%Y", "%m/%d/%y", "%m-%d-%Y", "%b %d, %Y", "%B %d, %Y", "%d %b %Y"):
            try:
                d = datetime.strptime(s, fmt).date()
                break
            except ValueError:
                continue
        if d is None:
            errors.append(f"{label} isn't a date I recognize: {s} (use YYYY-MM-DD or MM/DD/YYYY)")
            return None
    d = _two_digit_year(d)
    if d.year < 1900 or d > date.today() + timedelta(days=1):
        errors.append(f"{label} {d:%m/%d/%Y} looks mistyped (it's in the future or before 1900).")
        return None
    return d


def row_to_fields(raw: dict, sold_sheet: bool = False) -> tuple[dict, dict, list[str], dict]:
    """(coin fields, valuation fields, errors, series hints) for one spreadsheet row. The hints (a Type column,
    words after the date, our own inventory number) say which series the coin is, for sorting a mixed file."""
    vals: dict = {}
    for header, value in raw.items():
        field = ALIASES.get(_key(header))
        if field and field not in vals:
            vals[field] = value
    errors: list[str] = []
    f: dict = {}

    # A run-together description in the date column: split out what has no column of its own.
    described = _text(vals.get("date"))
    if described:
        remaining, found = split_description(described)
        took = {k: v for k, v in found.items() if not _text(vals.get(k))}
        if took:
            vals["date"] = remaining
            vals.update(took)

    # Date: "1881-S", "1878 8TF", or separate Year / Mint columns.
    year = mint = rest = None
    d = _text(vals.get("date"))
    if d:
        od, om, m = OVERDATE_RE.match(d), OVERMINT_RE.match(d), DATE_RE.match(d)
        if od:  # "1880/79-CC Reverse of 1878": year 1880, mint CC, variety "1880/79, Reverse of 1878"
            year, mint = int(od.group(1)), (od.group(3) or "").upper() or None
            rest = ", ".join(x for x in (f"{od.group(1)}/{od.group(2)}", od.group(4).strip()) if x)
        elif om:  # "1882-O/S Strong": the top letter is the mint mark, the over-mintmark is the variety
            year, mint = int(om.group(1)), om.group(2).upper()
            rest = ", ".join(x for x in (f"{om.group(2)}/{om.group(3)}".upper(), om.group(4).strip()) if x)
        elif m:
            year, mint, rest = int(m.group(1)), (m.group(2) or m.group(3) or "").upper() or None, m.group(4).strip() or None
    if _text(vals.get("year")):
        try:
            year = int(float(_text(vals["year"])))
        except ValueError:
            errors.append(f"Year isn't a number: {vals['year']}")
    if _text(vals.get("mint_mark")):
        mint = _text(vals["mint_mark"]).upper()
    if year is None:
        errors.append("No date: add a Date column like 1881-S, or Year and Mint columns")
    f["year"] = year
    f["mint_mark"] = mint or "P"
    # A series named in the date column ("1881-S Morgan Dollar") is used to sort the coin, not kept as a variety.
    hint = " ".join(x for x in (_text(vals.get("series_hint")), rest) if x)
    named = series_match.from_text(rest, year).series if rest else None
    f["variety"] = _text(vals.get("variety")) or (series_match.strip_series_words(rest, named) if named else rest)
    # Holders named with the coin ("1881-CC GSA", "1884-O Rattler"): packaging and slab, not a variety.
    holder_words = []
    if f["variety"]:
        if re.search(r"\bGSA\b", f["variety"], re.I):
            holder_words.append("GSA soft" if re.search(r"\bsoft\b", f["variety"], re.I) else "GSA hard")
            f["variety"] = _GSA_WORDS.sub(" ", f["variety"])
        for pattern, name in _CELL_HOLDERS:
            if pattern.search(f["variety"]):
                holder_words.append(name)
                f["variety"] = pattern.sub(" ", f["variety"])
    if f["variety"]:  # "(7TF)", "[VAM-3]" -> "7TF", "VAM-3"
        f["variety"] = " ".join(re.sub(r"[()\[\]{}]", " ", f["variety"]).split()).strip(" ,-") or None
    f["vam"] = _text(vals.get("vam"))

    # Grade: "MS65+ DMPL", "MS64PL", "PR69 DCAM", "Raw AU55", "65", and maybe the service, cert and CAC with it.
    grade_text, in_cell = split_grade_cell(_text(vals.get("grade")))
    for k in ("grading_service", "cert_number"):
        if in_cell.get(k) and not _text(vals.get(k)):
            vals[k] = in_cell[k]
    for k in ("slab", "packaging"):
        if in_cell.get(k) and not _text(vals.get(k)):
            vals[k] = ", ".join(in_cell[k])
    if in_cell.get("other_grader") and not _text(vals.get("grading_service")):
        vals["grading_service"] = in_cell["other_grader"]  # PCI, TruGrade...: an Other grading service
    if in_cell.get("cac") and not (_text(vals.get("cac")) or _text(vals.get("cac_sticker"))):
        vals["cac"] = in_cell["cac"]
    service = _text(vals.get("grading_service"))
    is_raw = False
    # Details grades: "AU Details", "AU55 Details - Cleaned", "Genuine - Cleaned - XF Details".
    is_details, problem = details.detect(grade_text)
    if is_details:
        f["details"], f["details_problem"] = True, problem
        found, _, d_prefix, d_grade = details.in_page(grade_text)
        raw = re.match(r"^\s*raw\b", grade_text or "", re.I)
        grade_text = f"{'Raw ' if raw else ''}{d_prefix}{d_grade or ''}" if found else None
        if not found:
            errors.append(f"Couldn't read the grade in “{_text(vals.get('grade'))}” (e.g. AU Details)")
    if _yes(vals.get("details")):
        f["details"] = True
    if _text(vals.get("details_problem")):
        f["details"] = True
        f["details_problem"] = details.problem_of(_text(vals.get("details_problem"))) or "other"
    if _text(vals.get("details_pct")):
        try:
            f["details_pct"] = int(Decimal(str(_text(vals.get("details_pct"))).rstrip("%")))
        except InvalidOperation:
            errors.append(f"Details % isn't a number: {vals.get('details_pct')}")
    if grade_text:
        # "BU", "Brilliant Unc.", "Uncirculated": Mint State without a number.
        grade_text = re.sub(r"^\s*(?:brilliant\s+)?unc(?:irculated|\.)?\b\.?", "MS ", grade_text, flags=re.I)
        grade_text = re.sub(r"^\s*BU\b", "MS ", grade_text, flags=re.I)
        m = GRADE_RE.match(grade_text)
        if m and (m.group(2) or m.group(3) or m.group(1)):
            is_raw = bool(m.group(1))
            prefix = (m.group(2) or "").upper() or None
            prefix = {"PF": "PR", "PROOF": "PR", "UNC": "MS", "EF": "XF"}.get(prefix, prefix)
            f["grade_prefix"] = prefix
            f["grade"] = int(m.group(3)) if m.group(3) else None
            # Letters that don't go with the number ("AG2", "VF40"): the number is what's meant.
            right = grades.letters_for(f["grade"])
            if prefix in grades.NUMBERS and right and right != prefix and not is_details:
                f["grade_prefix"] = right
                f["grade_fixed"] = (f"Grade {prefix}{f['grade']} read as {right}{f['grade']} "
                                    f"(a {f['grade']} is {GRADE_NAMES.get(right, right)}). Check it.")
            f["grade_plus"] = bool(m.group(4))
            f["grade_star"] = bool(m.group(5))
            # Designations after the grade ("PL", "DCAM", "Ultra Cameo"); other words ("Toned") go to Notes.
            tail = m.group(6).strip()
            if tail:
                f["strike_designation"] = canonical(tail)
                extra = [w for w in re.findall(r"[^\s,;/]+", tail) if unknown(w)]
                if extra:
                    f["grade_note"] = " ".join(extra)
        else:
            errors.append(f"Couldn't read the grade: {grade_text}")
    if _text(vals.get("strike_designation")):
        f["strike_designation"] = _text(vals["strike_designation"])
    if _text(vals.get("error_description")) and (_text(vals.get("error_description")) or "").lower() not in ("no", "none", "n"):
        f["is_error"], f["error_description"] = True, _text(vals["error_description"])

    if service:
        svc = SERVICES.get(_key(service).upper())
        if svc is None:
            # Any other company (PCI, TruGrade, SEGS...): an Other grading service, by its name.
            svc = "OTHER"
            f["other_service"] = " ".join(service.split())[:60]
        f["grading_service"] = svc
    else:
        f["grading_service"] = "RAW" if is_raw or not _text(vals.get("cert_number")) else None
        if f["grading_service"] is None:
            # No service column: tell it from the cert number's format (1234567-001 is NGC, 12345678 PCGS).
            guess, note = service_from_cert(_text(vals.get("cert_number")))
            if guess:
                f["grading_service"] = guess
                if note:
                    f["service_guessed"] = note
            else:
                errors.append("There's a cert number but no grading service (add PCGS, NGC... after it or in a column)")
                f["grading_service"] = "RAW"
    if is_raw:
        f["grading_service"] = "RAW"
    f["cert_number"] = _text(vals.get("cert_number"))
    if f["grading_service"] not in ("RAW", "OTHER") and not f["cert_number"]:  # some small graders have no certs
        errors.append(f"{f['grading_service']} coin without a cert number")

    # CAC: "Yes", or the sticker color in either column.
    sticker = (_text(vals.get("cac_sticker")) or "").lower()
    cac = (_text(vals.get("cac")) or "").lower()
    f["cac_sticker"] = sticker if sticker in ("green", "gold") else (cac if cac in ("green", "gold") else None)
    f["cac"] = bool(f["cac_sticker"]) or cac in YES

    slab = " ".join(x for x in (_text(vals.get("slab")), *holder_words) if x).lower()
    f.update(slab_soapbox="soapbox" in slab, slab_ngc_fatty="fatty" in slab, slab_rattler="rattler" in slab,
             slab_ogh="ogh" in slab or "old green" in slab)
    pack = (_text(vals.get("packaging")) or "").lower() + " " + slab
    # Anything that says GSA is a GSA holder: Soft Pack if it says soft, otherwise Hard Pack (the usual one).
    gsa = bool(re.search(r"\bgsa\b", pack))
    soft = gsa and "soft" in pack or (not gsa and bool(re.search(r"\bsoft\s*pack", pack)))
    hard = (gsa and not soft) or bool(re.search(r"\bhard\s*pack", pack))
    f.update(gsa_hard_pack=hard, gsa_soft_pack=soft, ike_blue_pack="blue" in pack,
             ike_brown_pack="brown" in pack,
             ogp=bool(re.search(r"\bogp\b|original (government|mint) packag", pack)) or (_text(vals.get("ogp")) or "").lower() in YES,
             capital_holder="capital" in pack)
    toning = (_text(vals.get("toning")) or "").lower()
    # Toning written with the grade or the coin ("MS64 Toned", "1881-S Rainbow toner"): broad on purpose.
    elsewhere = " ".join(x for x in (f.get("grade_note"), f.get("variety"), _text(vals.get("grade"))) if x).lower()
    if not toning and re.search(r"\bton(?:ed|er|ing)\b|\brainbow\b", elsewhere):
        toning = "rainbow" if "rainbow" in elsewhere else "yes"
        if f.get("grade_note"):
            f["grade_note"] = re.sub(r"\b(?:rainbow\s+)?ton(?:ed|er|ing)\b|\brainbow\b", " ", f["grade_note"], flags=re.I).strip() or None
        if f.get("variety"):
            f["variety"] = re.sub(r"\b(?:rainbow\s+)?ton(?:ed|er|ing)\b|\brainbow\b", " ", f["variety"], flags=re.I)
            f["variety"] = " ".join(f["variety"].split()).strip(" ,-") or None
    f.update(toning_obverse="obv" in toning, toning_reverse="rev" in toning, toning_dual="dual" in toning,
             toning_rainbow="rainbow" in toning, toning_rim="rim" in toning)
    if toning in YES and not any(f[k] for k in ("toning_obverse", "toning_reverse", "toning_dual", "toning_rainbow",
                                                 "toning_rim")):
        f["toning_obverse"] = True

    f["pcgs_number"] = _text(vals.get("pcgs_number"))
    f["price_paid"] = _money(vals.get("price_paid"), errors, "Price paid")
    f["purchase_date"] = _date(vals.get("purchase_date"), errors, "Date purchased")
    f["purchased_from"] = _text(vals.get("purchased_from"))
    # Our export's value at purchase is only the owner's own figure if it says so; otherwise it was worked out
    # and is worked out again here. Other spreadsheets: a value in the column is the owner's.
    source = (_text(vals.get("purchase_value_from")) or "").lower()
    if not source or source.startswith("your own"):
        f["purchase_value_custom"] = _money(vals.get("purchase_value"), errors, "Est. value at purchase")
    f["sale_price"] = _money(vals.get("sale_price"), errors, "Sale price")
    if _text(vals.get("asking_price")):
        f["asking_price"] = _money(vals.get("asking_price"), errors, "Asking price")
    f["sale_date"] = _date(vals.get("sale_date"), errors, "Sale date")
    f["sold_to"] = _text(vals.get("sold_to"))
    f["notes"] = _text(vals.get("notes"))
    grade_note = f.pop("grade_note", None)
    if grade_note:  # words after the grade that aren't a designation ("MS63 Toned")
        f["notes"] = "; ".join(x for x in (f["notes"], f"Grade note: {grade_note}") if x)
    service_guessed = f.pop("service_guessed", False)
    grade_fixed = f.pop("grade_fixed", None)
    if sold_sheet and f["sale_price"] is None and f["sale_date"] is None:
        errors.append("Row on the Sold sheet without a sale price or date")

    valuation = {
        "toner_premium": _money(vals.get("toner_premium"), errors, "Toner premium"),
        "holder_premium": _money(vals.get("holder_premium"), errors, "Holder premium"),
        "lowball_premium": _money(vals.get("lowball_premium"), errors, "Lowball premium"),
    }
    own = (_text(vals.get("value_source")) or "").lower().startswith("own")
    est = _money(vals.get("estimated_value"), errors, "Estimated value")
    if own and est is not None:
        valuation.update(value_source="custom", custom_value=est)

    if not errors:
        try:
            f = CoinFields(**f).model_dump(mode="json")
        except ValidationError as e:
            for err in e.errors():
                where = ".".join(str(p) for p in err["loc"])
                msg = err["msg"].removeprefix("Value error, ")
                errors.append(f"{where}: {msg}" if where else msg)
    else:
        f = {k: (v.isoformat() if isinstance(v, date) else str(v) if isinstance(v, Decimal) else v) for k, v in f.items()}
    valuation = {k: (str(v) if isinstance(v, Decimal) else v) for k, v in valuation.items() if v is not None}
    hints = {k: v for k, v in (("text", hint), ("inventory", _text(vals.get("inventory_hint")))) if v}
    if service_guessed:
        hints["service_guessed"] = service_guessed
    if grade_fixed:
        hints["grade_fixed"] = grade_fixed
    hints.update(_placement(vals, errors, sold=bool(f.get("sale_price") or f.get("sale_date"))))
    return f, valuation, errors, hints


STATUS_WORDS = {"inventory": "inventory", "ininventory": "inventory", "home": "inventory", "onhand": "inventory",
                "inhand": "inventory", "grading": "grading", "atgrading": "grading", "submitted": "grading",
                "outforgrading": "grading", "atgrader": "grading"}
COMPANY_WORDS = {"ngc": "NGC", "pcgs": "PCGS", "cacg": "CACG", "cacgrading": "CACG", "cac": "CAC", "caccsticker": "CAC",
                 "cacsticker": "CAC", "anacs": "ANACS", "icg": "ICG"}


def _placement(vals: dict, errors: list[str], sold: bool) -> dict:
    """Stored in / Position / Status / Submission / Submitted to, only from columns the spreadsheet has. Checked
    against the user's own storage spots and submissions when the rows are placed."""
    out: dict = {}
    spot, pos = _text(vals.get("storage_name")), _text(vals.get("storage_position"))
    if spot:
        if len(spot) > 100:
            errors.append("Stored in: names are 100 characters at most")
        out["storage"] = spot[:100]
        if pos:
            out["position"] = pos[:60]
    elif pos:
        errors.append("Position without a Stored in")
    status = _text(vals.get("status"))
    if status:
        st = STATUS_WORDS.get(_key(status))
        if st is None:
            errors.append(f"Status should be In Inventory or At Grading, not {status!r}")
        elif st == "grading":
            if sold:
                errors.append("A sold coin can't be At Grading")
            sub, comp = _text(vals.get("submission")), _text(vals.get("submit_company"))
            company = COMPANY_WORDS.get(_key(comp)) if comp else None
            if comp and company is None:
                errors.append(f"Submitted to should be NGC, PCGS, CACG, CAC, ANACS or ICG, not {comp!r}")
            if not sub and not comp:
                errors.append("At Grading needs a Submission (its # or name) or a Submitted to (e.g. NGC) column")
            out["status"] = "grading"
            if sub:
                out["submission"] = sub
            if company:
                out["submit_company"] = company
        else:
            out["status"] = "inventory"
    return out


def split_certs(text: str) -> list[str]:
    """Cert numbers from pasted text: one per line, or separated by commas / spaces."""
    seen = []
    for c in re.split(r"[\s,;]+", text or ""):
        c = c.strip().strip(".")
        if c and c not in seen:
            seen.append(c)
    return seen


def no_formulas(wb) -> None:
    """Exports never contain formulas: text a user typed that starts with "=" (a note, say) is kept as text,
    so opening the file can't run it."""
    for ws in wb.worksheets:
        for row in ws.iter_rows():
            for cell in row:
                if cell.data_type == "f":
                    cell.data_type = "s"
