"""
custom_build_parser.py — Case 2: merge GCS listing + request-quote pages for custom conveyors.
"""
import re
from urllib.parse import parse_qs, unquote_plus, urlparse

import listing_parser

# Options mapped to equipment detail sections (not repeated on page 1 add-ons).
SECTION_OPTION_KEYS = (
    "3-ply belt",
    "3 ply belt",
    "assembly less axel",
    "assembly-less axel",
)

POWER_LABELS = (
    (r"self\s+contained\s+electric\s+generator", "Self Contained Electric Generator"),
    (r"self\s+contained\s*\(\s*gas\s*/\s*hydraulic\s*\)", "Self Contained (Gas / Hydraulic)"),
    (r"self\s+contained\s*\(\s*diesel\s*/\s*hydraulic\s*\)", "Self Contained (Diesel / Hydraulic)"),
    (r"self\s+contained\s*\(\s*gas", "Self Contained (Gas / Hydraulic)"),
    (r"self\s+contained\s*\(\s*diesel", "Self Contained (Diesel / Hydraulic)"),
    (r"three\s+phase\s+electric", "Three Phase Electric"),
    (r"single[\s-]?phase\s+motor", "Single-Phase Motor"),
    (r"hydraulic\s+motor", "Hydraulic Motor"),
    (r"electric\s+motor", "Electric Motor"),
    (r"no\s+self\s+contained\s+power", "Electric (No Self Contained Power Unit)"),
)


def _norm(text):
    return re.sub(r"\s+", " ", str(text or "").strip())


def _listing_fact_lines(listing_md):
    """Description lines from listing, stopping before the Options list."""
    block = listing_parser._extract_description_region(listing_md)
    if not block:
        return []
    parts = re.split(r"(?im)^options\s*:?\s*$", block, maxsplit=1)
    pre = parts[0]
    intro_parts = []
    for line in pre.splitlines():
        s = line.strip()
        if not s or s.startswith("#"):
            continue
        if s.lower().startswith("share via"):
            break
        if s.startswith("*") and not s.startswith("\\*"):
            continue
        content = listing_parser._line_content(s)
        if content and not listing_parser._is_junk_line(content):
            intro_parts.append(content)
    return listing_parser._expand_flat_description_lines(intro_parts)


def _classify_fact(line):
    low = line.lower()
    if any(k in low for k in ("truss", "lagged head", "winged tail")):
        return "frame"
    if "cema" in low and "idler" in low:
        return "idlers"
    if "pipe axle" in low or "pipe axel" in low or ("wheel" in low and "tire" in low):
        return "undercarriage"
    if "discharge height" in low or "loading height" in low:
        return "other"
    return None


def _facts_to_sections(lines):
    sections = {k: [] for k in listing_parser.SECTION_KEYS}
    for line in lines:
        key = _classify_fact(line)
        if key:
            sections[key].append(line)
    return sections


def is_empty_quote_cart(quote_md):
    """True when the scraped quote page has no configured line item."""
    if not (quote_md or "").strip():
        return True
    low = quote_md.lower()
    if "your list is empty" in low:
        return True
    return not bool(_quote_item_block(quote_md, allow_empty_phrase=True))


def _quote_item_block(quote_md, allow_empty_phrase=False):
    if not quote_md:
        return ""
    if not allow_empty_phrase and "your list is empty" in quote_md.lower():
        return ""
    m = re.search(
        r"#\s*Request a Quote\s*(.*?)(?:Return to Shop|Browse the list|$)",
        quote_md,
        re.I | re.S,
    )
    if m:
        return m.group(1)
    return quote_md


def _quote_meta_lines(quote_md):
    meta = {}
    block = _quote_item_block(quote_md)
    for line in block.splitlines():
        m = re.match(r"^([^:|]+?):\s*(.+)$", line.strip())
        if not m:
            continue
        key = m.group(1).strip().lower().rstrip("*").strip()
        val = m.group(2).strip()
        if not key or not val or len(key) > 48:
            continue
        meta[key] = val
    return meta


def _normalize_width(raw):
    if not raw:
        return ""
    m = re.search(r"(\d+)\s*\"", str(raw))
    if m:
        return f'{m.group(1)}"'
    m = re.search(r"^(\d+)$", str(raw).strip())
    if m:
        return f'{m.group(1)}"'
    return str(raw).strip()


def _product_url_from_listing(listing_md):
    if not listing_md:
        return ""
    m = re.search(
        r"\]\((https://conveyors\.grindercrusherscreen\.com/product/[^)\s]+)\)",
        listing_md,
        re.I,
    )
    return m.group(1).strip() if m else ""


