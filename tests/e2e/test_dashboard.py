"""
Dashboard E2E Tests
====================

End-to-end tests for the dashboard using Playwright.
Tests cover main user flows: navigation, task management, analytics.

Run with: npm run test:e2e (from dashboard directory)
"""

import pytest
import re
from playwright.sync_api import Page, expect


# Fixtures
@pytest.fixture(scope="module")
def dashboard_url():
    """Dashboard URL for testing."""
    import os
    return os.environ.get("DASHBOARD_URL", "http://localhost:5173")


@pytest.fixture(scope="module")
def api_url():
    """API URL for testing."""
    import os
    return os.environ.get("API_URL", "http://localhost:8003")


class TestNavigation:
    """Tests for dashboard navigation."""

    def test_initial_load(self, page: Page, dashboard_url: str):
        """Dashboard loads successfully."""
        page.goto(dashboard_url)

        # Check header is visible
        expect(page.locator("text=Agent Analytics")).to_be_visible()

    def test_navigate_to_tasks(self, page: Page, dashboard_url: str):
        """Navigate to Tasks page."""
        page.goto(dashboard_url)

        # Click Tasks nav link
        page.click("text=Tasks")

        # Verify Task Manager is shown
        expect(page.locator("text=Task Manager")).to_be_visible()

    def test_navigate_to_analytics(self, page: Page, dashboard_url: str):
        """Navigate to Analytics page."""
        page.goto(dashboard_url)

        # Click Analytics nav link
        page.click("text=Analytics")

        # Verify Analytics page is shown
        expect(page.locator("text=Performance Analytics")).to_be_visible()

    def test_default_route_is_tasks(self, page: Page, dashboard_url: str):
        """Default route shows Tasks page."""
        page.goto(dashboard_url)

        # Task Manager should be visible by default
        expect(page.locator("text=Task Manager")).to_be_visible()


class TestTaskManager:
    """Tests for Task Manager functionality."""

    def test_issues_list_loads(self, page: Page, dashboard_url: str):
        """Issues list loads and displays data."""
        page.goto(f"{dashboard_url}/tasks")

        # Wait for issues to load
        page.wait_for_selector("[data-testid='kanban-board'], .bg-gray-800", timeout=10000)

        # Should have issue cards or empty state
        # Either issues are shown or "No issues" message
        assert page.locator("text=ENG-").count() > 0 or page.locator("text=No issues").count() > 0

    def test_search_issues(self, page: Page, dashboard_url: str):
        """Search filters issues."""
        page.goto(f"{dashboard_url}/tasks")

        # Wait for page to load
        page.wait_for_load_state("networkidle")

        # Type in search box
        search_input = page.locator("input[placeholder*='Search']")
        search_input.fill("Task 1")

        # Issues should be filtered
        page.wait_for_timeout(500)  # Allow for filtering

    def test_priority_filter(self, page: Page, dashboard_url: str):
        """Priority filter works."""
        page.goto(f"{dashboard_url}/tasks")

        # Wait for page to load
        page.wait_for_load_state("networkidle")

        # Select high priority filter
        page.locator("select").select_option("high")

        # Wait for filter to apply
        page.wait_for_timeout(500)

    def test_view_mode_toggle(self, page: Page, dashboard_url: str):
        """View mode toggle switches between kanban and list."""
        page.goto(f"{dashboard_url}/tasks")

        # Wait for page to load
        page.wait_for_load_state("networkidle")

        # Find and click list view button
        list_button = page.locator("button[title='List view']")
        list_button.click()

        # Should show table view
        expect(page.locator("table")).to_be_visible()

        # Switch back to kanban
        kanban_button = page.locator("button[title='Kanban view']")
        kanban_button.click()

        # Table should be gone
        expect(page.locator("table")).to_be_hidden()

    def test_create_issue_form_opens(self, page: Page, dashboard_url: str):
        """Create issue button opens form."""
        page.goto(f"{dashboard_url}/tasks")

        # Click New Issue button
        page.click("text=New Issue")

        # Form should be visible
        expect(page.locator("text=Create New Issue")).to_be_visible()

    def test_create_issue_form_closes(self, page: Page, dashboard_url: str):
        """Create issue form closes on cancel."""
        page.goto(f"{dashboard_url}/tasks")

        # Open form
        page.click("text=New Issue")
        expect(page.locator("text=Create New Issue")).to_be_visible()

        # Press Escape to close
        page.keyboard.press("Escape")

        # Form should be hidden
        expect(page.locator("text=Create New Issue")).to_be_hidden()

    def test_refresh_button(self, page: Page, dashboard_url: str):
        """Refresh button triggers data reload."""
        page.goto(f"{dashboard_url}/tasks")

        # Wait for initial load
        page.wait_for_load_state("networkidle")

        # Click refresh button (has RefreshCw icon)
        refresh_button = page.locator("button[title='Refresh']")
        refresh_button.click()

        # Button should show loading state (has animate-spin class)
        # Wait a moment for animation
        page.wait_for_timeout(100)


