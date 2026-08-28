"""
docgen.py — Generates the GrinderCrusherScreen sales quotation as an editable .docx
that matches the canonical template. Pure python-docx, no external services.
"""
import os
from datetime import datetime
from docx import Document
from docx.shared import Pt, RGBColor, Inches, Emu
from docx.enum.text import WD_ALIGN_PARAGRAPH
from docx.enum.table import WD_TABLE_ALIGNMENT, WD_ALIGN_VERTICAL
from docx.oxml.ns import qn
from docx.oxml import OxmlElement

# Brand palette (pulled from the template)
RED = RGBColor(0xC8, 0x10, 0x10)
BLACK = RGBColor(0x1A, 0x1A, 0x1A)
DARKHDR = RGBColor(0x20, 0x20, 0x20)
GREY_LABEL = RGBColor(0x80, 0x80, 0x80)
LIGHT_GREY = "F0F0F0"
ZEBRA = "F7F7F7"
HEADER_BLACK = "202020"
HIGHLIGHT = "FFF200"  # yellow subtotal highlight


def _set_cell_bg(cell, hex_color):
    tcPr = cell._tc.get_or_add_tcPr()
    shd = OxmlElement('w:shd')
    shd.set(qn('w:val'), 'clear')
    shd.set(qn('w:color'), 'auto')
    shd.set(qn('w:fill'), hex_color)
    tcPr.append(shd)


def _set_cell_margins(cell, top=80, bottom=80, left=120, right=120):
    tcPr = cell._tc.get_or_add_tcPr()
    m = OxmlElement('w:tcMar')
    for tag, val in (('top', top), ('bottom', bottom), ('start', left), ('end', right)):
        node = OxmlElement(f'w:{tag}')
        node.set(qn('w:w'), str(val))
        node.set(qn('w:type'), 'dxa')
        m.append(node)
    tcPr.append(m)


def _no_table_borders(table):
    tbl = table._tbl
    tblPr = tbl.tblPr
    borders = OxmlElement('w:tblBorders')
    for edge in ('top', 'left', 'bottom', 'right', 'insideH', 'insideV'):
        e = OxmlElement(f'w:{edge}')
        e.set(qn('w:val'), 'none')
        borders.append(e)
    tblPr.append(borders)


def _bottom_border(paragraph, color="C81010", size=12):
    p = paragraph._p
    pPr = p.get_or_add_pPr()
    pbdr = OxmlElement('w:pBdr')
    bottom = OxmlElement('w:bottom')
    bottom.set(qn('w:val'), 'single')
    bottom.set(qn('w:sz'), str(size))
    bottom.set(qn('w:space'), '1')
    bottom.set(qn('w:color'), color)
    pbdr.append(bottom)
    pPr.append(pbdr)


def _section_header(doc, text):
    """Grey bar with red accent tick + bold label, like the template's section heads."""
    table = doc.add_table(rows=1, cols=1)
    table.alignment = WD_TABLE_ALIGNMENT.CENTER
    _no_table_borders(table)
    cell = table.cell(0, 0)
    _set_cell_bg(cell, LIGHT_GREY)
    _set_cell_margins(cell, top=100, bottom=100, left=160, right=160)
    p = cell.paragraphs[0]
    run = p.add_run("▌ ")
    run.font.color.rgb = RED
    run.font.size = Pt(11)
    run2 = p.add_run(text)
    run2.bold = True
    run2.font.size = Pt(10.5)
    run2.font.color.rgb = BLACK
    doc.add_paragraph().paragraph_format.space_after = Pt(2)
    return table


def _money(v):
    try:
        n = float(str(v).replace("$", "").replace(",", "").strip() or 0)
    except ValueError:
        return str(v)
    return "${:,.0f}".format(n) if n == int(n) else "${:,.2f}".format(n)


def _clean_items(items, default_desc):
    """Drop rows with no description and no amount; keep at least one line."""
    kept = [it for it in (items or [])
            if str(it.get('desc', '')).strip() or str(it.get('amount', '')).strip()]
    return kept or [{"desc": default_desc, "amount": ""}]


