"""
utils/csv_parser.py
Reads the Test_Cases.csv and returns a list of test case dicts.
"""

import pandas as pd
from pathlib import Path


def load_test_cases(csv_path: str) -> list[dict]:
    """
    Load and validate the test cases CSV file.

    Expected columns:
        id, test_title, steps, expected_result

    Returns:
        List of dicts, one per test case.
    """
    path = Path(csv_path)
    if not path.exists():
        raise FileNotFoundError(f"Test cases CSV not found: {csv_path}")

    df = pd.read_csv(path)

    required_columns = {"id", "test_title", "steps", "expected_result"}
    missing = required_columns - set(df.columns.str.lower())
    if missing:
        raise ValueError(f"CSV is missing required columns: {missing}")

    # Normalize column names to lowercase
    df.columns = df.columns.str.lower().str.strip()
    df = df.fillna("")

    return df.to_dict(orient="records")
