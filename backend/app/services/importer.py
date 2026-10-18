"""Bulk import: turn spreadsheet rows (CSV / Excel, including our own export) into coin fields.

Parsing is forgiving about column names and formats; every row is then checked with the same rules as
adding a coin by hand, and problems are reported per row so the user can fix the file or skip the row.
"""

import csv
import io
import re
from datetime import date, datetime
from decimal import Decimal, InvalidOperation

from openpyxl import load_workbook
from pydantic import ValidationError

from ..schemas import CoinFields
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
    "dealer": "purchased_from", "from": "purchased_from",
    "saleprice": "sale_price", "soldfor": "sale_price",
    "saledate": "sale_date", "datesold": "sale_date",
    "soldto": "sold_to", "buyer": "sold_to",
    "notes": "notes", "note": "notes", "comments": "notes",
    "tonerpremium": "toner_premium", "holderpremium": "holder_premium",
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
SERVICES = {"PCGS": "PCGS", "NGC": "NGC", "ANACS": "ANACS", "ICG": "ICG", "CACG": "CACG", "CAC": "CACG", "CACGRADING": "CACG",
            "RAW": "RAW", "UNGRADED": "RAW", "NONE": "RAW"}
YES = {"yes", "y", "true", "1", "x", "✓", "green", "gold"}


def _yes(v) -> bool:
    return (_text(v) or "").strip().lower() in YES


def read_rows(filename: str, data: bytes, sheets: tuple[str, ...] = ("Coins", "Sold")) -> list[tuple[str, int, dict]]:
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


def _money(v, errors: list[str], label: str) -> Decimal | None:
    s = _text(v)
    if s is None:
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


def _date(v, errors: list[str], label: str) -> date | None:
    if v is None or v == "":
        return None
    if isinstance(v, datetime):
        return v.date()
    if isinstance(v, date):
        return v
    s = str(v).strip()
    for fmt in ("%Y-%m-%d", "%m/%d/%Y", "%m/%d/%y", "%m-%d-%Y", "%b %d, %Y", "%B %d, %Y", "%d %b %Y"):
        try:
            return datetime.strptime(s, fmt).date()
        except ValueError:
            continue
    errors.append(f"{label} isn't a date I recognize: {s} (use YYYY-MM-DD or MM/DD/YYYY)")
    return None


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
    f["vam"] = _text(vals.get("vam"))

    # Grade: "MS65+ DMPL", "PR69 DCAM", "Raw AU55", "65".
    service = _text(vals.get("grading_service"))
    grade_text = _text(vals.get("grade"))
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
        m = GRADE_RE.match(grade_text)
        if m and (m.group(2) or m.group(3) or m.group(1)):
            is_raw = bool(m.group(1))
            prefix = (m.group(2) or "").upper() or None
            prefix = {"PF": "PR", "PROOF": "PR", "UNC": "MS", "EF": "XF"}.get(prefix, prefix)
            f["grade_prefix"] = prefix
            f["grade"] = int(m.group(3)) if m.group(3) else None
            f["grade_plus"] = bool(m.group(4))
            f["grade_star"] = bool(m.group(5))
            f["strike_designation"] = m.group(6).strip() or None
        else:
            errors.append(f"Couldn't read the grade: {grade_text}")
    if _text(vals.get("strike_designation")):
        f["strike_designation"] = _text(vals["strike_designation"])
    if _text(vals.get("error_description")) and (_text(vals.get("error_description")) or "").lower() not in ("no", "none", "n"):
        f["is_error"], f["error_description"] = True, _text(vals["error_description"])

    if service:
        svc = SERVICES.get(_key(service).upper())
        if svc is None:
            errors.append(f"Unknown grading service: {service} (use PCGS, NGC, ANACS, CACG, ICG or Raw)")
        f["grading_service"] = svc or "RAW"
    else:
        f["grading_service"] = "RAW" if is_raw or not _text(vals.get("cert_number")) else None
        if f["grading_service"] is None:
            errors.append("There's a cert number but no grading service")
            f["grading_service"] = "RAW"
    if is_raw:
        f["grading_service"] = "RAW"
    f["cert_number"] = _text(vals.get("cert_number"))
    if f["grading_service"] != "RAW" and not f["cert_number"]:
        errors.append(f"{f['grading_service']} coin without a cert number")

    # CAC: "Yes", or the sticker color in either column.
    sticker = (_text(vals.get("cac_sticker")) or "").lower()
    cac = (_text(vals.get("cac")) or "").lower()
    f["cac_sticker"] = sticker if sticker in ("green", "gold") else (cac if cac in ("green", "gold") else None)
    f["cac"] = bool(f["cac_sticker"]) or cac in YES

    slab = (_text(vals.get("slab")) or "").lower()
    f.update(slab_soapbox="soapbox" in slab, slab_ngc_fatty="fatty" in slab, slab_rattler="rattler" in slab,
             slab_ogh="ogh" in slab or "old green" in slab)
    pack = (_text(vals.get("packaging")) or "").lower() + " " + slab
    f.update(gsa_hard_pack="hard" in pack, gsa_soft_pack="soft" in pack, ike_blue_pack="blue" in pack,
             ike_brown_pack="brown" in pack,
             ogp=bool(re.search(r"\bogp\b|original (government|mint) packag", pack)) or (_text(vals.get("ogp")) or "").lower() in YES,
             capital_holder="capital" in pack)
    toning = (_text(vals.get("toning")) or "").lower()
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
    f["sale_date"] = _date(vals.get("sale_date"), errors, "Sale date")
    f["sold_to"] = _text(vals.get("sold_to"))
    f["notes"] = _text(vals.get("notes"))
    if sold_sheet and f["sale_price"] is None and f["sale_date"] is None:
        errors.append("Row on the Sold sheet without a sale price or date")

    valuation = {
        "toner_premium": _money(vals.get("toner_premium"), errors, "Toner premium"),
        "holder_premium": _money(vals.get("holder_premium"), errors, "Holder premium"),
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
