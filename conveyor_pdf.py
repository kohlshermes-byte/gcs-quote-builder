"""Generate a PDF from a conveyor quote.

Prefers headless Chrome/Edge when available (pixel-faithful HTML print).
Falls back to ReportLab so Save PDF works on Macs that only have Safari.
"""
import json
import os
import shutil
import subprocess
import sys

from reportlab.lib.colors import HexColor, white
from reportlab.lib.enums import TA_LEFT, TA_RIGHT, TA_CENTER
from reportlab.lib.pagesizes import letter
from reportlab.lib.styles import ParagraphStyle
from reportlab.lib.units import inch
from reportlab.platypus import (
    SimpleDocTemplate,
    Table,
    TableStyle,
    Paragraph,
    Spacer,
    Image,
    KeepTogether,
    ListFlowable,
    ListItem,
    PageBreak,
    Flowable,
)

BASE = os.path.dirname(os.path.abspath(__file__))
LOGO_PATH = os.path.join(BASE, "assets", "logo.png")

RED = HexColor("#CC0000")
BLACK = HexColor("#111111")
GRAY = HexColor("#888888")
BORDER = HexColor("#DDDDDD")


def _browser_candidates():
    found = []
    for name in ("msedge", "chrome", "chromium", "google-chrome"):
        path = shutil.which(name)
        if path:
            found.append(path)

    if sys.platform == "win32":
        for path in (
            r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe",
            r"C:\Program Files\Microsoft\Edge\Application\msedge.exe",
            r"C:\Program Files\Google\Chrome\Application\chrome.exe",
            r"C:\Program Files (x86)\Google\Chrome\Application\chrome.exe",
        ):
            if os.path.isfile(path):
                found.append(path)
    elif sys.platform == "darwin":
        for path in (
            "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome",
            "/Applications/Microsoft Edge.app/Contents/MacOS/Microsoft Edge",
        ):
            if os.path.isfile(path):
                found.append(path)

    seen = set()
    out = []
    for path in found:
        norm = os.path.normcase(os.path.abspath(path))
        if norm not in seen:
            seen.add(norm)
            out.append(path)
    return out


def _file_url(path):
    path = os.path.abspath(path)
    return "file:///" + path.replace("\\", "/")


def prepare_print_html(html_path):
    """Write a print-ready HTML copy with local logo paths for file:// rendering."""
    html_path = os.path.abspath(html_path)
    with open(html_path, encoding="utf-8") as f:
        html = f.read()
    if os.path.isfile(LOGO_PATH):
        html = html.replace('src="/logo"', f'src="{_file_url(LOGO_PATH)}"')
    print_path = html_path.replace(".html", ".print.html")
    with open(print_path, "w", encoding="utf-8") as f:
        f.write(html)
    return print_path


def _run_print(browser, pdf_path, page_url):
    args = [
        browser,
        "--headless=new",
        "--disable-gpu",
        "--no-sandbox",
        "--disable-dev-shm-usage",
        "--no-pdf-header-footer",
        "--run-all-composables-before-draw",
        "--virtual-time-budget=5000",
        f"--print-to-pdf={pdf_path}",
        page_url,
    ]
    return subprocess.run(
        args,
        capture_output=True,
        text=True,
        timeout=60,
        check=False,
    )


