"""
agents/scanner_agent.py

App Scanner Agent
─────────────────
Crawls the Mendix application using a headless Playwright browser.
For each URL visited it:
  1. Captures the full DOM fragment (cleaned via BeautifulSoup).
  2. Takes a screenshot.
  3. Extracts every interactive element with all candidate locator
     attributes ordered by the Mendix locator priority rules.

Output is stored in-state as `ui_map`:
  {
    "<url>": {
      "title": "Page Title",
      "screenshot": "/path/to/screenshot.png",
      "elements": [
         {
           "tag": "button",
           "text": "Save",
           "role": "button",
           "aria_label": "Save record",
           "test_class": "test-save-btn",
           "mx_name": "mx-name-saveButton",
           "id": "",           # may be volatile, kept for reference only
           "selector_candidates": [...]  # ordered best→worst
         }, ...
      ]
    }
  }
"""

import os
import json
import logging
from pathlib import Path

from bs4 import BeautifulSoup
from playwright.sync_api import sync_playwright, Page, Browser

logger = logging.getLogger(__name__)


SCREENSHOTS_DIR = Path(__file__).parent.parent / "screenshots"
SCREENSHOTS_DIR.mkdir(parents=True, exist_ok=True)

# Mendix loading overlay — must be gone before scanning elements
MX_PROGRESS_SELECTOR = ".mx-progress"


def _wait_for_mendix(page: Page, timeout: int = 30_000) -> None:
    """Wait for Mendix async operations to finish."""
    try:
        page.locator(MX_PROGRESS_SELECTOR).wait_for(state="detached", timeout=timeout)
    except Exception:
        pass  # overlay may not appear; that's fine


def _extract_elements(page: Page, soup: BeautifulSoup) -> list[dict]:
    """
    Walk interactive tags and build locator candidate lists per
    playwright_mendix_locators.md priority order.
    """
    INTERACTIVE_TAGS = {"button", "a", "input", "select", "textarea",
                        "label", "span", "div"}

    elements = []
    for tag in soup.find_all(INTERACTIVE_TAGS):
        role        = tag.get("role", "")
        aria_label  = tag.get("aria-label", "")
        text        = tag.get_text(strip=True)[:80]
        tag_name    = tag.name
        id_attr     = tag.get("id", "")
        classes     = tag.get("class", [])
        name_attr   = tag.get("name", "")

        # Identify custom test / qa classes (set in Studio Pro)
        test_classes = [c for c in classes
                        if c.startswith("test-") or c.startswith("qa-")]

        # Identify Mendix modeler-name classes  (⚠️ fragile)
        mx_name_classes = [c for c in classes if c.startswith("mx-name-")]

        # Volatile Mendix widget IDs — flagged but never used in selectors
        is_volatile_id = id_attr.startswith("mxui_widget_")

        # Build ordered selector candidates (P1 → P5, skip volatile IDs)
        candidates = []

        # P1 — ARIA role + accessible name
        if role and (aria_label or text):
            label = aria_label or text
            candidates.append({
                "priority": 1,
                "api": "getByRole",
                "value": f"page.getByRole('{role}', {{ name: '{label}' }})"
            })

        # P2 — Visible label text (for form controls)
        if tag_name == "input" and text:
            candidates.append({
                "priority": 2,
                "api": "getByLabel",
                "value": f"page.getByLabel('{text}')"
            })

        # P3 — Static visible text (buttons, links, headings)
        if text and tag_name in {"button", "a", "span"}:
            candidates.append({
                "priority": 3,
                "api": "getByText",
                "value": f"page.getByText('{text}')"
            })

        # P4 — Custom .test-* / .qa-* classes (Studio Pro explicit)
        for tc in test_classes:
            candidates.append({
                "priority": 4,
                "api": "locator",
                "value": f"page.locator('.{tc}')"
            })

        # P5 — Mendix modeler mx-name-* (⚠️ fragile — rename-sensitive)
        for mc in mx_name_classes:
            candidates.append({
                "priority": 5,
                "api": "locator",
                "value": f"page.locator('.{mc}')"
            })

        # P6 (BLOCKED) — Never emit mxui_widget_* IDs

        if not candidates:
            continue  # skip elements with no viable locator

        elem = {
            "tag":       tag_name,
            "text":      text,
            "role":      role,
            "aria_label": aria_label,
            "name":      name_attr,
            "test_class": test_classes[0] if test_classes else "",
            "mx_name":   mx_name_classes[0] if mx_name_classes else "",
            "volatile_id_detected": is_volatile_id,
            "selector_candidates": sorted(candidates, key=lambda x: x["priority"]),
        }
        elements.append(elem)

    return elements


def run_scanner_agent(state: dict) -> dict:
    """
    LangGraph node: App Scanner Agent.

    Reads `state["base_url"]` and `state["pages_to_scan"]`, crawls
    each URL with Playwright, then returns updated state with `ui_map`.
    """
    base_url: str       = state.get("base_url", "")
    pages: list[str]    = state.get("pages_to_scan", [base_url])
    headless: bool      = state.get("headless", True)
    ui_map: dict        = {}

    logger.info(f"[Scanner] Scanning {len(pages)} pages on {base_url}")

    with sync_playwright() as pw:
        browser: Browser = pw.chromium.launch(headless=headless)
        context = browser.new_context(viewport={"width": 1280, "height": 800})
        page: Page = context.new_page()

        for url in pages:
            try:
                logger.info(f"[Scanner]  → {url}")
                page.goto(url, wait_until="networkidle", timeout=60_000)
                _wait_for_mendix(page)

                title = page.title()

                # Screenshot
                screenshot_path = str(SCREENSHOTS_DIR / f"{title.replace(' ', '_')}.png")
                page.screenshot(path=screenshot_path, full_page=True)

                # Parse DOM
                html = page.content()
                soup = BeautifulSoup(html, "lxml")
                elements = _extract_elements(page, soup)

                ui_map[url] = {
                    "title":      title,
                    "screenshot": screenshot_path,
                    "elements":   elements,
                }

                logger.info(f"[Scanner]    Found {len(elements)} elements on '{title}'")

            except Exception as exc:
                logger.error(f"[Scanner] Failed to scan {url}: {exc}")
                ui_map[url] = {"title": "", "screenshot": "", "elements": [], "error": str(exc)}

        browser.close()

    # Persist ui_map for debugging / caching
    ui_map_path = Path(__file__).parent.parent / "ui_map.json"
    with open(ui_map_path, "w") as f:
        json.dump(ui_map, f, indent=2)

    return {**state, "ui_map": ui_map}
