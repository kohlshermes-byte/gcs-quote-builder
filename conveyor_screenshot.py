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


def _PAGINATE_JS():
    return """
() => {
  const PAGE_H = 1056;   // template .page height at 96dpi (8.5x11in)
  const pages = Array.from(document.querySelectorAll('.page'));
  if (!pages.length) return 0;

  // Fix every page to exactly one letter page.
  const style = document.createElement('style');
  style.textContent = '.page { height: ' + PAGE_H + 'px !important; min-height: 0 !important; }';
  document.head.appendChild(style);

  const first = pages[0];
  const cs = getComputedStyle(first);
  const padBottom = parseFloat(cs.paddingBottom) || 0;
  const f0 = first.querySelector('.footer-bar');
  const footerH = f0 ? f0.getBoundingClientRect().height : 27;
  const LIMIT = PAGE_H - padBottom - footerH - 2;

  const bottomRel = (pg, el) =>
    el.getBoundingClientRect().bottom - pg.getBoundingClientRect().top;

  const mkFooter = () => {
    const ft = document.createElement('div');
    ft.className = 'footer-bar';
    ft.style.marginTop = 'auto';
    ft.innerHTML = '<span></span><span></span><span>GrinderCrusherScreen &nbsp;|&nbsp; Smyrna, GA</span>';
    return ft;
  };

  const mkPage = (srcPg, afterEl) => {
    const np = document.createElement('div');
    np.className = 'page';
    const tb = srcPg.querySelector('.top-bar');
    if (tb) np.appendChild(tb.cloneNode(true));
    np.appendChild(mkFooter());
    afterEl.parentNode.insertBefore(np, afterEl.nextSibling);
    return np;
  };

  // Break an oversized .equipment-detail-block into page-fillable units:
  // head (name/desc/image), each label+content category pair, spec table.
  const toUnits = (block) => {
    if (!block.classList.contains('equipment-detail-block')) return [block];
    if (block.getBoundingClientRect().height <= LIMIT) return [block];
    const units = [];
    const head = document.createElement('div');
    let pair = null;
    for (const c of Array.from(block.childNodes)) {
      if (c.nodeType !== 1) { continue; }
      if (c.classList.contains('detail-category-label')) {
        if (pair) units.push(pair);
        pair = document.createElement('div');
        pair.appendChild(c.cloneNode(true));
      } else if (pair) {
        pair.appendChild(c.cloneNode(true));
        units.push(pair);
        pair = null;
      } else {
        head.appendChild(c.cloneNode(true));
      }
    }
    if (pair) units.push(pair);
    units.unshift(head);
    return units;
  };

  // Split a table that overflows even on an empty page, row by row.
  const splitTableRows = (table, state) => {
    const thead = table.querySelector('thead');
    const bodies = Array.from(table.tBodies);
    let rows = [];
    bodies.forEach((b) => { rows.push(...Array.from(b.rows)); table.removeChild(b); });
    let curTable = null, curBody = null;
    const ensure = () => {
      if (curTable) return;
      curTable = table.cloneNode(false);
      if (thead) curTable.appendChild(thead.cloneNode(true));
      curBody = document.createElement('tbody');
      curTable.appendChild(curBody);
      state.cur.appendChild(curTable);
      state.curHas = true;
    };
    while (rows.length) {
      ensure();
      const row = rows.shift();
      curBody.appendChild(row);
      if (bottomRel(state.cur, curTable) > LIMIT && curBody.rows.length > 1) {
        curBody.removeChild(row);
        rows.unshift(row);
        curTable = null; curBody = null;
        state.newPage();
      }
    }
  };

  let created = 0;

  for (const pg of pages) {
    const footer = pg.querySelector('.footer-bar');
    const tb = pg.querySelector('.top-bar');
    const contentKids = Array.from(pg.children).filter(
      (el) => el !== footer && el !== tb
    );
    const queue = [];
    for (const el of contentKids) {
      const units = toUnits(el);   // measure while still laid out in the page
      pg.removeChild(el);
      queue.push(...units);
    }
    if (footer) pg.removeChild(footer);

    const state = {
      cur: pg,
      curHas: false,
      newPage: () => { state.cur = mkPage(pg, state.cur); created++; state.curHas = false; },
    };

    while (queue.length) {
      const u = queue.shift();
      state.cur.appendChild(u);
      if (bottomRel(state.cur, u) > LIMIT) {
        if (!state.curHas) {
          const isTable = u.tagName === 'TABLE' && u.tBodies.length;
          if (isTable) {
            state.cur.removeChild(u);
            splitTableRows(u, state);
          }
          // Non-table oversized unit alone on an empty page: leave it.
          state.curHas = true;
        } else {
          state.cur.removeChild(u);
          queue.unshift(u);
          state.newPage();
        }
      } else {
        state.curHas = true;
      }
    }
  }

  // Re-append a footer (last child) to every page and renumber.
  const all = Array.from(document.querySelectorAll('.page'));
  all.forEach((p, i) => {
    const old = p.querySelector('.footer-bar');
    if (old) old.remove();
    const ft = mkFooter();
    p.appendChild(ft);
    const spans = ft.querySelectorAll('span');
    spans[0].textContent = (p.querySelector('.quote-num') || {}).textContent || '';
    spans[1].textContent = 'Page ' + (i + 1) + ' of ' + all.length;
  });
  return all.length;
}
"""


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
                # Wait for logo / remote images to fully load
                try:
                    page.wait_for_function(
                        "Array.from(document.images).every(i => i.complete)",
                        timeout=10000,
                    )
                except Exception:
                    pass
                page.wait_for_timeout(300)

                # True pagination: fix page height, move overflow blocks to
                # new pages with proper top-bar/footer, renumber footers.
                n_pages = page.evaluate(_PAGINATE_JS())
                page.wait_for_timeout(100)

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
