"""Screenshot conveyor quote pages with Playwright and assemble a letter-size PDF."""
import os
import re
import tempfile

from reportlab.lib.pagesizes import letter
from reportlab.pdfgen import canvas

BASE = os.path.dirname(os.path.abspath(__file__))


def _inject_base_href(html, base_url):
    """Ensure relative assets (/logo, etc.) resolve against the local server."""
    base_url = (base_url or "").rstrip("/") + "/"
    base_tag = f'<base href="{base_url}">'
    if re.search(r"<base\s", html, flags=re.I):
        return html
    if re.search(r"<head[^>]*>", html, flags=re.I):
        return re.sub(r"(<head[^>]*>)", r"\1" + base_tag, html, count=1, flags=re.I)
    return f"<!DOCTYPE html><html><head>{base_tag}</head><body>{html}</body></html>"


def _prepare_html(html, base_url):
    html = html or ""
    if "<html" not in html.lower():
        html = f"<!DOCTYPE html><html><head></head><body>{html}</body></html>"
    return _inject_base_href(html, base_url)


def build_screenshot_pdf(pdf_path, *, html, base_url):
    """Load quote HTML in Playwright, screenshot each .page, write letter PDF.

    Each screenshot is placed at exactly 8.5 × 11 inches (US Letter).
    """
    try:
        from playwright.sync_api import sync_playwright
    except ImportError as exc:
        raise RuntimeError(
            "Playwright is not installed. Restart the app once so it can finish setup, "
            "or run: python3 -m pip install playwright && python3 -m playwright install chromium"
        ) from exc

    html = _prepare_html(html, base_url)
    pdf_path = os.path.abspath(pdf_path)
    os.makedirs(os.path.dirname(pdf_path) or ".", exist_ok=True)
    if os.path.isfile(pdf_path):
        os.remove(pdf_path)

    with tempfile.TemporaryDirectory(prefix="gcs_shot_") as tmp:
        png_paths = []
        with sync_playwright() as p:
            try:
                browser = p.chromium.launch(headless=True)
            except Exception as exc:
                raise RuntimeError(
                    "Playwright Chromium is not installed. Run: "
                    "python3 -m playwright install chromium"
                ) from exc

            try:
                context = browser.new_context(
                    device_scale_factor=3,
                    viewport={"width": 1100, "height": 1400},
                )
                page = context.new_page()
                page.set_content(html, wait_until="networkidle", timeout=60000)
                page.add_style_tag(
                    content="""
                    #toolbar { display: none !important; }
                    body { background: #ffffff !important; }
                    #pages { padding: 0 !important; gap: 0 !important; }
                    .page {
                      box-shadow: none !important;
                      margin: 0 auto !important;
                    }
                    """
                )
                # Wait for logo / remote images
                page.wait_for_timeout(500)
                locators = page.locator(".page")
                count = locators.count()
                if count < 1:
                    raise RuntimeError("No quote pages found in the HTML (.page elements).")

                for i in range(count):
                    out = os.path.join(tmp, f"page_{i + 1}.png")
                    locators.nth(i).screenshot(path=out, type="png")
                    png_paths.append(out)
            finally:
                browser.close()

        _images_to_letter_pdf(png_paths, pdf_path)

    if not os.path.isfile(pdf_path) or os.path.getsize(pdf_path) < 1:
        raise RuntimeError("Screenshot PDF was not created.")
    return pdf_path


def _images_to_letter_pdf(png_paths, pdf_path):
    """Place each PNG on its own US Letter page at exactly 8.5 × 11 inches."""
    page_w, page_h = letter  # 612 × 792 pt
    c = canvas.Canvas(pdf_path, pagesize=letter)
    for png in png_paths:
        # Stretch to exact letter size as requested.
        c.drawImage(
            png,
            0,
            0,
            width=page_w,
            height=page_h,
            preserveAspectRatio=False,
            mask="auto",
        )
        c.showPage()
    c.save()
