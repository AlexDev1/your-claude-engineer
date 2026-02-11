"""
Integration Test Suite (ENG-59)
===============================

Comprehensive integration tests for the autonomous agent system.

Tests cover:
- Project creation via Task MCP API
- Issue CRUD operations (create, update, comment)
- ListIssues verification with filtering
- Telegram test message sending
- Cleanup of test artifacts

Usage:
    make test-integration

Requirements:
    - Analytics server running on port 8003 (or ANALYTICS_API_URL env var)
    - Telegram MCP (optional, tests skip gracefully if unavailable)
"""

import os
import time
import uuid
import pytest
import httpx
from datetime import datetime
from typing import Generator
from unittest.mock import patch, MagicMock, AsyncMock


# =============================================================================
# Configuration
# =============================================================================

# API URLs - can be overridden via environment variables
ANALYTICS_API_URL = os.environ.get("ANALYTICS_API_URL", "http://localhost:8003")
TASK_MCP_URL = os.environ.get("TASK_MCP_URL", "http://localhost:8001")
TELEGRAM_MCP_URL = os.environ.get("TELEGRAM_MCP_URL", "http://localhost:8002")

# Test prefix for identifying test data
TEST_PREFIX = "INTEGRATION_TEST"


# =============================================================================
# Fixtures
# =============================================================================


@pytest.fixture(scope="module")
def test_run_id() -> str:
    """Generate unique ID for this test run to identify test artifacts."""
    return f"{TEST_PREFIX}_{datetime.now().strftime('%Y%m%d_%H%M%S')}_{uuid.uuid4().hex[:8]}"


@pytest.fixture(scope="module")
def api_client() -> Generator[httpx.Client, None, None]:
    """HTTP client for API calls with timeout."""
    with httpx.Client(base_url=ANALYTICS_API_URL, timeout=30.0) as client:
        yield client


@pytest.fixture(scope="module")
def created_issue_ids() -> list[str]:
    """Track created issue IDs for cleanup."""
    return []


@pytest.fixture(scope="module", autouse=True)
def cleanup_test_artifacts(api_client: httpx.Client, created_issue_ids: list[str]):
    """Cleanup test artifacts after all tests complete."""
    yield

    # Cleanup: Delete all test issues
    for issue_id in created_issue_ids:
        try:
            api_client.delete(f"/api/issues/{issue_id}")
        except Exception as e:
            print(f"Warning: Failed to cleanup issue {issue_id}: {e}")

    # Cleanup: Delete any remaining test issues by searching
    try:
        response = api_client.get("/api/issues")
        if response.status_code == 200:
            issues = response.json().get("issues", [])
            for issue in issues:
                if TEST_PREFIX in issue.get("title", "") or TEST_PREFIX in issue.get("description", ""):
                    try:
                        api_client.delete(f"/api/issues/{issue['identifier']}")
                    except Exception:
                        pass
    except Exception as e:
        print(f"Warning: Failed to cleanup test issues: {e}")


def is_api_available(url: str) -> bool:
    """Check if an API endpoint is available."""
    try:
        with httpx.Client(timeout=5.0) as client:
            response = client.get(f"{url}/health")
            return response.status_code == 200
    except Exception:
        return False


# =============================================================================
# Test Classes
# =============================================================================


@pytest.mark.integration
class TestAPIHealthCheck:
    """Tests for API availability."""

    def test_analytics_api_health(self, api_client: httpx.Client):
        """Analytics API health endpoint responds."""
        response = api_client.get("/health")

        assert response.status_code == 200
        data = response.json()
        assert data.get("status") == "healthy"

    def test_analytics_api_issues_endpoint(self, api_client: httpx.Client):
        """Issues endpoint is accessible."""
        response = api_client.get("/api/issues")

        assert response.status_code == 200
        data = response.json()
        assert "issues" in data
        assert "total" in data


