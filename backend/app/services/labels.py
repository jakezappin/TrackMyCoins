"""Coin labels: 2x2 squares on letter paper (cut out for flips), Avery address labels (5160/8160, 30 per sheet) and
2" x 1" thermal labels. Each label has the coin's QR code (its own link) and whatever details the owner picked.

Labels are drawn once as reportlab Drawings: the same drawing becomes the printed PDF and the on-screen preview
(SVG), so the preview is exactly what prints. Text never gets cut off: long lines wrap, and if the label is still too
full the whole label's text gets smaller until it fits.
"""

import io
from dataclasses import dataclass

from decimal import Decimal

from reportlab.graphics import renderPDF, renderSVG
from reportlab.graphics.barcode.qr import QrCodeWidget
from reportlab.graphics.shapes import Drawing, Line as SLine, Rect, String
from reportlab.lib import colors
from reportlab.lib.pagesizes import letter
from reportlab.pdfbase.pdfmetrics import stringWidth
from reportlab.pdfgen import canvas as pdfcanvas

from ..models import Coin, User
from . import details, price_code

IN = 72.0
SIZES = ("2x2", "avery5160", "thermal2x1")
SIZE_LABELS = {"2x2": '2x2 squares on letter paper (20 per page)', "avery5160": 'Avery address labels, 1" × 2⅝" '
               '(5160 / 8160, 30 per sheet)', "thermal2x1": 'Thermal 2" × 1"'}
MIN_FONT = 5.0  # below this, the preview warns that the text is very small
FLOOR_FONT = 3.5


@dataclass(frozen=True)
class Sheet:
    """Where labels sit on a page (points, from the page's top left)."""

    page: tuple[float, float]
    label: tuple[float, float]
    cols: int
    rows: int
    left: float
    top: float
    pitch: tuple[float, float]
    pad: tuple[float, float]  # inside each label: horizontal, vertical
    qr: float
    max_font: float
    modes: tuple[str, ...] = ("corner",)  # where the QR code goes (see _layout); the first that fits biggest wins


def sheet_for(size: str, square: float = 2.0) -> Sheet:
    if size == "2x2":
        s = square * IN
        return Sheet(letter, (s, s), 4, 5, (letter[0] - 4 * s) / 2, (letter[1] - 5 * s) / 2, (s, s), (9, 9),
                     0.7 * IN, 13)
    if size == "avery5160":
        return Sheet(letter, (2.625 * IN, IN), 3, 10, 0.1875 * IN, 0.5 * IN, (2.75 * IN, IN), (7, 5), 0.62 * IN, 10,
                     ("side", "corner"))
    w, h = 2 * IN, IN
    return Sheet((w, h), (w, h), 1, 1, 0, 0, (w, h), (5, 4), 0.5 * IN, 9.5)


# ---- What goes on a label --------------------------------------------------------------------------------------


@dataclass
class Options:
    size: str = "2x2"
    square: float = 2.0  # 2x2 squares: 2" or 1.875" (a size that slides into flips)
    cut_lines: bool = True
    start: int = 1  # sheets: the first unused spot (1 = top left), for a partly used sheet
    inventory: bool = True
    variety: bool = True
    grade: bool = True
    cert: bool = True
    cac: bool = True
    storage: bool = False
    qr: bool = True
    price: str = "off"  # off | plain | code
    purchase_date: str = "off"  # off | plain | code
    asking: bool = True


@dataclass
class Text:
    left: str
    right: str = ""
    bold: bool = False
    scale: float = 1.0
    mono: bool = False
    right_bold: bool = False


@dataclass
class LabelData:
    lines: list[Text]
    url: str | None


def _money(v: Decimal) -> str:
    v = Decimal(v)
    return f"${v:,.0f}" if v == v.to_integral_value() else f"${v:,.2f}"


def grade_text(c: Coin) -> str:
    if c.details:
        g = details.label(c)
    else:
        g = f"{c.grade_prefix or ''}{c.grade or ''}{'+' if c.grade_plus else ''}{'*' if c.grade_star else ''}"
    if c.strike_designation and g:
        g += f" {c.strike_designation}"
    return g


