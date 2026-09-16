# GCS Conveyor Quote Builder — Progress Journal

**Last updated:** 2026-06-16  
**Runnable app path:** `Grinder Crusher Screen Quote Builder/GCS-Quote-Builder/`  
**Start command:** Double-click `Start GCS Quote Builder.bat` (Desktop) or `Start (Windows).bat` (app folder)

---

## Session Summary

This session extended the existing GCS Quote Builder (equipment PDF/DOCX flow) with a **new Conveyor Quote pipeline** powered by **Firecrawl** scraping and a structured **Detailed Equipment Information** page on the conveyor HTML template.

Two major phases were completed:

1. **Conveyor + Firecrawl pipeline** (2-stage intake → extract → review → build quote)
2. **Case 1 structured equipment details** (listing-only: Description, Frame, Idlers, Undercarriage, Belt, Other, Specifications)

---

## Completed Work

### Phase 1 — Conveyor Firecrawl Pipeline

| Item | Status | Notes |
|------|--------|-------|
| Copy & integrate conveyor HTML template | Done | `conveyor_template.html` with `{{PLACEHOLDER}}` tokens |
| Detailed Equipment Information section (page 3) | Done | Appended after pages 1–2; dynamic pagination |
| `firecrawl_extract.py` | Done | Firecrawl `/v1/scrape` + `/v1/extract`; dual-URL merge scaffold |
| `conveyor_render.py` | Done | Fills template from `conveyor.json` |
| `conveyor_intake.html` | Done | Split-pane UI at `/conveyor` |
| API routes in `app.py` | Done | `/conveyor`, `/conveyor/quote`, `/api/conveyor/*` |
| Job persistence | Done | `jobs/<id>/conveyor.json`, scrape cache, rendered HTML |
| `requirements.txt` | Done | `requests`, `python-docx`, `reportlab` |
| `.env.example` + `.env` | Done | `FIRECRAWL_API_KEY` configured |
| `.gitignore` | Done | Excludes `.env`, `jobs/` |
| README updates | Done | Conveyor flow + Firecrawl setup documented |
| Launcher scripts | Done | Install deps; kill stale `app.py` on Windows/Mac |
| Nav links | Done | Equipment ↔ Conveyor links in top bars |
| Browser opens `/conveyor` by default | Done | `app.py` main() |
| Saved Quotes drawer (conveyor) | Done | Search, open, duplicate, delete |
| Fix stale server / 404 on `/conveyor` | Done | Old `app.py` on port 8765 caused 404; bat now kills stale instances |

### Phase 2 — Case 1 Structured Equipment Details (Listing Only)

| Item | Status | Notes |
|------|--------|-------|
| `listing_parser.py` | Done | Parses GCS listing markdown into 7 sections |
| Case 1 extract path | Done | Listing-only uses parser (not Firecrawl extract) |
| `quote_mode` + `custom_addons_required` in schema | Done | `listing_only` vs `custom_build` |
| Intake toggle | Done | "Custom add-ons required" hides request-quote URL |
| Category review fields | Done | Description, Frame, Idlers, Undercarriage, Belt, Other, Specs |
| Per-field status dots | Done | Green/red after extract |
| Structured render on page 3 | Done | Category labels + bullet lists + specs table |
| TC3030 validation | Done | Tested against cached scrape + render |

### Reference Listing (validated)

- **URL:** `https://www.grindercrusherscreen.com/listings/5485994-screen-usa-tc3030-track-mounted-conveyor`
- **Expected:** $55,900, full Description + 5 bullet categories + 10 specification rows
- **Cached scrape:** `jobs/20260616_221542__conveyor/scrape_listing.md`

---

## Architecture (Current)

```
/conveyor  →  conveyor_intake.html
    │
    ├─ POST /api/conveyor/extract
    │     ├─ Firecrawl scrape → scrape_listing.md (cached)
    │     └─ listing_parser.py (Case 1) OR dual-URL merge (Case 2 stub)
    │
    ├─ POST /api/conveyor/save  →  jobs/<id>/conveyor.json
    │
    └─ POST /api/conveyor/render  →  jobs/<id>/GCS_Conveyor_Quote.html
          └─ GET /conveyor/quote?id=  →  preview / print PDF
```

