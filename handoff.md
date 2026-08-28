# Handoff Prompt — GCS Conveyor Quote Builder

**Copy everything below the line into a new Cursor chat to resume work.**

---

You are continuing work on the **GCS Conveyor Quote Builder** — a local Python app for GrinderCrusherScreen sales reps to build conveyor quotes from GCS product listing URLs.

## Read first

1. **`PROGRESS_JOURNAL.md`** — completed work, known issues, and the live to-do list
2. **`README.md`** — how to run the app
3. **Plan files** (if attached): `conveyor_firecrawl_pipeline` and `case_1_equipment_details`

## Project location (IMPORTANT)

The **runnable app** lives here — NOT in the `__MACOSX` folder:

```
Grinder Crusher Screen Quote Builder/GCS-Quote-Builder/
```

**Start:** Double-click `Start GCS Quote Builder.bat` on the Desktop, or `Start (Windows).bat` in the app folder.

**Conveyor UI:** `http://127.0.0.1:8765/conveyor`  
**Legacy equipment UI:** `http://127.0.0.1:8765/`

If `/conveyor` 404s or shows the old UI, close all command windows and restart — stale `app.py` on port 8765 is the usual cause.

## What exists today

### Two quote flows

| Flow | Entry | Output |
|------|-------|--------|
| Equipment (legacy) | `/` → `ui.html` | PDF / DOCX via `pdfgen.py`, `docgen.py` |
| Conveyor (new) | `/conveyor` → `conveyor_intake.html` | HTML quote → browser print PDF |

### Conveyor pipeline (2 stages)

1. **Stage 1 — Intake + extract:** User pastes listing URL (+ optional request-quote URL). Firecrawl scrapes to markdown. Data is parsed, reviewed, and saved to `jobs/<id>/conveyor.json`.
2. **Stage 2 — Build quote:** `conveyor_render.py` fills `conveyor_template.html` including **Detailed Equipment Information** (page 3).

### Case 1 vs Case 2 (intake toggle)

- **Case 1 — `listing_only`** (toggle OFF): New or used conveyor, no custom add-ons. **One URL only.** Sections parsed by `listing_parser.py` from scraped markdown.
- **Case 2 — `custom_build`** (toggle ON): New conveyor with custom add-ons. **Two URLs** (listing + request-quote). **Partially stubbed** — dual URL scrape exists but full merge into add-ons/pricing is **not done yet**.

### Case 1 equipment sections (page 3)

Parsed from GCS listing pages and rendered in order:

- Description
- Frame
- Idlers
- Undercarriage
- Belt
- Other
- Specifications (label/value table)

**Reference listing (validated):**  
`https://www.grindercrusherscreen.com/listings/5485994-screen-usa-tc3030-track-mounted-conveyor`  
Cached scrape: `jobs/20260616_221542__conveyor/scrape_listing.md`

## Key files

| File | Role |
|------|------|
| `app.py` | HTTP server + all API routes |
| `conveyor_intake.html` | Intake / review UI |
| `conveyor_template.html` | Quote HTML template (3 pages) |
| `conveyor_render.py` | Template renderer |
| `firecrawl_extract.py` | Firecrawl scrape + extraction orchestration |
| `listing_parser.py` | GCS listing markdown → 7 structured sections |
| `.env` | `FIRECRAWL_API_KEY` (gitignored) |

## API routes (conveyor)

| Route | Method | Purpose |
|-------|--------|---------|
| `/conveyor` | GET | Intake UI |
| `/conveyor/quote?id=` | GET | Rendered quote HTML |
| `/api/conveyor/extract` | POST | Scrape + parse listing |
| `/api/conveyor/save` | POST | Save `conveyor.json` |
| `/api/conveyor/render` | POST | Build HTML quote |
| `/api/conveyor/job?id=` | GET | Load saved quote |
| `/api/conveyor/jobs` | GET | List conveyor jobs |
| `/api/conveyor/defaults` | GET | Default quote schema |
| `/api/conveyor/config` | GET | `{ has_api_key: bool }` |

## Data model (`conveyor.json` highlights)

```json
{
  "quote_mode": "listing_only",
  "custom_addons_required": false,
  "urls": { "listing": "...", "request_quote": "" },
  "line_items": [{ "model": "", "addons": "", "description": "", "amount": "", "lead_time": "" }],
  "equipment_details": [{
    "name": "",
    "description": "",
    "frame": [],
    "idlers": [],
    "undercarriage": [],
    "belt": [],
    "other": [],
    "specifications": [{ "label": "", "value": "" }],
    "image_url": ""
  }],
  "field_status": {},
  "scrape_meta": {}
}
```

## Technical notes

- **Firecrawl `/v1/extract` returns empty** for GCS listings — Case 1 uses **`listing_parser.py`** on cached `scrape_listing.md` instead.
- Scrape cache: `jobs/<id>/scrape_listing.md`, `scrape_quote.md`
- Output: `jobs/<id>/GCS_Conveyor_Quote.html`
- Python deps: `requests`, `python-docx`, `reportlab` (see `requirements.txt`)

## Next priority (from PROGRESS_JOURNAL.md)

**Implement Case 2** — custom build with request-quote URL:

1. Parse request-quote page for selected options / add-ons
2. Merge into page 1 line item Custom Add-Ons
3. Override price and lead time from request-quote when available
4. Optionally merge configured options into Frame/Belt/Other sections

## Conventions

- Extend existing patterns in `app.py` / `conveyor_intake.html`; don't break legacy `/` flow
- Match conveyor template styling (`.section-title`, `.detail-category-label`, `.spec-table`)
- Human review gate: always allow edit before Build Quote
- Update `PROGRESS_JOURNAL.md` when completing tasks

## Your task this session

<!-- Replace this line with the specific goal for the new session, e.g.: -->
<!-- "Implement Case 2 request-quote parsing and merge into Custom Add-Ons." -->

_[Describe what you want done]_