def label_lines(c: Coin, type_name: str, opts: Options, user: User, asking: Decimal | None, url: str | None) -> LabelData:
    title = f"{c.year}{'' if c.mint_mark == 'P' else '-' + c.mint_mark} {type_name}"
    lines = [Text(title, bold=True, scale=1.2)]
    if opts.variety:
        bits = [x for x in (c.variety, c.vam) if x]
        if c.is_error and c.error_description:
            bits.append(f"Error: {c.error_description}")
        if bits:
            lines.append(Text(" · ".join(bits)))
    if opts.grade or opts.cac:
        bits = []
        if opts.grade:
            g = grade_text(c)
            bits.append(f"{g} {c.grading_service}".strip() if c.grading_service != "RAW" else f"Raw {g}".strip())
        if opts.cac and (c.cac or c.cac_sticker):
            bits.append("CAC Gold" if c.cac_sticker == "gold" else "CAC")
        if bits:
            lines.append(Text(" · ".join(bits)))
    left = f"#{c.cert_number}" if opts.cert and c.cert_number and c.grading_service != "RAW" else ""
    right = c.inventory_number if opts.inventory else ""
    if left or right:
        lines.append(Text(left, right))
    if opts.storage and c.storage is not None:
        lines.append(Text(" · ".join(x for x in (c.storage.name, c.storage_position) if x)))
    coded: list[str] = []
    mono = False
    if opts.price != "off" and c.price_paid is not None:
        if opts.price == "code":
            coded.append(price_code.encode_price(c.price_paid, user.price_code_phrase or "", user.price_code_start or 0,
                                                 user.price_code_length, seed=str(c.id)))
            mono = True
        else:
            coded.append(_money(c.price_paid))
    if opts.purchase_date != "off" and c.purchase_date is not None:
        if opts.purchase_date == "code":
            coded.append(price_code.encode_date(c.purchase_date, user.price_code_phrase or "", user.price_code_start or 0))
            mono = True
        else:
            coded.append(f"{c.purchase_date:%m/%d/%y}")
    ask = _money(asking) if opts.asking and asking is not None else ""
    if coded or ask:
        lines.append(Text(" · ".join(coded), ask, mono=mono, right_bold=True, scale=1.0))
    return LabelData(lines, url if opts.qr else None)


# ---- Laying text out ------------------------------------------------------------------------------------------


def _font(t: Text, right: bool = False) -> str:
    if right:
        return "Helvetica-Bold" if t.right_bold else "Helvetica"
    if t.mono:
        return "Courier-Bold"
    return "Helvetica-Bold" if t.bold else "Helvetica"


def _wrap(text: str, font: str, size: float, width: float, split_words: bool = True) -> list[str] | None:
    """Lines of at most `width`. Breaks go between " · " parts first, so "CAC Gold" or "Reverse of 1879" stays
    together, then between words (or inside a word too long for a line)."""
    out: list[str] = []
    for part in text.split(" · "):
        trial = f"{out[-1]} · {part}" if out else part
        if out and stringWidth(trial, font, size) <= width:
            out[-1] = trial
        elif stringWidth(part, font, size) <= width:
            out.append(part)
        else:
            rows = _wrap_words(part, font, size, width, split_words)
            if rows is None:
                return None
            out += rows
    return out


def _wrap_words(text: str, font: str, size: float, width: float, split_words: bool) -> list[str] | None:
    out: list[str] = []
    cur = ""
    for word in text.split():
        trial = f"{cur} {word}".strip()
        if stringWidth(trial, font, size) <= width:
            cur = trial
            continue
        if cur:
            out.append(cur)
        cur = ""
        if not split_words and stringWidth(word, font, size) > width:
            return None  # a cert # or title word would have to be split: try smaller text first
        while stringWidth(word, font, size) > width and len(word) > 1:
            n = len(word)
            while n > 1 and stringWidth(word[:n], font, size) > width:
                n -= 1
            out.append(word[:n])
            word = word[n:]
        cur = word
    if cur:
        out.append(cur)
    return out


@dataclass
class Placed:
    x: float
    y: float  # baseline, from the label's bottom
    text: str
    font: str
    size: float
    anchor: str = "start"


