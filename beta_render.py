"""BETA feature: inject the customer's logo into the rendered quote HTML.

Called from app.py's beta-only branch after conveyor_render writes the quote.
Embeds the logo as a data URI so it survives the auth-gated Playwright PDF
renderer (which has no session cookie).

Placement: right side of the meta strip (the two lines holding Quote Date),
all the way right, vertically centered on those lines. Absolutely positioned
so it never moves the layout.
"""
import os

from cust_logo import logo_data_uri

_STYLE = (
    "<style>.meta-strip{position:relative;}.cust-logo{position:absolute;"
    "left:50%;top:calc(50% - 14px);transform:translate(-50%,-50%);"
    "max-height:46px;max-width:260px;object-fit:contain;"
    "pointer-events:none;}</style>"
)

_LOGO_GAP_PX = 12  # equal space above and below the logo inside the strip


def _displayed_logo_height(job_dir):
    """Height the logo renders at under max-height:46px / max-width:260px."""
    import io

    from PIL import Image
    path = os.path.join(job_dir, "cust_logo.png")
    if not os.path.isfile(path):
        return 0
    try:
        with Image.open(path) as im:
            w, h = im.size
    except Exception:
        return 0
    if not w or not h:
        return 0
    scale = min(46.0 / h, 260.0 / w, 1.0)
    return max(1, round(h * scale))


def _remove_quote_date_cell(html):
    """Beta: drop the Quote Date meta-cell (date appears elsewhere in the
    quote). Removes the div with balanced tag matching so layout survives."""
    label = html.find('>Quote Date<')
    if label == -1:
        return html
    start = html.rfind('<div class="meta-cell">', 0, label)
    if start == -1:
        return html
    depth = 0
    i = start
    while i < len(html):
        m_open = html.find('<div', i)
        m_close = html.find('</div>', i)
        if m_close == -1:
            return html
        if m_open != -1 and m_open < m_close:
            depth += 1
            i = m_open + 4
        else:
            depth -= 1
            i = m_close + 6
            if depth == 0:
                return html[:start] + html[i:]
    return html


def inject_logo(html, job_dir):
    uri = logo_data_uri(job_dir)
    if not uri:
        return html
    strip_tag = '<div class="meta-strip"'  # without '>' so min-height attr is ok
    idx = html.find(strip_tag)
    if idx == -1:
        return html
    img = (
        '<img class="cust-logo" src="' + uri + '" alt="customer logo" '
        'contenteditable="false">'
    )
    # beta: the quote date cell is redundant — remove it (before computing
    # insertion so indexes stay valid)
    html = _remove_quote_date_cell(html)
    idx = html.find(strip_tag)
    if idx == -1:
        return html
    close = html.find('>', idx) + 1  # end of the opening strip tag
    # keep the strip tall enough that the logo fits with equal gaps above and
    # below (the logo is absolutely positioned and can't push the border down)
    lh = _displayed_logo_height(job_dir)
    if lh:
        mh = lh + 2 * _LOGO_GAP_PX
        html = (
            html[:idx]
            + '<div class="meta-strip" style="min-height:' + str(mh) + 'px">'
            + html[close:]
        )
        close = html.find('>', idx) + 1
    html = html[:close] + img + html[close:]
    html = html.replace("</head>", _STYLE + "</head>", 1)
    return html


def clear_logo(job_dir):
    path = os.path.join(job_dir, "cust_logo.png")
    try:
        os.remove(path)
    except OSError:
        pass