def _is_generic_quote_url(url):
    if not url:
        return False
    path = urlparse(url.strip()).path.rstrip("/").lower()
    return path.endswith("/request-quote")


def _config_from_url(url):
    """Read WooCommerce attribute query params from a product or quote URL."""
    if not url:
        return {"belt_width": "", "power": "", "options": []}
    qs = parse_qs(urlparse(url.strip()).query, keep_blank_values=False)
    belt_width = ""
    power = ""
    options = []
    for key, vals in qs.items():
        if not vals:
            continue
        val = unquote_plus(str(vals[0]).replace("+", " ")).strip()
        if not val:
            continue
        key_low = key.lower().replace("_", "-")
        if "width" in key_low:
            belt_width = belt_width or _normalize_width(val)
            continue
        if "power" in key_low and "supply" in key_low:
            power = power or val
            continue
        if key_low.startswith("attribute") or key_low.startswith("pa-"):
            if val not in options:
                options.append(val)
    return {"belt_width": belt_width, "power": power, "options": options}


def _extract_belt_width(quote_md, request_quote_url=""):
    url_cfg = _config_from_url(request_quote_url)
    if url_cfg["belt_width"]:
        return url_cfg["belt_width"]

    meta = _quote_meta_lines(quote_md)
    for key in ("conveyor width", "width"):
        if key in meta:
            return _normalize_width(meta[key])

    block = _quote_item_block(quote_md) or quote_md
    m = re.search(
        r"conveyor\s+width\*?\s*:?\s*\n?\s*(\d+)\s*\"",
        block,
        re.I | re.S,
    )
    if m:
        return f'{m.group(1)}"'
    for line in block.splitlines():
        s = line.strip()
        if re.match(r'^(\d+)\s*"\s*$', s):
            return _normalize_width(s)
    m = re.search(r"(\d+)\s*[x×]\s*(\d+)", block, re.I)
    if m:
        return f'{m.group(1)}"'
    return ""


def _meaningful_custom_price(val):
    """True when the user entered a real custom price (not empty/zero placeholders)."""
    text = str(val or "").strip()
    if not text or text.lower() == "enter custom price":
        return False
    cleaned = text.replace("$", "").replace(",", "").strip()
    if not cleaned:
        return False
    try:
        return float(cleaned) > 0
    except ValueError:
        return True


def _extract_price(quote_md, listing_md=""):
    for md in (quote_md, listing_md):
        if not md:
            continue
        m = re.search(
            r"order\s+total\s*:?\s*\|\s*\$?([\d,]+(?:\.\d{2})?)",
            md,
            re.I,
        )
        if m:
            return f"${m.group(1)}"
        m = re.search(r"####\s*\$([\d,]+(?:\.\d{2})?)", md)
        if m:
            return f"${m.group(1)}"
    parsed = listing_parser.parse_listing_markdown(listing_md or "")
    return parsed.get("price") or ""


def _option_lines(quote_md):
    """Pull selected add-on lines from the quote cart item block."""
    block = _quote_item_block(quote_md)
    if not block:
        return []
    found = []
    skip_heads = (
        "conveyor width",
        "travel",
        "road portable",
        "power supply",
        "drive motor",
        "backstop",
        "240v",
        "product price",
        "order total",
        "add to",
        "remove this item",
    )
    for line in block.splitlines():
        s = line.strip()
        if not s or s.startswith("#") or s.startswith("|") or s.startswith("!["):
            continue
        low = s.lower().lstrip("\\-").strip()
        if any(low.startswith(h) for h in skip_heads):
            continue
        if re.match(r"^\$[\d,]", s):
            continue
        cleaned = listing_parser._clean_bullet(s)
        if len(cleaned) >= 3 and cleaned not in found:
            found.append(cleaned)
    return found


def _selected_options(quote_md, request_quote_url=""):
    url_cfg = _config_from_url(request_quote_url)
    selected = list(url_cfg["options"])

    block = _quote_item_block(quote_md)
    if not block:
        return selected

    meta = _quote_meta_lines(quote_md)
    skip_meta = {"conveyor width", "width", "power supply", "travel", "quantity", "qty"}
    for key, val in meta.items():
        if key in skip_meta:
            continue
        if val and val not in selected:
            selected.append(val)

    for opt in _option_lines(quote_md):
        if opt not in selected:
            selected.append(opt)

    blob = block.lower()
    if re.search(r"assembly\s+less\s+axel", blob) and "Assembly less Axel" not in selected:
        selected.append("Assembly less Axel")
    if re.search(r"3[\s-]?ply\s+belt", blob) and "3-Ply Belt" not in selected:
        selected.append("3-Ply Belt")
    return selected


