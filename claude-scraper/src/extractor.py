"""
extractor.py — Claude-powered data extraction from raw HTML.
"""
import json
import re
from urllib.parse import urljoin

from bs4 import BeautifulSoup

from claude_runner import ClaudeRunner

# Maximum characters of cleaned page text sent to Claude per page.
_MAX_PAGE_TEXT = 60_000

# Next-page anchor text patterns tried before falling back to Claude.
_NEXT_LABELS = {"next", "next page", "›", "»", ">", "→", "next »", "next›"}


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _clean_html(html: str) -> str:
    """Strip boilerplate tags and return readable page text."""
    soup = BeautifulSoup(html, "html.parser")
    for tag in soup(["script", "style", "meta", "link", "noscript", "head", "svg"]):
        tag.decompose()
    lines = [ln for ln in soup.get_text("\n", strip=True).splitlines() if ln.strip()]
    return "\n".join(lines)[:_MAX_PAGE_TEXT]


def _parse_json_array(text: str) -> list[dict]:
    """Extract the first JSON array found in a Claude response."""
    match = re.search(r"\[.*\]", text, re.DOTALL)
    if not match:
        return []
    try:
        return json.loads(match.group())
    except json.JSONDecodeError:
        return []


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def extract_data(runner: ClaudeRunner, html: str, extraction_prompt: str) -> list[dict]:
    """Send cleaned page text to Claude and return a list of extracted records."""
    page_text = _clean_html(html)

    system = (
        "You are a web scraping assistant. Extract structured data from web page text.\n"
        "Return ONLY a valid JSON array of objects — one object per item/record.\n"
        "Use concise, consistent key names (snake_case).\n"
        "If nothing matches, return an empty array: []\n"
        "Do not include any explanation or markdown — just the JSON array."
    )
    prompt = (
        f"Extract the following from this page:\n{extraction_prompt}\n\n"
        f"--- PAGE CONTENT ---\n{page_text}\n--- END ---\n\n"
        "Return the JSON array now."
    )

    response = runner.complete(prompt, system=system)
    return _parse_json_array(response)


def find_next_page(runner: ClaudeRunner, html: str, current_url: str) -> str | None:
    """
    Return the URL of the next paginated page, or None if there is no next page.

    Strategy (cheapest-first):
      1. <link rel="next"> — standard HTML pagination hint
      2. Anchors whose visible text matches common "next" labels
      3. Anchors with aria-label or parent class containing "next"
      4. Ask Claude as a last resort
    """
    soup = BeautifulSoup(html, "html.parser")

    # Strategy 1: canonical link rel="next"
    link_tag = soup.find("link", rel="next")
    if link_tag and link_tag.get("href"):
        return urljoin(current_url, link_tag["href"])

    # Strategy 2: anchor text — exact match OR starts with "next"
    for anchor in soup.find_all("a", href=True):
        label = anchor.get_text(strip=True).lower()
        href = anchor["href"]
        if not href or href == "#":
            continue
        if label in _NEXT_LABELS or label.startswith("next"):
            return urljoin(current_url, href)

    # Strategy 3: anchor own class/aria OR parent element has "next" class
    for anchor in soup.find_all("a", href=True):
        href = anchor["href"]
        if not href or href == "#":
            continue
        aria = (anchor.get("aria-label") or "").lower()
        own_classes = " ".join(anchor.get("class", [])).lower()
        parent = anchor.parent
        parent_classes = " ".join(parent.get("class", [])).lower() if parent else ""
        if "next" in aria or "next" in own_classes or "next" in parent_classes:
            return urljoin(current_url, href)

    # Strategy 4: ask Claude with a small HTML snippet
    snippet = html[:12_000]
    system = "You find next-page URLs in paginated HTML. Reply with ONLY the URL or the word NONE."
    prompt = (
        f"Current URL: {current_url}\n\n"
        f"HTML snippet:\n{snippet}\n\n"
        "What is the URL of the next page? Return the full URL, a relative path, or NONE."
    )

    result = runner.complete(prompt, system=system).strip()
    if result.upper() == "NONE" or not result:
        return None

    if result.startswith(("http://", "https://", "/")):
        return urljoin(current_url, result)

    return None
