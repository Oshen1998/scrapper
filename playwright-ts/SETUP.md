# DigiKey Scraper — TypeScript Setup, Installation & Execution

## Prerequisites

| Requirement | Minimum version | Check |
|---|---|---|
| Node.js | 18+ | `node --version` |
| npm | 9+ | `npm --version` |

---

## Installation

### 1. Navigate to this directory

```bash
cd playwright-ts
```

### 2. Install npm dependencies

```bash
npm install
```

This installs:
- `playwright` — browser automation
- `dotenv` — loads `.env` config
- `ts-node` — runs TypeScript directly without a build step
- `typescript` — TypeScript compiler

### 3. Install the Chromium browser binary

Playwright ships without a browser. Download Chromium once:

```bash
npx playwright install chromium
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

### Scrape (default — reads all settings from `.env`)

```bash
npm run scrape
```

### Scrape headlessly (no browser window)

```bash
npm run scrape:headless
```

### Scrape with debug logging + error screenshots

```bash
npm run scrape:debug
```

### Run the diagnostic tool

Dumps the raw HTML structure of the first 2 product rows to `output/diag/cell-structure.json`. Useful when the site's DOM changes and you need to reverse-engineer selectors.

```bash
npm run diagnose
```

### Build TypeScript to JavaScript (optional)

Compiles `src/` → `dist/`. Only needed if you want to run via plain `node` instead of `ts-node`.

```bash
npm run build
node dist/scraper.js
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
| `diag/cell-structure.json` | JSON | Raw cell HTML from `npm run diagnose` |

---

## Troubleshooting

**`playwright install` must be re-run after upgrading the `playwright` package.**
The browser binary version is tied to the npm package version.

**Browser window opens but the page is blank / shows a CAPTCHA.**
Set `SCRAPER_DEBUG=true` and re-run. A screenshot will be saved to `output/debug-load.png` showing exactly what the browser sees.

**`ts-node: command not found`**
Run `npm install` again. `ts-node` is a dev dependency and must be installed locally.