def _extract_power(quote_md, request_quote_url=""):
    url_cfg = _config_from_url(request_quote_url)
    if url_cfg["power"]:
        return url_cfg["power"]

    meta = _quote_meta_lines(quote_md)
    if meta.get("power supply"):
        return meta["power supply"]

    block = _quote_item_block(quote_md) or quote_md
    text = block.lower()
    for pattern, label in POWER_LABELS:
        if re.search(pattern, text):
            return label
    return ""


def _assembly_text(quote_md, listing_md):
    blob = f"{quote_md}\n{listing_md}".lower()
    if re.search(r"assembly\s+less\s+axel", blob):
        return "Assembly-Less Axel - Pre-Assembled"
    return "Assembly Required"


def _belt_from_options(selected_options):
    for opt in selected_options:
        if re.search(r"3[\s-]?ply\s+belt", opt, re.I):
            return ["3-Ply Belt"]
    return []


def _parse_labeled_sections(text):
    """Parse 'Label:\\nvalue' blocks from pasted quote-cart text."""
    sections = {}
    key = None
    vals = []
    for line in (text or "").splitlines():
        s = line.strip()
        if not s:
            continue
        if re.match(r"^.+:\s*$", s):
            if key:
                sections[key] = "\n".join(vals).strip()
            key = s[:-1].strip()
            vals = []
            continue
        m = re.match(r"^(.+?):\s*(.+)$", s)
        if m and key is None:
            sections[m.group(1).strip()] = m.group(2).strip()
            continue
        if key:
            vals.append(s)
    if key:
        sections[key] = "\n".join(vals).strip()
    return sections


def _section_lookup(sections, label_fragment, exact=False):
    frag = label_fragment.lower().strip()
    for key, val in sections.items():
        if key.lower().strip() == frag:
            return (val or "").strip()
    if exact:
        return ""
    for key, val in sections.items():
        if frag in key.lower():
            return (val or "").strip()
    return ""


def parse_pasted_config(pasted_addons):
    """Extract structured custom-build fields from pasted quote cart text."""
    sections = _parse_labeled_sections(pasted_addons)
    travel = _section_lookup(sections, "travel")
    road_portable = ""
    if "road portable" in travel.lower():
        for key, val in sections.items():
            if "road portable" in key.lower() and "option" in key.lower():
                road_portable = (val or "").strip()
                break

    belt_width = _normalize_width(_section_lookup(sections, "conveyor width"))
    power_supply = _section_lookup(sections, "power supply")
    drive_motor = ""
    for key, val in sections.items():
        if "drive motor" in key.lower():
            drive_motor = (val or "").strip()
            break

    power = power_supply
    if drive_motor:
        power = f"{power_supply}\n{drive_motor}".strip() if power_supply else drive_motor

    options_raw = _section_lookup(sections, "options", exact=True)
    options = [ln.strip() for ln in options_raw.splitlines() if ln.strip()]

    blob = (pasted_addons or "").lower()
    assembly = "Assembly-Less Axel - Pre-Assembled" if re.search(
        r"assembly\s+less\s+axel", blob
    ) else "Assembly Required"

    belt = []
    if re.search(r"3[\s-]?ply\s+belt", blob):
        belt = ["3-Ply Belt"]

    return {
        "belt_width": belt_width,
        "travel": travel,
        "road_portable_option": road_portable,
        "power": power,
        "assembly": assembly,
        "belt": belt,
        "options": options,
    }


def _merge_other_with_options(listing_other, option_lines):
    """Append pasted Options lines to listing Other facts."""
    other = list(listing_other or [])
    for opt in option_lines or []:
        if opt and opt not in other:
            other.append(opt)
    return other


def _is_road_portable(travel):
    return "road portable" in (travel or "").lower()


def _title_word(word):
    if not word:
        return word
    if word.upper() == "GCS":
        return "GCS"
    if word.upper() == "X":
        return "X"
    if re.match(r"^\d", word):
        return word
    if "-" in word:
        return "-".join(_title_word(part) for part in word.split("-"))
    if len(word) == 1:
        return word.upper()
    return word[0].upper() + word[1:].lower()