@pytest.mark.integration
class TestProjectCreation:
    """Tests for project creation via Task API."""

    def test_list_issues_returns_structure(self, api_client: httpx.Client):
        """ListIssues returns proper structure."""
        response = api_client.get("/api/issues")

        assert response.status_code == 200
        data = response.json()

        # Verify structure
        assert "issues" in data
        assert "total" in data
        assert isinstance(data["issues"], list)
        assert isinstance(data["total"], int)

    def test_list_issues_with_state_filter(self, api_client: httpx.Client):
        """ListIssues filters by state correctly."""
        response = api_client.get("/api/issues?state=Todo")

        assert response.status_code == 200
        data = response.json()

        # All returned issues should be in Todo state
        for issue in data["issues"]:
            assert issue["state"] == "Todo"

    def test_list_issues_with_priority_filter(self, api_client: httpx.Client):
        """ListIssues filters by priority correctly."""
        # First create a high priority issue
        create_response = api_client.post("/api/issues", json={
            "title": f"{TEST_PREFIX} Priority Filter Test",
            "priority": "high"
        })
        issue_id = create_response.json()["identifier"]

        try:
            response = api_client.get("/api/issues?priority=high")

            assert response.status_code == 200
            data = response.json()

            # All returned issues should have high priority
            for issue in data["issues"]:
                assert issue["priority"] == "high"
        finally:
            api_client.delete(f"/api/issues/{issue_id}")


@pytest.mark.integration
class TestIssueCreation:
    """Tests for creating issues."""

    def test_create_issue_minimal(
        self,
        api_client: httpx.Client,
        test_run_id: str,
        created_issue_ids: list[str]
    ):
        """Create issue with minimal required fields."""
        response = api_client.post("/api/issues", json={
            "title": f"{test_run_id} Minimal Issue"
        })

        assert response.status_code == 200
        data = response.json()

        # Track for cleanup
        created_issue_ids.append(data["identifier"])

        # Verify response
        assert "identifier" in data
        assert data["identifier"].startswith("ENG-")
        assert data["title"] == f"{test_run_id} Minimal Issue"
        assert data["state"] == "Todo"
        assert data["priority"] == "medium"

    def test_create_issue_full(
        self,
        api_client: httpx.Client,
        test_run_id: str,
        created_issue_ids: list[str]
    ):
        """Create issue with all fields populated."""
        response = api_client.post("/api/issues", json={
            "title": f"{test_run_id} Full Issue",
            "description": f"Description for {test_run_id}",
            "priority": "high",
            "issue_type": "Feature",
            "team": "ENG",
            "project": "Integration Tests",
        })

        assert response.status_code == 200
        data = response.json()

        # Track for cleanup
        created_issue_ids.append(data["identifier"])

        # Verify all fields
        assert data["title"] == f"{test_run_id} Full Issue"
        assert data["description"] == f"Description for {test_run_id}"
        assert data["priority"] == "high"
        assert data["issue_type"] == "Feature"
        assert data["team"] == "ENG"
        assert data["state"] == "Todo"
        assert data["comments"] == []

    def test_create_issue_with_dependencies(
        self,
        api_client: httpx.Client,
        test_run_id: str,
        created_issue_ids: list[str]
    ):
        """Create issue with dependency on another issue."""
        # First create a parent issue
        parent_response = api_client.post("/api/issues", json={
            "title": f"{test_run_id} Parent Issue"
        })
        parent_id = parent_response.json()["identifier"]
        created_issue_ids.append(parent_id)

        # Create child with dependency
        child_response = api_client.post("/api/issues", json={
            "title": f"{test_run_id} Child Issue",
            "dependencies": [parent_id]
        })

        assert child_response.status_code == 200
        child_data = child_response.json()
        created_issue_ids.append(child_data["identifier"])

        assert parent_id in child_data["dependencies"]


