"""
exporter.py — Save extracted data as JSON, CSV, or PDF.
"""
import csv
import json
from datetime import datetime
from pathlib import Path

from rich.console import Console

console = Console()

_OUTPUT_DIR = Path("output")


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def export_data(records: list[dict], fmt: str) -> str:
    """
    Write records to disk in the requested format.

    Args:
        records: List of extracted data dicts.
        fmt:     One of 'json', 'csv', 'pdf'.

    Returns:
        Absolute path of the saved file as a string.
    """
    _OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")

    if fmt == "csv":
        return _to_csv(records, ts)
    if fmt == "pdf":
        return _to_pdf(records, ts)
    return _to_json(records, ts)  # Default


# ---------------------------------------------------------------------------
# Format writers
# ---------------------------------------------------------------------------

def _to_json(records: list[dict], ts: str) -> str:
    path = _OUTPUT_DIR / f"scraped_{ts}.json"
    with open(path, "w", encoding="utf-8") as fh:
        json.dump(records, fh, indent=2, ensure_ascii=False)
    return str(path.resolve())


def _to_csv(records: list[dict], ts: str) -> str:
    path = _OUTPUT_DIR / f"scraped_{ts}.csv"

    if not records:
        path.touch()
        return str(path.resolve())

    # Preserve column order: collect all unique keys across all records
    all_keys: list[str] = []
    for rec in records:
        for key in rec:
            if key not in all_keys:
                all_keys.append(key)

    with open(path, "w", newline="", encoding="utf-8") as fh:
        writer = csv.DictWriter(fh, fieldnames=all_keys, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(records)

    return str(path.resolve())


def _to_pdf(records: list[dict], ts: str) -> str:
    try:
        from fpdf import FPDF
    except ImportError:
        console.print("[yellow]fpdf2 is not installed — falling back to JSON output.[/yellow]")
        return _to_json(records, ts)

    path = _OUTPUT_DIR / f"scraped_{ts}.pdf"

    pdf = FPDF()
    pdf.set_auto_page_break(auto=True, margin=15)
    pdf.add_page()
    w = pdf.epw  # Effective page width (respects margins)

    # Title
    pdf.set_font("Helvetica", style="B", size=18)
    pdf.cell(w, 12, "Scraped Data Report", new_x="LMARGIN", new_y="NEXT", align="C")
    pdf.set_font("Helvetica", size=10)
    pdf.cell(
        w, 8,
        f"Generated: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}   |   "
        f"Records: {len(records)}",
        new_x="LMARGIN", new_y="NEXT", align="C",
    )
    pdf.ln(6)

    # Records
    for idx, record in enumerate(records, start=1):
        pdf.set_font("Helvetica", style="B", size=11)
        pdf.cell(w, 8, f"Record {idx}", new_x="LMARGIN", new_y="NEXT")
        pdf.set_font("Helvetica", size=9)

        for key, value in record.items():
            safe_text = f"  {key}: {str(value)}"
            # Encode to latin-1 with replacement so fpdf does not crash on
            # rare unicode code points outside the built-in font's range.
            safe_text = safe_text.encode("latin-1", errors="replace").decode("latin-1")
            pdf.set_x(pdf.l_margin)  # Always reset x before multi_cell
            pdf.multi_cell(w, 6, safe_text, new_x="LMARGIN", new_y="NEXT")

        pdf.ln(4)

    pdf.output(str(path))
    return str(path.resolve())
