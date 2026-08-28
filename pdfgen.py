"""
pdfgen.py — Generates the GrinderCrusherScreen sales quotation as a finished PDF
that mirrors the canonical template. Uses reportlab (offline, no services).
"""
import os
from reportlab.lib.pagesizes import letter
from reportlab.lib.units import inch
from reportlab.lib.colors import HexColor, white
from reportlab.lib.enums import TA_LEFT, TA_RIGHT, TA_CENTER
from reportlab.platypus import (SimpleDocTemplate, Table, TableStyle, Paragraph,
                                Spacer, Image, HRFlowable)
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle

RED = HexColor("#C81010")
BLACK = HexColor("#1A1A1A")
HDR_BLACK = HexColor("#202020")
GREY = HexColor("#808080")
LIGHT = HexColor("#F0F0F0")
ZEBRA = HexColor("#F7F7F7")
YELLOW = HexColor("#FFF200")

CONTENT_W = 6.7 * inch


def _num(v):
    try:
        return float(str(v).replace("$", "").replace(",", "").strip() or 0)
    except (ValueError, TypeError):
        return 0.0


def _money(v):
    n = _num(v)
    return "${:,.0f}".format(n) if n == int(n) else "${:,.2f}".format(n)


def _clean_items(items, default_desc):
    """Drop rows with no description and no amount; keep at least one line."""
    kept = [it for it in (items or [])
            if str(it.get('desc', '')).strip() or str(it.get('amount', '')).strip()]
    return kept or [{"desc": default_desc, "amount": ""}]