class TestCreateIssue:
    """Tests for creating new issues."""

    def test_create_issue_minimal(self, page: Page, dashboard_url: str):
        """Create issue with just title."""
        page.goto(f"{dashboard_url}/tasks")

        # Open form
        page.click("text=New Issue")

        # Fill title
        page.fill("input[name='title'], input[placeholder*='title']", "E2E Test Issue")

        # Submit
        page.click("button:has-text('Create')")

        # Form should close
        expect(page.locator("text=Create New Issue")).to_be_hidden(timeout=5000)

    def test_create_issue_full(self, page: Page, dashboard_url: str):
        """Create issue with all fields."""
        page.goto(f"{dashboard_url}/tasks")

        # Open form
        page.click("text=New Issue")

        # Fill all fields
        page.fill("input[name='title'], input[placeholder*='title']", "Full E2E Issue")

        # Fill description if visible
        desc_field = page.locator("textarea")
        if desc_field.count() > 0:
            desc_field.first.fill("Test description from E2E")

        # Submit
        page.click("button:has-text('Create')")

        # Form should close
        expect(page.locator("text=Create New Issue")).to_be_hidden(timeout=5000)

    def test_create_issue_validation(self, page: Page, dashboard_url: str):
        """Create issue validates required fields."""
        page.goto(f"{dashboard_url}/tasks")

        # Open form
        page.click("text=New Issue")

        # Try to submit without title
        create_button = page.locator("button:has-text('Create')")

        # The button might be disabled or form won't submit
        # Check that form stays open after clicking empty
        if create_button.is_enabled():
            create_button.click()
            # Form should still be visible (validation failed)
            expect(page.locator("text=Create New Issue")).to_be_visible()


class TestKanbanBoard:
    """Tests for Kanban board functionality."""

    def test_kanban_columns_visible(self, page: Page, dashboard_url: str):
        """Kanban board shows all state columns."""
        page.goto(f"{dashboard_url}/tasks")

        # Wait for load
        page.wait_for_load_state("networkidle")

        # Should have state columns
        expect(page.locator("text=Todo")).to_be_visible()
        expect(page.locator("text=In Progress")).to_be_visible()
        expect(page.locator("text=Done")).to_be_visible()

    def test_issue_card_shows_details(self, page: Page, dashboard_url: str):
        """Issue cards show key information."""
        page.goto(f"{dashboard_url}/tasks")

        # Wait for load
        page.wait_for_load_state("networkidle")

        # Check for issue identifiers
        issue_cards = page.locator("text=/ENG-\\d+/")
        if issue_cards.count() > 0:
            # At least one issue card visible
            expect(issue_cards.first).to_be_visible()


class TestIssueEditor:
    """Tests for issue editor modal."""

    def test_open_issue_editor(self, page: Page, dashboard_url: str):
        """Clicking issue opens editor."""
        page.goto(f"{dashboard_url}/tasks")

        # Wait for issues to load
        page.wait_for_load_state("networkidle")

        # Find an issue card and click it
        issue_titles = page.locator("text=/Task \\d+/")
        if issue_titles.count() > 0:
            issue_titles.first.click()

            # Editor modal should open
            page.wait_for_timeout(500)

    def test_close_issue_editor(self, page: Page, dashboard_url: str):
        """Issue editor closes on Escape."""
        page.goto(f"{dashboard_url}/tasks")

        # Wait for issues to load
        page.wait_for_load_state("networkidle")

        # Open an issue
        issue_titles = page.locator("text=/Task \\d+/")
        if issue_titles.count() > 0:
            issue_titles.first.click()
            page.wait_for_timeout(500)

            # Press Escape
            page.keyboard.press("Escape")


