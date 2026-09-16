"""
conveyor_render.py — Populate conveyor_template.html from conveyor.json data.
"""
import html
import os
import re

BASE = os.path.dirname(os.path.abspath(__file__))
TEMPLATE_PATH = os.path.join(BASE, "conveyor_template.html")


def _esc(text):
    return html.escape(str(text or ""))


def _rich_text(text):
    """Escape HTML and render markdown-style _italic_ spans as <em>."""
    s = str(text or "")
    if not s:
        return ""
    if "_" not in s:
        return _esc(s)
    out = []
    pos = 0
    for m in re.finditer(r"_(.+?)_", s):
        if m.start() > pos:
            out.append(_esc(s[pos:m.start()]))
        out.append(f"<em>{_esc(m.group(1))}</em>")
        pos = m.end()
    if pos < len(s):
        out.append(_esc(s[pos:]))
    return "".join(out)


def _rich_text_block(text):
    """Like _rich_text but preserve line breaks for multiline fields."""
    lines = str(text or "").splitlines()
    if not lines:
        return ""
    return "<br>".join(_rich_text(line) for line in lines)

def _parse_money(val):
    if val is None or str(val).strip() == "":
        return None
    s = str(val).strip().replace("$", "").replace(",", "")
    try:
        return float(s)
    except ValueError:
        return None


def _format_component_money(val):
    """Subtotal/freight/tax/line amounts: omit .00 unless cents are present."""
    n = _parse_money(val)
    if n is None:
        return str(val or "").strip() or "$0.00"
    if abs(n - round(n)) < 0.000001:
        return f"${n:,.0f}"
    return f"${n:,.2f}"


def _format_total_money(val):
    """Grand total: always show two decimal places."""
    n = _parse_money(val)
    if n is None:
        return "$0.00"
    return f"${n:,.2f}"


def _format_customer_address(customer):
    """Format customer address for the quote document."""
    import address_format

    customer = customer or {}
    legacy = (customer.get("address") or "").strip()
    street = address_format.format_street(customer.get("street"))
    city = address_format.format_city(customer.get("city"))
    state = address_format.format_state(customer.get("state"))
    zip_code = address_format.format_zip(customer.get("zip") or customer.get("zip_code"))
    country = address_format.format_country(customer.get("country"))

    if not any((street, city, state, zip_code, country)):
        return address_format.format_legacy_address(legacy) or "[Street | City, ST ZIP]"

    parts = []
    if street:
        parts.append(street)
    if city:
        parts.append(city)
    state_zip = " ".join(part for part in (state, zip_code) if part).strip()
    if state_zip:
        parts.append(state_zip)
    line = ", ".join(parts)
    if country:
        line = f"{line}, {country}" if line else country
    return line or legacy or "[Street | City, ST ZIP]"


def _format_lead_time(val):
    text = str(val or "").strip()
    if not text or text in ("—", "-"):
        return "In Stock"
    return text

def _format_money(val):
    return _format_component_money(val)


def _is_addon_category_label(line):
    """True for section headers like 'Conveyor Width:' or 'Options:'."""
    text = str(line or "").strip()
    return not text or text.endswith(":")


def _format_custom_addon_value(line):
    """Format a single custom add-on value line for the quote item block."""
    text = str(line or "").strip()
    if not text:
        return ""
    width_match = re.match(r'^(\d+\s*")', text)
    if width_match:
        return f'{width_match.group(1).strip()} Wide Belt'
    return text


def _format_custom_addons(text):
    """Render pasted custom add-ons: values only, one line break between sections."""
    text = str(text or "").strip()
    if not text:
        return "[Custom add-ons]"
    pieces = [piece.strip() for piece in re.split(r"\n\s*\n+", text) if piece.strip()]
    if not pieces:
        pieces = [text]
    blocks = []
    for piece in pieces:
        values = []
        for line in piece.splitlines():
            line = line.strip()
            if _is_addon_category_label(line):
                continue
            formatted = _format_custom_addon_value(line)
            if formatted:
                values.append(_rich_text(formatted))
        if values:
            blocks.append("<br>".join(values))
    return "<br>".join(blocks) if blocks else "[Custom add-ons]"