def build_quote_pdf(data, out_path):
    doc = SimpleDocTemplate(out_path, pagesize=letter,
                            leftMargin=0.9*inch, rightMargin=0.9*inch,
                            topMargin=0.55*inch, bottomMargin=0.5*inch)
    ss = getSampleStyleSheet()
    el = []

    def P(text, size=10, color=BLACK, bold=False, italic=False, align=TA_LEFT,
          font="Helvetica", leading=None):
        f = font
        if bold and italic:
            f = "Helvetica-BoldOblique"
        elif bold:
            f = "Helvetica-Bold"
        elif italic:
            f = "Helvetica-Oblique"
        st = ParagraphStyle("x", fontName=f, fontSize=size, textColor=color,
                            alignment=align, leading=leading or size*1.25)
        return Paragraph(text, st)

    # ---------- HEADER ----------
    logo_path = data.get('_logo_path')
    company_block = [
        P(data.get('company_name', 'GrinderCrusherScreen'), 16, BLACK, bold=True, align=TA_RIGHT),
        P(data.get('company_address', '1772 Corn Rd, Smyrna, GA 30080'), 9, GREY, align=TA_RIGHT),
        P(data.get('company_phone', '770-433-2670'), 9, GREY, align=TA_RIGHT),
    ]
    if logo_path and os.path.exists(logo_path):
        try:
            img = Image(logo_path, width=2.0*inch, height=1.2*inch, kind='proportional')
            left = img
        except Exception:
            left = P(data.get('company_name', ''), 14, BLACK, bold=True)
    else:
        left = P("", 10)
    htab = Table([[left, company_block]], colWidths=[3.2*inch, 3.5*inch])
    htab.setStyle(TableStyle([
        ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
        ('LEFTPADDING', (0, 0), (-1, -1), 0),
        ('RIGHTPADDING', (0, 0), (-1, -1), 0),
    ]))
    el.append(htab)
    el.append(Spacer(1, 6))
    el.append(HRFlowable(width="100%", thickness=2.2, color=RED, spaceAfter=8))

    # ---------- TITLE ----------
    title_left = [
        P("SALES QUOTATION", 23, BLACK, bold=True),
        P(data.get('subtitle', 'Equipment &amp; Freight Estimate'), 11, RED, italic=True),
    ]
    title_right = [
        P(f"<b>Date</b>  {data.get('date','')}", 9, BLACK, align=TA_RIGHT),
        P(f"<b>Valid Until</b>  {data.get('valid_until','')}", 9, BLACK, align=TA_RIGHT),
    ]
    ttab = Table([[title_left, title_right]], colWidths=[4.4*inch, 2.3*inch])
    ttab.setStyle(TableStyle([
        ('VALIGN', (0, 0), (0, 0), 'TOP'),
        ('VALIGN', (1, 0), (1, 0), 'BOTTOM'),
        ('LEFTPADDING', (0, 0), (-1, -1), 0),
        ('RIGHTPADDING', (0, 0), (-1, -1), 0),
    ]))
    el.append(ttab)
    el.append(Spacer(1, 10))

    # ---------- PREPARED BY / CUSTOMER ----------
    def kv_rows(rows):
        data_rows = []
        for label, val, red in rows:
            data_rows.append([
                P(label, 8, GREY, bold=True),
                P(str(val), 10, RED if red else BLACK, bold=red),
            ])
        t = Table(data_rows, colWidths=[1.15*inch, 2.0*inch])
        t.setStyle(TableStyle([
            ('VALIGN', (0, 0), (-1, -1), 'TOP'),
            ('LEFTPADDING', (0, 0), (-1, -1), 0),
            ('TOPPADDING', (0, 0), (-1, -1), 3),
            ('BOTTOMPADDING', (0, 0), (-1, -1), 3),
            ('LINEBELOW', (1, 0), (1, -1), 0.5, HexColor("#DDDDDD")),
        ]))
        return t

    def section_bar(label):
        lbl = P(label, 10, BLACK, bold=True)
        bar = Table([["", lbl]], colWidths=[0.07*inch, 3.18*inch])
        bar.setStyle(TableStyle([
            ('BACKGROUND', (0, 0), (0, 0), RED),
            ('BACKGROUND', (1, 0), (1, 0), LIGHT),
            ('TOPPADDING', (0, 0), (-1, -1), 6),
            ('BOTTOMPADDING', (0, 0), (-1, -1), 6),
            ('LEFTPADDING', (0, 0), (0, 0), 0),
            ('LEFTPADDING', (1, 0), (1, 0), 8),
            ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
        ]))
        return bar

    prep = [
        section_bar("PREPARED BY"), Spacer(1, 4),
        kv_rows([
            ("NAME", data.get('rep_name', ''), False),
            ("TITLE", data.get('rep_title', ''), False),
            ("MOBILE", data.get('rep_mobile', ''), True),
        ])
    ]
    cust = [
        section_bar("CUSTOMER INFORMATION"), Spacer(1, 4),
        kv_rows([
            ("NAME", data.get('cust_name', ''), False),
            ("COMPANY", data.get('cust_company', ''), False),
            ("CITY / STATE", data.get('cust_city', ''), False),
            ("EMAIL", data.get('cust_email', ''), False),
        ])
    ]
    info = Table([[prep, cust]], colWidths=[3.35*inch, 3.35*inch])
    info.setStyle(TableStyle([
        ('VALIGN', (0, 0), (-1, -1), 'TOP'),
        ('LEFTPADDING', (0, 0), (0, 0), 0),
        ('RIGHTPADDING', (1, 0), (1, 0), 0),
        ('LEFTPADDING', (1, 0), (1, 0), 12),
    ]))
    el.append(info)
    el.append(Spacer(1, 10))

    # ---------- EQUIPMENT ----------
    def line_table(header_right, items, default_desc):
        rows = [[P("DESCRIPTION", 9, white, bold=True),
                 P(header_right, 9, white, bold=True, align=TA_RIGHT)]]
        items = _clean_items(items, default_desc)
        for it in items:
            amt = it.get('amount', '')
            rows.append([
                P(it.get('desc', ''), 10, BLACK),
                P(_money(amt) if amt not in ('', None) else '', 10, BLACK, align=TA_RIGHT),
            ])
        t = Table(rows, colWidths=[5.0*inch, 1.7*inch])
        style = [
            ('BACKGROUND', (0, 0), (-1, 0), HDR_BLACK),
            ('TOPPADDING', (0, 0), (-1, 0), 7),
            ('BOTTOMPADDING', (0, 0), (-1, 0), 7),
            ('TOPPADDING', (0, 1), (-1, -1), 6),
            ('BOTTOMPADDING', (0, 1), (-1, -1), 6),
            ('LEFTPADDING', (0, 0), (-1, -1), 10),
            ('RIGHTPADDING', (0, 0), (-1, -1), 10),
            ('LINEBELOW', (0, 1), (-1, -1), 0.5, HexColor("#E5E5E5")),
            ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
        ]
        for i in range(1, len(rows)):
            if i % 2 == 0:
                style.append(('BACKGROUND', (0, i), (-1, i), ZEBRA))
        t.setStyle(TableStyle(style))
        return t, items

    el.append(section_bar_full("EQUIPMENT & PRICING"))
    el.append(Spacer(1, 6))
    eq_table, eq_items = line_table("AMOUNT", data.get('equipment_items', []), "Machine / Equipment")
    el.append(eq_table)
    el.append(HRFlowable(width="100%", thickness=1.2, color=RED, spaceBefore=2, spaceAfter=2))
    eq_total = sum(_num(i.get('amount')) for i in eq_items)
    subtab = Table([[P("Equipment Subtotal", 10.5, BLACK, bold=True),
                     P(_money(eq_total), 10.5, BLACK, bold=True, align=TA_RIGHT)]],
                   colWidths=[5.0*inch, 1.7*inch])
    subtab.setStyle(TableStyle([
        ('BACKGROUND', (1, 0), (1, 0), YELLOW),
        ('LEFTPADDING', (0, 0), (-1, -1), 10),
        ('RIGHTPADDING', (0, 0), (-1, -1), 10),
        ('TOPPADDING', (0, 0), (-1, -1), 5),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 5),
    ]))
    el.append(subtab)
    el.append(Spacer(1, 10))

    # ---------- FREIGHT ----------
    el.append(section_bar_full("FREIGHT ESTIMATE"))
    el.append(Spacer(1, 6))
    fr_table, fr_items = line_table("ESTIMATED COST", data.get('freight_items', []), "Freight to Customer")
    el.append(fr_table)
    fr_total = sum(_num(i.get('amount')) for i in fr_items)
    fsub = Table([[P("Freight Subtotal", 10.5, BLACK, bold=True),
                   P(_money(fr_total), 10.5, BLACK, bold=True, align=TA_RIGHT)]],
                 colWidths=[5.0*inch, 1.7*inch])
    fsub.setStyle(TableStyle([
        ('LEFTPADDING', (0, 0), (-1, -1), 10),
        ('RIGHTPADDING', (0, 0), (-1, -1), 10),
        ('TOPPADDING', (0, 0), (-1, -1), 5),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 5),
    ]))
    el.append(fsub)
    el.append(Spacer(1, 10))

    # ---------- TOTAL ----------
    grand = eq_total + fr_total
    tot = Table([[P("TOTAL ESTIMATE", 12, white, bold=True),
                  P(_money(grand), 13, white, bold=True, align=TA_RIGHT)]],
                colWidths=[5.0*inch, 1.7*inch])
    tot.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (-1, -1), HDR_BLACK),
        ('LEFTPADDING', (0, 0), (-1, -1), 10),
        ('RIGHTPADDING', (0, 0), (-1, -1), 10),
        ('TOPPADDING', (0, 0), (-1, -1), 9),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 9),
        ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
    ]))
    el.append(tot)
    el.append(Spacer(1, 10))

    # ---------- NOTES & TERMS ----------
    el.append(section_bar_full("NOTES & TERMS"))
    el.append(Spacer(1, 6))
    for label, val in [("Payment Terms:", data.get('payment_terms', '')),
                       ("Lead Time:", data.get('lead_time', '')),
                       ("Freight Note:", data.get('freight_note', '')),
                       ("Additional Notes:", data.get('additional_notes', ''))]:
        if val:
            el.append(P(f"<b>{label}</b> {val}", 9.5, BLACK))
            el.append(Spacer(1, 3))

    el.append(Spacer(1, 10))
    el.append(P(data.get('footer',
        "Thank you for the opportunity to earn your business.  •  "
        "GrinderCrusherScreen.com  •  770-433-2670"), 8.5, GREY, italic=True, align=TA_CENTER))

    doc.build(el)
    return out_path


def section_bar_full(label):
    lbl = Paragraph(label, ParagraphStyle("s", fontName="Helvetica-Bold",
                                          fontSize=10, textColor=BLACK))
    # tiny first column acts as the red accent tick
    bar = Table([["", lbl]], colWidths=[0.07*inch, CONTENT_W - 0.07*inch])
    bar.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (0, 0), RED),
        ('BACKGROUND', (1, 0), (1, 0), LIGHT),
        ('TOPPADDING', (0, 0), (-1, -1), 6),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 6),
        ('LEFTPADDING', (0, 0), (0, 0), 0),
        ('LEFTPADDING', (1, 0), (1, 0), 8),
        ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
    ]))
    return bar
