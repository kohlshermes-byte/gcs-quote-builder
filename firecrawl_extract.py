"""
firecrawl_extract.py — Scrape conveyor listing / request-quote pages via Firecrawl API.
"""
import json
import os
import re
from datetime import datetime

try:
    import requests
except ImportError:
    requests = None

FIRECRAWL_BASE = "https://api.firecrawl.dev/v1"

CONVEYOR_SCHEMA = {
    "type": "object",
    "properties": {
        "model": {"type": "string", "description": "Conveyor model name or SKU"},
        "sku": {"type": "string", "description": "Product SKU or part number"},
        "description": {"type": "string", "description": "Product summary description"},
        "price": {"type": "string", "description": "Quoted or listed price with currency symbol if shown"},
        "lead_time": {"type": "string", "description": "Lead time or availability"},
        "custom_addons": {
            "type": "array",
            "items": {"type": "string"},
            "description": "Selected options, add-ons, or custom build features",
        },
        "specifications": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "label": {"type": "string"},
                    "value": {"type": "string"},
                },
            },
            "description": "Technical specs: belt width, length, HP, discharge height, mobility, etc.",
        },
        "features": {
            "type": "array",
            "items": {"type": "string"},
            "description": "Key product features or bullet points",
        },
        "images": {
            "type": "array",
            "items": {"type": "string"},
            "description": "Image URLs for the product",
        },
    },
}

EXTRACT_PROMPT = (
    "Extract conveyor equipment quote data from this page. "
    "Include model/SKU, description, price if shown, lead time, custom options, "
    "technical specifications (belt width, length, horsepower, discharge height, "
    "frame type, mobility), features, and product image URLs."
)


