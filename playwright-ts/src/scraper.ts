/**
 * DigiKey Product Table Scraper
 * ─────────────────────────────
 * Tech stack : TypeScript + Playwright
 * Target     : https://www.digikey.com/en/products/filter/accessories/783
 *
 * Key challenges solved here:
 *  1. React SPA  – the table is rendered by JavaScript, not baked into the raw
 *                  HTML.  We must wait for it to appear after the JS runs.
 *  2. Dynamic CSS – DigiKey uses TSS-generated class names like `tss-css-1xyz`
 *                  that change between deployments.  We rely on stable HTML
 *                  structure (table > thead > tr > th) and ARIA roles instead.
 *  3. Bot detection – Sift Science and GTM watch for headless-browser signals.
 *                  We spoof a real user-agent, disable the `webdriver` flag, and
 *                  add a small random delay between pages.
 *  4. Pagination  – After each page we look for the "Next" button, click it,
 *                  and wait for the new rows to load before extracting.
 */

import { chromium, Browser, BrowserContext, Page } from "playwright";
import fs from "fs";
import path from "path";
import dotenv from "dotenv";
import type { Product, ScraperConfig, ScrapeResult } from "./types";

// Load .env file before reading any process.env values
dotenv.config();

// ─── Configuration ────────────────────────────────────────────────────────────

const maxPagesEnv = parseInt(process.env.SCRAPER_MAX_PAGES ?? "5", 10);

const CONFIG: ScraperConfig = {
  url:
    process.env.SCRAPER_URL ??
    "https://www.digikey.com/en/products/filter/accessories/783",
  maxPages: isNaN(maxPagesEnv) || maxPagesEnv === 0 ? Infinity : maxPagesEnv,
  outputDir: path.resolve(process.env.SCRAPER_OUTPUT_DIR ?? "./output"),
  headless: process.env.SCRAPER_HEADLESS === "true",
  delayBetweenPages: parseInt(process.env.SCRAPER_DELAY_MS ?? "1500", 10),
};

const DEBUG = process.env.SCRAPER_DEBUG === "true";


function log(msg: string) {
  console.log(`[scraper] ${msg}`);
}
function warn(msg: string) {
  console.warn(`[scraper] ⚠  ${msg}`);
}
function debug(msg: string) {
  if (DEBUG) console.log(`[debug]   ${msg}`);
}


/**
 * Launch Chromium with settings that reduce bot-detection signals.
 *
 * What we do and why:
 *  --disable-blink-features=AutomationControlled  → removes the "Chrome is
 *    being controlled by automated software" banner and the corresponding DOM
 *    flag that Sift Science checks.
 *  headless: false (default)  → the full GUI is rendered; some fingerprinting
 *    scripts detect "headless" mode and block scrapers.
 */
async function launchBrowser(): Promise<Browser> {
  return chromium.launch({
    headless: CONFIG.headless,
    args: [
      "--no-sandbox",
      "--disable-setuid-sandbox",
      "--disable-blink-features=AutomationControlled",
      "--disable-infobars",
      "--window-size=1280,800",
    ],
  });
}

/**
 * Create a browser context that looks like a real macOS Chrome user.
 *
 * A "context" in Playwright is an isolated browser session – like an incognito
 * window.  Each context has its own cookies, localStorage, and cache.
 */
async function createContext(browser: Browser): Promise<BrowserContext> {
  return browser.newContext({
    userAgent:
      "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) " +
      "AppleWebKit/537.36 (KHTML, like Gecko) " +
      "Chrome/124.0.0.0 Safari/537.36",
    viewport: { width: 1280, height: 800 },
    locale: "en-US",
    timezoneId: "America/New_York",
    extraHTTPHeaders: {
      "Accept-Language": "en-US,en;q=0.9",
      Accept:
        "text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8",
    },
  });
}

/**
 * Open a new page and inject a script that removes the `navigator.webdriver`
 * property before ANY page JavaScript runs.
 *
 * Why: Playwright sets `navigator.webdriver = true` by default.
 * Anti-bot scripts read this property on page load to detect automation.
 * By overriding it to `undefined` before the page JS executes, we look like
 * a normal user.
 */