def _try_chromium_pdf(pdf_path, html_path):
    """Return pdf_path on success, else None. Does not raise."""
    browsers = _browser_candidates()
    if not browsers:
        return None

    print_html = prepare_print_html(html_path)
    target_url = _file_url(print_html)

    for browser in browsers:
        if os.path.isfile(pdf_path):
            try:
                os.remove(pdf_path)
            except OSError:
                pass
        try:
            result = _run_print(browser, pdf_path, target_url)
            if os.path.isfile(pdf_path) and os.path.getsize(pdf_path) > 0:
                return pdf_path
        except Exception:
            pass

        # Legacy Chromium builds use the older flag name.
        if os.path.isfile(pdf_path):
            try:
                os.remove(pdf_path)
            except OSError:
                pass
        try:
            result = subprocess.run(
                [
                    browser,
                    "--headless=new",
                    "--disable-gpu",
                    "--no-sandbox",
                    "--disable-dev-shm-usage",
                    "--print-to-pdf-no-header",
                    "--run-all-composables-before-draw",
                    "--virtual-time-budget=5000",
                    f"--print-to-pdf={pdf_path}",
                    target_url,
                ],
                capture_output=True,
                text=True,
                timeout=60,
                check=False,
            )
            if os.path.isfile(pdf_path) and os.path.getsize(pdf_path) > 0:
                return pdf_path
        except Exception:
            pass

    return None


def _load_quote_data(html_path, data=None):
    if data is not None:
        return data
    jdir = os.path.dirname(os.path.abspath(html_path))
    jp = os.path.join(jdir, "conveyor.json")
    if not os.path.isfile(jp):
        raise FileNotFoundError("Quote data (conveyor.json) not found for PDF fallback")
    with open(jp, encoding="utf-8") as f:
        return json.load(f)


def _p(text, size=10, color=BLACK, bold=False, align=TA_LEFT, leading=None):
    font = "Helvetica-Bold" if bold else "Helvetica"
    style = ParagraphStyle(
        "p",
        fontName=font,
        fontSize=size,
        textColor=color,
        alignment=align,
        leading=leading or size * 1.3,
    )
    return Paragraph(str(text or "").replace("\n", "<br/>"), style)


def _format_address(customer):
    try:
        import conveyor_render
        return conveyor_render._format_customer_address(customer)
    except Exception:
        return (customer or {}).get("address") or ""


def _money_component(val):
    try:
        import conveyor_render
        return conveyor_render._format_component_money(val)
    except Exception:
        return str(val or "$0")


def _money_total(val):
    try:
        import conveyor_render
        return conveyor_render._format_total_money(val)
    except Exception:
        return str(val or "$0.00")


def _lead_time(val):
    try:
        import conveyor_render
        return conveyor_render._format_lead_time(val)
    except Exception:
        return str(val or "In Stock")


def _issued_date(quote_date):
    try:
        import conveyor_render
        return conveyor_render._issued_date(quote_date)
    except Exception:
        return f"ISSUED {quote_date}" if quote_date else "ISSUED"


def _as_list(val):
    if not val:
        return []
    if isinstance(val, list):
        return [str(x).strip() for x in val if str(x).strip()]
    if isinstance(val, str):
        return [ln.strip() for ln in val.splitlines() if ln.strip()]
    return [str(val).strip()]


def _bullet_block(label, items):
    items = _as_list(items)
    if not items:
        return None
    flow = [
        _p(label.upper(), 8, GRAY, bold=True, leading=10),
        Spacer(1, 1),
        ListFlowable(
            [ListItem(_p(item, 9, BLACK, leading=11), leftIndent=6, bulletColor=BLACK) for item in items],
            bulletType="bullet",
            start="•",
            leftIndent=10,
            bulletFontSize=8,
            spaceBefore=0,
            spaceAfter=0,
        ),
        Spacer(1, 5),
    ]
    return flow  # list of flowables; caller should extend


def _hairline(space_before=0, space_after=0, width=6.8 * inch):
    """1px section rule with identical weight everywhere."""

    class _Rule(Flowable):
        def __init__(self, w):
            Flowable.__init__(self)
            self._w = w

        def wrap(self, availWidth, availHeight):
            # Always span the full content frame so every rule is the same length.
            self.width = availWidth
            return self.width, 1

        def draw(self):
            self.canv.setStrokeColor(BORDER)
            self.canv.setLineWidth(0.5)
            self.canv.setLineCap(1)
            self.canv.line(0, 0.5, self.width, 0.5)

    bits = []
    if space_before:
        bits.append(Spacer(1, space_before))
    bits.append(_Rule(width))
    if space_after:
        bits.append(Spacer(1, space_after))
    return bits


