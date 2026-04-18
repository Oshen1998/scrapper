"""
scraper.py — Page navigation and multi-page scraping orchestration.
"""
import asyncio

from claude_runner import ClaudeRunner
from playwright.async_api import Page
from rich.console import Console
from rich.progress import BarColumn, Progress, SpinnerColumn, TaskProgressColumn, TextColumn

from extractor import extract_data, find_next_page

console = Console()

# How long to wait (seconds) for JS-rendered content before giving up
_JS_WAIT_POLL_INTERVAL = 0.5
_JS_WAIT_MAX_SECONDS   = 12


async def _wait_for_content(page) -> None:
    """
    Wait until the page has meaningful body text (not just a bot-block page).

    Strategy:
      1. Poll every 0.5 s until document.body.innerText has > 500 chars of
         visible text — indicating real content has rendered.
      2. Cap at _JS_WAIT_MAX_SECONDS so we don't hang forever on broken pages.
      3. Always add a short fixed delay after the poll loop so AJAX calls that
         fire after DOM paint (price feeds, stock levels) have time to settle.
    """
    elapsed = 0.0
    while elapsed < _JS_WAIT_MAX_SECONDS:
        length = await page.evaluate(
            "() => (document.body ? document.body.innerText.trim().length : 0)"
        )
        if length > 500:
            break
        await asyncio.sleep(_JS_WAIT_POLL_INTERVAL)
        elapsed += _JS_WAIT_POLL_INTERVAL

    # Extra pause for deferred AJAX (prices, stock counts, etc.)
    await asyncio.sleep(3.0)


async def scrape_pages(
    page: Page,
    start_url: str,
    extraction_prompt: str,
    pagination: dict,
    runner: ClaudeRunner,
) -> list[dict]:
    """
    Navigate through paginated results and extract data from every page.

    Args:
        page:               Playwright Page object.
        start_url:          URL of the first page to scrape.
        extraction_prompt:  Natural-language description of what to extract.
        pagination:         Dict with keys 'mode' ('all' | 'specific') and 'count' (int | None).
        client:             Authenticated Anthropic client.

    Returns:
        Flat list of extracted record dicts across all scraped pages.
    """
    all_records: list[dict] = []
    current_url: str | None = start_url
    max_pages: int | None = pagination.get("count")
    pages_done = 0

    with Progress(
        SpinnerColumn(),
        TextColumn("[progress.description]{task.description}"),
        BarColumn(),
        TaskProgressColumn(),
        console=console,
        transient=False,
    ) as progress:
        task = progress.add_task("Scraping…", total=max_pages)

        while current_url:
            pages_done += 1
            progress.update(task, description=f"[cyan]Page {pages_done}[/cyan]  {current_url[:60]}")

            # Load the page
            try:
                await page.goto(current_url, wait_until="domcontentloaded", timeout=45_000)
                await _wait_for_content(page)
                html = await page.content()
            except Exception as exc:
                console.print(f"[red]  Failed to load page {pages_done}:[/red] {exc}")
                break

            # Extract structured data via Claude
            records = extract_data(runner, html, extraction_prompt)
            all_records.extend(records)
            progress.update(task, advance=1)
            console.print(
                f"  [dim]Page {pages_done}: {len(records)} items extracted "
                f"(running total: {len(all_records)})[/dim]"
            )

            # Stop if page limit reached
            if max_pages and pages_done >= max_pages:
                break

            # Find the next page
            next_url = find_next_page(runner, html, current_url)

            if not next_url or next_url == current_url:
                break

            current_url = next_url

    return all_records
