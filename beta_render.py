"""BETA feature: inject the customer's logo into the rendered quote HTML.

Called from app.py after conveyor_render writes the quote. Embeds the logo
as a data URI so it survives the Playwright PDF renderer (which has no
session cookie).

Two modes:

- LEGACY (job has no beta logo state on disk): the historical behavior —
  logo absolutely positioned dead-center of the meta strip, strip
  min-height grown just enough to fit it. Kept byte-compatible so
  production quotes and older beta quotes never change.

- NEW (beta logo job): the logo strip is FIXED at STRIP_HEIGHT_PX — the
  size of the approved Cork Environmental quote (20261027_235941).
  Placement, box size, aspect lock and image adjustments (brightness,
  contrast, saturation, sharpness, grayscale, sepia, blur, opacity) are
  stored per quote in logo_settings.json and edited interactively in the
  preview via beta_logo_ui.js ("logo stamp" tool). When the logo is
  disabled — or none was found — the entire meta strip is removed so no
  blank section is left behind.

State files (per job dir):
  conveyor.json        "logo_enabled": true/false   (display switch)
  logo_settings.json   {"x","y","w","h","aspect_lock","filters":{...}}
"""
import json
import os

from cust_logo import logo_data_uri

BASE = os.path.dirname(os.path.abspath(__file__))

# Fixed logo-strip height (px): the Cork Environmental quote rendered the
# strip at min-height:70px (46px logo + 12px gap above and below).
STRIP_HEIGHT_PX = 70
# Max logo box height in the stamp tool: 2x the strip (overflow is allowed
# and clamped so the box always still overlaps the strip).
MAX_LOGO_H_FACTOR = 2.0
LEGACY_GAP_PX = 12  # legacy equal space above/below the logo in the strip

STRIP_TAG = '<div class="meta-strip"'

DEFAULT_FILTERS = {
    "brightness": 100, "contrast": 100, "saturation": 100, "sharpen": 0,
    "grayscale": 0, "sepia": 0, "blur": 0, "opacity": 100,
}
_FILTER_RANGES = {
    "brightness": (0, 300), "contrast": (0, 300), "saturation": (0, 300),
    "sharpen": (0, 100), "grayscale": (0, 100), "sepia": (0, 100),
    "blur": (0, 20), "opacity": (0, 100),
}

# Byte-identical to the historical injection (legacy parity).
_LEGACY_STYLE = (
    "<style>.meta-strip{position:relative;}.cust-logo{position:absolute;"
    "left:50%;top:calc(50% - 14px);transform:translate(-50%,-50%);"
    "max-height:46px;max-width:260px;object-fit:contain;"
    "pointer-events:none;}</style>"
)

_NEW_HEAD_STYLE = (
    '<style id="gcs-logo-style">'
    ".meta-strip{position:relative;}"
    ".cust-logo{position:absolute;}"
    "img.cust-logo{user-select:none;-webkit-user-drag:none;}"
    "img.gcs-logo-selected{outline:1.5px dashed #CC0000;outline-offset:2px;}"
    ".gcs-logo-handle{position:absolute;width:12px;height:12px;background:#fff;"
    "border:2px solid #CC0000;border-radius:3px;z-index:6;box-sizing:border-box;"
    "display:none;}"
    ".gcs-logo-editing .gcs-logo-handle{display:block;}"
    ".gcs-h-nw,.gcs-h-se{cursor:nwse-resize;}"
    ".gcs-h-ne,.gcs-h-sw{cursor:nesw-resize;}"
    ".gcs-logo-panel{position:fixed;bottom:14px;right:14px;width:242px;"
    "max-height:calc(100vh - 72px);overflow:auto;background:#141317;color:#e8e8e8;"
    "border:1px solid #34343a;border-radius:10px;padding:12px 13px 10px;"
    "font:11px/1.45 Arial,Helvetica,sans-serif;z-index:9999;"
    "box-shadow:0 10px 34px rgba(0,0,0,.5);display:none;}"
    ".gcs-logo-panel h4{margin:0 0 8px;font-size:10px;letter-spacing:.14em;"
    "color:#fff;text-transform:uppercase;display:flex;"
    "justify-content:space-between;align-items:center;}"
    ".gcs-logo-panel h4 button{background:none;border:0;color:#888;"
    "font-size:14px;cursor:pointer;padding:0 2px;line-height:1;}"
    ".gcs-logo-panel h4 button:hover{color:#fff;}"
    ".gcs-chk{display:flex;align-items:center;gap:7px;margin:5px 0;"
    "color:#cfcfd4;cursor:pointer;}"
    ".gcs-chk input{accent-color:#CC0000;margin:0;}"
    ".gcs-row{display:flex;align-items:center;gap:6px;margin:5px 0;}"
    ".gcs-row label{flex:1;color:#b9b9c0;}"
    ".gcs-row input[type=number]{width:56px;background:#1d1c22;"
    "border:1px solid #45454d;color:#eee;border-radius:4px;padding:2px 5px;"
    "font:11px Arial;}"
    ".gcs-unit{color:#777;}"
    ".gcs-snap{display:grid;grid-template-columns:repeat(5,1fr);gap:4px;"
    "margin:6px 0 2px;}"
    ".gcs-btn{background:#232329;border:1px solid #45454d;color:#ddd;"
    "border-radius:4px;padding:3px 6px;font:10px Arial;cursor:pointer;}"
    ".gcs-btn:hover{border-color:#CC0000;color:#fff;}"
    ".gcs-btn-wide{width:100%;margin-top:8px;}"
    ".gcs-slider-row{display:flex;align-items:center;gap:7px;margin:4px 0;}"
    ".gcs-slider-row label{width:64px;color:#b9b9c0;flex:none;}"
    ".gcs-slider-row input[type=range]{flex:1;accent-color:#CC0000;min-width:0;}"
    ".gcs-slider-row .gcs-val{width:38px;text-align:right;color:#8b8b93;"
    "flex:none;font-size:10px;}"
    ".gcs-sep{border-top:1px solid #2b2b31;margin:8px 0 5px;}"
    ".gcs-hint{color:#6f6f78;font-size:9.5px;margin-top:7px;line-height:1.5;}"
    ".gcs-dim{opacity:.15;pointer-events:none;}"
    "</style>"
)

