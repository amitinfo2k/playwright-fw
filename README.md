# Mendix Playwright Automation Framework

An **Agentic AI** testing framework using **LangGraph + Playwright** that takes `Test_Cases.csv` as input and produces working Playwright **TypeScript** test files (.spec.ts).

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
│                     │  Agent (TypeScript)  │  │
│                     └──────────┬───────────┘  │
│                                ▼               │
│                     ┌──────────────────────┐  │
│                     │  HITL Review Node    │  │
│                     │  (Manual Approval)   │  │
│                     └──────────┬───────────┘  │
│                                ▼               │
│                     ┌──────────────────────┐  │
│                     │  Playwright Runner   │  │
│                     │  + Self-Heal Loop    │  │
│                     └──────────────────────┘  │
│                                │               │
└────────────────────────────────┼───────────────┘
      ↓                          ▼
generated_tests/*.spec.ts   Langfuse Traces (Observability)
```

### Locator Priority (from `playwright_mendix_locators.md`)

| Priority | Strategy | Playwright API |
|---|---|---|
| 1 ✅ | ARIA role + name | `page.getByRole('button', { name: 'Save' })` |
| 2 ✅ | Label text | `page.getByLabel('Email Address')` |
| 3 ✅ | Visible text | `page.getByText('Order Confirmation')` |
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

### 2. Install dependencies

```bash
pip install -r requirements.txt
npm install                      # For playwright test runner
```

### 3. Install Playwright browsers

```bash
npx playwright install chromium
```

### 4. Configure environment

```bash
cp .env.example .env
# Set the following in .env:
#   LLM_BASE_URL=https://api.openai.com/v1
#   LLM_API_KEY=your-api-key
#   LLM_MODEL=gpt-4o
#   LANGFUSE_PUBLIC_KEY=...
#   LANGFUSE_SECRET_KEY=...
#   HITL_ENABLED=true
```

---

## Usage

```bash
# Run full pipeline: scan → locate → generate → HITL → run tests
python main.py --csv Test_Cases.csv --url https://yourapp.mxapps.io

# Generate tests only (skip execution)
python main.py --no-run

# Run with visible browser
python main.py --no-headless

# Run generated tests manually via Playwright CLI
npx playwright test generated_tests/
```

### CLI Options

| Flag | Default | Description |
|---|---|---|
| `--csv` | `Test_Cases.csv` | Path to input CSV |
| `--url` | `$BASE_URL` | Mendix app base URL |
| `--headless / --no-headless` | `true` | Browser visibility |
| `--retries` | `3` | Self-heal max retries |
| `--no-run` | `false` | Skip Playwright execution |

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
├── playwright.config.ts        ← Playwright TS config
├── GEMINI.md                   ← AI agent context & rules
├── playwright_mendix_locators.md ← Locator rules reference
├── requirements.txt
├── .env.example
├── .gitignore
│
├── agents/
│   ├── scanner_agent.py        ← DOM crawler
│   ├── locator_agent.py        ← Locator resolution (CORE)
│   └── generator_agent.py      ← Test code writer (TS)
│
├── graph/
│   └── workflow.py             ← LangGraph orchestration + HITL
│
├── utils/
│   ├── llm_factory.py          ← Agnostic LLM + Langfuse
│   ├── csv_parser.py           ← CSV loader
│   └── code_writer.py          ← File writer (.spec.ts)
│
├── generated_tests/            ← OUTPUT: Playwright .spec.ts files
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
