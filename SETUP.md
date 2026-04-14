# DigiKey Scraper — Overview

A Playwright-based web scraper for DigiKey product tables. Available in two implementations that are functionally identical — use whichever language you prefer.

```
webscraping/
├── playwright-ts/    TypeScript implementation
└── playwright-py/    Python implementation
```

For full setup, installation, and execution details, see the guide for your chosen language:

- [playwright-ts/SETUP.md](playwright-ts/SETUP.md) — TypeScript + Node.js
- [playwright-py/SETUP.md](playwright-py/SETUP.md) — Python

---

## Quick comparison

| | TypeScript | Python |
|---|---|---|
| Runtime | Node.js 18+ | Python 3.11+ |
| Package manager | npm | pip |
| Dependencies | `npm install` | `pip install -r requirements.txt` |
| Browser install | `npx playwright install chromium` | `playwright install chromium` |
| Run scraper | `npm run scrape` | `python src/scraper.py` |
| Run diagnostic | `npm run diagnose` | `python src/diagnose.py` |
| Config | `.env` file | `.env` file |
| Output | `output/products.json` + `output/products.csv` | `output/products.json` + `output/products.csv` |

---

## Configuration (shared by both)

Both implementations read the same `.env` variables:

| Variable | Default | Description |
|---|---|---|
| `SCRAPER_URL` | DigiKey accessories page | Target URL to scrape |
| `SCRAPER_MAX_PAGES` | `0` (all pages) | Max table pages to scrape |
| `SCRAPER_HEADLESS` | `false` | Hide browser window |
| `SCRAPER_DELAY_MS` | `1500` | Delay (ms) between page navigations |
| `SCRAPER_OUTPUT_DIR` | `./output` | Directory for output files |
| `SCRAPER_DEBUG` | `false` | Verbose logging + error screenshots |