def _layout(lines: list[Text], w: float, h: float, pad: tuple[float, float], q: float, mode: str,
            fs: float, split_words: bool = False) -> list[Placed] | None:
    """Text placed at font size `fs`, or None if it doesn't fit. corner: the QR code top left, text beside it and
    then full width below it; side: the QR code on the left, all the text beside it."""
    px, py = pad
    gap = 5.0 if q else 0.0
    beside_x = px + q + gap
    regions = [(beside_x, h - py, w - px - beside_x, h - py - q if mode == "corner" and q else py)]
    if mode == "corner" and q:
        regions.append((px, h - py - q - 2, w - 2 * px, py))
    r = 0
    x, top, width, bottom = regions[0]
    cursor = top
    out: list[Placed] = []
    for t in lines:
        while True:
            size = fs * t.scale
            lead = size * 1.18
            font, rfont = _font(t), _font(t, True)
            rw = stringWidth(t.right, rfont, size) if t.right else 0.0
            rows = _wrap(t.left, font, size, width, split_words) if t.left else []
            same_line = bool(t.right) and (not rows or stringWidth(rows[-1], font, size) + 6 + rw <= width)
            if t.right and rw > width:
                rows = None  # the right-hand text alone is too wide here
            same_line = same_line and rows is not None
            n = len(rows or []) + (0 if same_line or not t.right else 1)
            if rows is not None and cursor - n * lead >= bottom - 0.5:
                break
            if r + 1 < len(regions):
                r += 1
                x, top, width, bottom = regions[r]
                cursor = top
                continue
            return None
        for row in rows:
            cursor -= lead
            out.append(Placed(x, cursor + (lead - size) / 2 + size * 0.22, row, font, size))
        if t.right:
            if not same_line:
                cursor -= lead
            out.append(Placed(x + width, cursor + (lead - size) / 2 + size * 0.22, t.right, rfont, size, "end"))
    return out


def fit(lines: list[Text], w: float, h: float, pad: tuple[float, float], q: float, max_font: float,
        modes: tuple[str, ...] = ("corner",)) -> tuple[list[Placed], str, float]:
    """The biggest text that fits, for each place the QR code can go: (placed text, mode, size). Words are only split
    (a long cert number over two lines) when nothing fits otherwise."""
    for split_words in (False, True):
        best: tuple[list[Placed], str, float] | None = None
        for mode in modes:
            fs = max_font
            while fs >= (MIN_FONT if not split_words else FLOOR_FONT):
                placed = _layout(lines, w, h, pad, q, mode, fs, split_words)
                if placed is not None:
                    if best is None or fs > best[2] + 0.01:
                        best = (placed, mode, fs)
                    break
                fs -= 0.25
        if best is not None:
            return best
    # Nothing fits even at the floor: keep everything, at the floor size.
    return _layout(lines, w, 10_000, pad, q, modes[0], FLOOR_FONT, True) or [], modes[0], FLOOR_FONT


def draw_label(d: Drawing, data: LabelData, x0: float, y0: float, sheet: Sheet) -> float:
    """Draw one label with its bottom left at (x0, y0). Returns the font size used."""
    w, h = sheet.label
    q = sheet.qr if data.url else 0.0
    placed, mode, fs = fit(data.lines, w, h, sheet.pad, q, sheet.max_font, sheet.modes)
    if data.url:
        qy = y0 + h - sheet.pad[1] - q if mode == "corner" else y0 + (h - q) / 2
        d.add(QrCodeWidget(data.url, x=x0 + sheet.pad[0], y=qy, barWidth=q, barHeight=q, barBorder=0, barLevel="M"))
    for p in placed:
        d.add(String(x0 + p.x, y0 + p.y, p.text, fontName=p.font, fontSize=p.size, fillColor=colors.black,
                     textAnchor=p.anchor))
    return fs


# ---- Pages ----------------------------------------------------------------------------------------------------


GUIDE = colors.HexColor("#9a9a9a")


