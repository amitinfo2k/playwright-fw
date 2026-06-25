"""
graph/workflow.py

LangGraph Workflow
──────────────────
Defines the full agent graph for the Mendix Playwright Automation Framework.

State machine:
  START
    ↓
  [scan]        — App Scanner Agent (DOM mapping)
    ↓
  [locate]      — Locator Strategy Agent (selector resolution)
    ↓
  [generate]    — Test Generator Agent (code writing)
    ↓
  [run_test]    — Playwright executor
    ↓ (pass)
  END
    ↓ (fail, retry < MAX_RETRIES)
  [heal]        → back to [locate]
    ↓ (max retries exceeded)
  [fail_rec]    → END

"""

import logging
import subprocess
import os
from typing import Literal
from langfuse.decorators import observe

from langgraph.graph import StateGraph, END
from typing_extensions import TypedDict

from agents.scanner_agent import run_scanner_agent
from agents.locator_agent import run_locator_agent, resolve_locator
from agents.generator_agent import run_generator_agent, parse_steps

logger = logging.getLogger(__name__)


# ─────────────────────────────────────────────────────────────────────────────
# State Schema
# ─────────────────────────────────────────────────────────────────────────────

class AutomationState(TypedDict, total=False):
    # Config
    base_url:        str
    pages_to_scan:   list[str]
    headless:        bool
    max_retries:     int

    # Test data
    test_cases:      list[dict]   # All rows from CSV
    current_test:    dict         # Active test case being processed
    current_index:   int          # Index into test_cases

    # Agent outputs
    ui_map:          dict         # Scanner output
    parsed_steps:    list[dict]   # Parsed step actions
    resolved_locators: list[dict] # Steps with locator results
    generated_code:  str          # Generated Playwright code
    generated_file:  str          # Path to written .spec.ts file
    generated_files: list[str]    # Accumulates all output files

    # Self-heal
    retry_count:     int
    failure_reason:  str
    failed_tests:    list[dict]
    hitl_enabled:    bool


# ─────────────────────────────────────────────────────────────────────────────
# Wrapper Nodes
# ─────────────────────────────────────────────────────────────────────────────

def scan_node(state: AutomationState) -> AutomationState:
    """Scan the application DOM. Only runs once per pipeline execution."""
    if state.get("ui_map"):
        logger.info("[Graph] Skipping scan — ui_map already populated.")
        return state
    return run_scanner_agent(state)


def prepare_test_node(state: AutomationState) -> AutomationState:
    """
    Advance to the next test case, parse its steps.
    Sets `current_test` and `parsed_steps`.
    """
    test_cases = state.get("test_cases", [])
    index = state.get("current_index", 0)

    if index >= len(test_cases):
        logger.info("[Graph] All test cases processed.")
        return {**state, "current_test": {}, "parsed_steps": []}

    current_test = test_cases[index]
    base_url = state.get("base_url", "")

    # Parse the free-text steps column into structured actions
    parsed = parse_steps(current_test.get("steps", ""), base_url)

    logger.info(f"[Graph] Preparing test #{index+1}: {current_test.get('test_title')}")
    return {
        **state,
        "current_test":  current_test,
        "parsed_steps":  parsed,
        "retry_count":   0,
        "failure_reason": "",
    }


def locate_node(state: AutomationState) -> AutomationState:
    """Run the Locator Strategy Agent."""
    return run_locator_agent(state)


@observe(name="Generate Test Node")
def generate_node(state: AutomationState) -> AutomationState:
    """Run the Test Generator Agent."""
    result = run_generator_agent(state)
    # Accumulate generated files list
    files = state.get("generated_files", [])
    new_file = result.get("generated_file", "")
    if new_file:
        files = files + [new_file]
    return {**result, "generated_files": files}


@observe(name="Review Node (HITL)")
def review_node(state: AutomationState) -> AutomationState:
    """
    HITL: Wait for user to review generated code.
    Enabled via env HITL_ENABLED=true or state.
    """
    is_hitl = os.getenv("HITL_ENABLED", "false").lower() == "true" or state.get("hitl_enabled", False)
    if not is_hitl:
        return state

    file_path = state.get("generated_file", "")
    print(f"\n[HITL] Test generated: {file_path}")
    print(f"[HITL] Please review the file and press ENTER to continue, or type 'abort' to stop.")
    user_input = input(">> ").lower().strip()

    if user_input == "abort":
        raise InterruptedError("User aborted the execution during HITL review.")

    return state


