"""
prompts.py — All interactive terminal prompts shown to the user.
"""
import sys

import questionary
from rich.console import Console
from rich.rule import Rule

console = Console()

_URL_HINT = "e.g. https://www.digikey.com/en/products/filter/accessories/818"

_EXTRACTION_HINTS = (
    "  Hint examples:\n"
    "    • Extract: product name, part number, price, availability, manufacturer\n"
    "    • Get: article title, author, publish date, category, summary\n"
    "    • Collect: company name, email, phone number, address, website URL\n"
    "    • Scrape: job title, location, salary range, company, posted date"
)


def ask_url() -> str:
    """Ask the user for the target page URL."""
    console.print(Rule("[bold]Target URL[/bold]", style="cyan"))
    console.print(f"[dim]{_URL_HINT}[/dim]\n")

    url = questionary.text(
        "Enter the page URL to scrape:",
        validate=lambda v: (
            True
            if v.strip().startswith(("http://", "https://"))
            else "URL must start with http:// or https://"
        ),
    ).ask()

    if url is None:
        sys.exit(0)

    return url.strip()


def ask_extraction_prompt() -> str:
    """Ask what fields the user wants to extract."""
    console.print(Rule("[bold]Extraction Instructions[/bold]", style="cyan"))
    console.print(
        "Describe the data you want extracted from each item on the page.\n"
        + _EXTRACTION_HINTS
        + "\n"
    )

    prompt = questionary.text(
        "What do you want to extract?",
        validate=lambda v: (
            True if len(v.strip()) > 5 else "Please be more specific about what to extract"
        ),
    ).ask()

    if prompt is None:
        sys.exit(0)

    return prompt.strip()


def ask_output_format() -> str:
    """Ask the user which output format they want (default JSON)."""
    console.print(Rule("[bold]Output Format[/bold]", style="cyan"))

    choice = questionary.select(
        "Choose output format:",
        choices=[
            questionary.Choice("JSON  — structured data (default)", value="json"),
            questionary.Choice("CSV   — spreadsheet / Excel", value="csv"),
            questionary.Choice("PDF   — printable document", value="pdf"),
        ],
        default="json",
    ).ask()

    if choice is None:
        sys.exit(0)

    return choice


def ask_pagination() -> dict:
    """Ask how many pages to scrape when pagination exists."""
    console.print(Rule("[bold]Pagination[/bold]", style="cyan"))

    mode = questionary.select(
        "How many pages do you want to scrape?",
        choices=[
            questionary.Choice("All pages  — follow pagination until the end", value="all"),
            questionary.Choice("Specific number of pages", value="specific"),
        ],
    ).ask()

    if mode is None:
        sys.exit(0)

    if mode == "specific":
        raw = questionary.text(
            "Number of pages:",
            validate=lambda v: (
                True if v.isdigit() and int(v) > 0 else "Enter a positive whole number"
            ),
        ).ask()

        if raw is None:
            sys.exit(0)

        return {"mode": "specific", "count": int(raw)}

    return {"mode": "all", "count": None}
