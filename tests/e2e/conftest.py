"""
Playwright E2E Test Configuration
===================================

Fixtures for Playwright E2E tests.
"""

import pytest
import os
from typing import Generator
from playwright.sync_api import Page, Browser, BrowserContext, Playwright


@pytest.fixture(scope="session")
def browser_context_args(browser_context_args):
    """Configure browser context."""
    return {
        **browser_context_args,
        "viewport": {"width": 1280, "height": 720},
        "ignore_https_errors": True,
    }


@pytest.fixture(scope="session")
def browser_type_launch_args(browser_type_launch_args):
    """Configure browser launch arguments."""
    return {
        **browser_type_launch_args,
        "headless": os.environ.get("HEADLESS", "true").lower() == "true",
        "slow_mo": int(os.environ.get("SLOW_MO", "0")),
    }


@pytest.fixture
def dashboard_url() -> str:
    """Dashboard URL for E2E tests."""
    return os.environ.get("DASHBOARD_URL", "http://localhost:5173")


@pytest.fixture
def api_url() -> str:
    """API URL for E2E tests."""
    return os.environ.get("API_URL", "http://localhost:8003")


@pytest.fixture(autouse=True)
def setup_page(page: Page, dashboard_url: str):
    """Setup before each test."""
    # Clear any existing state
    page.goto(dashboard_url)
    page.wait_for_load_state("domcontentloaded")

    yield

    # Cleanup after test
    # Take screenshot on failure is handled by pytest-playwright


@pytest.fixture
def authenticated_page(page: Page, dashboard_url: str) -> Page:
    """Page with authentication (if needed in future)."""
    # Currently no auth required, but hook for future
    page.goto(dashboard_url)
    return page


# Screenshot on failure hook
@pytest.hookimpl(tryfirst=True, hookwrapper=True)
def pytest_runtest_makereport(item, call):
    """Take screenshot on test failure."""
    outcome = yield
    report = outcome.get_result()

    if report.when == "call" and report.failed:
        page = item.funcargs.get("page")
        if page:
            screenshot_dir = os.path.join(
                os.path.dirname(os.path.dirname(os.path.dirname(__file__))),
                "screenshots"
            )
            os.makedirs(screenshot_dir, exist_ok=True)

            screenshot_path = os.path.join(
                screenshot_dir,
                f"failure-{item.name}.png"
            )
            try:
                page.screenshot(path=screenshot_path)
                print(f"\nScreenshot saved: {screenshot_path}")
            except Exception as e:
                print(f"\nFailed to capture screenshot: {e}")
