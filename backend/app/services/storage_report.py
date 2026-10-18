"""Storage printout (PDF): everything kept in one storage spot, in position order. With values (for insurance) or
as a checklist (for checking the box or album against the list)."""

import io
import re
from datetime import date
from decimal import Decimal

from reportlab.lib import colors
from reportlab.lib.pagesizes import landscape, letter
from reportlab.lib.units import inch
from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle

from ..models import BullionItem, Coin, StorageSpot, User
from . import bullion as bsvc
from .coins import value_estimate
from .insurance import CELL, GOLD, GRID, H1, HEAD, NAVY, SMALL, ZEBRA, _date_mint, _e, _grade, _money, _thumb, styles


def position_key(position: str | None, inv: str) -> tuple:
    """"Page 2, hole 10" after "Page 2, hole 9"; items without a position last."""
    if not position:
        return (1, [], inv)
    parts = [int(p) if p.isdigit() else p.lower() for p in re.findall(r"\d+|\D+", position)]
    return (0, [(0, p) if isinstance(p, int) else (1, p) for p in parts], inv)


def build_pdf(user: User, spot: StorageSpot, coins: list[Coin], items: list[BullionItem], type_names: dict[int, str],
              spots_now: dict[str, Decimal | None], values: bool) -> bytes:
    buf = io.BytesIO()
    doc = SimpleDocTemplate(buf, pagesize=landscape(letter), leftMargin=0.5 * inch, rightMargin=0.5 * inch,
                            topMargin=0.55 * inch, bottomMargin=0.55 * inch, title=f"Storage: {spot.name}",
                            author=f"{user.first_name} {user.last_name}")
    today = date.today()
    rows: list[tuple[tuple, list, Decimal | None]] = []
    for c in coins:
        v = value_estimate(c)
        desc = f"<b>{_date_mint(c)} {_e(type_names.get(c.coin_type_id, ''))}</b>"
        extras = [_e(x) for x in (c.variety, c.vam) if x]
        if extras:
            desc += "<br/>" + " · ".join(extras)
        if c.location == "grading":
            desc += '<br/><font color="#b45a0c">At grading</font>'
        service = "Raw" if c.grading_service == "RAW" else f"{c.grading_service} #{_e(c.cert_number) or '—'}"
        cells = [Paragraph(_e(c.storage_position) or "", CELL), _thumb(c), Paragraph(c.inventory_number, CELL),
                 Paragraph(desc, CELL), Paragraph(f"<b>{_e(_grade(c)) or '—'}</b><br/>{service}", CELL)]
        rows.append((position_key(c.storage_position, c.inventory_number), cells, v))
    for i in items:
        spot_ = spots_now.get(i.collection.metal)
        oz = bsvc.pure_oz(i)
        v = (oz * spot_).quantize(bsvc.CENTS) if spot_ is not None else None
        amount = f"${i.face_value} face" if i.face_value is not None else f"{Decimal(str(i.weight)).normalize()} {i.weight_unit}"
        if i.face_value is None and (i.quantity or 1) > 1:
            amount += f" × {i.quantity}"
        cells = [Paragraph(_e(i.storage_position) or "", CELL), _thumb(i, f"bullion-{i.id}"), Paragraph(i.inventory_number, CELL),
                 Paragraph(f"<b>{_e(i.description)}</b><br/>{amount}", CELL),
                 Paragraph(f"{Decimal(str(i.purity)).normalize()} fine<br/>{oz.normalize()} ozt pure", CELL)]
        rows.append((position_key(i.storage_position, i.inventory_number), cells, v))
    rows.sort(key=lambda r: r[0])

    last = "Value" if values else "✓"
    header = [Paragraph(h, HEAD) for h in ("Position", "Photo", "Inventory #", "Item", "Grade / details", last)]
    body = []
    for _, cells, v in rows:
        body.append(cells + [Paragraph(f"<b>{_money(v)}</b>", CELL) if values else ""])
    total = sum((v for _, _, v in rows if v is not None), Decimal(0))
    widths = [1.0 * inch, 0.8 * inch, 1.0 * inch, 3.3 * inch, 2.2 * inch, 1.7 * inch if values else 0.7 * inch]
    table_rows = [header] + body
    if values:
        table_rows.append(["", "", "", Paragraph(f"<b>{len(rows)} item{'s' if len(rows) != 1 else ''}</b>", CELL), "",
                           Paragraph(f"<b>{_money(total.quantize(bsvc.CENTS))}</b>", CELL)])
    table = Table(table_rows, colWidths=widths, repeatRows=1)
    style = [
        ("BACKGROUND", (0, 0), (-1, 0), NAVY), ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"), ("LINEBELOW", (0, 0), (-1, -1), 0.4, GRID),
        ("TOPPADDING", (0, 0), (-1, -1), 4), ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
    ]
    if values:
        style.append(("LINEABOVE", (0, -1), (-1, -1), 1, NAVY))
    else:
        # An empty box to tick for each item.
        for n in range(1, len(table_rows)):
            style.append(("BOX", (5, n), (5, n), 0.8, colors.HexColor("#555555")))
    for n in range(1, len(body) + 1):
        if n % 2 == 0:
            style.append(("BACKGROUND", (0, n), (4, n), ZEBRA))
    table.setStyle(TableStyle(style))

    story = [
        Paragraph(_e(spot.name), H1),
        Paragraph(f"{'Storage inventory with estimated values' if values else 'Storage checklist'} · "
                  f"{len(rows)} item{'s' if len(rows) != 1 else ''}", styles["Heading3"]),
    ]
    if spot.notes:
        story.append(Paragraph(_e(spot.notes).replace("\n", "<br/>"), styles["BodyText"]))
    story += [Paragraph(f"Owner: <b>{_e(user.first_name)} {_e(user.last_name)}</b> · {today:%B %d, %Y}", SMALL),
              Spacer(1, 10), table if rows else Paragraph("Nothing is stored here yet.", styles["BodyText"])]
    if values and rows:
        story += [Spacer(1, 8), Paragraph(
            "Coin values are the owner's estimates (CPG plus any premiums, or their own value); bullion is melt at "
            "today's spot. Estimates, not appraisals.", SMALL)]

    def footer(canvas, doc_):
        canvas.saveState()
        canvas.setFont("Helvetica", 8)
        canvas.setFillColor(colors.HexColor("#666666"))
        canvas.drawString(0.5 * inch, 0.35 * inch, f"TrackMyCoins · {spot.name} · {today:%B %d, %Y}")
        canvas.drawRightString(landscape(letter)[0] - 0.5 * inch, 0.35 * inch, f"Page {doc_.page}")
        canvas.setStrokeColor(GOLD)
        canvas.setLineWidth(2)
        canvas.line(0.5 * inch, landscape(letter)[1] - 0.4 * inch, landscape(letter)[0] - 0.5 * inch,
                    landscape(letter)[1] - 0.4 * inch)
        canvas.restoreState()

    doc.build(story, onFirstPage=footer, onLaterPages=footer)
    return buf.getvalue()