_JS_CACHE = None


# --------------------------------------------------------------------------
# settings storage
# --------------------------------------------------------------------------
def _settings_path(job_dir):
    return os.path.join(job_dir, "logo_settings.json")


def load_settings(job_dir):
    try:
        with open(_settings_path(job_dir), encoding="utf-8") as f:
            s = json.load(f)
        if isinstance(s, dict):
            return s
    except Exception:
        pass
    return None


def is_beta_logo_job(job_dir):
    """True when the job carries beta logo state → new placement engine."""
    if os.path.isfile(_settings_path(job_dir)):
        return True
    try:
        with open(os.path.join(job_dir, "conveyor.json"), encoding="utf-8") as f:
            return "logo_enabled" in json.load(f)
    except Exception:
        return False


def logo_enabled(job_dir):
    """Display switch: conveyor.json 'logo_enabled' wins; default on."""
    try:
        with open(os.path.join(job_dir, "conveyor.json"), encoding="utf-8") as f:
            d = json.load(f)
        if "logo_enabled" in d:
            return bool(d["logo_enabled"])
    except Exception:
        pass
    return True


def set_logo_enabled(job_dir, enabled):
    jp = os.path.join(job_dir, "conveyor.json")
    try:
        with open(jp, encoding="utf-8") as f:
            d = json.load(f)
    except Exception:
        return False
    d["logo_enabled"] = bool(enabled)
    try:
        with open(jp, "w", encoding="utf-8") as f:
            json.dump(d, f, indent=2)
    except Exception:
        return False
    return True


def save_logo_settings(job_dir, enabled=None, settings=None):
    """Merge preview-saved state. Returns the merged settings dict."""
    if enabled is not None:
        set_logo_enabled(job_dir, bool(enabled))
    if isinstance(settings, dict):
        _merge_settings(job_dir, settings)
    return load_settings(job_dir) or {}


def _merge_settings(job_dir, patch):
    cur = dict(load_settings(job_dir) or {})
    for k in ("x", "y", "w", "h"):
        if k in patch:
            try:
                v = float(patch[k])
            except (TypeError, ValueError):
                continue
            if k == "y":
                # vertical is free across the page (positions are strip-relative)
                v = max(-900.0, v)
            elif k == "x":
                # the logo may sit left of the strip's left edge (page margin)
                v = max(-100.0, v)
            else:
                v = max(0.0, v)
            cur[k] = v
    if "aspect_lock" in patch:
        cur["aspect_lock"] = bool(patch["aspect_lock"])
    f_in = patch.get("filters")
    if isinstance(f_in, dict):
        f = {k: float(v) for k, v in (cur.get("filters") or DEFAULT_FILTERS).items()}
        for k, (lo, hi) in _FILTER_RANGES.items():
            if k in f_in:
                try:
                    f[k] = min(hi, max(lo, float(f_in[k])))
                except (TypeError, ValueError):
                    pass
        cur["filters"] = f
    try:
        with open(_settings_path(job_dir), "w", encoding="utf-8") as fh:
            json.dump(cur, fh, indent=2)
    except Exception:
        pass


