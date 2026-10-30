/* GCS beta "Logo Studio" — stamp tool for the customer logo inside the
   quote's meta strip. Injected by beta_render.py; runs inside the quote
   preview iframe (same origin).

   Features: click to select, drag to move, corner handles to resize
   (aspect lock on/off), W/H inputs, snap buttons (center / vertical /
   horizontal / left / right), image adjustments (brightness, contrast,
   saturation, sharpness, grayscale, sepia, blur, opacity), and a logo
   on/off toggle. All changes POST to /api/conveyor/logo-settings and are
   re-applied server-side on the next render.

   PDF export: window.GCS_exportQuoteHTML() returns the document HTML with
   all Logo Studio chrome removed but the logo's inline styles intact. */
(function () {
  "use strict";

  var JOB_ID = window.GCS_JOB_ID ||
    new URLSearchParams(location.search).get("id") || "";
  var S = window.GCS_LOGO_SETTINGS || {};
  var DEF_F = {
    brightness: 100, contrast: 100, saturation: 100, sharpen: 0,
    grayscale: 0, sepia: 0, blur: 0, opacity: 100,
  };
  var MAX_H = 140; // hard cap for the logo box height (2x the fixed strip)

  // ---- PDF export hook (called by the intake's Save PDF buttons) ----
  window.GCS_exportQuoteHTML = function () {
    var clone = document.documentElement.cloneNode(true);
    Array.prototype.forEach.call(
      clone.querySelectorAll(".gcs-logo-ui, #gcs-logo-script"),
      function (n) { n.remove(); }
    );
    var i = clone.querySelector("img.cust-logo");
    if (i) {
      i.classList.remove("gcs-logo-selected");
      i.style.cursor = "";
    }
    return "<!DOCTYPE html>\n" + clone.outerHTML;
  };

  var strip = document.querySelector(".meta-strip");
  var img = document.querySelector("img.cust-logo");
  if (!strip || !img) return;

  var box = null;          // {x, y, w, h} in strip px (null = legacy center)
  var F = Object.assign({}, DEF_F, S.filters || {});
  var lock = S.aspect_lock !== false;
  var selected = false;
  var handles = {};
  var panel = null;
  var saveTimer = null;
  var naturalRatio = null;

  // ---------------- helpers ----------------
  function sw() { return strip.clientWidth; }
  function sh() { return strip.clientHeight; }
  function r1(n) { return Math.round(n * 10) / 10; }
  function clamp(v, lo, hi) {
    if (hi < lo) { var t = lo; lo = hi; hi = t; }
    return Math.max(lo, Math.min(hi, v));
  }

  function ratio() {
    if (naturalRatio) return naturalRatio;
    if (img.naturalWidth && img.naturalHeight) {
      naturalRatio = img.naturalWidth / img.naturalHeight;
      return naturalRatio;
    }
    return null;
  }
  if (img.complete) ratio();
  else img.addEventListener("load", ratio, { once: true });

  function ensureBox() {
    if (box) return;
    var ir = img.getBoundingClientRect();
    var sr = strip.getBoundingClientRect();
    box = {
      x: r1(ir.left - sr.left), y: r1(ir.top - sr.top),
      w: r1(ir.width), h: r1(ir.height),
    };
    clampPos();
  }

  // Page-relative bounds: the logo may be dropped anywhere on page 1.
  function pageBox() {
    var page = strip.closest(".page") || document.querySelector(".page");
    var pr = page.getBoundingClientRect();
    var sr = strip.getBoundingClientRect();
    return { dx: sr.left - pr.left, dy: sr.top - pr.top,
             w: pr.width, h: pr.height };
  }

  // Position clamp: free movement anywhere on the first page (positions are
  // stored relative to the strip, so convert through the strip's offset).
  function clampPos() {
    if (!box) return;
    var p = pageBox();
    box.x = clamp(box.x, -p.dx, p.w - p.dx - box.w);
    box.y = clamp(box.y, -p.dy, p.h - p.dy - box.h);
  }

  function setSharpen(a) {
    var m = document.querySelector("#gcsLogoSharpen feConvolveMatrix");
    if (!m) {
      // filter def not emitted server-side (sharpen was 0 at render) — add it
      var svg = document.createElementNS("http://www.w3.org/2000/svg", "svg");
      svg.setAttribute("id", "gcs-logo-svg");
      svg.setAttribute("class", "gcs-logo-svg");
      svg.setAttribute("aria-hidden", "true");
      svg.setAttribute("width", "0");
      svg.setAttribute("height", "0");
      svg.style.cssText = "position:absolute;width:0;height:0;overflow:hidden";
      svg.innerHTML =
        '<defs><filter id="gcsLogoSharpen" x="-5%" y="-5%" width="110%" ' +
        'height="110%" color-interpolation-filters="sRGB">' +
        '<feConvolveMatrix order="3" preserveAlpha="true" ' +
        'edgeMode="duplicate" divisor="1" ' +
        'kernelMatrix="0 -1 0 -1 5 -1 0 -1 0"/></filter></defs>';
      document.body.appendChild(svg);
      m = svg.querySelector("feConvolveMatrix");
      if (!m) return;
    }
    var k = a / 100, c = 1 + 4 * k;
    m.setAttribute("kernelMatrix",
      "0 " + (-k) + " 0 " + (-k) + " " + c + " " + (-k) + " 0 " + (-k) + " 0");
  }

  function filterCSS() {
    var p = [];
    if (F.brightness !== 100) p.push("brightness(" + F.brightness + "%)");
    if (F.contrast !== 100) p.push("contrast(" + F.contrast + "%)");
    if (F.saturation !== 100) p.push("saturate(" + F.saturation + "%)");
    if (F.grayscale) p.push("grayscale(" + F.grayscale + "%)");
    if (F.sepia) p.push("sepia(" + F.sepia + "%)");
    if (F.blur) p.push("blur(" + F.blur + "px)");
    if (F.opacity !== 100) p.push("opacity(" + F.opacity + "%)");
    if (F.sharpen) { setSharpen(F.sharpen); p.push("url(#gcsLogoSharpen)"); }
    return p.join(" ");
  }

  function apply() {
    if (!box) return;
    img.style.transform = "none";
    img.style.maxWidth = "none";
    img.style.maxHeight = "none";
    img.style.left = box.x + "px";
    img.style.top = box.y + "px";
    img.style.width = box.w + "px";
    img.style.height = box.h + "px";
    img.style.objectFit = "fill";
    img.style.filter = filterCSS();
    placeHandles();
    syncInputs();
  }

  // ---------------- persistence ----------------
  function post(payload) {
    if (!JOB_ID) return;
    try {
      fetch("/api/conveyor/logo-settings", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(payload),
      }).catch(function () {});
    } catch (e) { /* ignore */ }
  }
  function save() {
    if (!box) return;
    post({
      id: JOB_ID,
      settings: {
        x: box.x, y: box.y, w: box.w, h: box.h,
        aspect_lock: lock, filters: F,
      },
    });
  }
  function debounceSave() {
    clearTimeout(saveTimer);
    saveTimer = setTimeout(save, 350);
  }

  // ---------------- selection + handles ----------------
  ["nw", "ne", "sw", "se"].forEach(function (c) {
    var d = document.createElement("div");
    d.className = "gcs-logo-handle gcs-logo-ui gcs-h-" + c;
    d.dataset.corner = c;
    d.addEventListener("pointerdown", startResize);
    strip.appendChild(d);
    handles[c] = d;
  });

  function placeHandles() {
    if (!box) return;
    var pts = {
      nw: [box.x, box.y], ne: [box.x + box.w, box.y],
      sw: [box.x, box.y + box.h], se: [box.x + box.w, box.y + box.h],
    };
    for (var c in pts) {
      handles[c].style.left = pts[c][0] + "px";
      handles[c].style.top = pts[c][1] + "px";
    }
  }

  function select(on) {
    selected = (on === undefined) ? !selected : on;
    strip.classList.toggle("gcs-logo-editing", selected);
    img.classList.toggle("gcs-logo-selected", selected);
    if (selected) { ensureBox(); apply(); showPanel(); }
    else hidePanel();
  }

  // ---------------- drag to move ----------------
  img.addEventListener("pointerdown", function (e) {
    if (e.button) return;
    e.preventDefault();
    if (!selected) select(true);
    ensureBox();
    var sx = e.clientX, sy = e.clientY, ox = box.x, oy = box.y;
    try { img.setPointerCapture(e.pointerId); } catch (err) {}
    function mv(ev) {
      box.x = r1(ox + ev.clientX - sx);
      box.y = r1(oy + ev.clientY - sy);
      clampPos();
      apply();
      if (panel) { panel.classList.add("gcs-dim"); } // keep the logo grabbable
    }
    function up() {
      img.removeEventListener("pointermove", mv);
      img.removeEventListener("pointerup", up);
      img.removeEventListener("pointercancel", up);
      if (panel) panel.classList.remove("gcs-dim");
      apply(); save();
    }
    img.addEventListener("pointermove", mv);
    img.addEventListener("pointerup", up);
    img.addEventListener("pointercancel", up);
  });

  // ---------------- corner resize ----------------
  function startResize(e) {
    if (e.button) return;
    e.preventDefault(); e.stopPropagation();
    var corner = e.currentTarget.dataset.corner;
    ensureBox();
    var sx = e.clientX, sy = e.clientY, b0 = Object.assign({}, box);
    var el = e.currentTarget;
    try { el.setPointerCapture(e.pointerId); } catch (err) {}
    function mv(ev) {
      var dx = ev.clientX - sx, dy = ev.clientY - sy;
      var w0 = b0.w, h0 = b0.h, x0 = b0.x, y0 = b0.y;
      var nw = w0, nh = h0, nx = x0, ny = y0;
      if (corner === "se" || corner === "ne") nw = w0 + dx;
      else { nw = w0 - dx; nx = x0 + dx; }
      if (corner === "se" || corner === "sw") nh = h0 + dy;
      else { nh = h0 - dy; ny = y0 + dy; }
      if (lock && ratio()) {
        var r = ratio();
        if (Math.abs(dx) >= Math.abs(dy)) {
          nh = nw / r;
          if (corner === "ne" || corner === "nw") ny = y0 + (h0 - nh);
        } else {
          nw = nh * r;
          if (corner === "sw" || corner === "nw") nx = x0 + (w0 - nw);
        }
      }
      nw = clamp(nw, 12, sw());
      nh = clamp(nh, 12, MAX_H);
      box = { x: r1(nx), y: r1(ny), w: r1(nw), h: r1(nh) };
      clampPos();
      apply();
    }
    function up() {
      el.removeEventListener("pointermove", mv);
      el.removeEventListener("pointerup", up);
      el.removeEventListener("pointercancel", up);
      apply(); save();
    }
    el.addEventListener("pointermove", mv);
    el.addEventListener("pointerup", up);
    el.addEventListener("pointercancel", up);
  }

  // ---------------- snap ----------------
  function snap(kind) {
    ensureBox();
    if (kind === "center" || kind === "h") box.x = (sw() - box.w) / 2;
    if (kind === "center" || kind === "v") box.y = (sh() - box.h) / 2;
    if (kind === "left") { box.x = 0; box.y = (sh() - box.h) / 2; }
    if (kind === "right") { box.x = sw() - box.w; box.y = (sh() - box.h) / 2; }
    clampPos(); apply(); save();
  }

  // ---------------- panel ----------------
  var SLIDERS = [
    ["brightness", "Brightness", 0, 200, 1, "%"],
    ["contrast", "Contrast", 0, 200, 1, "%"],
    ["saturation", "Saturation", 0, 200, 1, "%"],
    ["sharpen", "Sharpness", 0, 100, 1, ""],
    ["grayscale", "Grayscale", 0, 100, 1, "%"],
    ["sepia", "Sepia", 0, 100, 1, "%"],
    ["blur", "Blur", 0, 8, 0.5, "px"],
    ["opacity", "Opacity", 0, 100, 1, "%"],
  ];
  var glpW, glpH, glpLock, glpEnabled, glpPos, sliderEls = {};

  function el(tag, cls, parent) {
    var n = document.createElement(tag);
    if (cls) n.className = cls;
    if (parent) parent.appendChild(n);
    return n;
  }

  function buildPanel() {
    panel = el("div", "gcs-logo-panel gcs-logo-ui", document.body);
    panel.id = "gcs-logo-panel";

    // draggable panel — park it anywhere; position is remembered locally
    try {
      var sp = JSON.parse(localStorage.getItem("gcsLogoPanelPos") || "null");
      if (sp && sp.l && sp.t) {
        panel.style.left = sp.l; panel.style.top = sp.t;
        panel.style.right = "auto"; panel.style.bottom = "auto";
      }
    } catch (e) {}

    var h4 = el("h4", null, panel);
    h4.appendChild(document.createTextNode("Logo Studio"));
    h4.style.cursor = "move";
    h4.title = "Drag to move this panel";
    var close = el("button", null, h4);
    close.type = "button"; close.textContent = "\u00d7";
    close.addEventListener("click", function () { select(false); });
    h4.addEventListener("pointerdown", function (e) {
      if (e.target.closest("button")) return;
      e.preventDefault();
      var sx = e.clientX, sy = e.clientY;
      var pr = panel.getBoundingClientRect();
      var ol = pr.left, ot = pr.top;
      function mm(ev) {
        panel.style.left = clamp(ol + ev.clientX - sx, 0, window.innerWidth - 90) + "px";
        panel.style.top = clamp(ot + ev.clientY - sy, 0, window.innerHeight - 50) + "px";
        panel.style.right = "auto"; panel.style.bottom = "auto";
      }
      function mu() {
        h4.removeEventListener("pointermove", mm);
        h4.removeEventListener("pointerup", mu);
        try {
          localStorage.setItem("gcsLogoPanelPos",
            JSON.stringify({ l: panel.style.left, t: panel.style.top }));
        } catch (err) {}
      }
      h4.addEventListener("pointermove", mm);
      h4.addEventListener("pointerup", mu);
    });

    var lab1 = el("label", "gcs-chk", panel);
    glpEnabled = document.createElement("input");
    glpEnabled.id = "glp-enabled";
    glpEnabled.type = "checkbox"; glpEnabled.checked = true;
    lab1.appendChild(glpEnabled);
    lab1.appendChild(document.createTextNode("Show logo on quote"));
    glpEnabled.addEventListener("change", function () {
      strip.style.display = glpEnabled.checked ? "" : "none";
      if (!glpEnabled.checked) select(false);
      post({ id: JOB_ID, enabled: glpEnabled.checked });
    });

    el("div", "gcs-sep", panel);

    var posRow = el("div", "gcs-row", panel);
    posRow.appendChild(Object.assign(document.createElement("label"),
      { textContent: "Position" }));
    glpPos = el("span", "gcs-unit", posRow);
    glpPos.id = "glp-pos";
    glpPos.style.flex = "none";
    glpPos.textContent = "x: \u2014  y: \u2014";

    el("div", "gcs-sep", panel);

    var rowW = el("div", "gcs-row", panel);
    rowW.appendChild(Object.assign(document.createElement("label"),
      { textContent: "Width" }));
    glpW = document.createElement("input");
    glpW.id = "glp-w";
    glpW.type = "number"; glpW.min = "12"; glpW.max = String(sw());
    rowW.appendChild(glpW);
    var u1 = el("span", "gcs-unit", rowW); u1.textContent = "px";
    glpW.addEventListener("change", function () {
      setW(parseFloat(glpW.value));
    });

    var rowH = el("div", "gcs-row", panel);
    rowH.appendChild(Object.assign(document.createElement("label"),
      { textContent: "Height" }));
    glpH = document.createElement("input");
    glpH.id = "glp-h";
    glpH.type = "number"; glpH.min = "12"; glpH.max = String(MAX_H);
    rowH.appendChild(glpH);
    var u2 = el("span", "gcs-unit", rowH); u2.textContent = "px";
    glpH.addEventListener("change", function () {
      setH(parseFloat(glpH.value));
    });

    var lab2 = el("label", "gcs-chk", panel);
    glpLock = document.createElement("input");
    glpLock.id = "glp-lock";
    glpLock.type = "checkbox"; glpLock.checked = lock;
    lab2.appendChild(glpLock);
    lab2.appendChild(document.createTextNode("Lock original aspect ratio"));
    glpLock.addEventListener("change", function () {
      lock = glpLock.checked;
      if (lock && ratio() && box) {
        // snap the box back to the natural ratio from its current width
        box.h = box.w / ratio();
        clampBoxSize(); clampPos(); apply();
      }
      save();
    });

    el("div", "gcs-sep", panel);
    var snapLbl = el("div", "gcs-hint", panel);
    snapLbl.style.margin = "0 0 2px";
    snapLbl.textContent = "Snap position";
    var snapRow = el("div", "gcs-snap", panel);
    [
      ["center", "Center"], ["v", "V ctr"], ["h", "H ctr"],
      ["left", "Left"], ["right", "Right"],
    ].forEach(function (sd) {
      var b = el("button", "gcs-btn", snapRow);
      b.type = "button"; b.textContent = sd[1]; b.dataset.snap = sd[0];
      b.addEventListener("click", function () { snap(b.dataset.snap); });
    });

    el("div", "gcs-sep", panel);
    SLIDERS.forEach(function (s) {
      var row = el("div", "gcs-slider-row", panel);
      var lab = el("label", null, row); lab.textContent = s[1];
      var inp = document.createElement("input");
      inp.type = "range"; inp.min = String(s[2]); inp.max = String(s[3]);
      inp.step = String(s[4]); inp.value = String(F[s[0]]);
      row.appendChild(inp);
      var val = el("span", "gcs-val", row);
      val.textContent = F[s[0]] + s[5];
      inp.addEventListener("input", function () {
        F[s[0]] = +inp.value;
        val.textContent = inp.value + s[5];
        apply(); debounceSave();
      });
      sliderEls[s[0]] = { input: inp, val: val, unit: s[5] };
    });

    var reset = el("button", "gcs-btn gcs-btn-wide", panel);
    reset.id = "glp-reset";
    reset.type = "button"; reset.textContent = "Reset image adjustments";
    reset.addEventListener("click", function () {
      F = Object.assign({}, DEF_F);
      syncSliders(); apply(); save();
    });

    var hint = el("div", "gcs-hint", panel);
    hint.textContent = "Drag the logo to move it \u00b7 drag a red corner " +
      "to resize \u00b7 click away to close";
  }

  function clampBoxSize() {
    if (!box) return;
    box.w = clamp(box.w, 12, sw());
    box.h = clamp(box.h, 12, MAX_H);
  }

  function setW(v) {
    if (!isFinite(v)) return;
    ensureBox();
    v = clamp(v, 12, sw());
    if (lock && ratio()) {
      var h = v / ratio();
      if (h > MAX_H) { h = MAX_H; v = h * ratio(); }
      box.w = v; box.h = h;
    } else {
      box.w = v;
    }
    clampBoxSize(); clampPos(); apply(); save();
  }

  function setH(v) {
    if (!isFinite(v)) return;
    ensureBox();
    v = clamp(v, 12, MAX_H);
    if (lock && ratio()) {
      var w = v * ratio();
      if (w > sw()) { w = sw(); v = w / ratio(); }
      box.h = v; box.w = w;
    } else {
      box.h = v;
    }
    clampBoxSize(); clampPos(); apply(); save();
  }

  function syncInputs() {
    if (!panel || !box) return;
    glpW.value = String(Math.round(box.w));
    glpH.value = String(Math.round(box.h));
    if (glpPos) {
      glpPos.textContent = "x: " + Math.round(box.x) + "  y: " + Math.round(box.y);
    }
  }

  function syncSliders() {
    if (!panel) return;
    SLIDERS.forEach(function (s) {
      var se = sliderEls[s[0]];
      if (!se) return;
      se.input.value = String(F[s[0]]);
      se.val.textContent = F[s[0]] + se.unit;
    });
  }

  function showPanel() {
    if (!panel) buildPanel();
    panel.style.display = "block";
    glpEnabled.checked = strip.style.display !== "none";
    syncInputs(); syncSliders();
  }
  function hidePanel() {
    if (panel) panel.style.display = "none";
  }

  // ---------------- deselect ----------------
  document.addEventListener("pointerdown", function (e) {
    if (!selected) return;
    if (e.target === img) return;
    if (e.target.closest &&
        e.target.closest(".gcs-logo-handle, .gcs-logo-panel")) return;
    select(false);
  }, true);
  document.addEventListener("keydown", function (e) {
    if (e.key === "Escape") select(false);
  });

  // ---------------- init ----------------
  if (typeof S.x === "number" && typeof S.y === "number" &&
      typeof S.w === "number" && typeof S.h === "number") {
    box = { x: S.x, y: S.y, w: S.w, h: S.h };
    clampBoxSize(); clampPos();
    apply(); // normalizes legacy max-*/transform and positions handles
  }
  img.setAttribute("draggable", "false");
})();
