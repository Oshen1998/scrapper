"""
Avnet DRAM product scraper — with sign-in support.

Flow
----
1. WAF warm-up on the homepage.
2. Sign in with the Avnet account (email + password).
3. Navigate to the DRAM product listing.
4. Poll until product rows are rendered, then extract all records.
5. Export to JSON and CSV.

Run:
    cd claude-scraper
    python scrape_avnet.py
"""
import asyncio
import json
import sys

sys.path.insert(0, "src")

from playwright.async_api import async_playwright, Page
from exporter import export_data

# ── Credentials ──────────────────────────────────────────────────────────────
_EMAIL    = "oshend@vyrian.com"
_PASSWORD = "OshenDikkumbura98"

# ── URLs ─────────────────────────────────────────────────────────────────────
_BASE_URL  = "https://www.avnet.com/americas/"
_LOGIN_URL = "https://www.avnet.com/wps/portal/abr/OMLoginRegistration/"
_DRAM_URL  = (
    "https://www.avnet.com/americas/products/c/memory/drams/"
    "?go=eyJDYXRlZ29yaWVzIjp7InMiOlt7InZhbHVlIjoiRFJBTXMiLCJoaWRkZW5fcGF5bG9h"
    "ZCI6eyJMZXZlbCI6Mn19XSwibWFpbl9sYWJlbCI6IkNhdGVnb3J5In19"
    "&page=1&limit=20&orderby=&orderbydirection=asc"
)

# ── Technical-spec column map (idx → field name) ──────────────────────────────
_SPEC_COLUMNS = {
    5:  "operating_temp_min",
    6:  "mounting",
    7:  "operating_temp_max",
    8:  "lead_finish",
    9:  "msl_level",
    10: "data_bus_width",
    11: "bits_per_word",
    12: "num_io_lines",
    13: "ic_mounting",
    14: "clock_frequency_max",
    15: "max_processing_temp",
    16: "screening_level",
    17: "address_bus_width",
    18: "operating_temperature",
    19: "num_banks",
    20: "supply_voltage_nom",
    21: "memory_density",
    22: "num_pins",
    23: "supplier_package",
    24: "density",
    25: "type",
    26: "ic_case_package",
    27: "maximum_clock_rate",
    28: "operating_supply_voltage",
    29: "pin_count",
    30: "dram_type",
    31: "organization",
    32: "max_random_access_time",
    33: "product_dimensions",
    34: "package",
    35: "max_operating_current",
    36: "memory_configuration",
    37: "packaging",
    38: "product_range",
    39: "sub_category",
    40: "rad_hard",
    41: "product_family",
}

