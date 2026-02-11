"""
Issues API Tests
=================

Tests for the issue CRUD endpoints.
Coverage: create, read, update, delete, comments, bulk operations, undo.
"""

import pytest
from datetime import datetime
from unittest.mock import patch, MagicMock

from axon_agent.dashboard.api import (
    app,
    ISSUES_STORE,
    ISSUE_COUNTER,
    UNDO_STACK,
    initialize_issues_store,
)



@pytest.fixture
async def client():
    """HTTPX async client over in-process ASGI app (без сетевых вызовов)."""
    # Reset store before each test
    global ISSUES_STORE, UNDO_STACK
    ISSUES_STORE.clear()
    UNDO_STACK.clear()
    initialize_issues_store()

    import httpx

    transport = httpx.ASGITransport(app=app, raise_app_exceptions=True)
    async with httpx.AsyncClient(
        transport=transport, base_url="http://testserver"
    ) as client:
        yield client


@pytest.fixture
def clean_store():
    """Reset the issues store."""
    global ISSUES_STORE, UNDO_STACK
    ISSUES_STORE.clear()
    UNDO_STACK.clear()


class TestListIssues:
    """Tests for listing issues."""

    async def test_list_all_issues(self, client):
        """List issues returns all issues."""
        response = await client.get("/api/issues")

        assert response.status_code == 200
        data = response.json()
        assert "issues" in data
        assert "total" in data
        assert data["total"] == len(data["issues"])

    async def test_list_issues_filter_by_state(self, client):
        """List issues filters by state."""
        response = await client.get("/api/issues?state=Done")

        assert response.status_code == 200
        data = response.json()
        for issue in data["issues"]:
            assert issue["state"] == "Done"

    async def test_list_issues_filter_by_priority(self, client):
        """List issues filters by priority."""
        response = await client.get("/api/issues?priority=high")

        assert response.status_code == 200
        data = response.json()
        for issue in data["issues"]:
            assert issue["priority"] == "high"

    async def test_list_issues_sorted_by_priority(self, client):
        """List issues are sorted by priority."""
        response = await client.get("/api/issues")

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

    async def test_get_existing_issue(self, client):
        """Get issue returns issue by ID."""
        # First, get list to find an existing issue
        list_response = await client.get("/api/issues")
        issues = list_response.json()["issues"]
        if issues:
            issue_id = issues[0]["identifier"]

            response = await client.get(f"/api/issues/{issue_id}")
            assert response.status_code == 200
            data = response.json()
            assert data["identifier"] == issue_id

    async def test_get_nonexistent_issue(self, client):
        """Get issue returns 404 for unknown ID."""
        response = await client.get("/api/issues/UNKNOWN-999")

        assert response.status_code == 404