def _clean_settings(settings):
    """Whitelist what gets embedded into the page's boot script."""
    s = settings or {}
    out = {}
    for k in ("x", "y", "w", "h"):
        v = s.get(k)
        if isinstance(v, (int, float)):
            out[k] = float(v)
    if "aspect_lock" in s:
        out["aspect_lock"] = bool(s.get("aspect_lock"))
    f = s.get("filters")
    if isinstance(f, dict):
        clean_f = {}
        for k in DEFAULT_FILTERS:
            if k in f:
                try:
                    clean_f[k] = float(f[k])
                except (TypeError, ValueError):
                    pass
        out["filters"] = clean_f
    return out


# --------------------------------------------------------------------------
# CSS builders
# --------------------------------------------------------------------------
def _filter_css(filters):
    f = {k: float(v) for k, v in DEFAULT_FILTERS.items()}
    if isinstance(filters, dict):
        for k in DEFAULT_FILTERS:
            try:
                f[k] = float(filters.get(k, DEFAULT_FILTERS[k]))
            except (TypeError, ValueError):
                pass
    parts = []
    if f["brightness"] != 100:
        parts.append("brightness(%g%%)" % f["brightness"])
    if f["contrast"] != 100:
        parts.append("contrast(%g%%)" % f["contrast"])
    if f["saturation"] != 100:
        parts.append("saturate(%g%%)" % f["saturation"])
    if f["grayscale"]:
        parts.append("grayscale(%g%%)" % f["grayscale"])
    if f["sepia"]:
        parts.append("sepia(%g%%)" % f["sepia"])
    if f["blur"]:
        parts.append("blur(%gpx)" % f["blur"])
    if f["opacity"] != 100:
        parts.append("opacity(%g%%)" % f["opacity"])
    if f["sharpen"]:
        parts.append("url(#gcsLogoSharpen)")
    return " ".join(parts)


def _logo_style(settings):
    """Inline style for the logo img (new mode)."""
    s = settings or {}
    base = (
        "position:absolute;left:50%;top:calc(50% - 14px);"
        "transform:translate(-50%,-50%);max-height:46px;max-width:260px;"
        "object-fit:contain;z-index:2;pointer-events:auto;cursor:move;"
        "user-select:none;-webkit-user-drag:none;"
    )
    if all(isinstance(s.get(k), (int, float)) for k in ("x", "y", "w", "h")):
        base = (
            "position:absolute;left:%gpx;top:%gpx;width:%gpx;height:%gpx;"
            "object-fit:fill;z-index:2;pointer-events:auto;cursor:move;"
            "user-select:none;-webkit-user-drag:none;"
            % (float(s["x"]), float(s["y"]), float(s["w"]), float(s["h"]))
        )
    filt = _filter_css(s.get("filters"))
    if filt:
        base += "filter:" + filt + ";"
    return base


def _load_ui_js():
    global _JS_CACHE
    if _JS_CACHE is None:
        try:
            with open(os.path.join(BASE, "beta_logo_ui.js"), encoding="utf-8") as f:
                _JS_CACHE = f.read()
        except Exception:
            _JS_CACHE = ""
    return _JS_CACHE


def _body_ui(jid, settings, enabled):
    boot = (
        "window.GCS_JOB_ID=%s;window.GCS_LOGO_SETTINGS=%s;window.GCS_LOGO_ENABLED=%s;"
        % (
            json.dumps(jid),
            json.dumps(_clean_settings(settings)),
            "true" if enabled else "false",
        )
    )
    return _svg_sharpen(settings) + '<script id="gcs-logo-script">' + boot + _load_ui_js() + "</script>"