def _format_custom_title(text):
    """Title-case custom conveyor names: GCS stays caps, X stays caps, rest title case."""
    s = _norm(text)
    if not s:
        return ""
    return " ".join(_title_word(word) for word in s.split())


def _build_description_name(listing_name, belt_width):
    name = _norm(listing_name)
    width = _normalize_width(belt_width)
    if not name:
        return ""
    if not width:
        return name
    if re.search(r'\bX\s*\d+\s*"', name, re.I):
        return name
    m = re.match(r"^(GCS\s+\d+'\s+)(.+)$", name, re.I)
    if m:
        return f"{m.group(1)}X {width} {m.group(2)}"
    m = re.match(r"^(.+?\d+'\s+)(.+)$", name, re.I)
    if m:
        return f"{m.group(1)}X {width} {m.group(2)}"
    return f"{name} X {width}"


def _addons_for_line_item(selected_options, belt, power, assembly):
    used = set()
    for opt in selected_options:
        low = opt.lower()
        if re.search(r"3[\s-]?ply\s+belt", low):
            used.add(opt)
        if "assembly less axel" in low:
            used.add(opt)
    if power:
        pl = power.lower()
        for o in selected_options:
            if o.lower() == pl:
                used.add(o)
    remaining = [o for o in selected_options if o not in used]
    if not remaining:
        return ""
    return "\n".join(f"• {o}" for o in remaining)


def merge_custom_build(listing_md, quote_md, request_quote_url="", pasted_addons=""):
    """Return parsed dict for Case 2 custom conveyor quotes."""
    listing_parsed = listing_parser.parse_listing_markdown(listing_md or "")
    listing_name = _format_custom_title(listing_parsed.get("name") or "")
    fact_lines = _listing_fact_lines(listing_md or "")
    sections = _facts_to_sections(fact_lines)

    pasted = parse_pasted_config(pasted_addons)

    belt_width = pasted.get("belt_width") or _extract_belt_width(quote_md or "", request_quote_url)
    selected = _selected_options(quote_md or "", request_quote_url)
    power = pasted.get("power") or _extract_power(quote_md or "", request_quote_url)
    assembly = pasted.get("assembly") or _assembly_text(quote_md or "", listing_md or "")
    belt = pasted.get("belt") or _belt_from_options(selected)
    travel = pasted.get("travel") or ""
    road_portable = pasted.get("road_portable_option") or ""
    if travel and not _is_road_portable(travel):
        road_portable = ""
    other = _merge_other_with_options(sections["other"], pasted.get("options"))
    price = _extract_price(quote_md or "", listing_md or "")

    description = _build_description_name(listing_name, belt_width)
    if not description and listing_parsed.get("description"):
        description = listing_parsed.get("description").split("\n")[0]
    description = _format_custom_title(description)

    return {
        "name": listing_name,
        "description": description,
        "frame": sections["frame"],
        "idlers": sections["idlers"],
        "undercarriage": sections["undercarriage"],
        "belt": belt,
        "other": other,
        "travel": travel,
        "road_portable_option": road_portable,
        "power": power,
        "assembly": assembly,
        "price": price,
        "selected_options": selected,
        "belt_width": belt_width,
        "specifications": [],
        "image_url": listing_parsed.get("image_url") or "",
        "fact_lines": fact_lines,
        "quote_cart_empty": is_empty_quote_cart(quote_md or ""),
        "product_url": _product_url_from_listing(listing_md or ""),
    }


def to_quote_fields(parsed):
    """Map Case 2 parse result to conveyor.json shape."""
    parsed = parsed or {}
    name = parsed.get("name") or "Conveyor"
    price = parsed.get("price") or ""
    if price and not str(price).startswith("$"):
        price = f"${price}"

    description = parsed.get("description") or ""
    selected = parsed.get("selected_options") or []
    power = parsed.get("power") or ""
    assembly = parsed.get("assembly") or "Assembly Required"

    equipment_detail = {
        "name": name,
        "description": description,
        "frame": list(parsed.get("frame") or []),
        "idlers": list(parsed.get("idlers") or []),
        "undercarriage": list(parsed.get("undercarriage") or []),
        "belt": list(parsed.get("belt") or []),
        "other": list(parsed.get("other") or []),
        "travel": parsed.get("travel") or "",
        "road_portable_option": parsed.get("road_portable_option") or "",
        "power": power,
        "assembly": assembly,
        "specifications": [],
        "image_url": parsed.get("image_url") or "",
    }

    line_item = {
        "model": name,
        "addons": "",
        "description": description.split("\n")[0] if description else "",
        "amount": "",
        "lead_time": "—",
    }

    return {
        "line_items": [line_item],
        "equipment_details": [equipment_detail],
        "totals": {
            "subtotal": "",
            "freight": "",
            "tax": "",
            "grand_total": "",
        },
    }