def pages(labels: list[LabelData], opts: Options, preview: bool = False) -> tuple[list[Drawing], float]:
    """One Drawing per page (per label for thermal), and the smallest font size used."""
    sheet = sheet_for(opts.size, opts.square)
    per_page = sheet.cols * sheet.rows
    skip = max(0, min(per_page - 1, opts.start - 1)) if per_page > 1 else 0
    slots = [None] * skip + labels
    out: list[Drawing] = []
    smallest = 99.0
    for first in range(0, max(1, len(slots)), per_page):
        d = Drawing(*sheet.page)
        d.add(Rect(0, 0, *sheet.page, fillColor=colors.white, strokeColor=None))
        chunk = slots[first:first + per_page]
        for i in range(per_page):
            col, row = i % sheet.cols, i // sheet.cols
            x = sheet.left + col * sheet.pitch[0]
            y = sheet.page[1] - sheet.top - row * sheet.pitch[1] - sheet.label[1]
            data = chunk[i] if i < len(chunk) else None
            if preview and opts.size == "avery5160":
                d.add(Rect(x, y, *sheet.label, rx=6, ry=6, fillColor=None if data else colors.HexColor("#f1f1f1"),
                           strokeColor=GUIDE, strokeWidth=0.5, strokeDashArray=[2, 2]))
            if data is not None:
                smallest = min(smallest, draw_label(d, data, x, y, sheet))
        if opts.size == "2x2" and opts.cut_lines:
            _cut_lines(d, sheet)
        elif preview and opts.size == "thermal2x1":
            d.add(Rect(0.5, 0.5, sheet.page[0] - 1, sheet.page[1] - 1, rx=5, ry=5, fillColor=None, strokeColor=GUIDE,
                       strokeWidth=0.5, strokeDashArray=[2, 2]))
        out.append(d)
    return out, smallest


def closeup(data: LabelData, opts: Options) -> Drawing:
    """One label on its own, outlined: the preview's close-up of what each label looks like."""
    sheet = sheet_for(opts.size, opts.square)
    w, h = sheet.label
    d = Drawing(w, h)
    d.add(Rect(0, 0, w, h, fillColor=colors.white, strokeColor=None))
    draw_label(d, data, 0, 0, sheet)
    r = 0 if opts.size == "2x2" else 5
    d.add(Rect(0.5, 0.5, w - 1, h - 1, rx=r, ry=r, fillColor=None, strokeColor=GUIDE, strokeWidth=0.5,
               strokeDashArray=[2, 2]))
    return d


def _cut_lines(d: Drawing, sheet: Sheet) -> None:
    """Dashed lines edge to edge along every square's sides: one straight cut does two squares."""
    w, h = sheet.page
    top = h - sheet.top
    for c in range(sheet.cols + 1):
        x = sheet.left + c * sheet.pitch[0]
        d.add(SLine(x, 0, x, h, strokeColor=GUIDE, strokeWidth=0.5, strokeDashArray=[3, 3]))
    for r in range(sheet.rows + 1):
        y = top - r * sheet.pitch[1]
        d.add(SLine(0, y, w, y, strokeColor=GUIDE, strokeWidth=0.5, strokeDashArray=[3, 3]))


def pdf(drawings: list[Drawing], title: str = "Coin labels") -> bytes:
    buf = io.BytesIO()
    c = pdfcanvas.Canvas(buf, pagesize=(drawings[0].width, drawings[0].height))
    c.setTitle(title)
    for d in drawings:
        c.setPageSize((d.width, d.height))
        renderPDF.draw(d, c, 0, 0)
        c.showPage()
    c.save()
    return buf.getvalue()


# The PDF's built-in fonts, as browsers name them (same letter widths), so the preview matches the print.
_SVG_FONTS = {
    "Courier-Bold": "'Courier New', Courier, monospace; font-weight: bold",
    "Helvetica-Bold": "Helvetica, Arial, sans-serif; font-weight: bold",
    "Helvetica": "Helvetica, Arial, sans-serif",
}


def svg(d: Drawing) -> str:
    out = renderSVG.drawToString(d)
    for name, css in _SVG_FONTS.items():
        out = out.replace(f"font-family: {name};", f"font-family: {css};")
    return out