# ── DOM extraction script ─────────────────────────────────────────────────────
_EXTRACT_JS = """
() => {
    const rows = [...document.querySelectorAll("tbody tr")];
    const specCols = {
        5:"operating_temp_min", 6:"mounting", 7:"operating_temp_max",
        8:"lead_finish", 9:"msl_level", 10:"data_bus_width",
        11:"bits_per_word", 12:"num_io_lines", 13:"ic_mounting",
        14:"clock_frequency_max", 15:"max_processing_temp",
        16:"screening_level", 17:"address_bus_width",
        18:"operating_temperature", 19:"num_banks",
        20:"supply_voltage_nom", 21:"memory_density", 22:"num_pins",
        23:"supplier_package", 24:"density", 25:"type",
        26:"ic_case_package", 27:"maximum_clock_rate",
        28:"operating_supply_voltage", 29:"pin_count", 30:"dram_type",
        31:"organization", 32:"max_random_access_time",
        33:"product_dimensions", 34:"package",
        35:"max_operating_current", 36:"memory_configuration",
        37:"packaging", 38:"product_range", 39:"sub_category",
        40:"rad_hard", 41:"product_family"
    };

    return rows.map(row => {
        const tds  = [...row.querySelectorAll("td")];
        const cell = idx => (tds[idx] ? tds[idx].innerText.trim() : "");

        // ── Product cell (idx 0) ──────────────────────────────────────────
        const prodText  = cell(0);
        const prodLines = prodText.split("\\n").map(s => s.trim()).filter(Boolean);

        const avnetPfx  = "Avnet Manufacturer Part #:";
        const avnetLine = prodLines.find(l => l.startsWith(avnetPfx)) || "";
        const avnetPart = avnetLine.replace(avnetPfx, "").trim();

        const skipWords = ["Add", "Avnet", "DRAM", "Datasheet", "Lifecycle", "Compare"];

        const partLine = prodLines.find(
            l => l.length < 60 && l !== "--" && !skipWords.some(w => l.startsWith(w))
        ) || "";

        const partIdx = prodLines.indexOf(partLine);
        const mfrLine = prodLines.find(
            (l, i) => i > partIdx && l.length < 60 &&
                      !skipWords.some(w => l.startsWith(w)) &&
                      l !== partLine
        ) || "";

        const descLine = prodLines.find(l => l.startsWith("DRAM")) ||
                         prodLines.filter(l => !skipWords.some(w => l.startsWith(w)) &&
                                               l !== partLine && l !== mfrLine)
                                  .sort((a, b) => b.length - a.length)[0] || "";

        // ── Price cell (idx 1) ─────────────────────────────────────────────
        const priceText  = cell(1);
        const priceLines = priceText.split("\\n").map(s => s.trim()).filter(Boolean);
        const stopWords  = ["USD", "Min:", "ADD", "Need"];
        const tierLines  = [];
        for (const l of priceLines) {
            if (stopWords.some(w => l.startsWith(w))) break;
            if (l === "CLICK TO QUOTE") { tierLines.push(l); break; }
            tierLines.push(l);
        }

        let unitPrice = "";
        const tierPairs = [];
        for (let i = 0; i < tierLines.length - 1; i += 2) {
            const qty = tierLines[i];
            const prc = tierLines[i + 1];
            if (prc && prc.startsWith("$")) {
                const pair = qty + ": " + prc;
                if (!unitPrice) unitPrice = pair;
                tierPairs.push(pair);
            } else if (qty === "CLICK TO QUOTE") {
                if (!unitPrice) unitPrice = qty;
                tierPairs.push(qty);
                break;
            } else {
                tierPairs.push(qty);
                break;
            }
        }
        const minMultLine = priceLines.find(l => l.startsWith("Min:")) || "";

        // ── Availability cell (idx 2) ──────────────────────────────────────
        const availText  = cell(2);
        const availLines = availText.split("\\n").map(s => s.trim()).filter(Boolean);

        let statusLine, stockQty;
        if (availLines[0] && (availLines[0].startsWith("In Stock") ||
                              availLines[0].startsWith("Out of Stock"))) {
            statusLine = availLines[0];
            stockQty   = availLines[1] || "";
        } else if (availLines.some(l => l.includes("Partner Stock"))) {
            statusLine = "Partner Stock";
            stockQty   = availLines[0] || "0";
        } else {
            statusLine = availLines[0] || "";
            stockQty   = availLines[1] || "";
        }
        const shipsLine = availLines.find(l => l.startsWith("Ships")) || "";
        const leadLine  = availLines.find(l => l.startsWith("Factory Lead Time")) || "";
        const leadTime  = leadLine.replace("Factory Lead Time:", "").trim();

        // ── Spec columns ───────────────────────────────────────────────────
        const infoText = cell(4);
        const specs    = {};
        for (const k in specCols) {
            const val = cell(parseInt(k, 10));
            if (val) specs[specCols[k]] = val;
        }

        return Object.assign({
            part_number:       partLine,
            avnet_part_number: avnetPart || partLine,
            manufacturer:      mfrLine || cell(3),
            description:       descLine,
            unit_price:        unitPrice,
            price_tiers:       tierPairs.join(" | "),
            min_mult:          minMultLine,
            stock_status:      statusLine,
            stock_quantity:    stockQty,
            ships_info:        shipsLine,
            lead_time:         leadTime,
            information:       infoText,
        }, specs);
    });
}
"""


# ─────────────────────────────────────────────────────────────────────────────
# Login
# ─────────────────────────────────────────────────────────────────────────────

async def _try_header_signin(page: Page) -> bool:
    """
    Attempt to click the 'Sign In' link that lives in the site header.
    Returns True if the login modal / page appeared, False otherwise.
    """
    selectors = [
        "a[href*='LoginRegistration']",
        "a[href*='login']",
        "a:has-text('Sign In')",
        "button:has-text('Sign In')",
        "[data-testid='sign-in']",
        ".sign-in-link",
        "#signInLink",
    ]
    for sel in selectors:
        try:
            el = page.locator(sel).first
            if await el.is_visible(timeout=2_000):
                await el.click()
                return True
        except Exception:
            pass
    return False