def _contact_table(rows, value_width=2.0 * inch):
    """Label + value rows with fixed label column (matches HTML .contact-row)."""
    # Fixed label column so every value lines up on the same left edge,
    # with a clear gutter after the longest label ("ADDRESS").
    label_w = 1.05 * inch
    data = []
    for label, value in rows:
        data.append([
            Paragraph(
                str(label or "").upper(),
                ParagraphStyle(
                    "cl",
                    fontName="Helvetica",
                    fontSize=7,
                    textColor=GRAY,
                    leading=9,
                ),
            ),
            Paragraph(
                str(value or "—"),
                ParagraphStyle(
                    "cv",
                    fontName="Helvetica",
                    fontSize=9,
                    textColor=BLACK,
                    leading=11,
                ),
            ),
        ])
    t = Table(data, colWidths=[label_w, value_width])
    t.setStyle(TableStyle([
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("LEFTPADDING", (0, 0), (0, -1), 0),
        ("RIGHTPADDING", (0, 0), (0, -1), 0),
        ("LEFTPADDING", (1, 0), (1, -1), 10),
        ("RIGHTPADDING", (1, 0), (1, -1), 0),
        ("TOPPADDING", (0, 0), (-1, -1), 3),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 3),
    ]))
    return t


def _resolve_equipment_image(image_url, cache_dir):
    """Download or reuse a cached equipment image for PDF embedding."""
    url = (image_url or "").strip()
    if not url:
        return None
    if os.path.isfile(url):
        return url

    cache_dir = cache_dir or os.path.join(BASE, "jobs")
    os.makedirs(cache_dir, exist_ok=True)

    # Stable cache name from URL path
    import hashlib
    import urllib.parse

    path = urllib.parse.urlparse(url).path
    ext = os.path.splitext(path)[1].lower()
    if ext not in (".jpg", ".jpeg", ".png", ".gif", ".webp"):
        ext = ".jpg"
    digest = hashlib.sha1(url.encode("utf-8")).hexdigest()[:16]
    dest = os.path.join(cache_dir, f"equipment_{digest}{ext}")

    if os.path.isfile(dest) and os.path.getsize(dest) > 0:
        return dest

    try:
        import requests
        resp = requests.get(url, timeout=25)
        resp.raise_for_status()
        with open(dest, "wb") as f:
            f.write(resp.content)
        if os.path.getsize(dest) > 0:
            return dest
    except Exception:
        if os.path.isfile(dest):
            try:
                os.remove(dest)
            except OSError:
                pass
    return None


def _equipment_image_flowable(image_url, cache_dir):
    path = _resolve_equipment_image(image_url, cache_dir)
    if not path:
        return None
    try:
        # HTML: max-width 280px, max-height 180px
        img = Image(path, width=2.4 * inch, height=1.55 * inch, kind="proportional")
        # Thin border like the HTML quote
        framed = Table([[img]], colWidths=[2.5 * inch])
        framed.setStyle(TableStyle([
            ("BOX", (0, 0), (-1, -1), 0.5, BORDER),
            ("LEFTPADDING", (0, 0), (-1, -1), 3),
            ("RIGHTPADDING", (0, 0), (-1, -1), 3),
            ("TOPPADDING", (0, 0), (-1, -1), 3),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 3),
        ]))
        return KeepTogether([framed, Spacer(1, 6)])
    except Exception:
        return None


