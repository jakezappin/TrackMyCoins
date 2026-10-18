"""Bullion spreadsheets: export a collection (or everything) to Excel, and import a CSV / Excel file of items.

The export's columns import back as they are; other spreadsheets work with headings like Description, Qty,
Weight, Unit, Purity (".999", "999", "90%", "22k"), Face value, Price paid, Date purchased, Dealer, Notes.
"""

import io
import re
from decimal import Decimal, InvalidOperation

from openpyxl import Workbook
from openpyxl.styles import Font, PatternFill

from ..models import BullionItem
from . import bullion as svc
from .importer import _date, _key, _money, _text, no_formulas, read_rows

COLUMNS = ["Inventory #", "Collection", "Description", "Packaging", "Quantity", "Weight", "Unit", "Purity",
           "Face value", "Pure ozt", "Price paid", "Date purchased", "Purchased from", "Melt value", "Sale price",
           "Sale date", "Sold to", "Notes"]

ALIASES = {
    "description": "description", "item": "description", "product": "description", "name": "description",
    "packaging": "packaging", "type": "packaging", "form": "packaging",
    "quantity": "quantity", "qty": "quantity", "pieces": "quantity", "count": "quantity",
    "weight": "weight", "weighteach": "weight", "weightperpiece": "weight", "unitweight": "weight", "size": "weight",
    "unit": "weight_unit", "units": "weight_unit", "weightunit": "weight_unit",
    "purity": "purity", "fineness": "purity", "fine": "purity", "karat": "purity",
    "facevalue": "face_value", "face": "face_value",
    "pricepaid": "price_paid", "paid": "price_paid", "cost": "price_paid", "totalcost": "price_paid",
    "purchaseprice": "price_paid",
    "datepurchased": "purchase_date", "purchasedate": "purchase_date", "purchased": "purchase_date", "date": "purchase_date",
    "purchasedfrom": "purchased_from", "dealer": "purchased_from", "seller": "purchased_from", "from": "purchased_from",
    "saleprice": "sale_price", "soldfor": "sale_price",
    "saledate": "sale_date", "datesold": "sale_date",
    "soldto": "sold_to", "buyer": "sold_to",
    "notes": "notes", "note": "notes", "comments": "notes",
}

UNIT_WORDS = {"ozt": "ozt", "oz": "ozt", "troyoz": "ozt", "troyounce": "ozt", "troyounces": "ozt", "ounce": "ozt",
              "ounces": "ozt", "g": "g", "gram": "g", "grams": "g", "gr": "g", "kg": "kg", "kilo": "kg", "kilos": "kg",
              "kilogram": "kg", "kilograms": "kg"}
KARATS = {"24k": "0.999", "22k": "0.9167", "18k": "0.75", "14k": "0.585", "10k": "0.417"}


def parse_purity(v) -> Decimal | None:
    """'.999', '999', '9999', '0.999', '99.9%', '90%', '90', '22k', '22 karat', '22kt' -> a share between 0 and 1.
    Anything else (a bare '2', say) is refused rather than guessed."""
    text = (_text(v) or "").lower().replace(" ", "").replace("fine", "")
    if not text:
        return None
    karat = re.fullmatch(r"(\d{1,2})(k|kt|karat|carat|ct)", text)
    if karat:
        k = int(karat.group(1))
        return Decimal(KARATS[f"{k}k"]) if f"{k}k" in KARATS else (Decimal(k) / 24).quantize(Decimal("0.0001")) if 0 < k <= 24 else None
    try:
        if text.endswith("%"):
            n = Decimal(text[:-1]) / 100
        else:
            n = Decimal(text)
            if n > 1:
                if 10 <= n <= 100:
                    n = n / 100  # percent: 90, 99.9
                elif 100 < n < 1000:
                    n = n / 1000  # millesimal: 925, 999
                elif n == 1000:
                    n = Decimal(1)  # 1000 fine: pure
                elif 1000 < n <= 10000:
                    n = n / 10000  # 9999
                else:
                    return None  # 2, 5...: not a purity
    except InvalidOperation:
        return None
    return n if 0 < n <= 1 else None


def _number(text: str) -> Decimal | None:
    """'1', '1,000', '0.5', '1/10', '2 1/2'."""
    text = text.replace(",", "").strip()
    m = re.fullmatch(r"(?:(\d+)\s+)?(\d+)/(\d+)", text)
    try:
        if m:
            whole = Decimal(m.group(1) or 0)
            return whole + Decimal(m.group(2)) / Decimal(m.group(3)) if Decimal(m.group(3)) else None
        return Decimal(text)
    except InvalidOperation:
        return None


def parse_weight(v, unit_v) -> tuple[Decimal | None, str]:
    """'1', '10 oz', '1/10 oz', '1,000 g', '1 kilo' (a unit in the weight wins over the Unit column)."""
    text = (_text(v) or "").lower()
    unit = UNIT_WORDS.get(_key(unit_v) or "", "ozt")
    m = re.match(r"^\s*((?:\d+\s+)?[0-9][0-9,]*(?:\.[0-9]+)?(?:/[0-9]+)?|\.[0-9]+)\s*([a-z .]*)$", text)
    if not m:
        return None, unit
    if m.group(2).strip():
        unit = UNIT_WORDS.get(re.sub(r"[^a-z]", "", m.group(2)), unit)
    n = _number(m.group(1))
    return (n if n is not None and n > 0 else None), unit


