"""
claude_runner.py — Thin wrapper around `claude --print` for making LLM calls
using Claude Code's existing browser-based auth (no API key required).
"""
import subprocess
import sys

from rich.console import Console

console = Console()


class ClaudeRunner:
    """
    Makes Claude API calls by shelling out to the `claude` CLI.
    Requires the user to be authenticated via `claude auth login`.
    """

    def complete(self, prompt: str, system: str | None = None) -> str:
        """
        Send a prompt to Claude and return the plain-text response.

        Args:
            prompt: The user message.
            system: Optional system instruction prepended before the prompt.

        Returns:
            Claude's response as a plain string.

        Raises:
            RuntimeError: If the CLI call fails.
        """
        # Combine system + prompt into a single stdin payload.
        # claude --print reads the prompt from stdin when no positional arg is given.
        payload = f"{system}\n\n{prompt}" if system else prompt

        result = subprocess.run(
            ["claude", "--print", "--output-format", "text"],
            input=payload,
            capture_output=True,
            text=True,
            timeout=120,
        )

        if result.returncode != 0:
            stderr = result.stderr.strip()
            if "Not logged in" in stderr or "login" in stderr.lower():
                console.print(
                    "[red]Claude session expired.[/red] "
                    "Run  claude auth login  to re-authenticate."
                )
                sys.exit(1)
            raise RuntimeError(f"Claude CLI error: {stderr[:300]}")

        return result.stdout.strip()