def build_quote(data, out_path):
    """data: dict with the quote fields. out_path: where to write the .docx."""
    doc = Document()

    # US Letter, 1" margins
    sec = doc.sections[0]
    sec.page_width = Inches(8.5)
    sec.page_height = Inches(11)
    for m in ('top', 'bottom', 'left', 'right'):
        setattr(sec, f'{m}_margin', Inches(0.9))

    style = doc.styles['Normal']
    style.font.name = 'Arial'
    style.font.size = Pt(10)

    # ---------- HEADER: logo (optional) + company block ----------
    htab = doc.add_table(rows=1, cols=2)
    _no_table_borders(htab)
    htab.columns[0].width = Inches(3.0)
    htab.columns[1].width = Inches(3.7)
    logo_cell = htab.cell(0, 0)
    logo_path = data.get('_logo_path')
    if logo_path and os.path.exists(logo_path):
        try:
            logo_cell.paragraphs[0].add_run().add_picture(logo_path, width=Inches(2.0))
        except Exception:
            logo_cell.paragraphs[0].add_run(data.get('company_name', 'GrinderCrusherScreen')).bold = True
    co_cell = htab.cell(0, 1)
    co_cell.vertical_alignment = WD_ALIGN_VERTICAL.CENTER
    cp = co_cell.paragraphs[0]
    cp.alignment = WD_ALIGN_PARAGRAPH.RIGHT
    r = cp.add_run(data.get('company_name', 'GrinderCrusherScreen'))
    r.bold = True
    r.font.size = Pt(16)
    r.font.color.rgb = BLACK
    for line in (data.get('company_address', '1772 Corn Rd, Smyrna, GA 30080'),
                 data.get('company_phone', '770-433-2670')):
        pl = co_cell.add_paragraph()
        pl.alignment = WD_ALIGN_PARAGRAPH.RIGHT
        rl = pl.add_run(line)
        rl.font.size = Pt(9)
        rl.font.color.rgb = GREY_LABEL

    rule = doc.add_paragraph()
    _bottom_border(rule, color="C81010", size=18)

    # ---------- TITLE BLOCK ----------
    ttab = doc.add_table(rows=1, cols=2)
    _no_table_borders(ttab)
    ttab.columns[0].width = Inches(4.3)
    ttab.columns[1].width = Inches(2.4)
    tcell = ttab.cell(0, 0)
    tp = tcell.paragraphs[0]
    tr = tp.add_run("SALES QUOTATION")
    tr.bold = True
    tr.font.size = Pt(26)
    tr.font.color.rgb = BLACK
    sp = tcell.add_paragraph()
    sr = sp.add_run(data.get('subtitle', 'Equipment & Freight Estimate'))
    sr.italic = True
    sr.font.size = Pt(11)
    sr.font.color.rgb = RED

    dcell = ttab.cell(0, 1)
    dcell.vertical_alignment = WD_ALIGN_VERTICAL.BOTTOM
    for label, val in (("Date", data.get('date', '')),
                       ("Valid Until", data.get('valid_until', ''))):
        dp = dcell.add_paragraph()
        dp.alignment = WD_ALIGN_PARAGRAPH.RIGHT
        lr = dp.add_run(f"{label}  ")
        lr.bold = True
        lr.font.size = Pt(9)
        lr.font.color.rgb = GREY_LABEL
        vr = dp.add_run(str(val))
        vr.font.size = Pt(9)
        vr.font.color.rgb = BLACK

    doc.add_paragraph().paragraph_format.space_after = Pt(4)

    # ---------- PREPARED BY / CUSTOMER ----------
    info = doc.add_table(rows=1, cols=2)
    _no_table_borders(info)
    info.columns[0].width = Inches(3.35)
    info.columns[1].width = Inches(3.35)

    def info_block(cell, header, rows):
        # header bar
        htbl = cell.add_table(rows=1, cols=1)
        _no_table_borders(htbl)
        hc = htbl.cell(0, 0)
        _set_cell_bg(hc, LIGHT_GREY)
        _set_cell_margins(hc, 70, 70, 140, 140)
        hpar = hc.paragraphs[0]
        a = hpar.add_run("▌ ")
        a.font.color.rgb = RED
        b = hpar.add_run(header)
        b.bold = True
        b.font.size = Pt(10)
        b.font.color.rgb = BLACK
        cell.add_paragraph().paragraph_format.space_after = Pt(2)
        for label, val, red in rows:
            rp = cell.add_paragraph()
            rp.paragraph_format.space_after = Pt(3)
            lr = rp.add_run(label + "\t")
            lr.bold = True
            lr.font.size = Pt(8)
            lr.font.color.rgb = GREY_LABEL
            vr = rp.add_run(str(val))
            vr.font.size = Pt(10)
            vr.font.color.rgb = RED if red else BLACK
            if red:
                vr.bold = True
            # tab stop for alignment
            tab_stops = rp.paragraph_format.tab_stops
            tab_stops.add_tab_stop(Inches(1.15))

    # clear default paragraph in cells
    info.cell(0, 0).paragraphs[0].text = ""
    info.cell(0, 1).paragraphs[0].text = ""

    info_block(info.cell(0, 0), "PREPARED BY", [
        ("NAME", data.get('rep_name', ''), False),
        ("TITLE", data.get('rep_title', ''), False),
        ("MOBILE", data.get('rep_mobile', ''), True),
    ])
    info_block(info.cell(0, 1), "CUSTOMER INFORMATION", [
        ("NAME", data.get('cust_name', ''), False),
        ("COMPANY", data.get('cust_company', ''), False),
        ("CITY / STATE", data.get('cust_city', ''), False),
        ("EMAIL", data.get('cust_email', ''), False),
    ])

    doc.add_paragraph().paragraph_format.space_after = Pt(6)

    # ---------- EQUIPMENT & PRICING ----------
    _section_header(doc, "EQUIPMENT & PRICING")

    eq = doc.add_table(rows=1, cols=2)
    eq.alignment = WD_TABLE_ALIGNMENT.CENTER
    eq.columns[0].width = Inches(5.0)
    eq.columns[1].width = Inches(1.7)
    # header row
    hdr = eq.rows[0]
    for i, (txt, align) in enumerate([("DESCRIPTION", WD_ALIGN_PARAGRAPH.LEFT),
                                      ("AMOUNT", WD_ALIGN_PARAGRAPH.RIGHT)]):
        c = hdr.cells[i]
        _set_cell_bg(c, HEADER_BLACK)
        _set_cell_margins(c, 90, 90, 140, 140)
        p = c.paragraphs[0]
        p.alignment = align
        run = p.add_run(txt)
        run.bold = True
        run.font.size = Pt(9)
        run.font.color.rgb = RGBColor(0xFF, 0xFF, 0xFF)

    line_items = _clean_items(data.get('equipment_items', []), "Machine / Equipment")
    for idx, item in enumerate(line_items):
        row = eq.add_row()
        c0, c1 = row.cells
        _set_cell_margins(c0, 80, 80, 140, 140)
        _set_cell_margins(c1, 80, 80, 140, 140)
        if idx % 2 == 1:
            _set_cell_bg(c0, ZEBRA)
            _set_cell_bg(c1, ZEBRA)
        p0 = c0.paragraphs[0]
        r0 = p0.add_run(item.get('desc', ''))
        r0.font.size = Pt(10)
        p1 = c1.paragraphs[0]
        p1.alignment = WD_ALIGN_PARAGRAPH.RIGHT
        amt = item.get('amount', '')
        r1 = p1.add_run(_money(amt) if amt not in ('', None) else '')
        r1.font.size = Pt(10)

    # red rule above subtotal
    rl = doc.add_paragraph()
    _bottom_border(rl, color="C81010", size=12)

    sub = doc.add_table(rows=1, cols=2)
    sub.columns[0].width = Inches(5.0)
    sub.columns[1].width = Inches(1.7)
    sc0, sc1 = sub.rows[0].cells
    _set_cell_margins(sc0, 60, 60, 140, 140)
    _set_cell_margins(sc1, 60, 60, 140, 140)
    sp0 = sc0.paragraphs[0]
    sr0 = sp0.add_run("Equipment Subtotal")
    sr0.bold = True
    sr0.font.size = Pt(10.5)
    sp1 = sc1.paragraphs[0]
    sp1.alignment = WD_ALIGN_PARAGRAPH.RIGHT
    _set_cell_bg(sc1, HIGHLIGHT)
    eq_total = sum(_to_num(i.get('amount')) for i in line_items)
    sr1 = sp1.add_run(_money(eq_total))
    sr1.bold = True
    sr1.font.size = Pt(10.5)

    doc.add_paragraph().paragraph_format.space_after = Pt(6)

    # ---------- FREIGHT ESTIMATE ----------
    _section_header(doc, "FREIGHT ESTIMATE")
    fr = doc.add_table(rows=1, cols=2)
    fr.columns[0].width = Inches(5.0)
    fr.columns[1].width = Inches(1.7)
    fhdr = fr.rows[0]
    for i, (txt, align) in enumerate([("DESCRIPTION", WD_ALIGN_PARAGRAPH.LEFT),
                                      ("ESTIMATED COST", WD_ALIGN_PARAGRAPH.RIGHT)]):
        c = fhdr.cells[i]
        _set_cell_bg(c, HEADER_BLACK)
        _set_cell_margins(c, 90, 90, 140, 140)
        p = c.paragraphs[0]
        p.alignment = align
        run = p.add_run(txt)
        run.bold = True
        run.font.size = Pt(9)
        run.font.color.rgb = RGBColor(0xFF, 0xFF, 0xFF)

    freight_items = _clean_items(data.get('freight_items', []), "Freight to Customer")
    for idx, item in enumerate(freight_items):
        row = fr.add_row()
        c0, c1 = row.cells
        _set_cell_margins(c0, 80, 80, 140, 140)
        _set_cell_margins(c1, 80, 80, 140, 140)
        if idx % 2 == 1:
            _set_cell_bg(c0, ZEBRA)
            _set_cell_bg(c1, ZEBRA)
        r0 = c0.paragraphs[0].add_run(item.get('desc', ''))
        r0.font.size = Pt(10)
        p1 = c1.paragraphs[0]
        p1.alignment = WD_ALIGN_PARAGRAPH.RIGHT
        amt = item.get('amount', '')
        r1 = p1.add_run(_money(amt) if amt not in ('', None) else '')
        r1.font.size = Pt(10)

    # freight subtotal
    fsub = doc.add_table(rows=1, cols=2)
    fsub.columns[0].width = Inches(5.0)
    fsub.columns[1].width = Inches(1.7)
    fc0, fc1 = fsub.rows[0].cells
    _set_cell_margins(fc0, 60, 60, 140, 140)
    _set_cell_margins(fc1, 60, 60, 140, 140)
    fr0 = fc0.paragraphs[0].add_run("Freight Subtotal")
    fr0.bold = True
    fr0.font.size = Pt(10.5)
    fp1 = fc1.paragraphs[0]
    fp1.alignment = WD_ALIGN_PARAGRAPH.RIGHT
    freight_total = sum(_to_num(i.get('amount')) for i in freight_items)
    fr1 = fp1.add_run(_money(freight_total))
    fr1.bold = True
    fr1.font.size = Pt(10.5)

    doc.add_paragraph().paragraph_format.space_after = Pt(8)

    # ---------- TOTAL ----------
    tot = doc.add_table(rows=1, cols=2)
    tot.columns[0].width = Inches(5.0)
    tot.columns[1].width = Inches(1.7)
    tc0, tc1 = tot.rows[0].cells
    _set_cell_bg(tc0, HEADER_BLACK)
    _set_cell_bg(tc1, HEADER_BLACK)
    _set_cell_margins(tc0, 110, 110, 140, 140)
    _set_cell_margins(tc1, 110, 110, 140, 140)
    tr0 = tc0.paragraphs[0].add_run("TOTAL ESTIMATE")
    tr0.bold = True
    tr0.font.size = Pt(12)
    tr0.font.color.rgb = RGBColor(0xFF, 0xFF, 0xFF)
    tp1 = tc1.paragraphs[0]
    tp1.alignment = WD_ALIGN_PARAGRAPH.RIGHT
    grand = eq_total + freight_total
    tr1 = tp1.add_run(_money(grand))
    tr1.bold = True
    tr1.font.size = Pt(13)
    tr1.font.color.rgb = RGBColor(0xFF, 0xFF, 0xFF)

    doc.add_paragraph().paragraph_format.space_after = Pt(6)

    # ---------- NOTES & TERMS ----------
    _section_header(doc, "NOTES & TERMS")
    terms = [
        ("Payment Terms:", data.get('payment_terms', '')),
        ("Lead Time:", data.get('lead_time', '')),
        ("Freight Note:", data.get('freight_note', '')),
        ("Additional Notes:", data.get('additional_notes', '')),
    ]
    for label, val in terms:
        if not val:
            continue
        p = doc.add_paragraph()
        p.paragraph_format.space_after = Pt(3)
        lr = p.add_run(label + " ")
        lr.bold = True
        lr.font.size = Pt(9.5)
        vr = p.add_run(str(val))
        vr.font.size = Pt(9.5)

    foot = doc.add_paragraph()
    foot.alignment = WD_ALIGN_PARAGRAPH.CENTER
    foot.paragraph_format.space_before = Pt(14)
    fr = foot.add_run(data.get('footer',
        "Thank you for the opportunity to earn your business.  •  "
        "GrinderCrusherScreen.com  •  770-433-2670"))
    fr.font.size = Pt(8.5)
    fr.font.color.rgb = GREY_LABEL
    fr.italic = True

    doc.save(out_path)
    return out_path


def _to_num(v):
    try:
        return float(str(v).replace("$", "").replace(",", "").strip() or 0)
    except (ValueError, TypeError):
        return 0.0