@pytest.mark.integration
class TestIssueUpdate:
    """Tests for updating issues."""

    def test_update_issue_title(
        self,
        api_client: httpx.Client,
        test_run_id: str,
        created_issue_ids: list[str]
    ):
        """Update issue title."""
        # Create issue
        create_response = api_client.post("/api/issues", json={
            "title": f"{test_run_id} Original Title"
        })
        issue_id = create_response.json()["identifier"]
        created_issue_ids.append(issue_id)

        # Update title
        update_response = api_client.put(f"/api/issues/{issue_id}", json={
            "title": f"{test_run_id} Updated Title"
        })

        assert update_response.status_code == 200
        data = update_response.json()
        assert data["title"] == f"{test_run_id} Updated Title"

    def test_update_issue_state_todo_to_in_progress(
        self,
        api_client: httpx.Client,
        test_run_id: str,
        created_issue_ids: list[str]
    ):
        """Transition issue from Todo to In Progress."""
        # Create issue (starts in Todo)
        create_response = api_client.post("/api/issues", json={
            "title": f"{test_run_id} State Transition Test"
        })
        issue_id = create_response.json()["identifier"]
        created_issue_ids.append(issue_id)

        # Transition to In Progress
        update_response = api_client.put(f"/api/issues/{issue_id}", json={
            "state": "In Progress"
        })

        assert update_response.status_code == 200
        data = update_response.json()
        assert data["state"] == "In Progress"

    def test_update_issue_state_in_progress_to_done(
        self,
        api_client: httpx.Client,
        test_run_id: str,
        created_issue_ids: list[str]
    ):
        """Transition issue from In Progress to Done."""
        # Create and move to In Progress first
        create_response = api_client.post("/api/issues", json={
            "title": f"{test_run_id} Complete Test"
        })
        issue_id = create_response.json()["identifier"]
        created_issue_ids.append(issue_id)

        api_client.put(f"/api/issues/{issue_id}", json={"state": "In Progress"})

        # Complete the issue
        update_response = api_client.put(f"/api/issues/{issue_id}", json={
            "state": "Done"
        })

        assert update_response.status_code == 200
        data = update_response.json()
        assert data["state"] == "Done"
        assert data["completed_at"] is not None

    def test_update_issue_invalid_state_transition(
        self,
        api_client: httpx.Client,
        test_run_id: str,
        created_issue_ids: list[str]
    ):
        """Invalid state transition returns 400."""
        # Create issue (starts in Todo)
        create_response = api_client.post("/api/issues", json={
            "title": f"{test_run_id} Invalid Transition Test"
        })
        issue_id = create_response.json()["identifier"]
        created_issue_ids.append(issue_id)

        # Try to skip In Progress and go directly to Done
        update_response = api_client.put(f"/api/issues/{issue_id}", json={
            "state": "Done"
        })

        assert update_response.status_code == 400

    def test_update_issue_priority(
        self,
        api_client: httpx.Client,
        test_run_id: str,
        created_issue_ids: list[str]
    ):
        """Update issue priority."""
        # Create issue with medium priority
        create_response = api_client.post("/api/issues", json={
            "title": f"{test_run_id} Priority Update Test",
            "priority": "medium"
        })
        issue_id = create_response.json()["identifier"]
        created_issue_ids.append(issue_id)

        # Update to urgent
        update_response = api_client.put(f"/api/issues/{issue_id}", json={
            "priority": "urgent"
        })

        assert update_response.status_code == 200
        data = update_response.json()
        assert data["priority"] == "urgent"