def build_conveyor_pdf_reportlab(pdf_path, data, cache_dir=None):
    """Render conveyor quote JSON to PDF without Chrome/Edge."""
    customer = data.get("customer") or {}
    rep = data.get("rep") or {}
    totals = data.get("totals") or {}
    line_items = data.get("line_items") or []
    details = data.get("equipment_details") or []
    quote_num = data.get("quote_num") or "GCS-00000000"
    quote_date = data.get("quote_date") or ""
    issued = _issued_date(quote_date)
    custom_build = bool(
        data.get("quote_mode") == "custom_build" or data.get("custom_addons_required")
    )
    total_pages = 2 if details else 1
    if not cache_dir:
        cache_dir = os.path.dirname(os.path.abspath(pdf_path))

    doc = SimpleDocTemplate(
        pdf_path,
        pagesize=letter,
        leftMargin=0.85 * inch,
        rightMargin=0.85 * inch,
        topMargin=0.55 * inch,
        bottomMargin=0.55 * inch,
    )
    story = []

    # Top bar
    top = Table(
        [[
            _p("OFFICIAL QUOTATION", 8, BLACK, bold=True),
            _p(f'DOC N<super rise="2" size="5">o</super>  <b>{quote_num}</b>', 8, GRAY),
            _p(issued, 8, GRAY, align=TA_RIGHT),
        ]],
        colWidths=[2.2 * inch, 2.4 * inch, 2.2 * inch],
    )
    top.setStyle(TableStyle([
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ("LEFTPADDING", (0, 0), (-1, -1), 0),
        ("RIGHTPADDING", (0, 0), (-1, -1), 0),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 8),
    ]))
    story.append(top)
    story.extend(_hairline(space_after=14))

    # Header: logo | company | Quotation
    if os.path.isfile(LOGO_PATH):
        try:
            logo = Image(LOGO_PATH, width=1.9 * inch, height=1.15 * inch, kind="proportional")
        except Exception:
            logo = _p("GrinderCrusherScreen", 12, BLACK, bold=True)
    else:
        logo = _p("GrinderCrusherScreen", 12, BLACK, bold=True)

    company = [
        _p("GrinderCrusherScreen", 11, BLACK, bold=True),
        _p("1772 Cord Rd SE", 9, BLACK),
        _p("Smyrna, GA 30080", 9, BLACK),
        _p("Office: 770-433-2670", 9, BLACK),
        _p("Web: GrinderCrusherScreen.com", 9, BLACK),
    ]
    quotation = [
        _p("CUSTOMER DOCUMENT", 7, GRAY, align=TA_RIGHT),
        Paragraph(
            'Quot<font color="#CC0000">a</font>tion',
            ParagraphStyle(
                "qw",
                fontName="Times-Bold",
                fontSize=36,
                textColor=BLACK,
                alignment=TA_RIGHT,
                leading=40,
            ),
        ),
        _p(f"Ref: <b>{quote_num}</b>", 9, GRAY, align=TA_RIGHT),
    ]
    header = Table([[logo, company, quotation]], colWidths=[2.1 * inch, 2.4 * inch, 2.3 * inch])
    header.setStyle(TableStyle([
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ("LEFTPADDING", (0, 0), (-1, -1), 0),
        ("RIGHTPADDING", (0, 0), (0, 0), 10),
        ("LEFTPADDING", (1, 0), (1, 0), 10),
        ("LINEBEFORE", (1, 0), (1, 0), 0.5, BORDER),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 10),
    ]))
    story.append(header)
    story.extend(_hairline(space_after=14))

    # Quote date strip
    story.append(_p("QUOTE DATE", 7, GRAY, bold=True))
    story.append(Spacer(1, 4))
    story.append(_p(quote_date or "—", 13, BLACK, bold=True))
    story.append(Spacer(1, 12))
    story.extend(_hairline())

    # Parties: Issued To | Prepared By
    # Horizontal rules are separate hairlines (identical weight/length).
    # Vertical divider only on the parties table.
    cust_block = [
        Spacer(1, 12),
        _p("ISSUED TO", 7, GRAY, bold=True),
        Spacer(1, 6),
        _p(customer.get("company") or "[Customer Company]", 18, BLACK, bold=True, leading=22),
        Spacer(1, 10),
        _contact_table([
            ("Contact", customer.get("contact") or "[Contact Name]"),
            ("Email", customer.get("email") or "[customer@email.com]"),
            ("Phone", customer.get("phone") or "[Phone Number]"),
            ("Address", _format_address(customer)),
        ]),
        Spacer(1, 10),
    ]
    rep_block = [
        Spacer(1, 12),
        _p("PREPARED BY", 7, GRAY, bold=True),
        Spacer(1, 6),
        _p(rep.get("name") or "[Sales Rep Name]", 18, BLACK, bold=True, leading=22),
        Spacer(1, 10),
        _contact_table([
            ("Email", rep.get("email") or "[rep@grindercrusherscreen.com]"),
            ("Phone", rep.get("phone") or "[Direct Number]"),
        ]),
        Spacer(1, 10),
    ]
    parties = Table([[cust_block, rep_block]], colWidths=[3.4 * inch, 3.4 * inch])
    parties.setStyle(TableStyle([
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("LEFTPADDING", (0, 0), (0, 0), 0),
        ("RIGHTPADDING", (0, 0), (0, 0), 16),
        ("LEFTPADDING", (1, 0), (1, 0), 16),
        ("RIGHTPADDING", (1, 0), (1, 0), 0),
        ("TOPPADDING", (0, 0), (-1, -1), 0),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 0),
        ("LINEBEFORE", (1, 0), (1, 0), 0.5, BORDER),
    ]))
    story.append(parties)
    # Small gap so the vertical divider does not collide with the bottom rule.
    story.append(Spacer(1, 4))
    story.extend(_hairline(space_after=16))

    story.append(_p("ITEMS & PRICING", 9, BLACK, bold=True))
    story.append(Spacer(1, 6))

    item_rows = [[
        _p("ITEM", 8, white, bold=True),
        _p("AMOUNT", 8, white, bold=True, align=TA_RIGHT),
        _p("LEAD TIME", 8, white, bold=True, align=TA_RIGHT),
    ]]
    for item in line_items or [{"model": "[SKU / Model]", "amount": "$0", "lead_time": "—"}]:
        model = item.get("model") or "[SKU / Model]"
        if custom_build:
            addons = (item.get("addons") or "").strip() or "[Custom add-ons]"
            desc_bits = [f"<b>{model}</b>", "<font size='7' color='#888888'>CUSTOM ADD-ONS</font>", addons]
        else:
            desc = (item.get("description") or "").strip()
            desc_bits = [f"<b>{model}</b>"]
            if desc:
                desc_bits.append(desc)
        item_rows.append([
            _p("<br/>".join(desc_bits), 10, BLACK),
            _p(_money_component(item.get("amount")), 11, BLACK, bold=True, align=TA_RIGHT),
            _p(_lead_time(item.get("lead_time")), 10, BLACK, align=TA_RIGHT),
        ])

    items_tbl = Table(item_rows, colWidths=[4.2 * inch, 1.3 * inch, 1.3 * inch])
    items_tbl.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, 0), BLACK),
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("TOPPADDING", (0, 0), (-1, 0), 7),
        ("BOTTOMPADDING", (0, 0), (-1, 0), 7),
        ("TOPPADDING", (0, 1), (-1, -1), 10),
        ("BOTTOMPADDING", (0, 1), (-1, -1), 10),
        ("LEFTPADDING", (0, 0), (-1, -1), 8),
        ("RIGHTPADDING", (0, 0), (-1, -1), 8),
        ("LINEBELOW", (0, -1), (-1, -1), 1.5, BLACK),
    ]))
    story.append(items_tbl)
    story.append(Spacer(1, 16))

    financing = [
        _p("FINANCING", 9, BLACK, bold=True),
        Spacer(1, 4),
        _p(
            "Equipment financing options available by request.<br/><br/>"
            "No pre-payment penalty after 1 year.<br/><br/>"
            "Visit GrinderCrusherScreen.com/pages/financing",
            10,
            GRAY,
        ),
    ]
    total_rows = [
        [_p("SUBTOTAL", 8, GRAY), _p(_money_component(totals.get("subtotal")), 10, BLACK, bold=True, align=TA_RIGHT)],
        [_p("FREIGHT RATE", 8, GRAY), _p(_money_component(totals.get("freight")), 10, BLACK, bold=True, align=TA_RIGHT)],
        [_p("TAX", 8, GRAY), _p(_money_component(totals.get("tax")), 10, BLACK, bold=True, align=TA_RIGHT)],
        [_p("TOTAL", 9, RED, bold=True), _p(_money_total(totals.get("grand_total")), 14, RED, bold=True, align=TA_RIGHT)],
    ]
    totals_tbl = Table(total_rows, colWidths=[1.6 * inch, 1.5 * inch])
    totals_tbl.setStyle(TableStyle([
        ("LINEBELOW", (0, 0), (-1, 2), 0.5, BORDER),
        ("LINEBELOW", (0, 3), (-1, 3), 1.5, BLACK),
        ("TOPPADDING", (0, 0), (-1, -1), 6),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 6),
        ("LEFTPADDING", (0, 0), (-1, -1), 0),
        ("RIGHTPADDING", (0, 0), (-1, -1), 0),
    ]))
    bottom = Table([[financing, totals_tbl]], colWidths=[3.5 * inch, 3.3 * inch])
    bottom.setStyle(TableStyle([
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("LEFTPADDING", (0, 0), (-1, -1), 0),
        ("ALIGN", (1, 0), (1, 0), "RIGHT"),
    ]))
    story.append(bottom)
    story.append(Spacer(1, 24))

    footer1 = Table(
        [[
            _p(quote_num, 7, GRAY),
            _p(f"Page 1 of {total_pages}", 7, GRAY, align=TA_CENTER),
            _p("GrinderCrusherScreen  |  Smyrna, GA", 7, GRAY, align=TA_RIGHT),
        ]],
        colWidths=[2.2 * inch, 2.4 * inch, 2.2 * inch],
    )
    footer1.setStyle(TableStyle([
        ("LINEABOVE", (0, 0), (-1, -1), 0.5, BORDER),
        ("TOPPADDING", (0, 0), (-1, -1), 10),
        ("LEFTPADDING", (0, 0), (-1, -1), 0),
        ("RIGHTPADDING", (0, 0), (-1, -1), 0),
    ]))
    story.append(footer1)

    # Detail pages
    if details:
        story.append(PageBreak())
        top2 = Table(
            [[
                _p("OFFICIAL QUOTATION", 8, BLACK, bold=True),
                _p(f'DOC N<super rise="2" size="5">o</super>  <b>{quote_num}</b>', 8, GRAY),
                _p(issued, 8, GRAY, align=TA_RIGHT),
            ]],
            colWidths=[2.2 * inch, 2.4 * inch, 2.2 * inch],
        )
        top2.setStyle(TableStyle([
            ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
            ("LEFTPADDING", (0, 0), (-1, -1), 0),
            ("RIGHTPADDING", (0, 0), (-1, -1), 0),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 8),
        ]))
        story.append(top2)
        story.extend(_hairline(space_after=14))
        story.append(_p("DETAILED EQUIPMENT INFORMATION", 9, BLACK, bold=True))
        story.append(Spacer(1, 12))

        for detail in details:
            story.append(_p(detail.get("name") or "Equipment", 13, BLACK, bold=True))
            story.append(Spacer(1, 8))

            img_flow = _equipment_image_flowable(detail.get("image_url"), cache_dir)
            if img_flow:
                story.append(img_flow)

            desc = (detail.get("description") or "").strip()
            if desc:
                story.append(_p("DESCRIPTION", 8, GRAY, bold=True))
                story.append(Spacer(1, 2))
                story.append(_p(desc, 10, BLACK))
                story.append(Spacer(1, 8))

            for label, key in (
                ("Frame", "frame"),
                ("Idlers", "idlers"),
                ("Undercarriage", "undercarriage"),
                ("Belt", "belt"),
                ("Other", "other"),
            ):
                block = _bullet_block(label, detail.get(key))
                if block:
                    story.extend(block)

            for label, key in (
                ("Travel", "travel"),
                ("Road Portable Option", "road_portable_option"),
                ("Power", "power"),
                ("Custom Add-Ons", "custom_addons"),
                ("Assembly", "assembly"),
            ):
                block = _bullet_block(label, detail.get(key))
                if block:
                    story.extend(block)

            if not custom_build:
                specs = detail.get("specifications") or []
                spec_rows = []
                for spec in specs:
                    label = (spec.get("label") or "").strip()
                    value = (spec.get("value") or "").strip()
                    if label and value:
                        spec_rows.append([
                            _p(label.upper(), 8, GRAY),
                            _p(value, 10, BLACK, bold=True),
                        ])
                if spec_rows:
                    story.append(_p("SPECIFICATIONS", 8, GRAY, bold=True))
                    story.append(Spacer(1, 4))
                    st = Table(spec_rows, colWidths=[2.6 * inch, 4.2 * inch])
                    st.setStyle(TableStyle([
                        ("LINEBELOW", (0, 0), (-1, -1), 0.5, BORDER),
                        ("TOPPADDING", (0, 0), (-1, -1), 5),
                        ("BOTTOMPADDING", (0, 0), (-1, -1), 5),
                        ("LEFTPADDING", (0, 0), (-1, -1), 0),
                        ("VALIGN", (0, 0), (-1, -1), "TOP"),
                    ]))
                    story.append(st)
                    story.append(Spacer(1, 10))

            features = detail.get("features") or []
            if features and not any(detail.get(k) for k in ("frame", "idlers", "belt", "other")):
                block = _bullet_block("Features", features)
                if block:
                    story.extend(block)

            story.append(Spacer(1, 12))

        footer2 = Table(
            [[
                _p(quote_num, 7, GRAY),
                _p(f"Page 2 of {total_pages}", 7, GRAY, align=TA_CENTER),
                _p("GrinderCrusherScreen  |  Smyrna, GA", 7, GRAY, align=TA_RIGHT),
            ]],
            colWidths=[2.2 * inch, 2.4 * inch, 2.2 * inch],
        )
        footer2.setStyle(TableStyle([
            ("LINEABOVE", (0, 0), (-1, -1), 0.5, BORDER),
            ("TOPPADDING", (0, 0), (-1, -1), 10),
            ("LEFTPADDING", (0, 0), (-1, -1), 0),
            ("RIGHTPADDING", (0, 0), (-1, -1), 0),
        ]))
        story.append(footer2)

    doc.build(story)
    return pdf_path


def build_conveyor_pdf(pdf_path, *, html_path, data=None):
    """Render saved quote HTML/data to PDF.

    Uses Chrome/Edge when installed. Otherwise builds with ReportLab so
    Save PDF works in Safari (and any browser) without installing Chrome.
    """
    html_path = os.path.abspath(html_path)
    pdf_path = os.path.abspath(pdf_path)
    if not os.path.isfile(html_path) and data is None:
        raise FileNotFoundError(f"Quote HTML not found: {html_path}")

    os.makedirs(os.path.dirname(pdf_path) or ".", exist_ok=True)
    if os.path.isfile(pdf_path):
        os.remove(pdf_path)

    if os.path.isfile(html_path):
        chromium = _try_chromium_pdf(pdf_path, html_path)
        if chromium:
            return chromium

    quote_data = _load_quote_data(html_path if os.path.isfile(html_path) else ".", data)
    cache_dir = os.path.dirname(html_path) if os.path.isfile(html_path) else os.path.dirname(pdf_path)
    return build_conveyor_pdf_reportlab(pdf_path, quote_data, cache_dir=cache_dir)
