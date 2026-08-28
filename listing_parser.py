"""
listing_parser.py — Parse GCS conveyor listing markdown into structured equipment sections.
"""
import os
import re

SECTION_KEYS = ("frame", "idlers", "undercarriage", "belt", "other")
SECTION_ALIASES = {
    "frame": ("frame",),
    "idlers": ("idlers", "idler"),
    "undercarriage": ("undercarriage", "under carrage", "undercarrage", "under carriage", "undercariage"),
    "belt": ("belt", "conveyor"),
    "other": ("other", "engine", "hopper", "dimensions", "capacity", "options"),
}

STOP_HEADINGS = (
    "### documents",
    "[grindercrusherscreen",
    "##### equipment",
    "© copyright",
)


def _clean_bullet(line):
    line = line.strip()
    line = re.sub(r"^\\?-\s*", "", line)
    line = re.sub(r"^-\s*", "", line)
    return line.strip()


def _is_bullet(line):
    s = line.strip()
    return bool(re.match(r"^\\?-\s+", s) or re.match(r"^-\s+", s))


def _map_subsection_header(header):
    key = header.strip().lower().rstrip(":").strip()
    key_compact = key.replace(" ", "")
    for section, aliases in SECTION_ALIASES.items():
        for alias in aliases:
            alias_compact = alias.replace(" ", "")
            if key == alias or key_compact == alias_compact:
                return section
    return None


def _is_junk_line(text):
    if re.match(r"^[A-Z]{2,}\s+[A-Z0-9]+$", text or ""):
        return True
    if re.match(r"^[A-Z]{2,6}$", text or ""):
        return True
    return False


def _line_content(line):
    s = line.strip()
    if _is_bullet(s):
        return _clean_bullet(s)
    return s


def _extract_description_region(md):
    m = re.search(r"###\s*Description\s*\n(.*?)(?=\n###\s|\Z)", md, re.I | re.S)
    return m.group(1) if m else ""


def _should_split_comma_facts(text):
    """True when a sentence looks like comma-separated dimension/fact clauses."""
    if text.count(",") < 2:
        return False
    parts = [p.strip() for p in text.split(",")]
    measure = sum(
        1
        for p in parts
        if re.search(r"\d['\"]", p)
        or re.search(
            r"\b(tall|wide|long|high|height|width|length|diameter|transport|assembled)\b",
            p,
            re.I,
        )
    )
    return measure >= 2


def _expand_flat_description_lines(intro_parts):
    """Split flat description content into one display fact per line."""
    facts = []
    for part in intro_parts:
        part = part.strip()
        if not part:
            continue
        for sentence in re.split(r"(?<=[.!?])\s+", part):
            sentence = sentence.strip()
            if not sentence:
                continue
            if _should_split_comma_facts(sentence):
                for chunk in sentence.split(","):
                    chunk = chunk.strip().rstrip(".")
                    if chunk:
                        facts.append(chunk)
            else:
                facts.append(sentence)
    return facts


def _parse_description_region(block):
    """Parse intro text and category bullets from the Description section."""
    intro_parts = []
    sections = {key: [] for key in SECTION_KEYS}
    current_section = None
    headers_seen = False

    for line in block.splitlines():
        s = line.strip()
        if not s or s.startswith("#"):
            continue
        if s.lower().startswith("share via"):
            break

        header_match = re.match(r"^\*\*(.+?)\*\*\s*$", s, re.I)
        if header_match:
            headers_seen = True
            current_section = _map_subsection_header(header_match.group(1))
            if current_section is None:
                current_section = "other"
            continue

        content = _line_content(s)
        if not content or _is_junk_line(content):
            continue

        if current_section is None:
            intro_parts.append(content)
        else:
            sections[current_section].append(content)

    if headers_seen:
        description = " ".join(intro_parts).strip()
    elif intro_parts:
        # Flat listings (feeder/hopper, etc.): preserve line breaks from the page,
        # and split single-paragraph dimension lists into separate facts.
        description = "\n".join(_expand_flat_description_lines(intro_parts))
    else:
        description = ""

    return description, sections


def _truncate_at_footer(text):
    low = text.lower()
    for stop in STOP_HEADINGS:
        idx = low.find(stop)
        if idx != -1:
            text = text[:idx]
            break
    return text


def _extract_title(md):
    for line in md.splitlines():
        m = re.match(r"^#\s+(.+)$", line.strip())
        if m:
            title = m.group(1).strip()
            if title and "grindercrusherscreen" not in title.lower():
                return title
    return ""


def _extract_price(md):
    m = re.search(r"####\s*(\$[\d,]+(?:\.\d{2})?)\s*(?:\(USD\))?", md, re.I)
    if m:
        return m.group(1)
    m = re.search(r"\$[\d,]+(?:\.\d{2})?", md)
    return m.group(0) if m else ""


def _extract_image(md, title_hint=""):
    title_low = (title_hint or "").lower()
    for m in re.finditer(r"!\[[^\]]*\]\((https?://[^)]+)\)", md):
        url = m.group(1)
        if url.endswith(".gif") or "loader" in url.lower():
            continue
        if "machineryhost.com" in url or "large-watermarked" in url:
            return url
    return ""


def _extract_specifications(md):
    m = re.search(r"###\s*Specifications\s*\n(.*?)(?=\n###\s|\Z)", md, re.I | re.S)
    if not m:
        return []
    block = m.group(1)
    specs = []
    for line in block.splitlines():
        line = line.strip()
        if not line.startswith("|"):
            continue
        if re.match(r"^\|\s*-+\s*\|", line):
            continue
        cells = [c.strip() for c in line.strip("|").split("|")]
        if len(cells) >= 2 and cells[0] and cells[1]:
            if cells[0].lower() in ("", "specification", "feature"):
                continue
            specs.append({"label": cells[0], "value": cells[1]})
    return specs