def row_to_item(raw: dict) -> tuple[dict, list[str]]:
    vals: dict = {}
    for header, value in raw.items():
        field = ALIASES.get(_key(header))
        if field and field not in vals:
            vals[field] = value
    errors: list[str] = []
    f: dict = {"description": _text(vals.get("description"))}
    if not f["description"]:
        errors.append("No description")
    purity = parse_purity(vals.get("purity"))
    if purity is None:
        errors.append(f"Couldn't read the purity: {vals.get('purity')!r} (use .999, 90%, 22k...)")
    f["purity"] = str(purity) if purity is not None else None
    face = _money(vals.get("face_value"), errors, "Face value")
    weight, unit = parse_weight(vals.get("weight"), vals.get("weight_unit"))
    if face is not None:
        f.update(face_value=str(face), weight=None, quantity=1)
    elif weight is None:
        errors.append("No weight (or face value for junk silver)")
    else:
        f.update(weight=str(weight), face_value=None)
    f["weight_unit"] = unit
    if face is None:
        try:
            q = Decimal(str(_text(vals.get("quantity")) or "1").replace(",", ""))
            if q != q.to_integral_value() or q < 1:
                raise InvalidOperation
            f["quantity"] = int(q)
        except InvalidOperation:
            errors.append(f"Quantity must be a whole number of pieces, 1 or more: {vals.get('quantity')}")
            f["quantity"] = 1
    pack = (_text(vals.get("packaging")) or "").lower()
    f["packaging"] = next((p for p in svc.PACKAGING if p in pack), "tube" if f.get("quantity", 1) > 1 and "roll" not in pack else "single")
    if "roll" in pack:
        f["packaging"] = "roll"
    for k, label in (("price_paid", "Price paid"), ("sale_price", "Sale price")):
        m_ = _money(vals.get(k), errors, label)
        f[k] = str(m_) if m_ is not None else None
    for k, label in (("purchase_date", "Date purchased"), ("sale_date", "Sale date")):
        d = _date(vals.get(k), errors, label)
        f[k] = d.isoformat() if d else None
    for k in ("purchased_from", "sold_to", "notes"):
        f[k] = _text(vals.get(k))
    return f, errors


def read(filename: str, data: bytes) -> list[tuple[str, int, dict]]:
    return read_rows(filename, data, sheets=("Bullion", "Sold"))


def export_xlsx(items: list[BullionItem], spots: dict[str, Decimal | None]) -> bytes:
    wb = Workbook()
    held = wb.active
    held.title = "Bullion"
    sold = wb.create_sheet("Sold")
    for ws in (held, sold):
        ws.append(COLUMNS)
        for cell in ws[1]:
            cell.font = Font(bold=True, color="FFFFFF")
            cell.fill = PatternFill("solid", fgColor="1F3A5F")
    for i in sorted(items, key=lambda i: i.inventory_number):
        oz = svc.pure_oz(i)
        spot = spots.get(i.collection.metal)
        (sold if svc.is_sold(i) else held).append([
            i.inventory_number, i.collection.name, i.description, i.packaging, i.quantity,
            float(i.weight) if i.weight is not None else None, i.weight_unit, float(i.purity),
            float(i.face_value) if i.face_value is not None else None, float(oz),
            float(i.price_paid) if i.price_paid is not None else None, i.purchase_date, i.purchased_from,
            float((oz * spot).quantize(svc.CENTS)) if spot is not None else None,
            float(i.sale_price) if i.sale_price is not None else None, i.sale_date, i.sold_to, i.notes,
        ])
    for ws in (held, sold):
        for col, width in zip("ABCDEFGHIJKLMNOPQR", (12, 18, 28, 10, 9, 9, 6, 8, 10, 10, 11, 13, 18, 11, 11, 11, 16, 30)):
            ws.column_dimensions[col].width = width
        for row in ws.iter_rows(min_row=2):
            for idx in (10, 13, 14):  # money
                row[idx].number_format = '"$"#,##0.00'
            for idx in (11, 15):
                row[idx].number_format = "yyyy-mm-dd"
    buf = io.BytesIO()
    no_formulas(wb)
    wb.save(buf)
    return buf.getvalue()


TEMPLATE_CSV = (
    "Description,Packaging,Quantity,Weight,Unit,Purity,Face value,Price paid,Date purchased,Purchased from,Notes\n"
    "Buffalo Round,Tube,20,1,ozt,.999,,1150.00,2025-03-15,APMEX,\n"
    "Silvertown Bar,Single,1,10,ozt,.999,,330.00,2025-04-01,Local coin shop,\n"
    "90% dimes,,,,,90%,10.00,300.00,2025-05-10,Show,\n"
)

