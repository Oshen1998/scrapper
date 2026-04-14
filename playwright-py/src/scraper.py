"""
DigiKey Product Table Scraper
─────────────────────────────
Tech stack : Python + Playwright (async)
Target     : https://www.digikey.com/en/products/filter/accessories/783

Key challenges solved here:
 1. React SPA  – the table is rendered by JavaScript, not baked into the raw
                 HTML.  We must wait for it to appear after the JS runs.
 2. Dynamic CSS – DigiKey uses TSS-generated class names like `tss-css-1xyz`
                 that change between deployments.  We rely on stable HTML
                 structure (table > thead > tr > th) and ARIA roles instead.
 3. Bot detection – Sift Science and GTM watch for headless-browser signals.
                 We spoof a real user-agent, disable the `webdriver` flag, and
                 add a small random delay between pages.
 4. Pagination  – After each page we look for the "Next" button, click it,
                 and wait for the new rows to load before extracting.
"""

import asyncio
import csv
import json
import math
import os
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

from dotenv import load_dotenv
from playwright.async_api import async_playwright, Browser, BrowserContext, Page

# Load .env file before reading any env values
load_dotenv()

# ─── Types ────────────────────────────────────────────────────────────────────

# A single product row: keys are column header names, values are strings.
# Equivalent to the TypeScript `Product` interface (index signature).
Product = dict[str, str]


@dataclass
class ScraperConfig:
    """Scraper configuration – mirrors the TypeScript ScraperConfig interface."""
    url: str
    max_pages: float           # float so we can use math.inf for "all pages"
    output_dir: Path
    headless: bool
    delay_between_pages: int   # milliseconds


@dataclass
class ScrapeResult:
    """Summary printed at the end of each run."""
    total_products: int
    pages_scraped: int
    columns: list[str]
    output_files: list[str]


# ─── Configuration ────────────────────────────────────────────────────────────

def _load_config() -> ScraperConfig:
    max_pages_env = os.getenv("SCRAPER_MAX_PAGES", "5")
    try:
        max_pages_int = int(max_pages_env)
    except ValueError:
        max_pages_int = 5

    max_pages: float = math.inf if max_pages_int == 0 else float(max_pages_int)

    return ScraperConfig(
        url=os.getenv(
            "SCRAPER_URL",
            "https://www.digikey.com/en/products/filter/accessories/783",
        ),
        max_pages=max_pages,
        output_dir=Path(os.getenv("SCRAPER_OUTPUT_DIR", "./output")).resolve(),
        headless=os.getenv("SCRAPER_HEADLESS", "false").lower() == "true",
        delay_between_pages=int(os.getenv("SCRAPER_DELAY_MS", "1500")),
    )


CONFIG = _load_config()
DEBUG = os.getenv("SCRAPER_DEBUG", "false").lower() == "true"


# ─── Logging helpers ──────────────────────────────────────────────────────────

def log(msg: str) -> None:
    print(f"[scraper] {msg}")

def warn(msg: str) -> None:
    print(f"[scraper] ⚠  {msg}", file=sys.stderr)

def debug(msg: str) -> None:
    if DEBUG:
        print(f"[debug]   {msg}")


# ─── Browser setup ────────────────────────────────────────────────────────────

async def launch_browser(playwright) -> Browser:
    """
    Launch Chromium with settings that reduce bot-detection signals.

    --disable-blink-features=AutomationControlled  → removes the "Chrome is
      being controlled by automated software" banner and the corresponding DOM
      flag that Sift Science checks.
    headless: False (default)  → the full GUI is rendered; some fingerprinting
      scripts detect "headless" mode and block scrapers.
    """
    return await playwright.chromium.launch(
        headless=CONFIG.headless,
        args=[
            "--no-sandbox",
            "--disable-setuid-sandbox",
            "--disable-blink-features=AutomationControlled",
            "--disable-infobars",
            "--window-size=1280,800",
        ],
    )


async def create_context(browser: Browser) -> BrowserContext:
    """
    Create a browser context that looks like a real macOS Chrome user.

    A "context" in Playwright is an isolated browser session – like an incognito
    window.  Each context has its own cookies, localStorage, and cache.
    """
    return await browser.new_context(
        user_agent=(
            "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
            "AppleWebKit/537.36 (KHTML, like Gecko) "
            "Chrome/124.0.0.0 Safari/537.36"
        ),
        viewport={"width": 1280, "height": 800},
        locale="en-US",
        timezone_id="America/New_York",
        extra_http_headers={
            "Accept-Language": "en-US,en;q=0.9",
            "Accept": (
                "text/html,application/xhtml+xml,application/xml;"
                "q=0.9,image/webp,*/*;q=0.8"
            ),
        },
    )