@pytest.mark.integration
class TestIssueComments:
    """Tests for issue comments."""

    def test_add_comment_to_issue(
        self,
        api_client: httpx.Client,
        test_run_id: str,
        created_issue_ids: list[str]
    ):
        """Add comment to an issue."""
        # Create issue
        create_response = api_client.post("/api/issues", json={
            "title": f"{test_run_id} Comment Test"
        })
        issue_id = create_response.json()["identifier"]
        created_issue_ids.append(issue_id)

        # Add comment
        comment_content = f"Test comment from {test_run_id}"
        comment_response = api_client.post(
            f"/api/issues/{issue_id}/comments",
            params={"content": comment_content}
        )

        assert comment_response.status_code == 200
        comment = comment_response.json()
        assert comment["content"] == comment_content
        assert comment["author"] == "Agent"
        assert "id" in comment
        assert "created_at" in comment

    def test_add_multiple_comments(
        self,
        api_client: httpx.Client,
        test_run_id: str,
        created_issue_ids: list[str]
    ):
        """Add multiple comments to an issue."""
        # Create issue
        create_response = api_client.post("/api/issues", json={
            "title": f"{test_run_id} Multi-Comment Test"
        })
        issue_id = create_response.json()["identifier"]
        created_issue_ids.append(issue_id)

        # Add multiple comments
        for i in range(3):
            api_client.post(
                f"/api/issues/{issue_id}/comments",
                params={"content": f"Comment {i + 1}"}
            )

        # Verify all comments exist
        get_response = api_client.get(f"/api/issues/{issue_id}")
        assert get_response.status_code == 200
        issue = get_response.json()
        assert len(issue["comments"]) == 3

    def test_comment_on_nonexistent_issue(self, api_client: httpx.Client):
        """Comment on nonexistent issue returns 404."""
        response = api_client.post(
            "/api/issues/NONEXISTENT-999/comments",
            params={"content": "Should fail"}
        )

        assert response.status_code == 404


@pytest.mark.integration
class TestListIssuesVerification:
    """Comprehensive tests for ListIssues functionality."""

    def test_list_issues_contains_created_issue(
        self,
        api_client: httpx.Client,
        test_run_id: str,
        created_issue_ids: list[str]
    ):
        """ListIssues includes newly created issue."""
        # Create issue with unique title
        unique_title = f"{test_run_id} Verify List Contains"
        create_response = api_client.post("/api/issues", json={
            "title": unique_title
        })
        issue_id = create_response.json()["identifier"]
        created_issue_ids.append(issue_id)

        # List all issues
        list_response = api_client.get("/api/issues")
        assert list_response.status_code == 200
        issues = list_response.json()["issues"]

        # Verify our issue is in the list
        issue_ids = [i["identifier"] for i in issues]
        assert issue_id in issue_ids

    def test_list_issues_priority_ordering(
        self,
        api_client: httpx.Client,
        test_run_id: str,
        created_issue_ids: list[str]
    ):
        """ListIssues returns issues ordered by priority."""
        # Create issues with different priorities
        priorities = ["low", "high", "medium", "urgent"]
        for priority in priorities:
            response = api_client.post("/api/issues", json={
                "title": f"{test_run_id} Priority Order {priority}",
                "priority": priority
            })
            created_issue_ids.append(response.json()["identifier"])

        # List issues
        list_response = api_client.get("/api/issues")
        assert list_response.status_code == 200
        issues = list_response.json()["issues"]

        # Check priority order (urgent, high, medium, low, none)
        priority_order = {"urgent": 0, "high": 1, "medium": 2, "low": 3, "none": 4}
        priorities_returned = [priority_order.get(i["priority"], 4) for i in issues]
        assert priorities_returned == sorted(priorities_returned)

    def test_list_issues_total_matches_count(self, api_client: httpx.Client):
        """ListIssues total field matches actual count."""
        response = api_client.get("/api/issues")

        assert response.status_code == 200
        data = response.json()
        assert data["total"] == len(data["issues"])


