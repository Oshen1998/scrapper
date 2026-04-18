"""
main.py — Entry point. Orchestrates the full scraping session.
"""
import asyncio
import sys

from dotenv import load_dotenv
from rich.console import Console
from rich.panel import Panel
from rich.rule import Rule

load_dotenv()

from auth import connect_claude
from browser import close_browser, create_browser
from exporter import export_data
from prompts import ask_extraction_prompt, ask_output_format, ask_pagination, ask_url
from scraper import scrape_pages

console = Console()


# ---------------------------------------------------------------------------
# Async scraping runner (keeps playwright in its own async context)
# ---------------------------------------------------------------------------

async def _run(runner, url, extraction_prompt, pagination) -> list[dict]:
    playwright, browser, context = await create_browser()
    try:
        page = await context.new_page()
        return await scrape_pages(page, url, extraction_prompt, pagination, runner)
    finally:
        await close_browser(playwright, browser)


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main() -> None:
    console.print(
        Panel(
            "[bold cyan]Claude Web Scraper[/bold cyan]\n"
            "[dim]AI-powered web scraping — Claude + Playwright[/dim]\n"
            "[dim]Author — Oshen Dikkumbura[/dim]",
            border_style="cyan",
            padding=(1, 6),
        )
    )

    try:
        # ── Step 1: Authenticate with Claude ─────────────────────────────
        console.print(f"\n[bold blue]Step 1[/bold blue]  Connect to Claude")
        runner = connect_claude()

        # ── Step 2: Target URL ────────────────────────────────────────────
        console.print(f"\n[bold blue]Step 2[/bold blue]  Target page")
        url = ask_url()

        # ── Step 3: What to extract ───────────────────────────────────────
        console.print(f"\n[bold blue]Step 3[/bold blue]  Extraction instructions")
        extraction_prompt = ask_extraction_prompt()

        # ── Step 4: Output format ─────────────────────────────────────────
        console.print(f"\n[bold blue]Step 4[/bold blue]  Output format")
        output_format = ask_output_format()

        # ── Step 5: Pagination ────────────────────────────────────────────
        console.print(f"\n[bold blue]Step 5[/bold blue]  Pagination")
        pagination = ask_pagination()

        # ── Summary ───────────────────────────────────────────────────────
        console.print()
        console.print(Rule("[dim]Configuration[/dim]"))
        console.print(f"  [bold]URL[/bold]     {url}")
        console.print(
            f"  [bold]Extract[/bold] {extraction_prompt[:70]}"
            f"{'…' if len(extraction_prompt) > 70 else ''}"
        )
        console.print(f"  [bold]Format[/bold]  {output_format.upper()}")
        page_info = "all pages" if pagination["mode"] == "all" else f"{pagination['count']} page(s)"
        console.print(f"  [bold]Pages[/bold]   {page_info}")
        console.print(Rule())

        # ── Scrape ────────────────────────────────────────────────────────
        records = asyncio.run(_run(runner, url, extraction_prompt, pagination))

        if not records:
            console.print(
                "\n[yellow]No data extracted.[/yellow] "
                "The page may require a login, or try refining your extraction prompt."
            )
            return

        # ── Export ────────────────────────────────────────────────────────
        output_path = export_data(records, output_format)

        console.print(f"\n[bold green]Done![/bold green]")
        console.print(f"  Records saved : [bold]{len(records)}[/bold]")
        console.print(f"  Output file   : [cyan]{output_path}[/cyan]")

    except KeyboardInterrupt:
        console.print("\n[yellow]Interrupted — exiting.[/yellow]")
        sys.exit(0)


if __name__ == "__main__":
    main()