async def login(page: Page) -> bool:
    """
    Sign in to Avnet with the configured credentials.

    Strategy
    --------
    1. Navigate directly to the Avnet login page.
    2. Fill in the email field and submit.
    3. Fill in the password field and submit.
    4. Confirm successful login by waiting for a post-auth indicator.

    Returns True on success, False on failure.
    """
    print("[login] Navigating to sign-in page…")
    await page.goto(_LOGIN_URL, wait_until="domcontentloaded", timeout=30_000)
    await asyncio.sleep(2)

    # ── If the direct login URL redirected somewhere without a form,
    #    try clicking the Sign In button in the header instead ──────────────
    email_selectors = [
        "input[type='email']",
        "input[name='email']",
        "input[id*='email']",
        "input[placeholder*='email' i]",
        "input[placeholder*='Email' i]",
        "#okta-signin-username",
        "input[name='identifier']",
        "input[autocomplete='username']",
        "input[type='text']",
    ]

    email_field = None
    for sel in email_selectors:
        try:
            loc = page.locator(sel).first
            if await loc.is_visible(timeout=2_000):
                email_field = loc
                break
        except Exception:
            pass

    # If no email field found yet, try clicking the Sign In header link
    if email_field is None:
        print("[login] No form found at direct URL — trying header Sign In link…")
        await page.goto(_BASE_URL, wait_until="domcontentloaded", timeout=30_000)
        await asyncio.sleep(2)
        clicked = await _try_header_signin(page)
        if clicked:
            await asyncio.sleep(2)
            for sel in email_selectors:
                try:
                    loc = page.locator(sel).first
                    if await loc.is_visible(timeout=2_000):
                        email_field = loc
                        break
                except Exception:
                    pass

    if email_field is None:
        print("[login] ERROR: Could not locate the email input field.")
        return False

    # ── Fill email ─────────────────────────────────────────────────────────
    print(f"[login] Entering email: {_EMAIL}")
    await email_field.fill(_EMAIL)
    await asyncio.sleep(0.5)

    # Submit email (some flows split email and password onto separate screens)
    continue_selectors = [
        "button[type='submit']",
        "input[type='submit']",
        "button:has-text('Continue')",
        "button:has-text('Next')",
        "button:has-text('Sign In')",
        "#okta-signin-submit",
        "[data-se='o-form-input-submit']",
    ]
    submitted_email = False
    for sel in continue_selectors:
        try:
            btn = page.locator(sel).first
            if await btn.is_visible(timeout=1_500):
                await btn.click()
                submitted_email = True
                break
        except Exception:
            pass

    if not submitted_email:
        # Fallback: press Enter on the email field
        await email_field.press("Enter")

    await asyncio.sleep(2)

    # ── Fill password ──────────────────────────────────────────────────────
    password_selectors = [
        "input[type='password']",
        "input[name='password']",
        "input[id*='password']",
        "input[placeholder*='password' i]",
        "#okta-signin-password",
        "input[autocomplete='current-password']",
    ]
    password_field = None
    for sel in password_selectors:
        try:
            loc = page.locator(sel).first
            if await loc.is_visible(timeout=3_000):
                password_field = loc
                break
        except Exception:
            pass

    if password_field is None:
        print("[login] ERROR: Could not locate the password input field.")
        return False

    print("[login] Entering password…")
    await password_field.fill(_PASSWORD)
    await asyncio.sleep(0.5)

    # Submit the form
    submitted_pw = False
    for sel in continue_selectors:
        try:
            btn = page.locator(sel).first
            if await btn.is_visible(timeout=1_500):
                await btn.click()
                submitted_pw = True
                break
        except Exception:
            pass
    if not submitted_pw:
        await password_field.press("Enter")

    # ── Wait for post-login redirect ───────────────────────────────────────
    print("[login] Waiting for post-login redirect…")
    try:
        await page.wait_for_url(
            lambda url: (
                "LoginRegistration" not in url
                and "okta" not in url
                and "login" not in url.lower()
            ),
            timeout=20_000,
        )
    except Exception:
        pass  # Timeout is OK — we'll check the URL next

    await asyncio.sleep(2)

    current = page.url
    print(f"[login] Current URL after login: {current}")

    # Confirm we are NOT on a login/error page
    fail_indicators = ["LoginRegistration", "okta", "login", "signin", "error"]
    if any(ind in current.lower() for ind in fail_indicators):
        # Double-check: maybe there's a "logged-in" indicator in the DOM
        logged_in_selectors = [
            "[aria-label='My Account']",
            ".user-account",
            "a[href*='MyAccount']",
            "a[href*='logout']",
            "button:has-text('Sign Out')",
            "a:has-text('Sign Out')",
            "a:has-text('My Account')",
            ".account-icon",
        ]
        for sel in logged_in_selectors:
            try:
                if await page.locator(sel).first.is_visible(timeout=2_000):
                    print(f"[login] Logged-in indicator found ({sel}) — treating as success.")
                    return True
            except Exception:
                pass
        print("[login] Login appears to have failed.")
        return False

    print("[login] Sign-in successful.")
    return True


