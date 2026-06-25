## Goal

- **Mendix UI** Application Automation Testing framework using Playwright.
- Agentic AI framework which takes `Test_Cases.csv` (with detailed steps) as input and generates working Playwright test scripts.
- Autonomously fix locator issues and output working Playwright test scripts.
- Follow locator rules strictly as defined in `playwright_mendix_locators.md`. Mendix UI is dynamic in nature.

## Locator Rules Reference

All agents must follow the rules in [`playwright_mendix_locators.md`](./playwright_mendix_locators.md).

**Priority Order (Enforced by Locator Strategy Agent):**
1. ✅ `page.getByRole()` and `page.getByLabel()` — user-centric, most resilient
2. ✅ `page.getByText()` — for static visible text
3. ✅ `.test-*` / `.qa-*` custom classes — explicit, set in Mendix Studio Pro
4. ⚠️ `.mx-name-[WidgetName]` — fragile if element is renamed in modeler
5. ❌ `#mxui_widget_*` — **NEVER USE** (auto-generated, volatile IDs)
6. ⏳ Wait for `.mx-progress` to detach before next step (async Microflow/Nanoflow)

## Input / Output

- **Input:** `Test_Cases.csv` columns: `id`, `test_title`, `steps`, `expected_result`
- **Output:** Working Playwright TypeScript test files in `generated_tests/` (.spec.ts)

## Agent Responsibilities

1. **App Scanner Agent** — Crawls pages, maps DOM with priority-ranked locator candidates.
2. **Locator Strategy Agent** — Selects the best locator per the rules above; stores in `locator_map.json`.
3. **Test Generator Agent** — Reads CSV rows, queries Locator Strategy Agent, writes Playwright type-script tests.

## Self-Healing

If a test fails with any error (e.g., `TimeoutError`, `AssertionError`, etc.), the framework re-invokes the Locator Strategy Agent to re-scan and update the failing locator in `locator_map.json`, then re-runs the test.
