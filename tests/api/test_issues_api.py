"""
Issues API Tests
=================

Tests for the issue CRUD endpoints.
Coverage: create, read, update, delete, comments, bulk operations, undo.
"""

import pytest
from datetime import datetime
from unittest.mock import patch, MagicMock

import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(__file__))))

from analytics_server.server import (
    app,
    ISSUES_STORE,
    ISSUE_COUNTER,
    UNDO_STACK,
    initialize_issues_store,
)

from fastapi.testclient import TestClient


@pytest.fixture
def client():
    """Create FastAPI test client."""
    # Reset store before each test
    global ISSUES_STORE, UNDO_STACK
    ISSUES_STORE.clear()
    UNDO_STACK.clear()
    initialize_issues_store()
    return TestClient(app)


@pytest.fixture
def clean_store():
    """Reset the issues store."""
    global ISSUES_STORE, UNDO_STACK
    ISSUES_STORE.clear()
    UNDO_STACK.clear()


class TestListIssues:
    """Tests for listing issues."""

    def test_list_all_issues(self, client):
        """List issues returns all issues."""
        response = client.get("/api/issues")

        assert response.status_code == 200
        data = response.json()
        assert "issues" in data
        assert "total" in data
        assert data["total"] == len(data["issues"])

    def test_list_issues_filter_by_state(self, client):
        """List issues filters by state."""
        response = client.get("/api/issues?state=Done")

        assert response.status_code == 200
        data = response.json()
        for issue in data["issues"]:
            assert issue["state"] == "Done"

    def test_list_issues_filter_by_priority(self, client):
        """List issues filters by priority."""
        response = client.get("/api/issues?priority=high")

        assert response.status_code == 200
        data = response.json()
        for issue in data["issues"]:
            assert issue["priority"] == "high"

    def test_list_issues_sorted_by_priority(self, client):
        """List issues are sorted by priority."""
        response = client.get("/api/issues")

        assert response.status_code == 200
        data = response.json()
        issues = data["issues"]

        # Priority order: urgent, high, medium, low
        priority_order = {"urgent": 0, "high": 1, "medium": 2, "low": 3, "none": 4}
        priorities = [priority_order.get(i["priority"], 4) for i in issues]

        # Check that priorities are in ascending order
        assert priorities == sorted(priorities)


class TestGetIssue:
    """Tests for getting a single issue."""

    def test_get_existing_issue(self, client):
        """Get issue returns issue by ID."""
        # First, get list to find an existing issue
        list_response = client.get("/api/issues")
        issues = list_response.json()["issues"]
        if issues:
            issue_id = issues[0]["identifier"]

            response = client.get(f"/api/issues/{issue_id}")
            assert response.status_code == 200
            data = response.json()
            assert data["identifier"] == issue_id

    def test_get_nonexistent_issue(self, client):
        """Get issue returns 404 for unknown ID."""
        response = client.get("/api/issues/UNKNOWN-999")

        assert response.status_code == 404


class TestCreateIssue:
    """Tests for creating issues."""

    def test_create_issue_minimal(self, client):
        """Create issue with minimal data."""
        response = client.post("/api/issues", json={
            "title": "New Test Issue"
        })

        assert response.status_code == 200
        data = response.json()
        assert data["title"] == "New Test Issue"
        assert data["state"] == "Todo"
        assert data["priority"] == "medium"
        assert "identifier" in data
        assert data["identifier"].startswith("ENG-")

    def test_create_issue_full(self, client):
        """Create issue with all fields."""
        response = client.post("/api/issues", json={
            "title": "Full Test Issue",
            "description": "Detailed description",
            "priority": "high",
            "issue_type": "Feature",
            "team": "ENG",
            "project": "Test Project",
        })

        assert response.status_code == 200
        data = response.json()
        assert data["title"] == "Full Test Issue"
        assert data["description"] == "Detailed description"
        assert data["priority"] == "high"
        assert data["issue_type"] == "Feature"

    def test_create_issue_with_dependencies(self, client):
        """Create issue with dependencies."""
        # First create a parent issue
        parent_response = client.post("/api/issues", json={
            "title": "Parent Issue"
        })
        parent_id = parent_response.json()["identifier"]

        # Create issue with dependency
        response = client.post("/api/issues", json={
            "title": "Child Issue",
            "dependencies": [parent_id],
        })

        assert response.status_code == 200
        data = response.json()
        assert parent_id in data["dependencies"]

    def test_create_issue_adds_to_undo_stack(self, client):
        """Creating issue adds to undo stack."""
        global UNDO_STACK
        initial_stack_size = len(UNDO_STACK)

        client.post("/api/issues", json={"title": "Undo Test Issue"})

        assert len(UNDO_STACK) == initial_stack_size + 1
        assert UNDO_STACK[-1]["action"] == "create"


