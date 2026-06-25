"""
agents/locator_agent.py

Locator Strategy Agent
───────────────────────
The most critical agent in the pipeline. Given a natural-language
element description (from a test step) and the current `ui_map`, it
selects the BEST, most-resilient Playwright locator following the
rules in playwright_mendix_locators.md.

Priority order enforced:
  P1  getByRole(role, name)       — ARIA, most resilient
  P2  getByLabel(text)            — form labels
  P3  getByText(text)             — visible static text
  P4  locator('.test-*/.qa-*')    — explicit Studio Pro class
  P5  locator('.mx-name-*')       — ⚠️ fragile, rename-sensitive
  P6  BLOCKED — mxui_widget_* IDs — NEVER USED

Also builds the Mendix async wait statement when a step triggers
a Microflow/Nanoflow (detected by keywords in the step description).

Stores results in `locator_map.json` for caching and self-heal
inspection.
"""

import os
import json
import logging
from pathlib import Path
from langfuse.decorators import observe
from langchain_core.messages import SystemMessage, HumanMessage
from utils.llm_factory import get_llm

logger = logging.getLogger(__name__)

LOCATOR_MAP_PATH = Path(__file__).parent.parent / "locator_map.json"

# Keywords that typically trigger Mendix async Microflow/Nanoflow
ASYNC_TRIGGER_KEYWORDS = {
    "save", "submit", "create", "delete", "search",
    "filter", "login", "logout", "approve", "reject",
}

# LLM is now managed by factory


def _load_locator_map() -> dict:
    if LOCATOR_MAP_PATH.exists():
        with open(LOCATOR_MAP_PATH) as f:
            return json.load(f)
    return {}


def _save_locator_map(locator_map: dict) -> None:
    with open(LOCATOR_MAP_PATH, "w") as f:
        json.dump(locator_map, f, indent=2)


def _needs_async_wait(step_text: str) -> bool:
    """Return True if this step likely triggers a Mendix Microflow/Nanoflow."""
    lower = step_text.lower()
    return any(kw in lower for kw in ASYNC_TRIGGER_KEYWORDS)


def _select_best_locator_heuristic(element_description: str, candidates: list[dict]) -> dict | None:
    """
    Pure heuristic selection: return the highest-priority candidate
    whose value appears to match the element_description text.
    """
    lower_desc = element_description.lower()

    # Filter candidates that plausibly match the description
    matching = []
    for cand in candidates:
        val_lower = cand["value"].lower()
        # Check if description keyword appears in the selector value
        for word in lower_desc.split():
            if len(word) > 3 and word in val_lower:
                matching.append(cand)
                break

    if matching:
        return sorted(matching, key=lambda x: x["priority"])[0]

    # Fall back to best available
    if candidates:
        return sorted(candidates, key=lambda x: x["priority"])[0]

    return None


def _select_locator_with_llm(
    element_description: str,
    candidates: list[dict],
    step_text: str,
    locator_rules: str,
) -> dict | None:
    """
    Use LLM to select the best locator from candidates when
    heuristic matching is inconclusive.
    """
    llm = get_llm()

    candidates_text = json.dumps(candidates, indent=2)
    prompt = f"""You are a Mendix Playwright locator expert.

LOCATOR PRIORITY RULES (strictly follow):
{locator_rules}

TEST STEP: "{step_text}"
ELEMENT TO LOCATE: "{element_description}"

AVAILABLE LOCATOR CANDIDATES (already ranked by priority):
{candidates_text}

Task: Select the SINGLE best locator for this element from the candidates.
- Choose the highest-priority candidate that accurately targets this element.
- NEVER select any locator containing 'mxui_widget' (volatile IDs).
- Respond with ONLY valid JSON in this exact format:
{{
  "priority": <int>,
      "api": "<getByRole|getByLabel|getByText|locator>",
  "value": "<full playwright locator expression>",
  "reasoning": "<one line explanation>"
}}"""

    try:
        response = llm.invoke([SystemMessage(content="You are a test automation expert."),
                               HumanMessage(content=prompt)])
        raw = response.content.strip()

        # Strip markdown code fences if present
        if raw.startswith("```"):
            raw = raw.split("```")[1]
            if raw.startswith("json"):
                raw = raw[4:]

        return json.loads(raw.strip())
    except Exception as exc:
        logger.warning(f"[Locator] LLM selection failed: {exc}. Falling back to heuristic.")
        return None