async def open_page(context: BrowserContext) -> Page:
    """
    Open a new page and inject a script that removes the `navigator.webdriver`
    property before ANY page JavaScript runs.

    Why: Playwright sets `navigator.webdriver = true` by default.
    Anti-bot scripts read this property on page load to detect automation.
    By overriding it to `undefined` before the page JS executes, we look like
    a normal user.
    """
    page = await context.new_page()

    # add_init_script runs BEFORE any page script – ideal for patching globals
    await page.add_init_script("""
        () => {
            // Hide webdriver flag
            Object.defineProperty(navigator, 'webdriver', {
                get: () => undefined,
            });

            // Spoof plugins array (headless Chrome has 0 plugins, real browsers have some)
            Object.defineProperty(navigator, 'plugins', {
                get: () => [1, 2, 3],
            });

            // Spoof language list
            Object.defineProperty(navigator, 'languages', {
                get: () => ['en-US', 'en'],
            });
        }
    """)

    return page


# ─── Waiting helpers ──────────────────────────────────────────────────────────

async def wait_for_table(page: Page) -> None:
    """
    Wait until the product table has visible rows.

    DigiKey's table is rendered by React after several XHR calls.  We:
     1. Wait for `networkidle` (no more than 2 in-flight requests for 500 ms).
     2. Wait for at least one <tr> inside <tbody> to appear in the DOM.

    If neither selector matches within the timeout we log a warning and take
    a debug screenshot – useful when the site serves a CAPTCHA or login wall.
    """
    log("Waiting for page to load...")

    try:
        await page.wait_for_load_state("networkidle", timeout=30_000)
    except Exception:
        warn("networkidle timeout – page may still be loading.")

    # Try common table selectors from most-specific to least-specific
    selectors = [
        "table tbody tr[data-row-index]",        # data attribute strategy
        "table tbody tr",                         # plain table rows
        '[role="rowgroup"] [role="row"]',         # ARIA role strategy
        ".MuiTableBody-root .MuiTableRow-root",   # MUI class strategy
    ]

    for sel in selectors:
        try:
            await page.wait_for_selector(sel, timeout=10_000)
            debug(f"Table found with selector: {sel}")
            return
        except Exception:
            debug(f"Selector not found: {sel}")

    warn("Could not confirm table loaded – attempting extraction anyway.")
    if DEBUG:
        screenshot_path = CONFIG.output_dir / "debug-load.png"
        CONFIG.output_dir.mkdir(parents=True, exist_ok=True)
        await page.screenshot(path=str(screenshot_path), full_page=True)
        debug(f"Debug screenshot saved to {screenshot_path}")


# ─── Data extraction ──────────────────────────────────────────────────────────

async def extract_headers(page: Page) -> list[str]:
    """
    Extract column headers from the table.

    Strategy waterfall (we try the most reliable first):
     1. Standard <thead> → <tr> → <th> structure
     2. ARIA role="columnheader"
     3. MUI-specific class names

    We run this inside page.evaluate() which executes in the browser's
    JavaScript context (not in Python).  This lets us access `document`.
    """
    headers: list[str] = await page.evaluate("""
        () => {
            // Strategy 1 – standard semantic HTML
            const thElements = document.querySelectorAll('table thead th');
            if (thElements.length > 0) {
                return Array.from(thElements).map(th => th.textContent?.trim() ?? '');
            }

            // Strategy 2 – ARIA roles (used by many accessibility-compliant React tables)
            const ariaHeaders = document.querySelectorAll('[role="columnheader"]');
            if (ariaHeaders.length > 0) {
                return Array.from(ariaHeaders).map(h => h.textContent?.trim() ?? '');
            }

            // Strategy 3 – MUI table class names
            const muiHeaders = document.querySelectorAll('.MuiTableCell-head');
            if (muiHeaders.length > 0) {
                return Array.from(muiHeaders).map(h => h.textContent?.trim() ?? '');
            }

            return [];
        }
    """)

    # Remove empty/whitespace-only headers and provide fallback names
    cleaned = [h if h else f"Column_{i + 1}" for i, h in enumerate(headers)]
    debug(f"Raw headers: {json.dumps(cleaned)}")
    return cleaned