def parse_listing_markdown(md):
    """Parse GCS listing markdown into structured equipment data."""
    if not md:
        return _empty_parsed()

    # Specs live above the site footer — extract before truncation can clip them.
    specifications = _extract_specifications(md)
    md = _truncate_at_footer(md)
    name = _extract_title(md)
    price = _extract_price(md)
    description, sections = _parse_description_region(_extract_description_region(md))
    image_url = _extract_image(md, name)

    return {
        "name": name,
        "price": price,
        "description": description,
        "frame": sections["frame"],
        "idlers": sections["idlers"],
        "undercarriage": sections["undercarriage"],
        "belt": sections["belt"],
        "other": sections["other"],
        "specifications": specifications,
        "image_url": image_url,
    }


def _empty_parsed():
    return {
        "name": "",
        "price": "",
        "description": "",
        "frame": [],
        "idlers": [],
        "undercarriage": [],
        "belt": [],
        "other": [],
        "specifications": [],
        "image_url": "",
    }


def _first_sentence(text):
    if not text:
        return ""
    first_line = text.split("\n")[0].strip()
    m = re.match(r"^(.+?[.!?])(?:\s|$)", first_line)
    return m.group(1) if m else first_line[:200]


def to_quote_fields(parsed):
    """Map parsed listing data to conveyor quote JSON fields."""
    parsed = parsed or _empty_parsed()
    name = parsed.get("name") or "Conveyor"
    price = parsed.get("price") or ""
    if price and not price.startswith("$"):
        price = f"${price}"

    equipment_detail = {
        "name": name,
        "description": parsed.get("description") or "",
        "frame": list(parsed.get("frame") or []),
        "idlers": list(parsed.get("idlers") or []),
        "undercarriage": list(parsed.get("undercarriage") or []),
        "belt": list(parsed.get("belt") or []),
        "other": list(parsed.get("other") or []),
        "specifications": list(parsed.get("specifications") or []),
        "image_url": parsed.get("image_url") or "",
    }

    line_item = {
        "model": name,
        "addons": "",
        "description": _first_sentence(parsed.get("description") or ""),
        "amount": price or "$0.00",
        "lead_time": "—",
    }

    return {
        "line_items": [line_item],
        "equipment_details": [equipment_detail],
        "totals": {
            "subtotal": price or "",
            "freight": "",
            "tax": "",
            "grand_total": "",
        },
    }


def field_status(parsed):
    """Return per-category scrape status for review UI."""
    def st_str(val):
        return "ok" if str(val or "").strip() else "missing"

    def st_list(val):
        return "ok" if val else "missing"

    parsed = parsed or _empty_parsed()
    return {
        "model": st_str(parsed.get("name")),
        "price": st_str(parsed.get("price")),
        "description": st_str(parsed.get("description")),
        "frame": st_list(parsed.get("frame")),
        "idlers": st_list(parsed.get("idlers")),
        "undercarriage": st_list(parsed.get("undercarriage")),
        "belt": st_list(parsed.get("belt")),
        "other": st_list(parsed.get("other")),
        "specifications": st_list(parsed.get("specifications")),
        "images": st_str(parsed.get("image_url")),
    }


def is_sparse(parsed):
    """True if parser failed to get meaningful content."""
    parsed = parsed or _empty_parsed()
    if parsed.get("name") and parsed.get("description"):
        return False
    if parsed.get("specifications"):
        return False
    for key in SECTION_KEYS:
        if parsed.get(key):
            return False
    return True


def apply_parsed_to_quote(data, parsed):
    """Merge freshly parsed listing data into a conveyor quote dict."""
    mapped = to_quote_fields(parsed)
    data = data or {}

    items = list(data.get("line_items") or [])
    new_li = mapped["line_items"][0]
    if items:
        items[0] = {
            **items[0],
            "model": new_li["model"],
            "description": new_li["description"],
        }
        if new_li.get("amount") and new_li["amount"] not in ("", "$0.00"):
            items[0]["amount"] = new_li["amount"]
    else:
        items = mapped["line_items"]
    data["line_items"] = items

    details = list(data.get("equipment_details") or [])
    new_eq = mapped["equipment_details"][0]
    if details:
        details[0] = {**details[0], **new_eq}
    else:
        details = mapped["equipment_details"]
    data["equipment_details"] = details

    price = (parsed.get("price") or "").strip()
    if price:
        if not price.startswith("$"):
            price = f"${price}"
        totals = dict(data.get("totals") or {})
        if not str(totals.get("subtotal") or "").strip():
            totals["subtotal"] = price
        data["totals"] = totals

    data["field_status"] = field_status(parsed)
    meta = dict(data.get("scrape_meta") or {})
    meta["parsed_raw"] = parsed
    meta["parser"] = "listing_parser"
    data["scrape_meta"] = meta
    return data


def refresh_quote_from_scrape(jdir, data):
    """Re-parse jobs/<id>/scrape_listing.md with the latest parser rules."""
    data = data or {}
    if data.get("quote_mode") == "custom_build" or data.get("custom_addons_required"):
        return data
    scrape_path = os.path.join(jdir, "scrape_listing.md")
    if not os.path.isfile(scrape_path):
        return data
    with open(scrape_path, encoding="utf-8") as f:
        md = f.read()
    if not md.strip():
        return data
    parsed = parse_listing_markdown(md)
    if is_sparse(parsed):
        return data
    return apply_parsed_to_quote(data, parsed)