def _render_line_items(items, custom_build=False):
    rows = []
    for item in items or []:
        model = _esc(item.get("model") or "[SKU / Model]")
        amount = _esc(_format_money(item.get("amount")))
        lead = _esc(_format_lead_time(item.get("lead_time")))
        if custom_build:
            addons_html = _format_custom_addons(item.get("addons") or "")
            item_html = f"""
          <div class="item-model" contenteditable="true">{model}</div>
          <div class="item-addon-label">Custom Add-Ons</div>
          <div class="item-desc" contenteditable="true">{addons_html}</div>"""
        else:
            desc = (item.get("description") or "").strip()
            desc_html = ""
            if desc:
                desc_html = f"""
          <div class="item-desc" contenteditable="true">{_esc(desc)}</div>"""
            item_html = f"""
          <div class="item-model" contenteditable="true">{model}</div>{desc_html}"""
        rows.append(f"""
      <tr>
        <td class="col-item">{item_html}
        </td>
        <td class="col-amount">
          <div class="item-amount" contenteditable="true">{amount}</div>
        </td>
        <td class="col-lead">
          <div class="item-lead" contenteditable="true">{lead}</div>
        </td>
      </tr>""")
    return "\n".join(rows) if rows else _render_line_items([{
        "model": "[SKU / Model]", "addons": "", "description": "",
        "amount": "$0.00", "lead_time": "—",
    }], custom_build=custom_build)


def _render_category(label, bullets):
    if not bullets:
        return ""
    items = "".join(f"<li>{_rich_text(b)}</li>" for b in bullets if b)
    if not items:
        return ""
    return f"""
      <div class="detail-category-label">{_esc(label)}</div>
      <ul class="detail-bullet-list">{items}</ul>"""


def _render_equipment_block(detail, source_urls, custom_build=False):
    name = _esc(detail.get("name") or "Equipment")
    desc_raw = detail.get("description") or ""
    img = detail.get("image_url") or ""
    img_html = ""
    if img:
        img_html = f'<img class="equipment-detail-image" src="{_esc(img)}" alt="{name}">'

    categories_html = ""
    for label, key in (
        ("Frame", "frame"),
        ("Idlers", "idlers"),
        ("Undercarriage", "undercarriage"),
        ("Belt", "belt"),
    ):
        bullets = detail.get(key) or []
        if bullets and isinstance(bullets, str):
            bullets = [ln.strip() for ln in bullets.split("\n") if ln.strip()]
        categories_html += _render_category(label, bullets)

    travel = detail.get("travel") or ""
    if isinstance(travel, list):
        travel = travel[0] if travel else ""
    if travel:
        categories_html += _render_category("Travel", [travel])

    road_opt = detail.get("road_portable_option") or ""
    if isinstance(road_opt, list):
        road_opt = road_opt[0] if road_opt else ""
    if road_opt and "road portable" in travel.lower():
        categories_html += _render_category("Road Portable Option", [road_opt])

    power = detail.get("power") or ""
    if isinstance(power, list):
        power = power[0] if power else ""
    if power:
        power_lines = [ln.strip() for ln in str(power).split("\n") if ln.strip()]
        categories_html += _render_category("Power", power_lines or [power])

    addons = detail.get("custom_addons") or []
    if addons and isinstance(addons, str):
        addons = [ln.strip() for ln in addons.split("\n") if ln.strip()]
    categories_html += _render_category("Custom Add-Ons", addons)

    other = detail.get("other") or []
    if other and isinstance(other, str):
        other = [ln.strip() for ln in other.split("\n") if ln.strip()]
    categories_html += _render_category("Other", other)

    assembly = detail.get("assembly") or ""
    if isinstance(assembly, list):
        assembly = assembly[0] if assembly else ""
    if assembly:
        categories_html += _render_category("Assembly", [assembly])

    spec_rows = ""
    if not custom_build:
        for spec in detail.get("specifications") or []:
            label = _esc(spec.get("label") or "")
            value = _esc(spec.get("value") or "")
            if label and value:
                spec_rows += f"""
            <tr><td class="spec-label">{label}</td><td class="spec-value">{value}</td></tr>"""

    specs_html = ""
    if spec_rows:
        specs_html = f"""
      <div class="detail-category-label">Specifications</div>
      <table class="spec-table"><tbody>{spec_rows}</tbody></table>"""

    # Legacy features fallback
    features = detail.get("features") or []
    features_html = ""
    if features and not categories_html:
        items = "".join(f"<li>{_esc(f)}</li>" for f in features)
        features_html = f'<ul class="feature-list">{items}</ul>'

    sources = [u for u in source_urls if u]
    source_html = ""
    if sources:
        links = ", ".join(f'<a href="{_esc(u)}">{_esc(u)}</a>' for u in sources)
        source_html = f'<div class="source-note">Data sourced from {links}</div>'

    desc_html = ""
    if desc_raw:
        desc_html = f"""
      <div class="detail-category-label">Description</div>
      <div class="equipment-detail-desc">{_rich_text_block(desc_raw)}</div>"""

    return f"""
    <div class="equipment-detail-block">
      <div class="equipment-detail-name">{name}</div>
      {img_html}
      {desc_html}
      {categories_html}
      {specs_html}
      {features_html}
      {source_html}
    </div>"""