async function openPage(context: BrowserContext): Promise<Page> {
  const page = await context.newPage();

  // addInitScript runs BEFORE any page script – ideal for patching globals
  await page.addInitScript(() => {
    // Hide webdriver flag
    Object.defineProperty(navigator, "webdriver", {
      get: () => undefined,
    });

    // Spoof plugins array (headless Chrome has 0 plugins, real browsers have some)
    Object.defineProperty(navigator, "plugins", {
      get: () => [1, 2, 3],
    });

    // Spoof language list
    Object.defineProperty(navigator, "languages", {
      get: () => ["en-US", "en"],
    });
  });

  return page;
}

// ─── Waiting helpers ──────────────────────────────────────────────────────────

/**
 * Wait until the product table has visible rows.
 *
 * DigiKey's table is rendered by React after several XHR calls.  We:
 *  1. Wait for `networkidle` (no more than 2 in-flight requests for 500 ms).
 *  2. Wait for at least one <tr> inside <tbody> to appear in the DOM.
 *
 * If neither selector matches within the timeout we log a warning and take
 * a debug screenshot – useful when the site serves a CAPTCHA or login wall.
 */
async function waitForTable(page: Page): Promise<void> {
  log("Waiting for page to load...");

  try {
    // networkidle means the XHR requests for table data have finished
    await page.waitForLoadState("networkidle", { timeout: 30_000 });
  } catch {
    warn("networkidle timeout – page may still be loading.");
  }

  // Try common table selectors from most-specific to least-specific
  const selectors = [
    "table tbody tr[data-row-index]", // data attribute strategy
    "table tbody tr", // plain table rows
    '[role="rowgroup"] [role="row"]', // ARIA role strategy
    ".MuiTableBody-root .MuiTableRow-root", // MUI class strategy
  ];

  for (const sel of selectors) {
    try {
      await page.waitForSelector(sel, { timeout: 10_000 });
      debug(`Table found with selector: ${sel}`);
      return;
    } catch {
      debug(`Selector not found: ${sel}`);
    }
  }

  warn("Could not confirm table loaded – attempting extraction anyway.");
  if (DEBUG) {
    const screenshotPath = path.join(CONFIG.outputDir, "debug-load.png");
    fs.mkdirSync(CONFIG.outputDir, { recursive: true });
    await page.screenshot({ path: screenshotPath, fullPage: true });
    debug(`Debug screenshot saved to ${screenshotPath}`);
  }
}

// ─── Data extraction ──────────────────────────────────────────────────────────

/**
 * Extract column headers from the table.
 *
 * Strategy waterfall (we try the most reliable first):
 *  1. Standard <thead> → <tr> → <th> structure
 *  2. ARIA role="columnheader"
 *  3. MUI-specific class names
 *
 * We run this inside `page.evaluate()` which executes the function in the
 * browser's JavaScript context (not in Node.js).  This lets us access `document`.
 */
async function extractHeaders(page: Page): Promise<string[]> {
  const headers = await page.evaluate((): string[] => {
    // Strategy 1 – standard semantic HTML
    const thElements = document.querySelectorAll("table thead th");
    if (thElements.length > 0) {
      return Array.from(thElements).map((th) => th.textContent?.trim() ?? "");
    }

    // Strategy 2 – ARIA roles (used by many accessibility-compliant React tables)
    const ariaHeaders = document.querySelectorAll('[role="columnheader"]');
    if (ariaHeaders.length > 0) {
      return Array.from(ariaHeaders).map((h) => h.textContent?.trim() ?? "");
    }

    // Strategy 3 – MUI table class names
    const muiHeaders = document.querySelectorAll(".MuiTableCell-head");
    if (muiHeaders.length > 0) {
      return Array.from(muiHeaders).map((h) => h.textContent?.trim() ?? "");
    }

    return [];
  });

  // Remove empty/whitespace-only headers and deduplicate column names
  const cleaned = headers.map((h, i) => h || `Column_${i + 1}`);
  debug(`Raw headers: ${JSON.stringify(cleaned)}`);
  return cleaned;
}

/**
 * Extract all product rows from the currently visible table page.
 *
 * DigiKey diagnostics revealed that every <td> carries a stable `data-atag`
 * attribute that identifies the column type (e.g. "tr-unitPrice").
 * The checkbox cell (data-atag="tr-compareParts") also holds all key product
 * fields as data-* attributes on its inner <span> — this is the cleanest
 * extraction source because it's already structured (no newline-concatenated text).
 *
 * Field map:
 *  tr-compareParts  <span>  → data-mfg-number, data-product-number,
 *                              data-desc, data-mfg-name, data-price,
 *                              data-packaging, data-img, data-id
 *  tr-product       <a data-testid="data-table-product-number"> → product URL
 *  tr-qtyAvailable  <strong> → quantity number; secondary div → stock status
 *  tr-unitPrice     <strong> → unit price; data-testid="CellLabel" → packaging label
 *  all others       innerText (plain text is fine)
 */
