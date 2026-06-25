"""
main.py
───────
Entry point for the Mendix Playwright Automation Framework.

Usage:
    python main.py --csv Test_Cases.csv --url https://yourapp.mxapps.io
    python main.py  # uses .env defaults
"""

import os
import sys
import json
import argparse
import logging
from pathlib import Path
from dotenv import load_dotenv

load_dotenv()

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s — %(message)s",
    datefmt="%H:%M:%S",
)
logger = logging.getLogger("main")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Mendix Playwright Automation Framework"
    )
    parser.add_argument(
        "--csv",
        default="Test_Cases.csv",
        help="Path to the test cases CSV file (default: Test_Cases.csv)",
    )
    parser.add_argument(
        "--url",
        default=os.getenv("BASE_URL", "https://companysampleapp.mxapps.io"),
        help="Base URL of the Mendix application",
    )
    parser.add_argument(
        "--headless",
        default=os.getenv("HEADLESS", "true").lower() == "true",
        action=argparse.BooleanOptionalAction,
        help="Run browser in headless mode (default: true)",
    )
    parser.add_argument(
        "--retries",
        type=int,
        default=int(os.getenv("MAX_RETRIES", "3")),
        help="Max self-heal retries per test (default: 3)",
    )
    parser.add_argument(
        "--no-run",
        action="store_true",
        default=False,
        help="Generate tests only, skip Playwright execution",
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()

    # Validate inputs
    csv_path = Path(args.csv)
    if not csv_path.exists():
        logger.error(f"CSV file not found: {csv_path}")
        sys.exit(1)

    if not os.getenv("GOOGLE_API_KEY"):
        logger.warning("GOOGLE_API_KEY not set — LLM-powered locator resolution disabled.")

    # Import here so dotenv is loaded first
    from utils.csv_parser import load_test_cases
    from graph.workflow import build_graph

    # Load test cases
    test_cases = load_test_cases(str(csv_path))
    logger.info(f"Loaded {len(test_cases)} test case(s) from {csv_path}")

    # Determine pages to scan (unique URLs from test cases + base)
    pages_to_scan = list({args.url})  # extend as needed

    # Build the LangGraph
    graph = build_graph()

    # Initial state
    initial_state = {
        "base_url":       args.url,
        "pages_to_scan":  pages_to_scan,
        "headless":       args.headless,
        "max_retries":    args.retries,
        "test_cases":     test_cases,
        "current_index":  0,
        "ui_map":         {},
        "generated_files": [],
        "failed_tests":   [],
        "hitl_enabled":   os.getenv("HITL_ENABLED", "false").lower() == "true",
    }

    if args.no_run:
        # Monkey-patch run_test_node to skip execution
        import graph.workflow as wf_module
        original = wf_module.run_test_node
        wf_module.run_test_node = lambda s: {**s, "failure_reason": ""}
        logger.info("--no-run: Playwright execution skipped.")

    logger.info(f"Starting automation pipeline → {args.url}")
    logger.info("=" * 60)

    # Execute the graph
    final_state = graph.invoke(initial_state)

    # Summary report
    logger.info("=" * 60)
    generated = final_state.get("generated_files", [])
    failed    = final_state.get("failed_tests", [])

    logger.info(f"✅ Generated tests ({len(generated)}):")
    for f in generated:
        logger.info(f"   {f}")

    if failed:
        logger.warning(f"❌ Failed tests ({len(failed)}):")
        for ft in failed:
            logger.warning(f"   {ft['test'].get('test_title')} — {ft['reason'][:80]}")

    # Write summary JSON
    summary_path = Path("run_summary.json")
    with open(summary_path, "w") as f:
        json.dump({
            "generated_files": generated,
            "failed_tests": [
                {"title": ft["test"].get("test_title"), "reason": ft["reason"][:200]}
                for ft in failed
            ]
        }, f, indent=2)
    logger.info(f"Summary written → {summary_path}")


if __name__ == "__main__":
    main()