async def extract_rows(page: Page) -> list[Product]:
    """
    Extract all product rows from the currently visible table page.

    DigiKey diagnostics revealed that every <td> carries a stable `data-atag`
    attribute that identifies the column type (e.g. "tr-unitPrice").
    The checkbox cell (data-atag="tr-compareParts") also holds all key product
    fields as data-* attributes on its inner <span> — this is the cleanest
    extraction source because it's already structured (no newline-concatenated text).

    Field map:
     tr-compareParts  <span>  → data-mfg-number, data-product-number,
                                 data-desc, data-mfg-name, data-price,
                                 data-packaging, data-img, data-id
     tr-product       <a data-testid="data-table-product-number"> → product URL
     tr-qtyAvailable  <strong> → quantity number; secondary div → stock status
     tr-unitPrice     <strong> → unit price; data-testid="CellLabel" → packaging label
     all others       innerText (plain text is fine)
    """
    products: list[Product] = await page.evaluate("""
        () => {
            const products = [];
            const rows = Array.from(document.querySelectorAll('table tbody tr'));

            for (const row of rows) {
                const cells = Array.from(row.querySelectorAll('td'));
                if (cells.length === 0) continue;

                const product = {};

                for (const cell of cells) {
                    const atag = cell.querySelector('[data-atag]')?.getAttribute('data-atag')
                        ?? cell.getAttribute('data-atag')
                        ?? '';

                    // ── Checkbox cell: richest source of clean product metadata ─────
                    if (atag === 'tr-compareParts') {
                        const span = cell.querySelector('span[data-mfg-number]');
                        if (span) {
                            product['DigiKey Part #']   = span.getAttribute('data-product-number') ?? '';
                            product['Mfr Part #']       = span.getAttribute('data-mfg-number')     ?? '';
                            product['Description']      = span.getAttribute('data-desc')            ?? '';
                            product['Manufacturer']     = span.getAttribute('data-mfg-name')        ?? '';
                            product['Unit Price (USD)'] = span.getAttribute('data-price')           ?? '';
                            product['Packaging']        = span.getAttribute('data-packaging')       ?? '';
                            const img = span.getAttribute('data-img') ?? '';
                            product['Image URL']        = img ? 'https:' + img : '';
                        }
                        continue;
                    }

                    // ── Product cell: grab the product detail page URL ───────────────
                    if (atag === 'tr-product') {
                        const a = cell.querySelector('a[data-testid="data-table-product-number"]');
                        product['Product URL'] = a?.getAttribute('href')
                            ? 'https://www.digikey.com' + a.getAttribute('href')
                            : (a?.href ?? '');
                        continue;
                    }

                    // ── Quantity Available: split number and stock status ────────────
                    if (atag === 'tr-qtyAvailable') {
                        const qty    = cell.querySelector('strong')?.textContent?.trim() ?? '';
                        const status = cell.querySelector('.tss-css-8e8qox-infoListDataSecondary')
                            ?.textContent?.trim()
                            ?? cell.innerText?.split('\\n')[1]?.trim()
                            ?? '';
                        product['Quantity Available'] = qty;
                        product['Stock Status']       = status;
                        continue;
                    }

                    // ── Unit Price: extract price and qty-break label ────────────────
                    if (atag === 'tr-unitPrice') {
                        const priceEl  = cell.querySelector('[data-testid="qty-price"]');
                        const strong   = priceEl?.querySelector('strong');
                        const fullText = priceEl?.innerText?.trim() ?? '';
                        // e.g. "1 : $0.75000" → split on ":"
                        const parts    = fullText.split(':');
                        product['Min Qty']     = parts[0]?.trim() ?? '1';
                        product['Price (USD)'] = strong?.textContent?.trim() ?? parts[1]?.trim() ?? '';
                        continue;
                    }

                    // ── All remaining cells: use data-atag as a readable key ─────────
                    const label = atag
                        .replace(/^tr-/, '')           // strip "tr-" prefix
                        .replace(/^CLS \\d+$/, '')      // drop generic "CLS 123"
                        || null;

                    if (!label) continue;              // skip un-labelled cells

                    // Convert known camelCase / concatenated keys to readable names
                    const readableLabel = {
                        tariff:        'Tariff Status',
                        series:        'Series',
                        packaging:     'Package',
                        productstatus: 'Product Status',
                    };

                    const colName = readableLabel[label.toLowerCase()] ?? label;
                    product[colName] = cell.innerText?.trim() ?? '';
                }

                // Only keep rows that have at least a part number
                if (product['Mfr Part #'] || product['DigiKey Part #']) {
                    products.push(product);
                }
            }

            return products;
        }
    """)

    return products