async function extractRows(page: Page): Promise<Product[]> {
  return page.evaluate((): Product[] => {
    const products: Product[] = [];
    const rows = Array.from(document.querySelectorAll("table tbody tr"));

    for (const row of rows) {
      const cells = Array.from(row.querySelectorAll("td"));
      if (cells.length === 0) continue;

      const product: Product = {};

      for (const cell of cells) {
        const atag = cell.querySelector("[data-atag]")?.getAttribute("data-atag")
          ?? cell.getAttribute("data-atag")
          ?? "";

        // ── Checkbox cell: richest source of clean product metadata ─────
        if (atag === "tr-compareParts") {
          const span = cell.querySelector("span[data-mfg-number]");
          if (span) {
            product["DigiKey Part #"]  = span.getAttribute("data-product-number") ?? "";
            product["Mfr Part #"]      = span.getAttribute("data-mfg-number")     ?? "";
            product["Description"]     = span.getAttribute("data-desc")            ?? "";
            product["Manufacturer"]    = span.getAttribute("data-mfg-name")        ?? "";
            product["Unit Price (USD)"]= span.getAttribute("data-price")           ?? "";
            product["Packaging"]       = span.getAttribute("data-packaging")       ?? "";
            const img = span.getAttribute("data-img") ?? "";
            product["Image URL"]       = img ? "https:" + img : "";
          }
          continue;
        }

        // ── Product cell: grab the product detail page URL ───────────────
        if (atag === "tr-product") {
          const a = cell.querySelector('a[data-testid="data-table-product-number"]');
          product["Product URL"] = a?.getAttribute("href")
            ? "https://www.digikey.com" + a.getAttribute("href")
            : (a as HTMLAnchorElement | null)?.href ?? "";
          continue;
        }

        // ── Quantity Available: split number and stock status ────────────
        if (atag === "tr-qtyAvailable") {
          const qty    = cell.querySelector("strong")?.textContent?.trim() ?? "";
          const status = cell.querySelector(".tss-css-8e8qox-infoListDataSecondary")
            ?.textContent?.trim()
            ?? (cell as HTMLElement).innerText?.split("\n")[1]?.trim()
            ?? "";
          product["Quantity Available"] = qty;
          product["Stock Status"]       = status;
          continue;
        }

        // ── Unit Price: extract price and qty-break label ────────────────
        if (atag === "tr-unitPrice") {
          // <strong> holds the dollar amount; the surrounding text has "1 :"
          const priceEl  = cell.querySelector('[data-testid="qty-price"]');
          const strong   = priceEl?.querySelector("strong");
          const fullText = (priceEl as HTMLElement | null)?.innerText?.trim() ?? "";
          // e.g. "1 : $0.75000" → split on ":"
          const parts    = fullText.split(":");
          product["Min Qty"]        = parts[0]?.trim() ?? "1";
          product["Price (USD)"]    = strong?.textContent?.trim() ?? parts[1]?.trim() ?? "";
          continue;
        }

        // ── All remaining cells: use data-atag as a readable key ─────────
        const label = atag
          .replace(/^tr-/, "")                    // strip "tr-" prefix
          .replace(/^CLS \d+$/, "")               // drop generic "CLS 123"
          || null;

        if (!label) continue;                      // skip un-labelled cells

        // Convert camelCase / concatenated keys to readable names
        const readableLabel: Record<string, string> = {
          tariff:        "Tariff Status",
          series:        "Series",
          packaging:     "Package",                // already captured above, but fine
          productstatus: "Product Status",
        };

        const colName = readableLabel[label.toLowerCase()] ?? label;
        product[colName] = (cell as HTMLElement).innerText?.trim() ?? "";
      }

      // Only keep rows that have at least a part number
      if (product["Mfr Part #"] || product["DigiKey Part #"]) {
        products.push(product);
      }
    }

    return products;
  });
}

// ─── Pagination ───────────────────────────────────────────────────────────────

/**
 * Read "Showing X - Y of Z" info from DigiKey's pagination bar.
 *
 * DigiKey renders this as a plain text node near the pagination buttons.
 * We walk every leaf text node in the document and match the pattern.
 */
