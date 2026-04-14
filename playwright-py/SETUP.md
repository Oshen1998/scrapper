# DigiKey Scraper — Python Setup, Installation & Execution

## Prerequisites

| Requirement | Minimum version | Check |
|---|---|---|
| Python | 3.11+ | `python3 --version` |
| pip | bundled with Python | `pip --version` |

---

## Installation

### 1. Navigate to this directory

```bash
cd playwright-py
```

### 2. Create a virtual environment

```bash
python3 -m venv .venv
```

### 3. Activate the virtual environment

**macOS / Linux:**
```bash
source .venv/bin/activate
```

**Windows:**
```bash
.venv\Scripts\activate
```

Your shell prompt will change to show `(.venv)` when the environment is active.

### 4. Install Python dependencies

```bash
pip install -r requirements.txt
```

This installs:
- `playwright` — browser automation (Python async API)
- `python-dotenv` — loads `.env` config

### 5. Install the Chromium browser binary

Playwright ships without a browser. Download Chromium once:

```bash
playwright install chromium
```

---

## Configuration

All settings are read from the `.env` file in this directory.

```env
# Target URL to scrape
SCRAPER_URL=https://www.digikey.com/en/products/filter/accessories/783

# How many table pages to scrape (0 = all pages)
SCRAPER_MAX_PAGES=0

# Run browser headlessly (true = no window, false = show browser window)
SCRAPER_HEADLESS=false

# Milliseconds to wait between page navigations
SCRAPER_DELAY_MS=1500

# Directory to save products.json and products.csv
SCRAPER_OUTPUT_DIR=./output

# Enable verbose debug logging + screenshots on errors
SCRAPER_DEBUG=false
```

Edit `.env` directly — no code changes needed to adjust behaviour.

---

## Execution

Make sure the virtual environment is activated before running any command (`source .venv/bin/activate`).

### Scrape (default — reads all settings from `.env`)

```bash
python src/scraper.py
```

### Scrape headlessly (no browser window)

```bash
SCRAPER_HEADLESS=true python src/scraper.py
```

### Scrape with debug logging + error screenshots

```bash
SCRAPER_DEBUG=true python src/scraper.py
```

### Limit to a specific number of pages

```bash
SCRAPER_MAX_PAGES=3 python src/scraper.py
```

### Run the diagnostic tool

Dumps the raw HTML structure of the first 2 product rows to `output/diag/cell-structure.json`. Useful when the site's DOM changes and you need to reverse-engineer selectors.

```bash
python src/diagnose.py
```

---

## Output

After a successful run, results are written to `./output/` (configurable via `SCRAPER_OUTPUT_DIR`):

| File | Format | Description |
|---|---|---|
| `products.json` | JSON array | All scraped products, one object per row |
| `products.csv` | CSV | Same data, Excel/Sheets-friendly |
| `debug-load.png` | PNG | Screenshot on table-load failure (debug mode only) |
| `error-screenshot.png` | PNG | Screenshot captured on unhandled error |
| `diag/cell-structure.json` | JSON | Raw cell HTML from `python src/diagnose.py` |

---

## Troubleshooting

**`playwright install` must be re-run after upgrading the `playwright` package.**
The browser binary version is tied to the pip package version.

**Browser window opens but the page is blank / shows a CAPTCHA.**
Set `SCRAPER_DEBUG=true` and re-run. A screenshot will be saved to `output/debug-load.png` showing exactly what the browser sees.

**`ModuleNotFoundError: No module named 'playwright'`**
The virtual environment is not activated. Run `source .venv/bin/activate` first.

**`python3` not found on Windows.**
Use `python` instead of `python3`. Verify with `python --version` that it reports 3.11+.