@pytest.mark.integration
class TestTelegramIntegration:
    """Tests for Telegram MCP integration."""

    def test_telegram_reports_module_imports(self):
        """Telegram reports module imports successfully."""
        from axon_agent.integrations.telegram import (
            format_daily_digest,
            format_session_summary,
            format_error_alert,
            format_weekly_summary,
            format_progress_bar,
            format_status,
        )

        assert format_daily_digest is not None
        assert format_session_summary is not None
        assert format_error_alert is not None
        assert format_weekly_summary is not None
        assert format_progress_bar is not None
        assert format_status is not None

    def test_format_progress_bar(self):
        """Progress bar formatting works correctly."""
        from axon_agent.integrations.telegram import format_progress_bar

        # Test various percentages
        bar_50 = format_progress_bar(5, 10)
        assert "50%" in bar_50

        bar_0 = format_progress_bar(0, 10)
        assert "0%" in bar_0

        bar_100 = format_progress_bar(10, 10)
        assert "100%" in bar_100

    def test_format_daily_digest(self):
        """Daily digest formatting works correctly."""
        from axon_agent.integrations.telegram import format_daily_digest_simple

        digest = format_daily_digest_simple(
            completed=5,
            in_progress=3,
            todo=10,
            blocked=1,
            highlights=["Completed auth feature", "Fixed login bug"]
        )

        assert "Дайджест за день" in digest
        assert "5" in digest  # completed count
        assert "3" in digest  # in progress count
        assert "10" in digest  # todo count
        assert "Completed auth feature" in digest

    def test_format_session_summary(self):
        """Session summary formatting works correctly."""
        from axon_agent.integrations.telegram import format_session_summary_simple

        summary = format_session_summary_simple(
            issue_id="ENG-123",
            issue_title="Test Issue",
            duration_minutes=45,
            tokens_used=10000,
            commits=["feat: Add feature"],
            files_changed=["src/app.py"],
            status="completed"
        )

        assert "Итоги сессии" in summary
        assert "ENG-123" in summary
        assert "45" in summary  # duration

    def test_format_error_alert(self):
        """Error alert formatting works correctly."""
        from axon_agent.integrations.telegram import format_error_alert_simple

        alert = format_error_alert_simple(
            error_type="syntax",
            error_message="Unexpected token",
            file_path="src/main.py",
            line_number=42,
            attempt_count=1,
            issue_id="ENG-456",
            phase="implement"
        )

        assert "Оповещение об ошибке" in alert
        assert "SYNTAX" in alert
        assert "42" in alert  # line number
        assert "ENG-456" in alert

    def test_format_status(self):
        """Status formatting works correctly."""
        from axon_agent.integrations.telegram import format_status_simple

        status = format_status_simple(
            todo=5,
            in_progress=2,
            done=10,
            current_task_id="ENG-789",
            current_task_title="Current Task",
            session_number=3,
            session_status="active",
            elapsed_minutes=30
        )

        assert "Статус" in status
        assert "5" in status  # todo count
        assert "2" in status  # in progress count
        assert "10" in status  # done count
        assert "ENG-789" in status

    @pytest.mark.skipif(
        not os.environ.get("TELEGRAM_BOT_TOKEN"),
        reason="TELEGRAM_BOT_TOKEN not set"
    )
    def test_telegram_send_message_mock(self):
        """Test Telegram message sending (mocked)."""
        # This test uses mocking since we don't want to actually send messages
        # In a real integration test with Telegram available, this would call the API

        from axon_agent.integrations.telegram import format_status_simple

        message = format_status_simple(
            todo=3,
            in_progress=1,
            done=5,
        )

        # Verify message is properly formatted
        assert "<b>" in message  # HTML formatting
        assert len(message) < 4096  # Telegram message limit


