"""
Diagnostic – dumps inner HTML of first 2 product rows so we can see
the exact sub-element structure inside each <td>.
"""

import asyncio
import json
import os
import sys
from pathlib import Path

from dotenv import load_dotenv
from playwright.async_api import async_playwright

load_dotenv()

OUTPUT = Path("./output/diag").resolve()
OUTPUT.mkdir(parents=True, exist_ok=True)


async def diagnose() -> None:
    async with async_playwright() as playwright:
        browser = await playwright.chromium.launch(
            headless=False,
            args=[
                "--disable-blink-features=AutomationControlled",
                "--window-size=1400,900",
            ],
        )
        ctx = await browser.new_context(
            user_agent=(
                "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/124.0.0.0 Safari/537.36"
            ),
            viewport={"width": 1400, "height": 900},
            locale="en-US",
        )
        page = await ctx.new_page()
        await page.add_init_script("""
            () => {
                Object.defineProperty(navigator, 'webdriver', { get: () => undefined });
            }
        """)

        url = os.getenv(
            "SCRAPER_URL",
            "https://www.digikey.com/en/products/filter/accessories/783",
        )
        await page.goto(url, wait_until="domcontentloaded", timeout=60_000)
        await page.wait_for_selector("table tbody tr", timeout=30_000)
        try:
            await page.wait_for_load_state("networkidle", timeout=20_000)
        except Exception:
            pass

        cell_html = await page.evaluate("""
            () => {
                const rows = Array.from(document.querySelectorAll('table tbody tr')).slice(0, 2);
                return rows.map((row, ri) => {
                    const cells = Array.from(row.querySelectorAll('td'));
                    return cells.map((td, ci) => ({
                        rowIndex:  ri,
                        cellIndex: ci,
                        innerText: td.innerText?.trim().slice(0, 200),
                        innerHTML: td.innerHTML.slice(0, 1500),
                    }));
                });
            }
        """)

        out_path = OUTPUT / "cell-structure.json"
        out_path.write_text(json.dumps(cell_html, indent=2, ensure_ascii=False), encoding="utf-8")
        print(f"Saved: {out_path}")

        # Print each cell for quick inspection
        for row in cell_html:
            if row:
                print(f"\n══════════════════ ROW {row[0]['rowIndex']} ═══════════════════════")
            for cell in row:
                print(f"\n  ── Cell {cell['cellIndex']} ──────────────────────────")
                print(f"  innerText: {cell['innerText']}")
                print(f"  innerHTML: {cell['innerHTML']}")

        await browser.close()


if __name__ == "__main__":
    try:
        asyncio.run(diagnose())
    except Exception as err:
        print(f"Error: {err}", file=sys.stderr)
        sys.exit(1)