@observe(name="Run Test Node")
def run_test_node(state: AutomationState) -> AutomationState:
    """
    Execute the generated Playwright test file via @playwright/test.
    Captures pass/fail result.
    """
    generated_file = state.get("generated_file", "")
    if not generated_file:
        return {**state, "failure_reason": "No generated file to run."}

    logger.info(f"[Graph] Running: npx playwright test {generated_file}")
    try:
        # We use --reporter=list for clean output, and -x to stop on first failure if needed,
        # but here we just want the result of this specific file.
        result = subprocess.run(
            ["npx", "playwright", "test", generated_file],
            capture_output=True, text=True, timeout=120
        )
        if result.returncode == 0:
            logger.info(f"[Graph] ✅ PASS: {generated_file}")
            return {**state, "failure_reason": ""}
        else:
            # Capture failure output for healing
            failure = result.stdout[-2000:] + result.stderr[-500:]
            logger.warning(f"[Graph] ❌ FAIL: {failure[-300:].strip()}")
            return {**state, "failure_reason": failure}
    except subprocess.TimeoutExpired:
        return {**state, "failure_reason": "Test execution timed out."}
    except FileNotFoundError:
        logger.warning("[Graph] playwright/npx not found — skipping test execution.")
        return {**state, "failure_reason": "Environment error: npx not found."}


@observe(name="Heal Node")
def heal_node(state: AutomationState) -> AutomationState:
    """
    Self-Heal: clear locator cache entries for the failed step
    so the Locator Agent re-evaluates them on the next attempt.
    """
    import json
    from pathlib import Path

    locator_map_path = Path("locator_map.json")
    retry_count = state.get("retry_count", 0) + 1
    logger.info(f"[Graph] Self-heal attempt {retry_count}...")

    if locator_map_path.exists():
        with open(locator_map_path) as f:
            locator_map = json.load(f)

        # Remove cache entries for the current test's base URL
        base_url = state.get("base_url", "")
        keys_to_remove = [k for k in locator_map if k.startswith(base_url)]
        for k in keys_to_remove:
            del locator_map[k]

        with open(locator_map_path, "w") as f:
            json.dump(locator_map, f, indent=2)

        logger.info(f"[Graph] Cleared {len(keys_to_remove)} cached locators for re-scan.")

    return {**state, "retry_count": retry_count}


def advance_node(state: AutomationState) -> AutomationState:
    """Advance to the next test case."""
    current_index = state.get("current_index", 0) + 1
    return {**state, "current_index": current_index}


def record_failure_node(state: AutomationState) -> AutomationState:
    """Record a permanently failed test and move on."""
    failed = state.get("failed_tests", [])
    current_test = state.get("current_test", {})
    failed = failed + [{
        "test": current_test,
        "reason": state.get("failure_reason", ""),
    }]
    logger.error(f"[Graph] Permanently failed: {current_test.get('test_title')}")
    return {**state, "failed_tests": failed}


# ─────────────────────────────────────────────────────────────────────────────
# Routing Logic
# ─────────────────────────────────────────────────────────────────────────────

def route_after_run(state: AutomationState) -> Literal["heal", "advance", "done"]:
    failure = state.get("failure_reason", "")
    retries = state.get("retry_count", 0)
    max_r   = state.get("max_retries", 3)
    index   = state.get("current_index", 0)
    total   = len(state.get("test_cases", []))

    if failure:
        if retries < max_r:
            return "heal"
        return "advance"   # record failure then advance

    # Test passed — go to next
    if index + 1 >= total:
        return "done"
    return "advance"


def route_after_prepare(state: AutomationState) -> Literal["locate", "done"]:
    """Check if there are remaining test cases."""
    if not state.get("current_test"):
        return "done"
    return "locate"


# ─────────────────────────────────────────────────────────────────────────────
# Build Graph
# ─────────────────────────────────────────────────────────────────────────────

def build_graph() -> StateGraph:
    g = StateGraph(AutomationState)

    # Add nodes
    g.add_node("scan",     scan_node)
    g.add_node("prepare",  prepare_test_node)
    g.add_node("locate",   locate_node)
    g.add_node("generate", generate_node)
    g.add_node("review",   review_node)
    g.add_node("run_test", run_test_node)
    g.add_node("heal",     heal_node)
    g.add_node("advance",  advance_node)
    g.add_node("fail_rec", record_failure_node)

    # Entry point
    g.set_entry_point("scan")

    # Edges
    g.add_edge("scan",     "prepare")
    g.add_conditional_edges("prepare", route_after_prepare, {
        "locate": "locate",
        "done":   END,
    })
    g.add_edge("locate",   "generate")
    g.add_edge("generate", "review")
    g.add_edge("review",   "run_test")
    g.add_conditional_edges("run_test", route_after_run, {
        "heal":    "heal",
        "advance": "advance",
        "done":    END,
    })
    g.add_edge("heal",     "locate")    # Re-locate → re-generate → re-run
    g.add_edge("advance",  "prepare")
    g.add_edge("fail_rec", "advance")

    return g.compile()