async function getPaginationInfo(
  page: Page,
): Promise<{ showing: string; totalProducts: number; totalPages: number }> {
  return page.evaluate(() => {
    // Walk all leaf text nodes looking for "Showing 1 - 25 of 1,575"
    const walker = document.createTreeWalker(
      document.body,
      NodeFilter.SHOW_TEXT,
    );
    let node: Node | null;
    while ((node = walker.nextNode())) {
      const text = node.textContent?.trim() ?? "";
      // Match: "Showing 1 - 25 of 1,575" or "1-25 of 1575"
      const m = text.match(/showing\s+([\d,]+)\s*[–-]\s*([\d,]+)\s+of\s+([\d,]+)/i)
        ?? text.match(/([\d,]+)\s*[–-]\s*([\d,]+)\s+of\s+([\d,]+)/i);
      if (m) {
        const total = parseInt(m[3].replace(/,/g, ""), 10);
        // DigiKey shows 25 rows per page by default
        const rowsPerPage = parseInt(m[2].replace(/,/g, ""), 10)
          - parseInt(m[1].replace(/,/g, ""), 10) + 1;
        return {
          showing:       text,
          totalProducts: total,
          totalPages:    Math.ceil(total / rowsPerPage),
        };
      }
    }
    return { showing: "unknown", totalProducts: 0, totalPages: 0 };
  });
}

/**
 * Click the "Next Page" button and wait for new rows to load.
 *
 * Key insight from diagnostics:
 *  DigiKey uses data-testid="btn-next-page" on the Next button (confirmed).
 *  The page uses client-side routing, so the URL does NOT change between pages.
 *  We detect a successful navigation by capturing the first product's part
 *  number before clicking, then waiting until it changes.
 *
 * Returns true if we successfully moved to the next page, false if we're done.
 */
async function goToNextPage(page: Page, currentPageNum: number): Promise<boolean> {
  // ── Check the Next button exists and is enabled ──────────────────────────
  // data-testid="btn-next-page" confirmed by live page inspection
  const btn = await page.$('[data-testid="btn-next-page"]');

  if (!btn) {
    debug("btn-next-page not found in DOM – last page reached.");
    return false;
  }

  const isDisabled =
    (await btn.getAttribute("disabled")) !== null ||
    (await btn.getAttribute("aria-disabled")) === "true";

  if (isDisabled) {
    log("Next page button is disabled – reached last page.");
    return false;
  }

  // ── Snapshot the first product's unique ID before clicking ─────────────
  // DigiKey's product link carries data-product-id which is unique per product.
  // When we move to the next page the first product changes, so this ID changes.
  // This is more reliable than comparing text because the first <td> is often
  // a checkbox/image cell with empty text content.
  const firstProductIdBefore = await page.evaluate((): string => {
    const link = document.querySelector(
      "table tbody tr:first-child a[data-product-id]"
    );
    return link?.getAttribute("data-product-id") ?? "";
  });

  debug(`First product-id before click: ${firstProductIdBefore}`);
  debug(`Clicking btn-next-page (currently on page ${currentPageNum})`);
  await btn.click();

  // ── Wait for the table to re-render with new rows ─────────────────────────
  // Strategy 1: wait until the first product-id is different (most reliable)
  if (firstProductIdBefore) {
    try {
      await page.waitForFunction(
        (prevId: string) => {
          const link = document.querySelector(
            "table tbody tr:first-child a[data-product-id]"
          );
          const newId = link?.getAttribute("data-product-id") ?? "";
          return newId !== "" && newId !== prevId;
        },
        firstProductIdBefore,
        { timeout: 20_000 },
      );
      debug("Confirmed: product list changed (new data-product-id on first row).");
    } catch {
      warn("Product IDs did not change after clicking Next – may be on last page.");
      return false;
    }
  } else {
    // Fallback: just wait for networkidle if we couldn't get a product ID
    debug("No product-id found to compare – falling back to networkidle wait.");
    await page.waitForLoadState("networkidle", { timeout: 15_000 }).catch(() => {});
    await page.waitForTimeout(1000);
  }

  // ── Extra wait for any lazy-loaded images / prices ────────────────────────
  await page.waitForLoadState("networkidle", { timeout: 10_000 }).catch(() => {});
  await page.waitForTimeout(CONFIG.delayBetweenPages);

  return true;
}

// ─── Output helpers ───────────────────────────────────────────────────────────