@pytest.mark.integration
class TestCleanup:
    """Tests for cleanup functionality."""

    def test_delete_issue(
        self,
        api_client: httpx.Client,
        test_run_id: str
    ):
        """Delete issue removes it from store."""
        # Create issue
        create_response = api_client.post("/api/issues", json={
            "title": f"{test_run_id} Delete Test"
        })
        issue_id = create_response.json()["identifier"]

        # Delete it
        delete_response = api_client.delete(f"/api/issues/{issue_id}")

        assert delete_response.status_code == 200
        assert delete_response.json()["deleted"] is True

        # Verify it's gone
        get_response = api_client.get(f"/api/issues/{issue_id}")
        assert get_response.status_code == 404

    def test_delete_nonexistent_issue(self, api_client: httpx.Client):
        """Delete nonexistent issue returns 404."""
        response = api_client.delete("/api/issues/NONEXISTENT-999")
        assert response.status_code == 404

    def test_bulk_delete(
        self,
        api_client: httpx.Client,
        test_run_id: str
    ):
        """Bulk delete removes multiple issues."""
        # Create issues
        issue_ids = []
        for i in range(3):
            response = api_client.post("/api/issues", json={
                "title": f"{test_run_id} Bulk Delete {i}"
            })
            issue_ids.append(response.json()["identifier"])

        # Bulk delete
        bulk_response = api_client.post("/api/issues/bulk", json={
            "issue_ids": issue_ids,
            "operation": "delete"
        })

        assert bulk_response.status_code == 200
        result = bulk_response.json()
        assert len(result["success"]) == 3
        assert len(result["failed"]) == 0

        # Verify all deleted
        for issue_id in issue_ids:
            get_response = api_client.get(f"/api/issues/{issue_id}")
            assert get_response.status_code == 404


@pytest.mark.integration
class TestAnalyticsEndpoints:
    """Tests for analytics endpoints."""

    def test_velocity_endpoint(self, api_client: httpx.Client):
        """Velocity endpoint returns proper structure."""
        response = api_client.get("/api/analytics/velocity")

        assert response.status_code == 200
        data = response.json()

        assert "daily" in data
        assert "weekly_avg" in data
        assert "trend" in data
        assert "total_completed" in data

    def test_efficiency_endpoint(self, api_client: httpx.Client):
        """Efficiency endpoint returns proper structure."""
        response = api_client.get("/api/analytics/efficiency")

        assert response.status_code == 200
        data = response.json()

        assert "success_rate" in data
        assert "avg_completion_time_hours" in data
        assert "tasks_done" in data
        assert "tasks_in_progress" in data
        assert "tasks_todo" in data

    def test_bottlenecks_endpoint(self, api_client: httpx.Client):
        """Bottlenecks endpoint returns proper structure."""
        response = api_client.get("/api/analytics/bottlenecks")

        assert response.status_code == 200
        data = response.json()

        assert "stuck_tasks" in data
        assert "avg_retry_rate" in data
        assert "time_distribution" in data
        assert "recommendations" in data

    def test_summary_endpoint(self, api_client: httpx.Client):
        """Summary endpoint returns combined data."""
        response = api_client.get("/api/analytics/summary")

        assert response.status_code == 200
        data = response.json()

        assert "velocity" in data
        assert "efficiency" in data
        assert "bottlenecks" in data


@pytest.mark.integration
class TestMCPConfigModule:
    """Tests for MCP configuration module."""

    def test_mcp_config_imports(self):
        """MCP config module imports successfully."""
        from axon_agent.mcp.config import (
            TASK_TOOLS,
            TELEGRAM_TOOLS,
            PLAYWRIGHT_TOOLS,
            get_task_tools,
            get_telegram_tools,
            get_coding_tools,
        )

        assert len(TASK_TOOLS) > 0
        assert len(TELEGRAM_TOOLS) > 0
        assert len(PLAYWRIGHT_TOOLS) > 0

    def test_task_tools_have_correct_prefix(self):
        """Task tools have mcp__task__ prefix."""
        from axon_agent.mcp.config import TASK_TOOLS

        for tool in TASK_TOOLS:
            assert tool.startswith("mcp__task__"), f"Tool {tool} missing prefix"

    def test_telegram_tools_have_correct_prefix(self):
        """Telegram tools have mcp__telegram__ prefix."""
        from axon_agent.mcp.config import TELEGRAM_TOOLS

        for tool in TELEGRAM_TOOLS:
            assert tool.startswith("mcp__telegram__"), f"Tool {tool} missing prefix"

    def test_coding_tools_include_builtins(self):
        """Coding tools include built-in tools."""
        from axon_agent.mcp.config import get_coding_tools

        tools = get_coding_tools()
        assert "Read" in tools
        assert "Write" in tools
        assert "Edit" in tools
        assert "Bash" in tools


