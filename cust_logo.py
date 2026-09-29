"""BETA feature: fetch a buyer's company logo from their website.

Finds a logo candidate on the given site URL, downloads it, trims/resizes it
with PIL and saves it as cust_logo.png in the job dir. Pure beta-side module —
never imported by the main builder paths.
"""
import base64
import io
import os
import re
import urllib.request

from PIL import Image

UA = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36",
    "Accept": "image/avif,image/webp,image/apng,image/*,*/*;q=0.8",
}


def _fetch(url, timeout=20):
    req = urllib.request.Request(url, headers=UA)
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return r.read()


def _normalize_site(url):
    url = (url or "").strip()
    if not url:
        return ""
    if not re.match(r"^https?://", url, re.I):
        url = "https://" + url
    return url


def _candidate_urls(html, site):
    cands = []
    # bare <img> tags that look like logos (most explicit signal)
    for m in re.finditer(r"<img[^>]+>", html, re.I):
        tag = m.group(0)
        if re.search(r"logo", tag, re.I):
            src = re.search(r'src=["\']([^"\']+)["\']', tag, re.I)
            if src:
                cands.append(src.group(1))
    # link rel icons — prefer apple-touch-icon (larger)
    for m in re.finditer(
        r'<link[^>]+rel=["\'][^"\']*apple-touch-icon[^"\']*["\'][^>]*>', html, re.I
    ):
        h = re.search(r'href=["\']([^"\']+)["\']', m.group(0), re.I)
        if h:
            cands.append(h.group(1))
    for m in re.finditer(
        r'<link[^>]+rel=["\'][^"\']*(?:icon|shortcut)[^"\']*["\'][^>]*>', html, re.I
    ):
        h = re.search(r'href=["\']([^"\']+)["\']', m.group(0), re.I)
        if h:
            cands.append(h.group(1))
    # og:image / og:logo last — often a marketing photo rather than the logo
    for m in re.finditer(
        r'<meta[^>]+property=["\']og:(?:image|logo)[^>]+content=["\']([^"\']+)["\']', html, re.I
    ):
        cands.append(m.group(1))
    for m in re.finditer(
        r'<meta[^>]+content=["\']([^"\']+)["\'][^>]+property=["\']og:(?:image|logo)["\']', html, re.I
    ):
        cands.append(m.group(1))
    # favicon fallback
    root = re.match(r"(https?://[^/]+)", site, re.I)
    if root:
        cands.append(root.group(1) + "/favicon.ico")
    out = []
    for c in cands:
        c = c.strip()
        if c.startswith("//"):
            c = "https:" + c
        elif c.startswith("/"):
            c = site.rstrip("/") + c
        elif not re.match(r"^https?://", c, re.I):
            continue
        if c not in out:
            out.append(c)
    return out


def _process_image(img, job_dir):
    """Normalize + save a PIL image as the job's cust_logo.png."""
    img = img.convert("RGBA")
    px = img.load()
    visible = [
        px[x, y] for y in range(img.height) for x in range(img.width)
        if px[x, y][3] > 128
    ]
    if visible and sum(1 for r, g, b, a in visible if r > 200 and g > 200 and b > 200) / len(visible) > 0.9:
        for y in range(img.height):
            for x in range(img.width):
                r, g, b, a = px[x, y]
                if a > 0:
                    px[x, y] = (17, 17, 17, a)
    try:
        from PIL import ImageChops

        bg = Image.new("RGBA", img.size, (255, 255, 255, 0))
        diff = ImageChops.difference(img, bg)
        bbox = diff.getbbox()
        if bbox and (bbox[2] - bbox[0]) > 8 and (bbox[3] - bbox[1]) > 8:
            img = img.crop(bbox)
    except Exception:
        pass
    scale = 96.0 / max(img.height, 1)
    if scale < 1:
        img = img.resize((max(1, int(img.width * scale)), 96), getattr(Image, "Resampling", Image).LANCZOS)
    if img.width > 520:
        img = img.resize((520, max(1, int(img.height * 520.0 / img.width))), getattr(Image, "Resampling", Image).LANCZOS)
    path = os.path.join(job_dir, "cust_logo.png")
    img.save(path, "PNG")
    return path


