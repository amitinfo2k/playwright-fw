"""
utils/code_writer.py
Writes a generated Playwright test script to the generated_tests/ directory.
"""

import os
from pathlib import Path


OUTPUT_DIR = Path(__file__).parent.parent / "generated_tests"


def write_test_file(test_id: str, test_title: str, code: str) -> str:
    """
    Write the generated Playwright code to a .py file.

    Args:
        test_id:    The id from the CSV (e.g., "1")
        test_title: The test title (used for filename)
        code:       Full TypeScript source code string

    Returns:
        Absolute path to the written file.
    """
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

    # Create a filesystem-safe filename
    safe_title = "".join(c if c.isalnum() or c in "-_" else "_" for c in test_title)
    filename = f"test_{test_id}_{safe_title}.spec.ts"
    file_path = OUTPUT_DIR / filename

    with open(file_path, "w", encoding="utf-8") as f:
        f.write(code)

    return str(file_path)