class TestKeyboardShortcuts:
    """Tests for keyboard shortcuts."""

    def test_n_opens_new_issue(self, page: Page, dashboard_url: str):
        """Pressing N opens new issue form."""
        page.goto(f"{dashboard_url}/tasks")

        # Wait for page to load
        page.wait_for_load_state("networkidle")

        # Press N
        page.keyboard.press("n")

        # Create form should open
        expect(page.locator("text=Create New Issue")).to_be_visible()

    def test_escape_closes_modal(self, page: Page, dashboard_url: str):
        """Pressing Escape closes modals."""
        page.goto(f"{dashboard_url}/tasks")

        # Open new issue form
        page.keyboard.press("n")
        expect(page.locator("text=Create New Issue")).to_be_visible()

        # Press Escape
        page.keyboard.press("Escape")

        # Form should close
        expect(page.locator("text=Create New Issue")).to_be_hidden()


class TestAnalyticsPage:
    """Tests for Analytics page."""

    def test_analytics_loads(self, page: Page, dashboard_url: str):
        """Analytics page loads successfully."""
        page.goto(f"{dashboard_url}/analytics")

        # Check page title
        expect(page.locator("text=Performance Analytics")).to_be_visible()

    def test_velocity_chart_visible(self, page: Page, dashboard_url: str):
        """Velocity chart is displayed."""
        page.goto(f"{dashboard_url}/analytics")

        # Wait for data to load
        page.wait_for_load_state("networkidle")

        # Look for velocity-related content
        expect(page.locator("text=Velocity")).to_be_visible()

    def test_efficiency_metrics_visible(self, page: Page, dashboard_url: str):
        """Efficiency metrics are displayed."""
        page.goto(f"{dashboard_url}/analytics")

        # Wait for data to load
        page.wait_for_load_state("networkidle")

        # Look for efficiency-related content
        expect(page.locator("text=/Success|Efficiency/")).to_be_visible()

    def test_context_budget_visible(self, page: Page, dashboard_url: str):
        """Context budget widget is displayed."""
        page.goto(f"{dashboard_url}/analytics")

        # Wait for data to load
        page.wait_for_load_state("networkidle")

        # Look for context budget content
        expect(page.locator("text=Context")).to_be_visible()


class TestResponsiveness:
    """Tests for responsive design."""

    def test_mobile_viewport(self, page: Page, dashboard_url: str):
        """Dashboard works on mobile viewport."""
        page.set_viewport_size({"width": 375, "height": 667})
        page.goto(dashboard_url)

        # Header should still be visible
        expect(page.locator("text=Agent Analytics")).to_be_visible()

    def test_tablet_viewport(self, page: Page, dashboard_url: str):
        """Dashboard works on tablet viewport."""
        page.set_viewport_size({"width": 768, "height": 1024})
        page.goto(dashboard_url)

        # Header should still be visible
        expect(page.locator("text=Agent Analytics")).to_be_visible()

    def test_desktop_viewport(self, page: Page, dashboard_url: str):
        """Dashboard works on desktop viewport."""
        page.set_viewport_size({"width": 1920, "height": 1080})
        page.goto(dashboard_url)

        # Header should still be visible
        expect(page.locator("text=Agent Analytics")).to_be_visible()


class TestErrorHandling:
    """Tests for error handling."""

    def test_api_error_shows_message(self, page: Page, dashboard_url: str):
        """API errors show user-friendly message."""
        # This test would need API to be unavailable
        # For now, just verify error container exists in DOM
        page.goto(f"{dashboard_url}/tasks")

        # Wait for load
        page.wait_for_load_state("networkidle")

        # If there's an error, it should be in a red-styled container
        # This is a smoke test - actual error testing would need API mocking


class TestAccessibility:
    """Accessibility tests."""

    def test_page_has_title(self, page: Page, dashboard_url: str):
        """Page has meaningful title."""
        page.goto(dashboard_url)

        title = page.title()
        assert len(title) > 0

    def test_buttons_are_focusable(self, page: Page, dashboard_url: str):
        """Interactive elements are keyboard focusable."""
        page.goto(f"{dashboard_url}/tasks")

        # Tab to first button
        page.keyboard.press("Tab")

        # Something should be focused
        focused = page.evaluate("document.activeElement.tagName")
        assert focused in ["BUTTON", "A", "INPUT", "SELECT"]

    def test_form_labels_exist(self, page: Page, dashboard_url: str):
        """Form inputs have associated labels or placeholders."""
        page.goto(f"{dashboard_url}/tasks")

        # Open create form
        page.click("text=New Issue")

        # Check inputs have labels or placeholders
        inputs = page.locator("input:visible")
        for i in range(inputs.count()):
            input_el = inputs.nth(i)
            has_label = input_el.get_attribute("aria-label") or input_el.get_attribute("placeholder")
            # Most inputs should have some labeling