**Legacy flow unchanged:** `/` → `ui.html` → PDF/DOCX via `pdfgen.py` / `docgen.py`

---

## Key Files

| File | Purpose |
|------|---------|
| `app.py` | HTTP server, all API routes |
| `conveyor_intake.html` | Stage 1 intake + review UI |
| `conveyor_template.html` | 2-page quote + page 3 equipment details |
| `conveyor_render.py` | Template population |
| `firecrawl_extract.py` | Firecrawl API + extraction orchestration |
| `listing_parser.py` | GCS listing markdown → structured sections |
| `ui.html` | Original equipment quote builder |
| `.env` | Firecrawl API key (local only, gitignored) |

---

## Known Issues / Gotchas

1. **Stale server:** If `/conveyor` returns 404 or shows the old equipment UI, close all black command windows and restart via `Start GCS Quote Builder.bat`. The launcher kills old `app.py` processes first.
2. **Wrong folder:** Cursor workspace may point at `__MACOSX/...` (archive stub). The **real app** is in `Grinder Crusher Screen Quote Builder/GCS-Quote-Builder/`.
3. **Firecrawl extract API** returns empty for GCS listings — **Case 1 uses `listing_parser` on scraped markdown instead** (by design).
4. **API key:** Rotate Firecrawl key if exposed in chat; update `.env`.
5. **Case 2** toggle shows request-quote URL but full custom-build merge is **not implemented yet**.

---

## To-Do List (Ongoing)

### High priority — Case 2 (Custom build with request-quote URL)

- [ ] Parse request-quote page for selected custom add-ons and configured options
- [ ] Merge request-quote data into line item **Custom Add-Ons** block (page 1)
- [ ] Override pricing / lead time from request-quote when present
- [ ] Optionally override Belt / Frame / Other bullets from configured build
- [ ] Remove "Case 2 coming next" placeholder note in intake UI when complete
- [ ] Field status dots for custom add-ons in Case 2

### Medium priority — UX & reliability

- [ ] Multi-page pagination for Detailed Equipment when content overflows one page
- [ ] Server-side PDF export (optional; print-to-PDF works today)
- [ ] Better error messages when Firecrawl scrape fails (blocked URL, timeout)
- [ ] "Last extracted" timestamp in intake UI
- [ ] Re-extract only when URLs change (debounce / compare URL hash)

### Lower priority — polish

- [ ] Auto quote number suffix for duplicates on same day (`GCS-MMDDYYYY-2`)
- [ ] Rep profile defaults editable without touching `app.py`
- [ ] Consolidate Cursor workspace to main app folder (not `__MACOSX`)
- [ ] Copy updated `conveyor_template.html` back to `Conveyor Quote Template/` in workspace if needed
- [ ] Git init + first commit (if desired)

### Testing checklist (manual)

- [ ] Case 1: TC3030 listing URL → extract → all 7 sections on page 3
- [ ] Case 1: Used conveyor listing (no custom add-ons)
- [ ] Save draft → reopen from Saved Quotes drawer
- [ ] Build quote → print / PDF export
- [ ] Case 2 smoke test once implemented

---

## Session Log (chronological)

| When | What |
|------|------|
| Session start | Planned 2-stage Conveyor + Firecrawl pipeline |
| Phase 1 | Built intake UI, extract module, render module, API routes, template integration |
| Mid-session | User reported 404 + old UI — fixed stale server on port 8765; bat kills old instances; opens `/conveyor` |
| Mid-session | User provided Firecrawl API key → saved to `.env` |
| Phase 2 | User specified 7 equipment categories from GCS listing pages |
| Phase 2 | Built `listing_parser.py`, Case 1 toggle, structured review + render |
| Session end | Validated TC3030 end-to-end; created this journal + `handoff.md` |
| Later session | PREPARED BY → Sales Rep dropdown (REPS table in intake JS) w/ builder styling |
| Later session | Removed "Custom Add-Ons Required" checkbox + paste box; added plain CUSTOM ADD-ONS textarea below Power (equipment_details.custom_addons), rendered in HTML + PDF. quote_mode now always listing_only |

---

## How to Update This Journal

After each work session:

1. Move completed items from **To-Do List** to **Completed Work** (with date).
2. Add a row to **Session Log**.
3. Update **Last updated** at the top.
4. Note any new gotchas in **Known Issues**.