# ─── Pagination ───────────────────────────────────────────────────────────────

async def get_pagination_info(page: Page) -> dict:
    """
    Read "Showing X - Y of Z" info from DigiKey's pagination bar.

    DigiKey renders this as a plain text node near the pagination buttons.
    We walk every leaf text node in the document and match the pattern.
    """
    return await page.evaluate("""
        () => {
            // Walk all leaf text nodes looking for "Showing 1 - 25 of 1,575"
            const walker = document.createTreeWalker(
                document.body,
                NodeFilter.SHOW_TEXT,
            );
            let node;
            while ((node = walker.nextNode())) {
                const text = node.textContent?.trim() ?? '';
                // Match: "Showing 1 - 25 of 1,575" or "1-25 of 1575"
                const m = text.match(/showing\\s+([\\d,]+)\\s*[\\u2013-]\\s*([\\d,]+)\\s+of\\s+([\\d,]+)/i)
                    ?? text.match(/([\\d,]+)\\s*[\\u2013-]\\s*([\\d,]+)\\s+of\\s+([\\d,]+)/i);
                if (m) {
                    const total = parseInt(m[3].replace(/,/g, ''), 10);
                    const rowsPerPage = parseInt(m[2].replace(/,/g, ''), 10)
                        - parseInt(m[1].replace(/,/g, ''), 10) + 1;
                    return {
                        showing:       text,
                        totalProducts: total,
                        totalPages:    Math.ceil(total / rowsPerPage),
                    };
                }
            }
            return { showing: 'unknown', totalProducts: 0, totalPages: 0 };
        }
    """)


async def go_to_next_page(page: Page, current_page_num: int) -> bool:
    """
    Click the "Next Page" button and wait for new rows to load.

    Key insight from diagnostics:
     DigiKey uses data-testid="btn-next-page" on the Next button (confirmed).
     The page uses client-side routing, so the URL does NOT change between pages.
     We detect a successful navigation by capturing the first product's part
     number before clicking, then waiting until it changes.

    Returns True if we successfully moved to the next page, False if we're done.
    """
    # ── Check the Next button exists and is enabled ──────────────────────────
    btn = await page.query_selector('[data-testid="btn-next-page"]')

    if not btn:
        debug("btn-next-page not found in DOM – last page reached.")
        return False

    is_disabled = (
        await btn.get_attribute("disabled") is not None
        or await btn.get_attribute("aria-disabled") == "true"
    )

    if is_disabled:
        log("Next page button is disabled – reached last page.")
        return False

    # ── Snapshot the first product's unique ID before clicking ─────────────
    first_product_id_before: str = await page.evaluate("""
        () => {
            const link = document.querySelector(
                'table tbody tr:first-child a[data-product-id]'
            );
            return link?.getAttribute('data-product-id') ?? '';
        }
    """)

    debug(f"First product-id before click: {first_product_id_before}")
    debug(f"Clicking btn-next-page (currently on page {current_page_num})")
    await btn.click()

    # ── Wait for the table to re-render with new rows ─────────────────────────
    # Strategy 1: wait until the first product-id is different (most reliable)
    if first_product_id_before:
        try:
            await page.wait_for_function(
                """
                (prevId) => {
                    const link = document.querySelector(
                        'table tbody tr:first-child a[data-product-id]'
                    );
                    const newId = link?.getAttribute('data-product-id') ?? '';
                    return newId !== '' && newId !== prevId;
                }
                """,
                first_product_id_before,
                timeout=20_000,
            )
            debug("Confirmed: product list changed (new data-product-id on first row).")
        except Exception:
            warn("Product IDs did not change after clicking Next – may be on last page.")
            return False
    else:
        # Fallback: just wait for networkidle if we couldn't get a product ID
        debug("No product-id found to compare – falling back to networkidle wait.")
        try:
            await page.wait_for_load_state("networkidle", timeout=15_000)
        except Exception:
            pass
        await page.wait_for_timeout(1000)

    # ── Extra wait for any lazy-loaded images / prices ────────────────────────
    try:
        await page.wait_for_load_state("networkidle", timeout=10_000)
    except Exception:
        pass
    await page.wait_for_timeout(CONFIG.delay_between_pages)

    return True


