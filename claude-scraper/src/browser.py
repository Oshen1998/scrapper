"""
browser.py — Playwright browser lifecycle management.

Runs in VISIBLE (non-headless) mode by default because many modern sites
(Akamai, Cloudflare, etc.) detect and block headless Chromium. Visible mode
combined with stealth arguments and a realistic user-agent passes most
bot-detection checks without extra libraries.
"""
from playwright.async_api import async_playwright, Browser, BrowserContext, Playwright

_USER_AGENT = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/124.0.0.0 Safari/537.36"
)

# Chromium launch flags that remove automation fingerprints
_STEALTH_ARGS = [
    "--disable-blink-features=AutomationControlled",
    "--no-sandbox",
    "--disable-dev-shm-usage",
]

# Script injected before every page load to mask webdriver presence
_STEALTH_SCRIPT = """
    Object.defineProperty(navigator, 'webdriver', { get: () => undefined });
    window.chrome = { runtime: {} };
"""


async def create_browser() -> tuple[Playwright, Browser, BrowserContext]:
    """
    Launch a visible (non-headless) Chromium browser with stealth settings.
    Returns the playwright instance, browser, and a pre-configured context.
    """
    playwright = await async_playwright().start()

    browser = await playwright.chromium.launch(
        headless=False,          # Visible window bypasses most WAF/bot checks
        args=_STEALTH_ARGS,
    )

    context = await browser.new_context(
        user_agent=_USER_AGENT,
        viewport={"width": 1440, "height": 900},
        locale="en-US",
        timezone_id="America/New_York",
        extra_http_headers={
            "Accept-Language": "en-US,en;q=0.9",
            "Accept": (
                "text/html,application/xhtml+xml,application/xml;"
                "q=0.9,image/avif,image/webp,*/*;q=0.8"
            ),
        },
    )

    # Inject stealth script before every page navigation
    await context.add_init_script(_STEALTH_SCRIPT)

    return playwright, browser, context


async def close_browser(playwright: Playwright, browser: Browser) -> None:
    """Cleanly close the browser and stop Playwright."""
    await browser.close()
    await playwright.stop()
