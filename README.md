# GCS Quote Builder

A local quote-building app for GrinderCrusherScreen. Equipment quotes run fully offline.
**Conveyor quotes** use the Firecrawl API to extract product data from listing URLs.

---

## First time setup (one time only)

You need **Python 3** installed. Most Macs already have it. To check / install:

- **Windows:** Download from https://www.python.org/downloads/ — during install,
  **check the box that says "Add Python to PATH"**.
- **Mac:** It's usually already there. If not, install from the same link.

The app installs its helper libraries automatically the first time you launch.

### Conveyor quotes — Firecrawl API key

1. Copy **`.env.example`** to **`.env`** in this folder.
2. Add your Firecrawl API key: `FIRECRAWL_API_KEY=fc-...`
3. Get a key at https://firecrawl.dev

Without a key, the conveyor intake UI works but **Extract Data** will fail.

---

## How to use it

1. **Start it:**
   - Mac: double-click **`Start (Mac).command`**
   - Windows: double-click **`Start (Windows).bat`**

   A small window opens (leave it open) and your browser pops up with the app.

2. **Equipment quotes** (original flow): open `http://127.0.0.1:8765/`
   Fill in customer, equipment lines, and freight. Download PDF or DOCX.

3. **Conveyor quotes** (new flow): open `http://127.0.0.1:8765/conveyor`
   - **Stage 1:** Enter customer info and paste a conveyor **listing URL** (and optional **request-quote URL**). Click **Extract Data**.
   - **Review** scraped fields (model, price, specs, add-ons). Edit anything that looks wrong.
   - **Stage 2:** Click **Build Quote** to fill the conveyor HTML template, including the **Detailed Equipment Information** section.
   - Click **Open / Print PDF** to export via the browser print dialog.

4. **Save Draft** (or Ctrl/Cmd + S) stores the quote in `jobs/<id>/conveyor.json`.

5. **Stop the app** by closing the launcher window.

---

## Where your data lives

- **Equipment quotes:** `jobs/<id>/quote.json` plus PDF/DOCX exports.
- **Conveyor quotes:** `jobs/<id>/conveyor.json`, `GCS_Conveyor_Quote.html`, and cached scrape files (`scrape_listing.md`, `scrape_quote.md`).
- To back up everything, copy the **`jobs/`** folder.

## Changing the defaults

Rep name, title, and mobile are pre-filled from `default_quote()` in `app.py`.
Conveyor rep defaults come from the same function via `default_conveyor_quote()`.

## The logo

The logo at **`assets/logo.png`** appears on equipment PDF/DOCX and conveyor HTML quotes.

---

## Notes

- The app runs only on this computer — nothing is exposed to the internet except Firecrawl API calls during conveyor extract.
- If port 8765 is busy, the app picks the next free port automatically.