def get_api_key():
    key = os.environ.get("FIRECRAWL_API_KEY", "").strip()
    if key:
        return key
    env_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), ".env")
    if os.path.isfile(env_path):
        with open(env_path, encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if line.startswith("FIRECRAWL_API_KEY="):
                    return line.split("=", 1)[1].strip().strip('"').strip("'")
    return ""


def _headers():
    key = get_api_key()
    if not key:
        raise RuntimeError(
            "FIRECRAWL_API_KEY is not set. Add it to .env or your environment."
        )
    return {"Authorization": f"Bearer {key}", "Content-Type": "application/json"}


def scrape_url(url):
    """Return markdown content for a single URL."""
    if not requests:
        raise RuntimeError("The 'requests' package is required. Run: pip install requests")
    resp = requests.post(
        f"{FIRECRAWL_BASE}/scrape",
        headers=_headers(),
        json={"url": url, "formats": ["markdown"]},
        timeout=120,
    )
    resp.raise_for_status()
    data = resp.json()
    if not data.get("success"):
        raise RuntimeError(data.get("error") or "Firecrawl scrape failed")
    md = (data.get("data") or {}).get("markdown") or ""
    return md


def extract_from_url(url):
    """Extract structured conveyor data from a URL using Firecrawl extract."""
    if not requests:
        raise RuntimeError("The 'requests' package is required. Run: pip install requests")
    resp = requests.post(
        f"{FIRECRAWL_BASE}/extract",
        headers=_headers(),
        json={
            "urls": [url],
            "prompt": EXTRACT_PROMPT,
            "schema": CONVEYOR_SCHEMA,
        },
        timeout=180,
    )
    resp.raise_for_status()
    data = resp.json()
    if not data.get("success"):
        raise RuntimeError(data.get("error") or "Firecrawl extract failed")
    result = data.get("data") or {}
    if isinstance(result, list) and result:
        result = result[0]
    return _normalize_extract(result if isinstance(result, dict) else {})


def _normalize_extract(raw):
    """Ensure consistent shape from extract response."""
    out = {
        "model": str(raw.get("model") or "").strip(),
        "sku": str(raw.get("sku") or "").strip(),
        "description": str(raw.get("description") or "").strip(),
        "price": str(raw.get("price") or "").strip(),
        "lead_time": str(raw.get("lead_time") or "").strip(),
        "custom_addons": [str(x).strip() for x in (raw.get("custom_addons") or []) if str(x).strip()],
        "specifications": [],
        "features": [str(x).strip() for x in (raw.get("features") or []) if str(x).strip()],
        "images": [str(x).strip() for x in (raw.get("images") or []) if str(x).strip()],
    }
    for spec in raw.get("specifications") or []:
        if not isinstance(spec, dict):
            continue
        label = str(spec.get("label") or "").strip()
        value = str(spec.get("value") or "").strip()
        if label and value:
            out["specifications"].append({"label": label, "value": value})
    return out


def _parse_markdown_fallback(md):
    """Lightweight fallback when extract returns sparse data."""
    out = _normalize_extract({})
    if not md:
        return out
    lines = [ln.strip() for ln in md.splitlines() if ln.strip()]
    for ln in lines[:30]:
        low = ln.lower()
        if not out["model"] and any(k in low for k in ("conveyor", "model", "series")):
            out["model"] = re.sub(r"^#+\s*", "", ln)[:120]
        m = re.search(r"\$[\d,]+(?:\.\d{2})?", ln)
        if m and not out["price"]:
            out["price"] = m.group(0)
    if not out["description"] and lines:
        out["description"] = " ".join(lines[1:4])[:500]
    return out


def merge_extractions(listing, quote_page):
    """Merge listing + request-quote extractions with explicit precedence."""
    listing = listing or _normalize_extract({})
    quote_page = quote_page or _normalize_extract({})
    merged = _normalize_extract({})

    merged["model"] = listing.get("model") or quote_page.get("model")
    merged["sku"] = listing.get("sku") or quote_page.get("sku")
    merged["description"] = listing.get("description") or quote_page.get("description")
    merged["price"] = quote_page.get("price") or listing.get("price")
    merged["lead_time"] = quote_page.get("lead_time") or listing.get("lead_time")

    addons = list(listing.get("custom_addons") or [])
    for a in quote_page.get("custom_addons") or []:
        if a not in addons:
            addons.append(a)
    merged["custom_addons"] = addons

    spec_map = {}
    for spec in listing.get("specifications") or []:
        spec_map[spec["label"].lower()] = spec
    for spec in quote_page.get("specifications") or []:
        spec_map[spec["label"].lower()] = spec
    merged["specifications"] = list(spec_map.values())

    features = list(listing.get("features") or [])
    for f in quote_page.get("features") or []:
        if f not in features:
            features.append(f)
    merged["features"] = features

    images = list(listing.get("images") or [])
    for img in quote_page.get("images") or []:
        if img not in images:
            images.append(img)
    merged["images"] = images

    return merged


def extraction_to_quote_fields(merged):
    """Map merged extraction to conveyor quote JSON fields."""
    model = merged.get("model") or merged.get("sku") or "Conveyor"
    if merged.get("sku") and merged.get("model") and merged["sku"] not in merged["model"]:
        model = f"{merged['model']} ({merged['sku']})"
    addons = "\n".join(f"• {a}" for a in merged.get("custom_addons") or [])
    price = merged.get("price") or ""
    if price and not price.startswith("$"):
        price = f"${price}" if re.match(r"^[\d,]", price) else price

    equipment_detail = {
        "name": merged.get("model") or model,
        "specifications": merged.get("specifications") or [],
        "features": merged.get("features") or [],
        "description": merged.get("description") or "",
        "image_url": (merged.get("images") or [""])[0],
    }

    line_item = {
        "model": model,
        "addons": addons,
        "description": merged.get("description") or "",
        "amount": price or "$0.00",
        "lead_time": merged.get("lead_time") or "—",
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


def _field_status(merged):
    """Return per-field scrape status for review UI."""
    def st(val):
        if val is None:
            return "missing"
        if isinstance(val, list):
            return "ok" if val else "missing"
        return "ok" if str(val).strip() else "missing"

    return {
        "model": st(merged.get("model")),
        "sku": st(merged.get("sku")),
        "description": st(merged.get("description")),
        "price": st(merged.get("price")),
        "lead_time": st(merged.get("lead_time")),
        "custom_addons": st(merged.get("custom_addons")),
        "specifications": st(merged.get("specifications")),
        "features": st(merged.get("features")),
        "images": st(merged.get("images")),
    }


def run_extraction(
    listing_url,
    request_quote_url=None,
    job_dir=None,
    force=False,
    custom_addons_required=False,
    quote_mode=None,
):
    """
    Scrape and extract from listing (+ optional request-quote URL for Case 2).
    Case 1 (listing only): parse GCS markdown sections via listing_parser.
    """
    import importlib
    import listing_parser
    importlib.reload(listing_parser)

    errors = []
    listing_md = ""
    quote_md = ""
    listing_only = quote_mode == "listing_only" or not custom_addons_required

    cache_listing = os.path.join(job_dir, "scrape_listing.md") if job_dir else None
    cache_quote = os.path.join(job_dir, "scrape_quote.md") if job_dir else None

    if listing_url:
        try:
            if not force and cache_listing and os.path.isfile(cache_listing):
                with open(cache_listing, encoding="utf-8") as f:
                    listing_md = f.read()
            else:
                listing_md = scrape_url(listing_url)
                if cache_listing:
                    os.makedirs(job_dir, exist_ok=True)
                    with open(cache_listing, "w", encoding="utf-8") as f:
                        f.write(listing_md)
        except Exception as e:
            errors.append(f"Listing scrape: {e}")

    if listing_only:
        parsed = listing_parser.parse_listing_markdown(listing_md)
        if listing_parser.is_sparse(parsed):
            try:
                listing_data = extract_from_url(listing_url)
                merged = merge_extractions(listing_data, _normalize_extract({}))
                mapped = extraction_to_quote_fields(merged)
                status = _field_status(merged)
            except Exception as e:
                errors.append(f"Listing extract fallback: {e}")
                mapped = listing_parser.to_quote_fields(parsed)
                status = listing_parser.field_status(parsed)
        else:
            mapped = listing_parser.to_quote_fields(parsed)
            status = listing_parser.field_status(parsed)

        now = datetime.now().isoformat(timespec="seconds")
        return {
            **mapped,
            "quote_mode": "listing_only",
            "custom_addons_required": False,
            "field_status": status,
            "scrape_meta": {
                "listing_scraped_at": now if listing_url and listing_md else "",
                "quote_scraped_at": "",
                "errors": errors,
                "parser": "listing_parser",
                "parsed_raw": parsed,
            },
        }

    # Case 2: dual URL (custom build)
    import custom_build_parser
    importlib.reload(custom_build_parser)

    if request_quote_url:
        try:
            if not force and cache_quote and os.path.isfile(cache_quote):
                with open(cache_quote, encoding="utf-8") as f:
                    quote_md = f.read()
            else:
                quote_md = scrape_url(request_quote_url)
                if cache_quote:
                    os.makedirs(job_dir, exist_ok=True)
                    with open(cache_quote, "w", encoding="utf-8") as f:
                        f.write(quote_md)
        except Exception as e:
            errors.append(f"Request-quote scrape: {e}")

    quote_url_used = (request_quote_url or "").strip()
    if quote_url_used and quote_md and custom_build_parser.is_empty_quote_cart(quote_md):
        product_url = ""
        if "/product/" in quote_url_used.lower():
            product_url = quote_url_used
        else:
            product_url = custom_build_parser._product_url_from_listing(listing_md)
        if product_url and product_url.rstrip("/") != quote_url_used.rstrip("/"):
            try:
                product_md = scrape_url(product_url)
                if product_md and not custom_build_parser.is_empty_quote_cart(product_md):
                    quote_md = product_md
                    quote_url_used = product_url
                elif product_md and custom_build_parser._config_from_url(quote_url_used).get("belt_width"):
                    quote_md = product_md
                    quote_url_used = product_url
            except Exception as e:
                errors.append(f"Product configurator scrape: {e}")

        if custom_build_parser.is_empty_quote_cart(quote_md):
            errors.append(
                "Quote cart URL scraped empty — paste configured options into Paste Custom Add-Ons instead."
            )

    parsed = custom_build_parser.merge_custom_build(
        listing_md, quote_md, quote_url_used
    )
    mapped = custom_build_parser.to_quote_fields(parsed)
    status = custom_build_parser.field_status(parsed)

    now = datetime.now().isoformat(timespec="seconds")
    return {
        **mapped,
        "quote_mode": "custom_build",
        "custom_addons_required": True,
        "field_status": status,
        "scrape_meta": {
            "listing_scraped_at": now if listing_url and listing_md else "",
            "quote_scraped_at": now if request_quote_url and quote_md else "",
            "errors": errors,
            "parser": "custom_build_parser",
            "parsed_raw": parsed,
        },
    }