class TestUpdateIssue:
    """Tests for updating issues."""

    def test_update_issue_title(self, client):
        """Update issue title."""
        # Create an issue first
        create_response = client.post("/api/issues", json={"title": "Original Title"})
        issue_id = create_response.json()["identifier"]

        # Update it
        response = client.put(f"/api/issues/{issue_id}", json={
            "title": "Updated Title"
        })

        assert response.status_code == 200
        data = response.json()
        assert data["title"] == "Updated Title"

    def test_update_issue_state_valid_transition(self, client):
        """Update issue with valid state transition."""
        # Create an issue (starts in Todo)
        create_response = client.post("/api/issues", json={"title": "State Test"})
        issue_id = create_response.json()["identifier"]

        # Valid transition: Todo -> In Progress
        response = client.put(f"/api/issues/{issue_id}", json={
            "state": "In Progress"
        })

        assert response.status_code == 200
        assert response.json()["state"] == "In Progress"

    def test_update_issue_state_invalid_transition(self, client):
        """Update issue with invalid state transition fails."""
        # Create an issue (starts in Todo)
        create_response = client.post("/api/issues", json={"title": "Invalid State Test"})
        issue_id = create_response.json()["identifier"]

        # Invalid transition: Todo -> Done (should go through In Progress first)
        response = client.put(f"/api/issues/{issue_id}", json={
            "state": "Done"
        })

        assert response.status_code == 400

    def test_update_issue_to_done_sets_completed_at(self, client):
        """Completing issue sets completed_at timestamp."""
        # Create and move to In Progress first
        create_response = client.post("/api/issues", json={"title": "Complete Test"})
        issue_id = create_response.json()["identifier"]

        client.put(f"/api/issues/{issue_id}", json={"state": "In Progress"})

        # Now complete it
        response = client.put(f"/api/issues/{issue_id}", json={"state": "Done"})

        assert response.status_code == 200
        data = response.json()
        assert data["state"] == "Done"
        assert data["completed_at"] is not None

    def test_update_nonexistent_issue(self, client):
        """Update nonexistent issue returns 404."""
        response = client.put("/api/issues/UNKNOWN-999", json={
            "title": "Should Fail"
        })

        assert response.status_code == 404


class TestDeleteIssue:
    """Tests for deleting issues."""

    def test_delete_issue(self, client):
        """Delete issue removes it from store."""
        # Create an issue
        create_response = client.post("/api/issues", json={"title": "Delete Test"})
        issue_id = create_response.json()["identifier"]

        # Delete it
        response = client.delete(f"/api/issues/{issue_id}")

        assert response.status_code == 200
        assert response.json()["deleted"] is True

        # Verify it's gone
        get_response = client.get(f"/api/issues/{issue_id}")
        assert get_response.status_code == 404

    def test_delete_nonexistent_issue(self, client):
        """Delete nonexistent issue returns 404."""
        response = client.delete("/api/issues/UNKNOWN-999")
        assert response.status_code == 404

    def test_delete_adds_to_undo_stack(self, client):
        """Deleting issue adds to undo stack with issue data."""
        # Create an issue
        create_response = client.post("/api/issues", json={"title": "Undo Delete Test"})
        issue_id = create_response.json()["identifier"]

        global UNDO_STACK
        initial_stack_size = len(UNDO_STACK)

        # Delete it
        client.delete(f"/api/issues/{issue_id}")

        assert len(UNDO_STACK) == initial_stack_size + 1
        assert UNDO_STACK[-1]["action"] == "delete"
        assert UNDO_STACK[-1]["issue_id"] == issue_id


class TestComments:
    """Tests for issue comments."""

    def test_add_comment(self, client):
        """Add comment to issue."""
        # Create an issue
        create_response = client.post("/api/issues", json={"title": "Comment Test"})
        issue_id = create_response.json()["identifier"]

        # Add a comment
        response = client.post(f"/api/issues/{issue_id}/comments?content=Test comment")

        assert response.status_code == 200
        comment = response.json()
        assert comment["content"] == "Test comment"
        assert comment["author"] == "Agent"
        assert "id" in comment
        assert "created_at" in comment

    def test_add_comment_updates_issue(self, client):
        """Adding comment updates issue's updated_at."""
        # Create an issue
        create_response = client.post("/api/issues", json={"title": "Comment Update Test"})
        issue_id = create_response.json()["identifier"]
        original_updated = create_response.json()["updated_at"]

        # Small delay to ensure timestamp difference
        import time
        time.sleep(0.1)

        # Add a comment
        client.post(f"/api/issues/{issue_id}/comments?content=Test comment")

        # Check issue was updated
        get_response = client.get(f"/api/issues/{issue_id}")
        assert get_response.json()["updated_at"] >= original_updated

    def test_add_comment_to_nonexistent_issue(self, client):
        """Add comment to nonexistent issue returns 404."""
        response = client.post("/api/issues/UNKNOWN-999/comments?content=Test")
        assert response.status_code == 404