/**
 * Persist results to disk as both JSON and CSV.
 *
 * JSON  – great for programmatic consumption and preserves all data types.
 * CSV   – easy to open in Excel / Google Sheets for quick inspection.
 */
function saveResults(products: Product[], outputDir: string): string[] {
  fs.mkdirSync(outputDir, { recursive: true });

  const outputFiles: string[] = [];

  // ── JSON ──────────────────────────────────────────────────────────────
  const jsonPath = path.join(outputDir, "products.json");
  fs.writeFileSync(jsonPath, JSON.stringify(products, null, 2), "utf8");
  log(`JSON saved  → ${jsonPath}`);
  outputFiles.push(jsonPath);

  // ── CSV ───────────────────────────────────────────────────────────────
  if (products.length > 0) {
    const colNames = Object.keys(products[0]);

    const escapeCell = (val: string) => `"${(val ?? "").replace(/"/g, '""')}"`;

    const csvLines = [
      colNames.map(escapeCell).join(","),
      ...products.map((p) =>
        colNames.map((c) => escapeCell(p[c] ?? "")).join(","),
      ),
    ];

    const csvPath = path.join(outputDir, "products.csv");
    fs.writeFileSync(csvPath, csvLines.join("\n"), "utf8");
    log(`CSV saved   → ${csvPath}`);
    outputFiles.push(csvPath);
  }

  return outputFiles;
}

// ─── Main ─────────────────────────────────────────────────────────────────────

async function scrape(): Promise<ScrapeResult> {
  log("Starting DigiKey scraper...");
  log(`Target URL  : ${CONFIG.url}`);
  log(`Max pages   : ${CONFIG.maxPages}`);
  log(`Headless    : ${CONFIG.headless}`);
  log("─".repeat(50));

  const browser = await launchBrowser();
  const context = await createContext(browser);
  const page = await openPage(context);

  const allProducts: Product[] = [];
  let pageNum = 0;

  try {
    // ── Navigate ───────────────────────────────────────────────────────
    log(`Navigating to page...`);
    await page.goto(CONFIG.url, {
      waitUntil: "domcontentloaded",
      timeout: 60_000,
    });

    await waitForTable(page);

    // ── Pagination loop ────────────────────────────────────────────────
    do {
      pageNum++;
      log(`── Page ${pageNum} ${"─".repeat(40 - String(pageNum).length)}`);

      // Log total available products on first page
      if (pageNum === 1) {
        const pagination = await getPaginationInfo(page);
        if (pagination.totalProducts > 0) {
          log(`Total products available: ${pagination.totalProducts.toLocaleString()} across ${pagination.totalPages} pages`);
          log(`Scraping up to ${CONFIG.maxPages === Infinity ? "all" : CONFIG.maxPages} pages`);
        }
      }

      const rows = await extractRows(page);
      log(`Rows extracted: ${rows.length}  |  Running total: ${allProducts.length + rows.length}`);
      allProducts.push(...rows);

      if (pageNum >= CONFIG.maxPages) {
        log(`Reached maxPages (${CONFIG.maxPages}). Stopping.`);
        break;
      }
    } while (await goToNextPage(page, pageNum));

    // ── Summary ────────────────────────────────────────────────────────
    log("─".repeat(50));
    log(`Scraping complete. Total products: ${allProducts.length}`);
  } catch (err) {
    warn(`Unhandled error: ${(err as Error).message}`);
    const p = path.join(CONFIG.outputDir, "error-screenshot.png");
    fs.mkdirSync(CONFIG.outputDir, { recursive: true });
    await page.screenshot({ path: p, fullPage: true });
    warn(`Error screenshot → ${p}`);
    throw err;
  } finally {
    await browser.close();
  }

  // ── Persist results ────────────────────────────────────────────────
  const outputFiles = saveResults(allProducts, CONFIG.outputDir);

  const columns = allProducts.length > 0 ? Object.keys(allProducts[0]) : [];

  const result: ScrapeResult = {
    totalProducts: allProducts.length,
    pagesScraped: pageNum,
    columns,
    outputFiles,
  };

  log("─".repeat(50));
  log(`Summary:`);
  log(`  Products  : ${result.totalProducts}`);
  log(`  Pages     : ${result.pagesScraped}`);
  log(`  Columns   : ${result.columns.length}`);
  log(`  Output    : ${result.outputFiles.join(", ")}`);

  return result;
}

// Entry point
scrape().catch((err) => {
  console.error("[scraper] Fatal error:", err);
  process.exit(1);
});
