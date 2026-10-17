"""Insurance inventory report (PDF): every coin on hand with photo, identification, cost and estimated value."""

import io
from datetime import date
from decimal import Decimal

from PIL import Image as PILImage
from PIL import ImageOps
from reportlab.lib import colors
from reportlab.lib.pagesizes import landscape, letter
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import inch
from reportlab.platypus import Image, KeepTogether, PageBreak, Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle

from ..config import get_settings
from ..models import Coin, Collection, User
from . import photos as photo_store
from .coins import CENTS, latest_quote, value_estimate

NAVY = colors.HexColor("#1f3a5f")
GOLD = colors.HexColor("#b8892b")
GRID = colors.HexColor("#d9d6cf")
ZEBRA = colors.HexColor("#f6f5f1")
THUMB = 0.62 * inch

styles = getSampleStyleSheet()
SMALL = ParagraphStyle("small", parent=styles["BodyText"], fontSize=8, leading=10)
CELL = ParagraphStyle("cell", parent=styles["BodyText"], fontSize=8.5, leading=10.5)
HEAD = ParagraphStyle("head", parent=CELL, fontName="Helvetica-Bold", textColor=colors.white)
H1 = ParagraphStyle("h1", parent=styles["Title"], fontSize=20, leading=24, textColor=NAVY, alignment=0)
H2 = ParagraphStyle("h2", parent=styles["Heading2"], fontSize=13, textColor=NAVY, spaceBefore=6, spaceAfter=4)


def _money(v) -> str:
    return "—" if v is None else f"${Decimal(v):,.2f}"


def _date_mint(c: Coin) -> str:
    return f"{c.year}" if c.mint_mark == "P" else f"{c.year}-{c.mint_mark}"


def _grade(c: Coin) -> str:
    g = f"{c.grade_prefix or ''}{c.grade or ''}{'+' if c.grade_plus else ''}{'★' if c.grade_star else ''}"
    if c.strike_designation and g:
        g += f" {c.strike_designation}"
    return f"Raw {g}".strip() if c.grading_service == "RAW" else g


def _thumb(c: Coin):
    """First readable photo, shrunk and re-encoded so a big collection doesn't make a huge PDF."""
    for p in c.photos:
        path = photo_store.photo_path(c.id, p.file_name)
        if not path.exists():
            continue
        try:
            with PILImage.open(path) as im:
                im = ImageOps.exif_transpose(im).convert("RGB")
                im.thumbnail((240, 240))
                out = io.BytesIO()
                im.save(out, "JPEG", quality=80)
        except Exception:  # HEIC or anything Pillow can't read
            continue
        out.seek(0)
        w, h = im.size
        scale = THUMB / max(w, h)
        return Image(out, width=w * scale, height=h * scale)
    return Paragraph('<font color="#999999">No photo</font>', SMALL)


def _value_note(c: Coin) -> str:
    if c.value_source == "custom":
        return "Owner's value"
    parts = []
    q = latest_quote(c)
    if q:
        parts.append(f"CPG {q.fetched_at:%b %d, %Y}")
    if c.toner_premium:
        parts.append(f"+ toner {_money(c.toner_premium)}")
    if c.holder_premium:
        parts.append(f"+ holder {_money(c.holder_premium)}")
    return " ".join(parts) or "Not yet valued"


def _coin_row(c: Coin, type_name: str) -> list:
    desc = f"<b>{_date_mint(c)} {type_name}</b>"
    extras = [x for x in (c.variety, c.vam) if x]
    if extras:
        desc += "<br/>" + " · ".join(extras)
    slab = [s for on, s in ((c.slab_rattler, "Rattler"), (c.slab_ngc_fatty, "NGC Fatty"), (c.slab_ogh, "OGH"),
                            (c.slab_soapbox, "Soapbox"), (c.gsa_hard_pack, "GSA Hard Pack"),
                            (c.gsa_soft_pack, "GSA Soft Pack")) if on]
    if slab:
        desc += f'<br/><font color="#666666">{", ".join(slab)}</font>'
    service = "Raw (ungraded)" if c.grading_service == "RAW" else f"{c.grading_service} #{c.cert_number or '—'}"
    cac = f"CAC ({c.cac_sticker.title()})" if c.cac and c.cac_sticker else ("CAC" if c.cac else "")
    bought = _money(c.price_paid)
    if c.purchase_date:
        bought += f'<br/><font color="#666666">{c.purchase_date:%b %d, %Y}</font>'
    if c.purchased_from:
        bought += f'<br/><font color="#666666">{c.purchased_from}</font>'
    return [
        _thumb(c),
        Paragraph(c.inventory_number, CELL),
        Paragraph(desc, CELL),
        Paragraph(f"<b>{_grade(c) or '—'}</b><br/>{service}" + (f"<br/>{cac}" if cac else ""), CELL),
        Paragraph(bought, CELL),
        Paragraph(f"<b>{_money(value_estimate(c))}</b><br/><font color='#666666'>{_value_note(c)}</font>", CELL),
    ]


