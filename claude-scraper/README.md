# Claude Web Scraper

A terminal-based AI web scraper powered by **Claude** (Anthropic) and **Playwright**.  
Run it, answer five questions, and receive clean structured data — no coding required.

```
┌─────────────────────────────────────────────────────┐
│          Claude Web Scraper                         │
│  AI-powered web scraping — Claude + Playwright      │
└─────────────────────────────────────────────────────┘

Step 1  Connect to Claude        → validates your API key
Step 2  Target page              → URL of the page to scrape
Step 3  Extraction instructions  → what fields you want
Step 4  Output format            → JSON / CSV / PDF
Step 5  Pagination               → all pages or specific count
```

---

## Prerequisites

| Requirement | Version | Where to get it |
|---|---|---|
| Python | 3.11 or newer | https://www.python.org/downloads/ |
| Anthropic API key | any | https://console.anthropic.com |

---

## Setup — macOS

### 1. Verify Python

```bash
python3 --version   # should print 3.11+
```

If Python is missing, install it via [Homebrew](https://brew.sh):

```bash
brew install python@3.12
```

### 2. Clone / download this repository

```bash
git clone <repo-url>
cd webscraping/claude-scraper
```

### 3. Create a virtual environment

```bash
python3 -m venv .venv
source .venv/bin/activate
```

Your prompt will change to `(.venv)` — keep this active for all commands below.

### 4. Install Python dependencies

```bash
pip install -r requirements.txt
```

### 5. Install the Chromium browser used by Playwright

```bash
playwright install chromium
```

### 6. Add your API key (optional — the app will also ask at runtime)

```bash
cp .env.example .env
# Open .env and paste your Anthropic API key
```

### 7. Run the scraper

```bash
python src/main.py
```

---

## Setup — Windows

> **Use PowerShell** for all commands below (not Command Prompt).

### 1. Install Python

Download the **Windows installer** from https://www.python.org/downloads/ and run it.  
**Important:** tick the box **"Add Python to PATH"** before clicking Install.

Verify:

```powershell
python --version    # should print 3.11+
```

### 2. Clone / download this repository

```powershell
git clone <repo-url>
cd webscraping\claude-scraper
```

### 3. Create a virtual environment

```powershell
python -m venv .venv
.venv\Scripts\Activate.ps1
```

If you see an execution policy error, run this once first:

```powershell
Set-ExecutionPolicy -Scope CurrentUser RemoteSigned
```

Your prompt will change to `(.venv)` — keep this active for all commands below.

### 4. Install Python dependencies

```powershell
pip install -r requirements.txt
```

### 5. Install the Chromium browser used by Playwright

```powershell
playwright install chromium
```

### 6. Add your API key (optional — the app will also ask at runtime)

```powershell
copy .env.example .env
# Open .env in Notepad and paste your Anthropic API key
```

### 7. Run the scraper

```powershell
python src\main.py
```

---

## Usage walkthrough

```
Step 1  Connect to Claude
  > Paste your Anthropic API key: sk-ant-...
  ✓ Connected to Claude successfully.

Step 2  Target page
  Example: https://www.digikey.com/en/products/filter/accessories/818
  > Enter the page URL to scrape: https://example.com/products

Step 3  Extraction instructions
  Hint: Extract: product name, part number, price, availability, manufacturer
  > What do you want to extract? Extract product name, price, and stock status

Step 4  Output format
  ❯ JSON  — structured data (default)
    CSV   — spreadsheet / Excel
    PDF   — printable document

Step 5  Pagination
  ❯ All pages  — follow pagination until the end
    Specific number of pages
```

Output is saved in the `output/` folder:

```
output/
└── scraped_20250414_153022.json
```

---

## Output formats

| Format | File | Best for |
|---|---|---|
| JSON | `scraped_<ts>.json` | APIs, further processing, default |
| CSV | `scraped_<ts>.csv` | Excel, Google Sheets, data analysis |
| PDF | `scraped_<ts>.pdf` | Sharing, printing, reports |

---

## Project structure

```
claude-scraper/
├── src/
│   ├── main.py        # Entry point — orchestrates the session
│   ├── auth.py        # Claude API key validation
│   ├── prompts.py     # All interactive terminal questions
│   ├── browser.py     # Playwright browser lifecycle
│   ├── scraper.py     # Page navigation + pagination loop
│   ├── extractor.py   # Claude AI extraction + next-page detection
│   └── exporter.py    # JSON / CSV / PDF output writers
├── output/            # Saved scrape results (git-ignored)
├── requirements.txt
├── .env.example
└── README.md
```

---

## Configuration via `.env`

If you prefer not to type your API key every run, create a `.env` file:

```
ANTHROPIC_API_KEY=sk-ant-your-key-here
```

The app loads this automatically on startup.

---

## Troubleshooting

**`playwright install chromium` fails on Windows**

Run PowerShell as Administrator and retry, or install system dependencies:

```powershell
playwright install-deps chromium
playwright install chromium
```

**`ModuleNotFoundError`**

Make sure the virtual environment is active (`(.venv)` in your prompt) before running `python src/main.py`.

**macOS SSL certificate error**

```bash
/Applications/Python\ 3.x/Install\ Certificates.command
```

Replace `3.x` with your Python version (e.g. `3.12`).

**"No data extracted"**

- The page may require a login — try logging in manually first and note session requirements.
- The page may use heavy JavaScript — increase the crawl delay by editing `asyncio.sleep(1.2)` in `src/scraper.py`.
- Refine your extraction prompt to be more specific about what to look for.

**API key error**

Confirm your key is active at https://console.anthropic.com and that your account has credits.