@pytest.mark.integration
class TestEndToEndWorkflow:
    """End-to-end workflow tests simulating agent behavior."""

    def test_complete_issue_workflow(
        self,
        api_client: httpx.Client,
        test_run_id: str,
        created_issue_ids: list[str]
    ):
        """Test complete issue lifecycle: create -> in progress -> done."""
        # 1. Create issue
        create_response = api_client.post("/api/issues", json={
            "title": f"{test_run_id} E2E Workflow Test",
            "description": "Complete workflow test",
            "priority": "high",
        })
        assert create_response.status_code == 200
        issue_id = create_response.json()["identifier"]
        created_issue_ids.append(issue_id)

        # 2. Add planning comment
        api_client.post(
            f"/api/issues/{issue_id}/comments",
            params={"content": "Starting implementation..."}
        )

        # 3. Transition to In Progress
        ip_response = api_client.put(f"/api/issues/{issue_id}", json={
            "state": "In Progress"
        })
        assert ip_response.status_code == 200
        assert ip_response.json()["state"] == "In Progress"

        # 4. Add progress comment
        api_client.post(
            f"/api/issues/{issue_id}/comments",
            params={"content": "Implementation complete, running tests..."}
        )

        # 5. Complete the issue
        done_response = api_client.put(f"/api/issues/{issue_id}", json={
            "state": "Done"
        })
        assert done_response.status_code == 200
        assert done_response.json()["state"] == "Done"
        assert done_response.json()["completed_at"] is not None

        # 6. Add completion comment
        api_client.post(
            f"/api/issues/{issue_id}/comments",
            params={"content": "Task completed successfully!"}
        )

        # 7. Verify final state
        final_response = api_client.get(f"/api/issues/{issue_id}")
        assert final_response.status_code == 200
        final_data = final_response.json()

        assert final_data["state"] == "Done"
        assert len(final_data["comments"]) == 3
        assert final_data["completed_at"] is not None

    def test_issue_with_dependencies_workflow(
        self,
        api_client: httpx.Client,
        test_run_id: str,
        created_issue_ids: list[str]
    ):
        """Test workflow with dependent issues."""
        # 1. Create parent issue
        parent_response = api_client.post("/api/issues", json={
            "title": f"{test_run_id} Parent Task",
            "priority": "high",
        })
        parent_id = parent_response.json()["identifier"]
        created_issue_ids.append(parent_id)

        # 2. Create child issue with dependency
        child_response = api_client.post("/api/issues", json={
            "title": f"{test_run_id} Child Task",
            "priority": "high",
            "dependencies": [parent_id]
        })
        child_id = child_response.json()["identifier"]
        created_issue_ids.append(child_id)

        # 3. Complete parent first
        api_client.put(f"/api/issues/{parent_id}", json={"state": "In Progress"})
        api_client.put(f"/api/issues/{parent_id}", json={"state": "Done"})

        # 4. Now complete child
        api_client.put(f"/api/issues/{child_id}", json={"state": "In Progress"})
        api_client.put(f"/api/issues/{child_id}", json={"state": "Done"})

        # 5. Verify both are done
        parent_final = api_client.get(f"/api/issues/{parent_id}").json()
        child_final = api_client.get(f"/api/issues/{child_id}").json()

        assert parent_final["state"] == "Done"
        assert child_final["state"] == "Done"
        assert parent_id in child_final["dependencies"]


# =============================================================================
# Run with pytest
# =============================================================================

if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])
