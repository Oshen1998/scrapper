/**
 * Diagnostic – dumps inner HTML of first 2 product rows so we can see
 * the exact sub-element structure inside each <td>.
 */

import { chromium } from 'playwright';
import fs from 'fs';
import path from 'path';
import dotenv from 'dotenv';

dotenv.config();

const OUTPUT = path.resolve('./output/diag');
fs.mkdirSync(OUTPUT, { recursive: true });

async function diagnose() {
  const browser = await chromium.launch({
    headless: false,
    args: ['--disable-blink-features=AutomationControlled', '--window-size=1400,900'],
  });
  const ctx = await browser.newContext({
    userAgent: 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36',
    viewport: { width: 1400, height: 900 },
    locale: 'en-US',
  });
  const page = await ctx.newPage();
  await page.addInitScript(() => {
    Object.defineProperty(navigator, 'webdriver', { get: () => undefined });
  });

  await page.goto(process.env.SCRAPER_URL ?? 'https://www.digikey.com/en/products/filter/accessories/783', {
    waitUntil: 'domcontentloaded', timeout: 60_000,
  });
  await page.waitForSelector('table tbody tr', { timeout: 30_000 });
  await page.waitForLoadState('networkidle', { timeout: 20_000 }).catch(() => {});

  const cellHTML = await page.evaluate(() => {
    const rows = Array.from(document.querySelectorAll('table tbody tr')).slice(0, 2);
    return rows.map((row, ri) => {
      const cells = Array.from(row.querySelectorAll('td'));
      return cells.map((td, ci) => ({
        rowIndex: ri,
        cellIndex: ci,
        innerText: (td as HTMLElement).innerText?.trim().slice(0, 200),
        innerHTML: td.innerHTML.slice(0, 1500),
      }));
    });
  });

  const outPath = path.join(OUTPUT, 'cell-structure.json');
  fs.writeFileSync(outPath, JSON.stringify(cellHTML, null, 2), 'utf8');
  console.log('Saved:', outPath);

  // Print each cell
  for (const row of cellHTML) {
    console.log('\n══════════════════ ROW', row[0]?.rowIndex, '═══════════════════════');
    for (const cell of row) {
      console.log(`\n  ── Cell ${cell.cellIndex} ──────────────────────────`);
      console.log('  innerText:', cell.innerText);
      console.log('  innerHTML:', cell.innerHTML);
    }
  }

  await browser.close();
}

diagnose().catch(err => { console.error(err); process.exit(1); });
