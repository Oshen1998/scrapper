"""
auth.py — Browser-based authentication via Claude Code.

Flow:
  1. Ask the user for permission to connect to their Claude account.
  2. Check current login state with `claude auth status`.
  3. If not logged in, open the browser via `claude auth login`.
  4. Return a ClaudeRunner that makes API calls through the authenticated CLI.
"""
import json
import shutil
import subprocess
import sys

import questionary
from rich.console import Console
from rich.panel import Panel

from claude_runner import ClaudeRunner

console = Console()


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _claude_installed() -> bool:
    return shutil.which("claude") is not None


def _auth_status() -> dict:
    """Return parsed `claude auth status --json`, or {} on error."""
    try:
        r = subprocess.run(
            ["claude", "auth", "status", "--json"],
            capture_output=True, text=True, timeout=10,
        )
        return json.loads(r.stdout.strip()) if r.returncode == 0 else {}
    except Exception:
        return {}


def _browser_login() -> None:
    """Open the browser-based OAuth flow via `claude auth login`."""
    console.print(
        "\n[bold cyan]Opening browser for Claude authentication…[/bold cyan]"
    )
    console.print("[dim]Complete the sign-in in your browser, then return here.[/dim]\n")
    subprocess.run(["claude", "auth", "login"])


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def connect_claude() -> ClaudeRunner:
    """
    Ask the user for permission to connect, authenticate via browser if needed,
    and return a ClaudeRunner ready to make API calls.
    """

    # ── 0. Require the claude CLI ─────────────────────────────────────────
    if not _claude_installed():
        console.print("[red]Claude Code CLI not found.[/red]")
        console.print("[dim]Install it from https://claude.ai/download then re-run.[/dim]")
        sys.exit(1)

    # ── 1. Ask user permission ────────────────────────────────────────────
    console.print(
        Panel(
            "[bold]This app needs access to your Claude account[/bold]\n"
            "[dim]It will use your existing Claude subscription to extract\n"
            "data from web pages. No API key is required.[/dim]",
            border_style="cyan",
            padding=(0, 2),
        )
    )

    allow = questionary.confirm(
        "Connect using your Claude account?",
        default=True,
    ).ask()

    if not allow:
        console.print("[yellow]Connection declined. Exiting.[/yellow]")
        sys.exit(0)

    # ── 2. Check / trigger login ──────────────────────────────────────────
    status = _auth_status()

    if not status.get("loggedIn"):
        _browser_login()
        status = _auth_status()

    if not status.get("loggedIn"):
        console.print("[red]Authentication failed or was cancelled.[/red]")
        sys.exit(1)

    # ── 3. Confirm and return runner ──────────────────────────────────────
    email    = status.get("email", "")
    org_name = status.get("orgName", "")
    label    = email + (f"  ({org_name})" if org_name else "")
    console.print(f"[green]Connected as:[/green] {label}")

    return ClaudeRunner()