def field_status(parsed):
    def st_str(val):
        return "ok" if str(val or "").strip() else "missing"

    def st_list(val):
        return "ok" if val else "missing"

    parsed = parsed or {}
    return {
        "model": st_str(parsed.get("name")),
        "price": "missing",
        "description": st_str(parsed.get("description"))
        if parsed.get("belt_width")
        else "missing",
        "frame": st_list(parsed.get("frame")),
        "idlers": st_list(parsed.get("idlers")),
        "undercarriage": st_list(parsed.get("undercarriage")),
        "belt": st_list(parsed.get("belt")),
        "other": st_list(parsed.get("other")),
        "travel": st_str(parsed.get("travel")),
        "road_portable_option": (
            st_str(parsed.get("road_portable_option"))
            if _is_road_portable(parsed.get("travel"))
            else "ok"
        ),
        "power": st_str(parsed.get("power")),
        "assembly": st_str(parsed.get("assembly")),
        "custom_addons": st_list(parsed.get("selected_options")),
        "specifications": "ok",
        "images": st_str(parsed.get("image_url")),
    }


def refresh_quote_from_scrape(jdir, data):
    """Re-merge listing + quote scrapes for custom build jobs."""
    import os

    data = data or {}
    listing_path = os.path.join(jdir, "scrape_listing.md")
    quote_path = os.path.join(jdir, "scrape_quote.md")
    listing_md = ""
    quote_md = ""
    if os.path.isfile(listing_path):
        with open(listing_path, encoding="utf-8") as f:
            listing_md = f.read()
    if os.path.isfile(quote_path):
        with open(quote_path, encoding="utf-8") as f:
            quote_md = f.read()
    if not listing_md.strip():
        return data
    request_quote_url = (data.get("urls") or {}).get("request_quote") or ""
    items = list(data.get("line_items") or [])
    saved_addons = (items[0].get("addons") or "") if items else ""
    parsed = merge_custom_build(listing_md, quote_md, request_quote_url, saved_addons)
    mapped = to_quote_fields(parsed)

    if items:
        keep = {}
        if str(items[0].get("lead_time") or "").strip():
            keep["lead_time"] = items[0]["lead_time"]
        if _meaningful_custom_price(items[0].get("amount")):
            keep["amount"] = items[0]["amount"]
        items[0] = {**items[0], **mapped["line_items"][0], **keep}
        items[0]["addons"] = saved_addons
        items[0]["addons_display"] = ""
    else:
        items = mapped["line_items"]
        if saved_addons and items:
            items[0]["addons"] = saved_addons
            items[0]["addons_display"] = ""
    data["line_items"] = items

    details = list(data.get("equipment_details") or [])
    saved_travel = details[0].get("travel") if details else ""
    saved_road = details[0].get("road_portable_option") if details else ""
    if details:
        details[0] = {**details[0], **mapped["equipment_details"][0]}
        if saved_travel and not parsed.get("travel"):
            details[0]["travel"] = saved_travel
        if saved_road and not parsed.get("road_portable_option"):
            details[0]["road_portable_option"] = saved_road
    else:
        details = mapped["equipment_details"]
    data["equipment_details"] = details

    items = data.get("line_items") or []
    if items and not _meaningful_custom_price(items[0].get("amount")):
        items[0]["amount"] = ""
    totals = dict(data.get("totals") or {})
    if not _meaningful_custom_price(totals.get("subtotal")):
        totals["subtotal"] = ""
    data["totals"] = totals

    fs = field_status(parsed)
    saved_amount = (data.get("line_items") or [{}])[0].get("amount") or ""
    saved_subtotal = (data.get("totals") or {}).get("subtotal") or ""
    if _meaningful_custom_price(saved_amount) or _meaningful_custom_price(saved_subtotal):
        fs["price"] = "ok"
    data["field_status"] = fs
    if saved_addons.strip():
        data["field_status"]["custom_addons"] = "ok"
    elif data.get("custom_addons_required"):
        data["field_status"]["custom_addons"] = "missing"
    meta = dict(data.get("scrape_meta") or {})
    meta["parsed_raw"] = parsed
    meta["parser"] = "custom_build_parser"
    data["scrape_meta"] = meta
    return data