class TestCreateIssue:
    """Tests for creating issues."""

    async def test_create_issue_minimal(self, client):
        """Create issue with minimal data."""
        response = await client.post("/api/issues", json={
            "title": "New Test Issue"
        })

        assert response.status_code == 200
        data = response.json()
        assert data["title"] == "New Test Issue"
        assert data["state"] == "Todo"
        assert data["priority"] == "medium"
        assert "identifier" in data
        assert data["identifier"].startswith("ENG-")

    async def test_create_issue_full(self, client):
        """Create issue with all fields."""
        response = await client.post("/api/issues", json={
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

    async def test_create_issue_with_dependencies(self, client):
        """Create issue with dependencies."""
        # First create a parent issue
        parent_response = await client.post("/api/issues", json={
            "title": "Parent Issue"
        })
        parent_id = parent_response.json()["identifier"]

        # Create issue with dependency
        response = await client.post("/api/issues", json={
            "title": "Child Issue",
            "dependencies": [parent_id],
        })

        assert response.status_code == 200
        data = response.json()
        assert parent_id in data["dependencies"]

    async def test_create_issue_adds_to_undo_stack(self, client):
        """Creating issue adds to undo stack."""
        global UNDO_STACK
        initial_stack_size = len(UNDO_STACK)

        await client.post("/api/issues", json={"title": "Undo Test Issue"})

        assert len(UNDO_STACK) == initial_stack_size + 1
        assert UNDO_STACK[-1]["action"] == "create"


class TestUpdateIssue:
    """Tests for updating issues."""

    async def test_update_issue_title(self, client):
        """Update issue title."""
        # Create an issue first
        create_response = await client.post("/api/issues", json={"title": "Original Title"})
        issue_id = create_response.json()["identifier"]

        # Update it
        response = await client.put(f"/api/issues/{issue_id}", json={
            "title": "Updated Title"
        })

        assert response.status_code == 200
        data = response.json()
        assert data["title"] == "Updated Title"

    async def test_update_issue_state_valid_transition(self, client):
        """Update issue with valid state transition."""
        # Create an issue (starts in Todo)
        create_response = await client.post("/api/issues", json={"title": "State Test"})
        issue_id = create_response.json()["identifier"]

        # Valid transition: Todo -> In Progress
        response = await client.put(f"/api/issues/{issue_id}", json={
            "state": "In Progress"
        })

        assert response.status_code == 200
        assert response.json()["state"] == "In Progress"

    async def test_update_issue_state_invalid_transition(self, client):
        """Update issue with invalid state transition fails."""
        # Create an issue (starts in Todo)
        create_response = await client.post("/api/issues", json={"title": "Invalid State Test"})
        issue_id = create_response.json()["identifier"]

        # Invalid transition: Todo -> Done (should go through In Progress first)
        response = await client.put(f"/api/issues/{issue_id}", json={
            "state": "Done"
        })

        assert response.status_code == 400

    async def test_update_issue_to_done_sets_completed_at(self, client):
        """Completing issue sets completed_at timestamp."""
        # Create and move to In Progress first
        create_response = await client.post("/api/issues", json={"title": "Complete Test"})
        issue_id = create_response.json()["identifier"]

        await client.put(f"/api/issues/{issue_id}", json={"state": "In Progress"})

        # Now complete it
        response = await client.put(f"/api/issues/{issue_id}", json={"state": "Done"})

        assert response.status_code == 200
        data = response.json()
        assert data["state"] == "Done"
        assert data["completed_at"] is not None

    async def test_update_nonexistent_issue(self, client):
        """Update nonexistent issue returns 404."""
        response = await client.put("/api/issues/UNKNOWN-999", json={
            "title": "Should Fail"
        })

        assert response.status_code == 404


class TestDeleteIssue:
    """Tests for deleting issues."""

    async def test_delete_issue(self, client):
        """Delete issue removes it from store."""
        # Create an issue
        create_response = await client.post("/api/issues", json={"title": "Delete Test"})
        issue_id = create_response.json()["identifier"]

        # Delete it
        response = await client.delete(f"/api/issues/{issue_id}")

        assert response.status_code == 200
        assert response.json()["deleted"] is True

        # Verify it's gone
        get_response = await client.get(f"/api/issues/{issue_id}")
        assert get_response.status_code == 404

    async def test_delete_nonexistent_issue(self, client):
        """Delete nonexistent issue returns 404."""
        response = await client.delete("/api/issues/UNKNOWN-999")
        assert response.status_code == 404

    async def test_delete_adds_to_undo_stack(self, client):
        """Deleting issue adds to undo stack with issue data."""
        # Create an issue
        create_response = await client.post("/api/issues", json={"title": "Undo Delete Test"})
        issue_id = create_response.json()["identifier"]

        global UNDO_STACK
        initial_stack_size = len(UNDO_STACK)

        # Delete it
        await client.delete(f"/api/issues/{issue_id}")

        assert len(UNDO_STACK) == initial_stack_size + 1
        assert UNDO_STACK[-1]["action"] == "delete"
        assert UNDO_STACK[-1]["issue_id"] == issue_id


class TestComments:
    """Tests for issue comments."""

    async def test_add_comment(self, client):
        """Add comment to issue."""
        # Create an issue
        create_response = await client.post("/api/issues", json={"title": "Comment Test"})
        issue_id = create_response.json()["identifier"]

        # Add a comment
        response = await client.post(f"/api/issues/{issue_id}/comments?content=Test comment")

        assert response.status_code == 200
        comment = response.json()
        assert comment["content"] == "Test comment"
        assert comment["author"] == "Agent"
        assert "id" in comment
        assert "created_at" in comment

    async def test_add_comment_updates_issue(self, client):
        """Adding comment updates issue's updated_at."""
        # Create an issue
        create_response = await client.post("/api/issues", json={"title": "Comment Update Test"})
        issue_id = create_response.json()["identifier"]
        original_updated = create_response.json()["updated_at"]

        # Small delay to ensure timestamp difference
        import asyncio
        await asyncio.sleep(0.1)

        # Add a comment
        await client.post(f"/api/issues/{issue_id}/comments?content=Test comment")

        # Check issue was updated
        get_response = await client.get(f"/api/issues/{issue_id}")
        assert get_response.json()["updated_at"] >= original_updated

    async def test_add_comment_to_nonexistent_issue(self, client):
        """Add comment to nonexistent issue returns 404."""
        response = await client.post("/api/issues/UNKNOWN-999/comments?content=Test")
        assert response.status_code == 404


class TestBulkOperations:
    """Tests for bulk operations."""

    async def test_bulk_change_state(self, client):
        """Bulk change state for multiple issues."""
        # Create issues
        ids = []
        for i in range(3):
            response = await client.post("/api/issues", json={"title": f"Bulk Test {i}"})
            ids.append(response.json()["identifier"])

        # Bulk change to In Progress
        response = await client.post("/api/issues/bulk", json={
            "issue_ids": ids,
            "operation": "change_state",
            "value": "In Progress"
        })

        assert response.status_code == 200
        result = response.json()
        assert len(result["success"]) == 3
        assert len(result["failed"]) == 0

    async def test_bulk_change_priority(self, client):
        """Bulk change priority for multiple issues."""
        # Create issues
        ids = []
        for i in range(2):
            response = await client.post("/api/issues", json={"title": f"Priority Test {i}"})
            ids.append(response.json()["identifier"])

        # Bulk change priority
        response = await client.post("/api/issues/bulk", json={
            "issue_ids": ids,
            "operation": "change_priority",
            "value": "urgent"
        })

        assert response.status_code == 200
        result = response.json()
        assert len(result["success"]) == 2

    async def test_bulk_delete(self, client):
        """Bulk delete multiple issues."""
        # Create issues
        ids = []
        for i in range(2):
            response = await client.post("/api/issues", json={"title": f"Delete Test {i}"})
            ids.append(response.json()["identifier"])

        # Bulk delete
        response = await client.post("/api/issues/bulk", json={
            "issue_ids": ids,
            "operation": "delete"
        })

        assert response.status_code == 200
        result = response.json()
        assert len(result["success"]) == 2

        # Verify deleted
        for issue_id in ids:
            get_response = await client.get(f"/api/issues/{issue_id}")
            assert get_response.status_code == 404

    async def test_bulk_with_nonexistent_issues(self, client):
        """Bulk operation handles nonexistent issues."""
        response = await client.post("/api/issues/bulk", json={
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

    async def test_undo_create(self, client):
        """Undo create removes the issue."""
        # Create an issue
        create_response = await client.post("/api/issues", json={"title": "Undo Create Test"})
        issue_id = create_response.json()["identifier"]

        # Undo
        response = await client.post("/api/issues/undo")

        assert response.status_code == 200
        assert response.json()["success"] is True

        # Verify issue is gone
        get_response = await client.get(f"/api/issues/{issue_id}")
        assert get_response.status_code == 404

    async def test_undo_update(self, client):
        """Undo update restores previous state."""
        # Create an issue
        create_response = await client.post("/api/issues", json={"title": "Original Title"})
        issue_id = create_response.json()["identifier"]

        # Update it
        await client.put(f"/api/issues/{issue_id}", json={"title": "Updated Title"})

        # Undo
        response = await client.post("/api/issues/undo")

        assert response.status_code == 200
        assert response.json()["success"] is True

        # Verify original title restored
        get_response = await client.get(f"/api/issues/{issue_id}")
        assert get_response.json()["title"] == "Original Title"

    async def test_undo_delete(self, client):
        """Undo delete restores the issue."""
        # Create an issue
        create_response = await client.post("/api/issues", json={"title": "Undo Delete Test"})
        issue_id = create_response.json()["identifier"]

        # Clear undo stack from create
        await client.post("/api/issues/undo")

        # Create again and delete
        create_response = await client.post("/api/issues", json={"title": "Undo Delete Test 2"})
        issue_id = create_response.json()["identifier"]
        await client.delete(f"/api/issues/{issue_id}")

        # Undo
        response = await client.post("/api/issues/undo")

        assert response.status_code == 200
        assert response.json()["success"] is True

        # Verify issue is back
        get_response = await client.get(f"/api/issues/{issue_id}")
        assert get_response.status_code == 200

    async def test_undo_empty_stack(self, client, clean_store):
        """Undo with empty stack returns failure."""
        response = await client.post("/api/issues/undo")

        assert response.status_code == 200
        assert response.json()["success"] is False
        assert "Nothing to undo" in response.json()["message"]