class TestBulkOperations:
    """Tests for bulk operations."""

    def test_bulk_change_state(self, client):
        """Bulk change state for multiple issues."""
        # Create issues
        ids = []
        for i in range(3):
            response = client.post("/api/issues", json={"title": f"Bulk Test {i}"})
            ids.append(response.json()["identifier"])

        # Bulk change to In Progress
        response = client.post("/api/issues/bulk", json={
            "issue_ids": ids,
            "operation": "change_state",
            "value": "In Progress"
        })

        assert response.status_code == 200
        result = response.json()
        assert len(result["success"]) == 3
        assert len(result["failed"]) == 0

    def test_bulk_change_priority(self, client):
        """Bulk change priority for multiple issues."""
        # Create issues
        ids = []
        for i in range(2):
            response = client.post("/api/issues", json={"title": f"Priority Test {i}"})
            ids.append(response.json()["identifier"])

        # Bulk change priority
        response = client.post("/api/issues/bulk", json={
            "issue_ids": ids,
            "operation": "change_priority",
            "value": "urgent"
        })

        assert response.status_code == 200
        result = response.json()
        assert len(result["success"]) == 2

    def test_bulk_delete(self, client):
        """Bulk delete multiple issues."""
        # Create issues
        ids = []
        for i in range(2):
            response = client.post("/api/issues", json={"title": f"Delete Test {i}"})
            ids.append(response.json()["identifier"])

        # Bulk delete
        response = client.post("/api/issues/bulk", json={
            "issue_ids": ids,
            "operation": "delete"
        })

        assert response.status_code == 200
        result = response.json()
        assert len(result["success"]) == 2

        # Verify deleted
        for issue_id in ids:
            get_response = client.get(f"/api/issues/{issue_id}")
            assert get_response.status_code == 404

    def test_bulk_with_nonexistent_issues(self, client):
        """Bulk operation handles nonexistent issues."""
        response = client.post("/api/issues/bulk", json={
            "issue_ids": ["UNKNOWN-1", "UNKNOWN-2"],
            "operation": "change_state",
            "value": "Done"
        })

        assert response.status_code == 200
        result = response.json()
        assert len(result["success"]) == 0
        assert len(result["failed"]) == 2


class TestUndo:
    """Tests for undo functionality."""

    def test_undo_create(self, client):
        """Undo create removes the issue."""
        # Create an issue
        create_response = client.post("/api/issues", json={"title": "Undo Create Test"})
        issue_id = create_response.json()["identifier"]

        # Undo
        response = client.post("/api/issues/undo")

        assert response.status_code == 200
        assert response.json()["success"] is True

        # Verify issue is gone
        get_response = client.get(f"/api/issues/{issue_id}")
        assert get_response.status_code == 404

    def test_undo_update(self, client):
        """Undo update restores previous state."""
        # Create an issue
        create_response = client.post("/api/issues", json={"title": "Original Title"})
        issue_id = create_response.json()["identifier"]

        # Update it
        client.put(f"/api/issues/{issue_id}", json={"title": "Updated Title"})

        # Undo
        response = client.post("/api/issues/undo")

        assert response.status_code == 200
        assert response.json()["success"] is True

        # Verify original title restored
        get_response = client.get(f"/api/issues/{issue_id}")
        assert get_response.json()["title"] == "Original Title"

    def test_undo_delete(self, client):
        """Undo delete restores the issue."""
        # Create an issue
        create_response = client.post("/api/issues", json={"title": "Undo Delete Test"})
        issue_id = create_response.json()["identifier"]

        # Clear undo stack from create
        client.post("/api/issues/undo")

        # Create again and delete
        create_response = client.post("/api/issues", json={"title": "Undo Delete Test 2"})
        issue_id = create_response.json()["identifier"]
        client.delete(f"/api/issues/{issue_id}")

        # Undo
        response = client.post("/api/issues/undo")

        assert response.status_code == 200
        assert response.json()["success"] is True

        # Verify issue is back
        get_response = client.get(f"/api/issues/{issue_id}")
        assert get_response.status_code == 200

    def test_undo_empty_stack(self, client, clean_store):
        """Undo with empty stack returns failure."""
        response = client.post("/api/issues/undo")

        assert response.status_code == 200
        assert response.json()["success"] is False
        assert "Nothing to undo" in response.json()["message"]
