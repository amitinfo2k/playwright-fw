# Mendix Playwright Automation Framework

An **Agentic AI** testing framework using **LangGraph + Playwright** that takes `Test_Cases.csv` as input and produces working Playwright Python test files.

---

## Architecture

```
Test_Cases.csv
      ↓
┌────────────────────────────────────────────────┐
│          LangGraph Orchestrator                │
│                                                │
│  ┌──────────────┐   ┌──────────────────────┐  │
│  │ App Scanner  │──▶│ Locator Strategy     │  │
│  │   Agent      │   │ Agent  ← CORE        │  │
│  └──────────────┘   │ (Mendix rules)       │  │
│                     └──────────┬───────────┘  │
│                                ▼               │
│                     ┌──────────────────────┐  │
│                     │  Test Generator      │  │
│                     │  Agent               │  │
│                     └──────────┬───────────┘  │
│                                ▼               │
│                     ┌──────────────────────┐  │
│                     │  Playwright Runner   │  │
│                     │  + Self-Heal Loop    │  │
│                     └──────────────────────┘  │
└────────────────────────────────────────────────┘
      ↓
generated_tests/*.py  (runnable Playwright tests)
```

### Locator Priority (from `playwright_mendix_locators.md`)

| Priority | Strategy | Playwright API |
|---|---|---|
| 1 ✅ | ARIA role + name | `page.get_by_role('button', name='Save')` |
| 2 ✅ | Label text | `page.get_by_label('Email Address')` |
| 3 ✅ | Visible text | `page.get_by_text('Order Confirmation')` |
| 4 ✅ | Custom `.test-*` / `.qa-*` class | `page.locator('.test-save-btn')` |
| 5 ⚠️ | Mendix modeler name | `page.locator('.mx-name-saveButton')` |
| 6 ❌ | Auto-generated ID | **NEVER** — `#mxui_widget_*` blocked |

---

## Setup

### 1. Create & activate a virtual environment

```bash
python -m venv .venv
source .venv/bin/activate        # Linux / macOS
# .venv\Scripts\activate         # Windows PowerShell
```

### 2. Install Python dependencies

```bash
pip install -r requirements.txt
```

### 3. Install Playwright browsers

```bash
# Install only Chromium (recommended — smallest download)
playwright install chromium

# OR install all browsers (Chromium, Firefox, WebKit)
playwright install

# Linux only — install required OS-level system dependencies
playwright install-deps chromium
# If you get missing library errors, run:
# sudo playwright install-deps
```

> **Verify the install:**
> ```bash
> playwright --version
> # Expected: Version X.Y.Z
> python -c "from playwright.sync_api import sync_playwright; print('Playwright OK')"
> ```

### 4. Configure environment

```bash
cp .env.example .env
# Open .env and set:
#   BASE_URL=https://yourapp.mxapps.io
#   GOOGLE_API_KEY=your-gemini-api-key
```

---

## Usage

```bash
# Run full pipeline: scan → locate → generate → run tests
python main.py --csv Test_Cases.csv --url https://yourapp.mxapps.io

# Generate tests only (no pytest execution)
python main.py --csv Test_Cases.csv --url https://yourapp.mxapps.io --no-run

# Run with visible browser (debugging)
python main.py --no-headless

# Run generated tests manually
pytest generated_tests/ -v
```

### CLI Options

| Flag | Default | Description |
|---|---|---|
| `--csv` | `Test_Cases.csv` | Path to input CSV |
| `--url` | `$BASE_URL` | Mendix app base URL |
| `--headless / --no-headless` | `true` | Browser visibility |
| `--retries` | `3` | Self-heal max retries |
| `--no-run` | `false` | Skip pytest execution |

---

## CSV Format

```csv
id,test_title,steps,expected_result
1,Login Success,"1. Navigate to /login, 2. Enter 'admin@test.com' in Email, 3. Click 'Sign In'",Dashboard is visible
```

**Step verbs recognised:** `Navigate`, `Click`, `Enter/Fill/Type`, `Select`, `Assert/Verify/Check`

---

## Project Structure

```
playwright-automation/
├── main.py                     ← Entry point
├── conftest.py                 ← Playwright pytest fixtures
├── pytest.ini                  ← Test discovery config
├── Test_Cases.csv              ← Input test cases
├── GEMINI.md                   ← AI agent context & rules
├── playwright_mendix_locators.md ← Locator rules reference
├── requirements.txt
├── .env.example
│
├── agents/
│   ├── scanner_agent.py        ← DOM crawler
│   ├── locator_agent.py        ← Locator resolution (CORE)
│   └── generator_agent.py      ← Test code writer
│
├── graph/
│   └── workflow.py             ← LangGraph orchestration
│
├── utils/
│   ├── csv_parser.py           ← CSV loader
│   └── code_writer.py          ← File writer
│
├── generated_tests/            ← ← OUTPUT: Playwright .py files
├── locator_map.json            ← Cached locator decisions
├── ui_map.json                 ← Cached DOM scan results
└── screenshots/                ← Page screenshots from scanner
```

---

## Self-Healing

If a test fails with `TimeoutError`:
1. Framework detects the failure
2. Clears locator cache for affected page
3. Re-invokes **Locator Strategy Agent** with fresh DOM scan
4. Regenerates the test file
5. Retries up to `--retries` times (default: 3)

---

## Outputs

| File | Description |
|---|---|
| `generated_tests/test_<id>_<title>.py` | Runnable Playwright test |
| `locator_map.json` | Cached locator decisions (inspect for audit) |
| `ui_map.json` | Full DOM scan results |
| `run_summary.json` | Pass/fail summary of the run |
| `screenshots/` | Full-page screenshots per page |