def _render_detail_page(page_num, total_pages, quote_num, issued_date, content_html):
    return f"""
  <div class="page" id="page-detail-{page_num}">
    <div class="top-bar">
      <span class="official">OFFICIAL QUOTATION</span>
      <span class="doc-no">DOC №</span>
      <span class="quote-num">{_esc(quote_num)}</span>
      <span class="issued">{_esc(issued_date)}</span>
    </div>
    <div class="section-header">
      <span class="section-title">Detailed Equipment Information</span>
    </div>
    {content_html}
    <div class="footer-bar" style="margin-top: auto;">
      <span>{_esc(quote_num)}</span>
      <span>Page {page_num} of {total_pages}</span>
      <span>GrinderCrusherScreen &nbsp;|&nbsp; Smyrna, GA</span>
    </div>
  </div>"""


def _render_equipment_pages(data, quote_num, issued_date, total_pages=2):
    details = data.get("equipment_details") or []
    if not details:
        return ""

    urls = data.get("urls") or {}
    source_urls = [urls.get("listing"), urls.get("request_quote")]
    custom_build = bool(
        data.get("quote_mode") == "custom_build" or data.get("custom_addons_required")
    )
    blocks = [_render_equipment_block(d, source_urls, custom_build) for d in details]
    combined = "".join(blocks)

    # Single detail page for now; split later if content grows
    detail_page_num = 2 if total_pages >= 2 else 1
    return _render_detail_page(detail_page_num, total_pages, quote_num, issued_date, combined)


def _issued_date(quote_date):
    if not quote_date:
        return "ISSUED"
    try:
        from datetime import datetime
        for fmt in ("%B %d, %Y", "%Y-%m-%d", "%m/%d/%Y"):
            try:
                dt = datetime.strptime(quote_date.strip(), fmt)
                return f"ISSUED {dt.strftime('%B %d, %Y').upper()}"
            except ValueError:
                continue
    except Exception:
        pass
    return f"ISSUED {quote_date.upper()}"


def render_quote_html(data):
    """Return filled HTML string from conveyor quote data."""
    with open(TEMPLATE_PATH, encoding="utf-8") as f:
        template = f.read()

    quote_num = data.get("quote_num") or "GCS-00000000"
    quote_date = data.get("quote_date") or ""
    issued = _issued_date(quote_date)

    customer = data.get("customer") or {}
    rep = data.get("rep") or {}
    totals = data.get("totals") or {}
    line_items = data.get("line_items") or []

    equipment_pages = ""
    has_details = bool(data.get("equipment_details"))
    total_pages = 2 if has_details else 1
    if has_details:
        equipment_pages = _render_equipment_pages(data, quote_num, issued, total_pages)
    page_1_of = f"Page 1 of {total_pages}"

    replacements = {
        "{{QUOTE_NUM}}": _esc(quote_num),
        "{{ISSUED_DATE}}": _esc(issued),
        "{{QUOTE_DATE}}": _esc(quote_date),
        "{{CUST_COMPANY}}": _esc(customer.get("company") or "[Customer Company]"),
        "{{CUST_CONTACT}}": _esc(customer.get("contact") or "[Contact Name]"),
        "{{CUST_EMAIL}}": _esc(customer.get("email") or "[customer@email.com]"),
        "{{CUST_PHONE}}": _esc(customer.get("phone") or "[Phone Number]"),
        "{{CUST_ADDRESS}}": _esc(_format_customer_address(customer)),
        "{{REP_NAME}}": _esc(rep.get("name") or "[Sales Rep Name]"),
        "{{REP_EMAIL}}": _esc(rep.get("email") or "[rep@grindercrusherscreen.com]"),
        "{{REP_PHONE}}": _esc(rep.get("phone") or "[Direct Number]"),
        "{{SUBTOTAL}}": _esc(_format_money(totals.get("subtotal"))),
        "{{FREIGHT}}": _esc(_format_money(totals.get("freight"))),
        "{{TAX}}": _esc(_format_money(totals.get("tax"))),
        "{{GRAND_TOTAL}}": _esc(_format_total_money(totals.get("grand_total"))),
        "{{LINE_ITEMS}}": _render_line_items(
            line_items,
            bool(data.get("quote_mode") == "custom_build" or data.get("custom_addons_required")),
        ),
        "{{EQUIPMENT_DETAIL_PAGES}}": equipment_pages,
        "{{PAGE_1_OF}}": page_1_of,
    }

    out = template
    for token, val in replacements.items():
        out = out.replace(token, val)

    return out


def write_quote_html(data, output_path):
    html_out = render_quote_html(data)
    os.makedirs(os.path.dirname(output_path), exist_ok=True)
    with open(output_path, "w", encoding="utf-8") as f:
        f.write(html_out)
    return output_path