# ─── Output helpers ───────────────────────────────────────────────────────────

def save_results(products: list[Product], output_dir: Path) -> list[str]:
    """
    Persist results to disk as both JSON and CSV.

    JSON  – great for programmatic consumption and preserves all data types.
    CSV   – easy to open in Excel / Google Sheets for quick inspection.
    """
    output_dir.mkdir(parents=True, exist_ok=True)
    output_files: list[str] = []

    # ── JSON ──────────────────────────────────────────────────────────────
    json_path = output_dir / "products.json"
    json_path.write_text(json.dumps(products, indent=2, ensure_ascii=False), encoding="utf-8")
    log(f"JSON saved  → {json_path}")
    output_files.append(str(json_path))

    # ── CSV ───────────────────────────────────────────────────────────────
    if products:
        col_names = list(products[0].keys())
        csv_path = output_dir / "products.csv"
        with csv_path.open("w", newline="", encoding="utf-8") as f:
            writer = csv.DictWriter(f, fieldnames=col_names, extrasaction="ignore")
            writer.writeheader()
            writer.writerows(products)
        log(f"CSV saved   → {csv_path}")
        output_files.append(str(csv_path))

    return output_files


# ─── Main ─────────────────────────────────────────────────────────────────────

async def scrape() -> ScrapeResult:
    log("Starting DigiKey scraper...")
    log(f"Target URL  : {CONFIG.url}")
    log(f"Max pages   : {CONFIG.max_pages}")
    log(f"Headless    : {CONFIG.headless}")
    log("─" * 50)

    all_products: list[Product] = []
    page_num = 0

    async with async_playwright() as playwright:
        browser = await launch_browser(playwright)
        context = await create_context(browser)
        page = await open_page(context)

        try:
            # ── Navigate ───────────────────────────────────────────────────────
            log("Navigating to page...")
            await page.goto(CONFIG.url, wait_until="domcontentloaded", timeout=60_000)
            await wait_for_table(page)

            # ── Pagination loop ────────────────────────────────────────────────
            while True:
                page_num += 1
                log(f"── Page {page_num} {'─' * (40 - len(str(page_num)))}")

                # Log total available products on first page
                if page_num == 1:
                    pagination = await get_pagination_info(page)
                    if pagination["totalProducts"] > 0:
                        log(
                            f"Total products available: "
                            f"{pagination['totalProducts']:,} across "
                            f"{pagination['totalPages']} pages"
                        )
                        max_label = "all" if math.isinf(CONFIG.max_pages) else int(CONFIG.max_pages)
                        log(f"Scraping up to {max_label} pages")

                rows = await extract_rows(page)
                log(
                    f"Rows extracted: {len(rows)}  |  "
                    f"Running total: {len(all_products) + len(rows)}"
                )
                all_products.extend(rows)

                if page_num >= CONFIG.max_pages:
                    log(f"Reached maxPages ({int(CONFIG.max_pages)}). Stopping.")
                    break

                if not await go_to_next_page(page, page_num):
                    break

            # ── Summary ────────────────────────────────────────────────────────
            log("─" * 50)
            log(f"Scraping complete. Total products: {len(all_products)}")

        except Exception as err:
            warn(f"Unhandled error: {err}")
            p = CONFIG.output_dir / "error-screenshot.png"
            CONFIG.output_dir.mkdir(parents=True, exist_ok=True)
            await page.screenshot(path=str(p), full_page=True)
            warn(f"Error screenshot → {p}")
            raise

        finally:
            await browser.close()

    # ── Persist results ────────────────────────────────────────────────
    output_files = save_results(all_products, CONFIG.output_dir)
    columns = list(all_products[0].keys()) if all_products else []

    result = ScrapeResult(
        total_products=len(all_products),
        pages_scraped=page_num,
        columns=columns,
        output_files=output_files,
    )

    log("─" * 50)
    log("Summary:")
    log(f"  Products  : {result.total_products}")
    log(f"  Pages     : {result.pages_scraped}")
    log(f"  Columns   : {len(result.columns)}")
    log(f"  Output    : {', '.join(result.output_files)}")

    return result


# Entry point
if __name__ == "__main__":
    try:
        asyncio.run(scrape())
    except Exception as err:
        print(f"[scraper] Fatal error: {err}", file=sys.stderr)
        sys.exit(1)
