"""
Pytest Configuration and Fixtures
==================================

Shared fixtures for all test modules.
"""

import os
import pytest
import asyncio
from typing import Generator, Any
from datetime import datetime

# Set test environment
os.environ.setdefault("TESTING", "1")
os.environ.setdefault("TASK_MCP_URL", "http://localhost:8001/sse")
os.environ.setdefault("TELEGRAM_MCP_URL", "http://localhost:8002/sse")


@pytest.fixture(scope="session")
def event_loop():
    """Create event loop for async tests."""
    loop = asyncio.new_event_loop()
    yield loop
    loop.close()


@pytest.fixture
def mock_issues() -> list[dict]:
    """Generate mock issue data for testing."""
    now = datetime.now()
    return [
        {
            "identifier": "ENG-1",
            "title": "Test Issue 1",
            "description": "Test description 1",
            "state": "Todo",
            "priority": "high",
            "issue_type": "Feature",
            "team": "ENG",
            "project": "Test Project",
            "parent_id": None,
            "dependencies": [],
            "comments": [],
            "created_at": now.isoformat(),
            "updated_at": now.isoformat(),
            "completed_at": None,
        },
        {
            "identifier": "ENG-2",
            "title": "Test Issue 2",
            "description": "Test description 2",
            "state": "In Progress",
            "priority": "medium",
            "issue_type": "Bug",
            "team": "ENG",
            "project": "Test Project",
            "parent_id": None,
            "dependencies": ["ENG-1"],
            "comments": [],
            "created_at": now.isoformat(),
            "updated_at": now.isoformat(),
            "completed_at": None,
        },
        {
            "identifier": "ENG-3",
            "title": "Test Issue 3",
            "description": "Test description 3",
            "state": "Done",
            "priority": "low",
            "issue_type": "Task",
            "team": "ENG",
            "project": "Test Project",
            "parent_id": None,
            "dependencies": [],
            "comments": [
                {
                    "id": "c1",
                    "author": "Agent",
                    "content": "Test comment",
                    "created_at": now.isoformat(),
                }
            ],
            "created_at": now.isoformat(),
            "updated_at": now.isoformat(),
            "completed_at": now.isoformat(),
        },
    ]


@pytest.fixture
def api_base_url() -> str:
    """Base URL for API tests."""
    return os.environ.get("API_BASE_URL", "http://localhost:8003")


@pytest.fixture
def dashboard_url() -> str:
    """Base URL for dashboard E2E tests."""
    return os.environ.get("DASHBOARD_URL", "http://localhost:5173")