def build_pdf(user: User, groups: list[tuple[Collection, list[Coin]]], type_names: dict[int, str], scope: str) -> bytes:
    buf = io.BytesIO()
    doc = SimpleDocTemplate(
        buf, pagesize=landscape(letter), leftMargin=0.5 * inch, rightMargin=0.5 * inch,
        topMargin=0.55 * inch, bottomMargin=0.55 * inch,
        title=f"Coin inventory: {scope}", author=f"{user.first_name} {user.last_name}",
    )
    today = date.today()
    all_coins = [c for _, coins in groups for c in coins]
    cost = sum((c.price_paid or Decimal(0) for c in all_coins), Decimal(0))
    est = sum((value_estimate(c) or Decimal(0) for c in all_coins), Decimal(0))
    unvalued = sum(1 for c in all_coins if value_estimate(c) is None)
    discount = Decimal(str(get_settings().wholesale_discount))

    story = [
        Paragraph("Coin Collection Inventory", H1),
        Paragraph(f"Prepared for insurance purposes · {scope}", styles["Heading3"]),
        Spacer(1, 6),
        Paragraph(f"Owner: <b>{user.first_name} {user.last_name}</b> ({user.email})", styles["BodyText"]),
        Paragraph(f"Date: <b>{today:%B %d, %Y}</b>", styles["BodyText"]),
        Spacer(1, 12),
    ]
    summary = [["Collections", str(len(groups))], ["Coins", str(len(all_coins))],
               ["Total cost", _money(cost)], ["Total estimated value", _money(est)],
               [f"Estimated wholesale ({int(discount * 100)}% below)", _money((est * (1 - discount)).quantize(CENTS))]]
    if unvalued:
        summary.append(["Coins without a value", str(unvalued)])
    t = Table(summary, colWidths=[2.8 * inch, 1.8 * inch], hAlign="LEFT")
    t.setStyle(TableStyle([
        ("FONT", (0, 0), (-1, -1), "Helvetica", 10), ("FONT", (1, 0), (1, -1), "Helvetica-Bold", 10),
        ("LINEBELOW", (0, 0), (-1, -1), 0.5, GRID), ("ALIGN", (1, 0), (1, -1), "RIGHT"),
        ("TOPPADDING", (0, 0), (-1, -1), 5), ("BOTTOMPADDING", (0, 0), (-1, -1), 5),
    ]))
    story += [t, Spacer(1, 14)]
    story.append(Paragraph(
        "Estimated values come from the CDN Certified Price Guide (CPG) retail values, plus any premiums the owner "
        "recorded for toning or holder, or from the owner's own estimate where noted. They are estimates, not "
        "appraisals. Coins already sold are not included.", SMALL))
    if groups:
        story.append(PageBreak())

    widths = [0.8 * inch, 0.95 * inch, 2.75 * inch, 2.0 * inch, 1.5 * inch, 2.0 * inch]
    header = [Paragraph(h, HEAD) for h in ("Photo", "Inventory #", "Coin", "Grade / certification",
                                                       "Purchased", "Estimated value")]
    for col, coins in groups:
        col_cost = sum((c.price_paid or Decimal(0) for c in coins), Decimal(0))
        col_est = sum((value_estimate(c) or Decimal(0) for c in coins), Decimal(0))
        rows = [header] + [_coin_row(c, type_names.get(c.coin_type_id, "")) for c in coins]
        rows.append(["", "", Paragraph(f"<b>{len(coins)} coin{'s' if len(coins) != 1 else ''}</b>", CELL), "",
                     Paragraph(f"<b>{_money(col_cost)}</b>", CELL), Paragraph(f"<b>{_money(col_est)}</b>", CELL)])
        table = Table(rows, colWidths=widths, repeatRows=1)
        style = [
            ("BACKGROUND", (0, 0), (-1, 0), NAVY), ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
            ("VALIGN", (0, 0), (-1, -1), "MIDDLE"), ("LINEBELOW", (0, 0), (-1, -1), 0.4, GRID),
            ("LINEABOVE", (0, -1), (-1, -1), 1, NAVY), ("TOPPADDING", (0, 0), (-1, -1), 4),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
        ]
        for i in range(1, len(rows) - 1):
            if i % 2 == 0:
                style.append(("BACKGROUND", (0, i), (-1, i), ZEBRA))
        table.setStyle(TableStyle(style))
        story += [KeepTogether([Paragraph(col.name, H2)]), table, Spacer(1, 14)]

    def footer(canvas, doc_):
        canvas.saveState()
        canvas.setFont("Helvetica", 8)
        canvas.setFillColor(colors.HexColor("#666666"))
        canvas.drawString(0.5 * inch, 0.35 * inch, f"TrackMyCoins · {user.first_name} {user.last_name} · {today:%B %d, %Y}")
        canvas.drawRightString(landscape(letter)[0] - 0.5 * inch, 0.35 * inch, f"Page {doc_.page}")
        canvas.setStrokeColor(GOLD)
        canvas.setLineWidth(2)
        canvas.line(0.5 * inch, landscape(letter)[1] - 0.4 * inch, landscape(letter)[0] - 0.5 * inch, landscape(letter)[1] - 0.4 * inch)
        canvas.restoreState()

    doc.build(story, onFirstPage=footer, onLaterPages=footer)
    return buf.getvalue()