# ─────────────────────────────────────────────────────────────────────────────
# Scrape
# ─────────────────────────────────────────────────────────────────────────────

async def scrape() -> list[dict]:
    async with async_playwright() as pw:
        browser = await pw.chromium.launch(
            headless=False,
            args=[
                "--disable-blink-features=AutomationControlled",
                "--no-sandbox",
                "--disable-dev-shm-usage",
            ],
        )
        ctx = await browser.new_context(
            user_agent=(
                "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/124.0.0.0 Safari/537.36"
            ),
            viewport={"width": 1440, "height": 900},
            locale="en-US",
            timezone_id="America/New_York",
            extra_http_headers={
                "Accept-Language": "en-US,en;q=0.9",
            },
        )
        await ctx.add_init_script(
            'Object.defineProperty(navigator, "webdriver", {get: () => undefined});'
            'window.chrome = { runtime: {} };'
        )
        page = await ctx.new_page()

        # ── 1. WAF warm-up ────────────────────────────────────────────────
        print("[1/4] WAF warm-up (homepage)…")
        await page.goto(_BASE_URL, wait_until="domcontentloaded", timeout=30_000)
        await asyncio.sleep(2)
        await page.mouse.move(400, 300)
        await asyncio.sleep(0.5)
        await page.mouse.wheel(0, 300)
        await asyncio.sleep(0.5)
        await page.mouse.wheel(0, -150)
        await asyncio.sleep(2)

        # ── 2. Sign in ────────────────────────────────────────────────────
        print("[2/4] Signing in to Avnet…")
        ok = await login(page)
        if not ok:
            print("Sign-in failed — aborting. Check credentials or complete CAPTCHA manually.")
            input("Press Enter to close the browser…")
            await browser.close()
            return []

        # ── 3. Navigate to DRAM product page ─────────────────────────────
        print("[3/4] Loading DRAM product page…")
        await page.goto(_DRAM_URL, wait_until="domcontentloaded", timeout=45_000)

        # ── 4. Wait for product rows ──────────────────────────────────────
        print("[4/4] Waiting for table rows to render via AJAX…")
        rows_count = 0
        for tick in range(30):
            rows_count = await page.locator("tbody tr").count()
            print(f"  t={tick+1:02d}s  rows={rows_count}")
            if rows_count >= 5:
                break
            await asyncio.sleep(1)

        if rows_count == 0:
            print("Table never loaded — page may require additional interaction.")
            input("Press Enter to close the browser…")
            await browser.close()
            return []

        # Extra pause for price / stock AJAX calls to settle
        await asyncio.sleep(4)
        rows_count = await page.locator("tbody tr").count()
        print(f"Final row count: {rows_count}")

        # ── 5. Extract from rendered DOM ──────────────────────────────────
        records = await page.evaluate(_EXTRACT_JS)
        await browser.close()
        return records


# ─────────────────────────────────────────────────────────────────────────────
# Entry point
# ─────────────────────────────────────────────────────────────────────────────

def main() -> None:
    print("=" * 60)
    print("Avnet DRAM product scraper  (authenticated)")
    print("=" * 60)

    records = asyncio.run(scrape())

    if not records:
        print("No records extracted.")
        return

    print(f"\nExtracted {len(records)} records\n")
    print("Sample record:")
    print(json.dumps(records[0], indent=2))

    p_json = export_data(records, "json")
    p_csv  = export_data(records, "csv")
    print(f"\nJSON → {p_json}")
    print(f"CSV  → {p_csv}")


if __name__ == "__main__":
    main()