LOCATOR_RULES_SUMMARY = """
1. BEST:  page.getByRole('button', { name: 'Save' }) — ARIA role + name
2. GOOD:  page.getByLabel('Email Address')          — form control labels
3. GOOD:  page.getByText('Order Confirmation')      — static visible text
4. OK:    page.locator('.test-save-btn')            — custom Studio Pro class
5. RISKY: page.locator('.mx-name-saveButton')       — Mendix modeler name (rename-sensitive)
6. NEVER: page.locator('#mxui_widget_*')            — volatile IDs, always blocked
"""


def resolve_locator(
    element_description: str,
    step_text: str,
    ui_map: dict,
    url: str,
) -> dict:
    """
    Resolve the best locator for an element description on a given page.

    Returns a locator_result dict:
    {
      "locator":    "<playwright expression>",
      "api":        "<api name>",
      "priority":   <int>,
      "needs_wait": <bool>,   # True → insert .mx-progress wait before next step
      "reasoning":  "<str>"
    }
    """
    cache_key = f"{url}::{element_description}"
    locator_map = _load_locator_map()

    # Return cached result if available
    if cache_key in locator_map:
        logger.info(f"[Locator] Cache hit: {cache_key}")
        return locator_map[cache_key]

    page_data = ui_map.get(url, {})
    all_candidates: list[dict] = []

    for elem in page_data.get("elements", []):
        all_candidates.extend(elem.get("selector_candidates", []))

    # Try heuristic first (fast, no LLM call)
    best = _select_best_locator_heuristic(element_description, all_candidates)

    # If heuristic is inconclusive, use LLM
    if not best or best["priority"] >= 5:
        logger.info(f"[Locator] Using LLM for: '{element_description}'")
        llm_result = _select_locator_with_llm(
            element_description, all_candidates, step_text, LOCATOR_RULES_SUMMARY
        )
        if llm_result:
            best = llm_result

    # Final fallback — generic text locator
    if not best:
        best = {
            "priority": 3,
            "api": "get_by_text",
            "value": f"page.getByText('{element_description}')",
            "reasoning": "Fallback: no candidates matched; using visible text.",
        }

    result = {
        "locator":    best["value"],
        "api":        best.get("api", "locator"),
        "priority":   best.get("priority", 99),
        "needs_wait": _needs_async_wait(step_text),
        "reasoning":  best.get("reasoning", ""),
    }

    # Cache the result
    locator_map[cache_key] = result
    _save_locator_map(locator_map)
    logger.info(f"[Locator] P{result['priority']} → {result['locator']}")
    return result


@observe(name="Locator Agent")
def run_locator_agent(state: dict) -> dict:
    """
    LangGraph node: Locator Strategy Agent.

    Iterates over `state["parsed_steps"]` for the current test case
    and resolves a locator for each step action. Stores results in
    `state["resolved_locators"]`.
    """
    ui_map: dict        = state.get("ui_map", {})
    base_url: str       = state.get("base_url", "")
    parsed_steps: list  = state.get("parsed_steps", [])
    resolved: list      = []

    for step in parsed_steps:
        action      = step.get("action", "")
        target      = step.get("target", "")
        url         = step.get("url", base_url)
        step_text   = step.get("raw", "")

        if action in {"navigate", "assert", "wait"} or not target:
            resolved.append({**step, "locator_result": None})
            continue

        locator_result = resolve_locator(
            element_description=target,
            step_text=step_text,
            ui_map=ui_map,
            url=url,
        )
        resolved.append({**step, "locator_result": locator_result})

    return {**state, "resolved_locators": resolved}