def _svg_sharpen(settings):
    """Sharpen filter def with the saved amount baked into the kernel, so the
    PDF is right even if the preview script never runs. kernel:
    [0 -k 0; -k 1+4k -k; 0 -k 0], divisor 1 (k = amount/100)."""
    s = settings or {}
    f = s.get("filters") if isinstance(s.get("filters"), dict) else {}
    try:
        k = max(0.0, min(1.0, float((f or {}).get("sharpen", 0)) / 100.0))
    except (TypeError, ValueError):
        k = 0.0
    if k <= 0:
        return ""
    c = 1 + 4 * k
    fmt = lambda v: ("%g" % v)
    kernel = "0 %s 0 %s %s %s 0 %s 0" % (fmt(-k), fmt(-k), fmt(c), fmt(-k), fmt(-k))
    return (
        '<svg id="gcs-logo-svg" class="gcs-logo-svg" aria-hidden="true" '
        'style="position:absolute;width:0;height:0;overflow:hidden" '
        'width="0" height="0">'
        '<defs><filter id="gcsLogoSharpen" x="-5%" y="-5%" width="110%" '
        'height="110%" color-interpolation-filters="sRGB">'
        '<feConvolveMatrix order="3" preserveAlpha="true" edgeMode="duplicate" '
        'divisor="1" kernelMatrix="' + kernel + '"/>'
        "</filter></defs></svg>"
    )


# --------------------------------------------------------------------------
# html surgery helpers
# --------------------------------------------------------------------------
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
    label = html.find(">Quote Date<")
    if label == -1:
        return html
    start = html.rfind('<div class="meta-cell">', 0, label)
    if start == -1:
        return html
    return _remove_element_at(html, start)


def _remove_element_at(html, idx):
    """Remove the balanced <div> element that starts at idx."""
    if idx < 0:
        return html
    depth = 0
    i = idx
    while i < len(html):
        m_open = html.find("<div", i)
        m_close = html.find("</div>", i)
        if m_close == -1:
            return html
        if m_open != -1 and m_open < m_close:
            depth += 1
            i = m_open + 4
        else:
            depth -= 1
            i = m_close + 6
            if depth == 0:
                return html[:idx] + html[i:]
    return html


# --------------------------------------------------------------------------
# injection entry points
# --------------------------------------------------------------------------
def inject_logo(html, job_dir, jid=None, enabled=None):
    """Inject (or remove) the customer logo. Legacy jobs keep the historical
    behavior byte-for-byte; beta logo jobs get the fixed strip + stamp tool."""
    if jid is None:
        jid = os.path.basename(os.path.abspath(job_dir))
    if not is_beta_logo_job(job_dir):
        return _inject_legacy(html, job_dir)

    # ---- NEW MODE ----
    if enabled is None:
        enabled = logo_enabled(job_dir)
    uri = logo_data_uri(job_dir) if enabled else None
    if not uri:
        # No logo to show: remove the strip entirely so no blank section
        # is left behind.
        return _remove_element_at(html, html.find(STRIP_TAG))

    settings = load_settings(job_dir) or {}
    html = _remove_quote_date_cell(html)
    idx = html.find(STRIP_TAG)
    if idx == -1:
        return html
    close = html.find(">", idx) + 1
    html = (
        html[:idx]
        + '<div class="meta-strip" style="min-height:%dpx">' % STRIP_HEIGHT_PX
        + html[close:]
    )
    img = (
        '<img class="cust-logo" src="' + uri + '" alt="customer logo" '
        'draggable="false" contenteditable="false" style="'
        + _logo_style(settings)
        + '">'
    )
    close = html.find(">", idx) + 1
    html = html[:close] + img + html[close:]
    html = html.replace("</head>", _NEW_HEAD_STYLE + "</head>", 1)
    html = html.replace("</body>", _body_ui(jid, settings, enabled) + "</body>", 1)
    return html


def _inject_legacy(html, job_dir):
    """Historical behavior, preserved byte-for-byte."""
    uri = logo_data_uri(job_dir)
    if not uri:
        return html
    idx = html.find(STRIP_TAG)  # without '>' so min-height attr is ok
    if idx == -1:
        return html
    img = (
        '<img class="cust-logo" src="' + uri + '" alt="customer logo" '
        'contenteditable="false">'
    )
    html = _remove_quote_date_cell(html)
    idx = html.find(STRIP_TAG)
    if idx == -1:
        return html
    close = html.find(">", idx) + 1  # end of the opening strip tag
    # keep the strip tall enough that the logo fits with equal gaps above and
    # below (the logo is absolutely positioned and can't push the border down)
    lh = _displayed_logo_height(job_dir)
    if lh:
        mh = lh + 2 * LEGACY_GAP_PX
        html = (
            html[:idx]
            + '<div class="meta-strip" style="min-height:' + str(mh) + 'px">'
            + html[close:]
        )
        close = html.find(">", idx) + 1
    html = html[:close] + img + html[close:]
    html = html.replace("</head>", _LEGACY_STYLE + "</head>", 1)
    return html


def clear_logo(job_dir):
    path = os.path.join(job_dir, "cust_logo.png")
    try:
        os.remove(path)
    except OSError:
        pass