def save_uploaded_image(data: bytes, job_dir):
    """Save a user-uploaded logo image through the same normalize pipeline."""
    from io import BytesIO

    img = Image.open(BytesIO(data))
    img.load()
    return _process_image(img, job_dir)


def save_from_url(url, job_dir):
    """Fetch a logo from a URL. If the URL points directly at an image,
    fetch it without scraping; otherwise fall back to site-logo search."""
    url = _normalize_site(url)
    if not url:
        return None
    path_ext = re.search(r"\.(png|jpe?g|gif|webp|bmp|svg)(\?|#|$)", url, re.I)
    if path_ext:
        try:
            data = _fetch(url)
            if url.lower().split("?")[0].endswith(".svg"):
                return None  # PIL can't rasterize SVG without extras
            img = Image.open(io.BytesIO(data))
            img.load()
            return _process_image(img, job_dir)
        except Exception:
            return None
    return find_and_save(url, job_dir)


def find_and_save(site_url, job_dir):
    """Returns the saved logo path, or None if no usable logo was found."""
    site = _normalize_site(site_url)
    if not site:
        return None
    try:
        html = _fetch(site).decode("utf-8", "ignore")
    except Exception:
        html = ""
    cands = _candidate_urls(html, site) if html else []
    if not site.lower().endswith("/favicon.ico"):
        root = re.match(r"(https?://[^/]+)", site, re.I)
        if root:
            cands.append(root.group(1) + "/favicon.ico")
    for cand in cands:
        try:
            data = _fetch(cand, timeout=15)
        except Exception:
            continue
        try:
            img = Image.open(io.BytesIO(data))
        except Exception:
            continue
        if (img.width or 0) < 16 or (img.height or 0) < 16:
            continue  # too tiny to be a logo
        try:
            img = img.convert("RGBA")
            # white wordmarks on transparent bg vanish on the white page —
            # if the visible pixels are nearly all near-white, darken them
            px = img.load()
            visible = [
                px[x, y] for y in range(img.height) for x in range(img.width)
                if px[x, y][3] > 128
            ]
            if visible and sum(1 for r, g, b, a in visible if r > 200 and g > 200 and b > 200) / len(visible) > 0.9:
                for y in range(img.height):
                    for x in range(img.width):
                        r, g, b, a = px[x, y]
                        if a > 0:
                            px[x, y] = (17, 17, 17, a)
            # trim uniform border so the mark doesn't carry big margins
            try:
                from PIL import ImageChops

                bg = Image.new("RGBA", img.size, (255, 255, 255, 0))
                diff = ImageChops.difference(img, bg)
                bbox = diff.getbbox()
                if bbox and (bbox[2] - bbox[0]) > 8 and (bbox[3] - bbox[1]) > 8:
                    img = img.crop(bbox)
            except Exception:
                pass
            # cap size: display ~28px tall; keep 2x for crisp PDF rendering
            scale = 64.0 / max(img.height, 1)
            if scale < 1:
                img = img.resize(
                    (max(1, int(img.width * scale)), 64), getattr(Image, 'Resampling', Image).LANCZOS
                )
            if img.width > 300:
                img = img.resize((300, max(1, int(img.height * 300.0 / img.width))), getattr(Image, 'Resampling', Image).LANCZOS)
            path = os.path.join(job_dir, 'cust_logo.png')
            img.save(path, "PNG")
            return path
        except Exception:
            continue
    return None


def logo_data_uri(job_dir):
    """Returns a data: URI for the saved logo, or None."""
    import os

    path = os.path.join(job_dir, 'cust_logo.png')
    if not os.path.isfile(path):
        return None
    with open(path, "rb") as f:
        b64 = base64.b64encode(f.read()).decode()
    return "data:image/png;base64," + b64
