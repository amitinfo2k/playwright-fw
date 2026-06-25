"""
conftest.py
Playwright pytest fixtures shared across all generated tests.
"""

import os
import pytest
from dotenv import load_dotenv
from playwright.sync_api import Playwright, Browser, BrowserContext, Page

load_dotenv()


@pytest.fixture(scope="session")
def browser_type_launch_args():
    """Override Playwright launch args from environment."""
    return {
        "headless": os.getenv("HEADLESS", "true").lower() == "true",
        "slow_mo":  int(os.getenv("SLOW_MO", "0")),
    }


@pytest.fixture(scope="session")
def browser_context_args():
    """Set viewport and other browser context options."""
    return {
        "viewport": {"width": 1280, "height": 800},
        "record_video_dir": "test_videos/",
    }
