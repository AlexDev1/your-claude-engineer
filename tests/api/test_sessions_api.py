"""
Session Replay API Tests
=========================

Tests for the session replay endpoints (ENG-75).
Coverage: list sessions, get single session, filtering, pagination,
          404 handling, corrupted files.
"""

import json
import os
import tempfile
from datetime import datetime, timezone, timedelta
from pathlib import Path
from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient

from axon_agent.dashboard.api import app
from axon_agent.dashboard.sessions import (
    SessionSummary,
    _calculate_duration,
    _load_session_file,
    _session_summary_from_data,
    _list_session_files,
)


@pytest.fixture
def client():
    """Create FastAPI test client."""
    return TestClient(app)


@pytest.fixture
def sessions_dir(tmp_path):
    """Create a temporary sessions directory with sample session files."""
    sessions = tmp_path / ".agent" / "sessions"
    sessions.mkdir(parents=True)

    now = datetime.now(timezone.utc)

    # Session 1: completed session
    session_1 = {
        "session_id": 1,
        "started_at": (now - timedelta(hours=3)).isoformat(),
        "ended_at": (now - timedelta(hours=2)).isoformat(),
        "issue_id": "ENG-74",
        "status": "completed",
        "events": [
            {"t": 0.0, "type": "tool_call", "data": {"tool": "Read"}},
            {"t": 1.5, "type": "bash", "data": {"command": "git status"}},
            {"t": 5.2, "type": "file_write", "data": {"path": "test.py"}},
        ],
    }
    (sessions / "session-1.json").write_text(json.dumps(session_1, indent=2))

    # Session 2: failed session
    session_2 = {
        "session_id": 2,
        "started_at": (now - timedelta(hours=1)).isoformat(),
        "ended_at": (now - timedelta(minutes=30)).isoformat(),
        "issue_id": "ENG-75",
        "status": "failed",
        "events": [
            {"t": 0.0, "type": "tool_call", "data": {"tool": "Read"}},
        ],
    }
    (sessions / "session-2.json").write_text(json.dumps(session_2, indent=2))

    # Session 3: running session (no ended_at)
    session_3 = {
        "session_id": 3,
        "started_at": now.isoformat(),
        "ended_at": None,
        "issue_id": "ENG-74",
        "status": "running",
        "events": [],
    }
    (sessions / "session-3.json").write_text(json.dumps(session_3, indent=2))

    return sessions


@pytest.fixture
def mock_sessions_dir(sessions_dir):
    """Patch _get_sessions_dir to use the temporary directory."""
    with patch(
        "axon_agent.dashboard.sessions._get_sessions_dir",
        return_value=sessions_dir,
    ):
        yield sessions_dir


# =============================================================================
# Unit Tests for Helper Functions
# =============================================================================


class TestCalculateDuration:
    """Tests for _calculate_duration helper."""

    def test_valid_timestamps(self):
        """Duration computed correctly from valid ISO timestamps."""
        start = "2026-02-09T10:00:00+00:00"
        end = "2026-02-09T11:30:00+00:00"
        result = _calculate_duration(start, end)
        assert result == 5400.0  # 1.5 hours = 5400 seconds

    def test_none_start(self):
        """Returns None when start is None."""
        assert _calculate_duration(None, "2026-02-09T11:00:00+00:00") is None

    def test_none_end(self):
        """Returns None when end is None."""
        assert _calculate_duration("2026-02-09T10:00:00+00:00", None) is None

    def test_both_none(self):
        """Returns None when both are None."""
        assert _calculate_duration(None, None) is None

    def test_invalid_format(self):
        """Returns None for unparseable timestamps."""
        assert _calculate_duration("not-a-date", "also-not-a-date") is None

    def test_empty_strings(self):
        """Returns None for empty strings."""
        assert _calculate_duration("", "") is None


class TestLoadSessionFile:
    """Tests for _load_session_file helper."""

    def test_valid_file(self, tmp_path):
        """Loads valid JSON session file."""
        filepath = tmp_path / "session-1.json"
        data = {"session_id": 1, "status": "completed"}
        filepath.write_text(json.dumps(data))

        result = _load_session_file(filepath)
        assert result is not None
        assert result["session_id"] == 1

    def test_missing_file(self, tmp_path):
        """Returns None for missing file."""
        filepath = tmp_path / "nonexistent.json"
        result = _load_session_file(filepath)
        assert result is None

    def test_corrupt_json(self, tmp_path):
        """Returns None for corrupt JSON."""
        filepath = tmp_path / "session-bad.json"
        filepath.write_text("{ this is not valid json }")

        result = _load_session_file(filepath)
        assert result is None


class TestSessionSummaryFromData:
    """Tests for _session_summary_from_data helper."""

    def test_complete_data(self):
        """Builds summary from complete session data."""
        data = {
            "session_id": 5,
            "started_at": "2026-02-09T10:00:00+00:00",
            "ended_at": "2026-02-09T10:30:00+00:00",
            "issue_id": "ENG-74",
            "status": "completed",
            "events": [{"t": 0, "type": "test", "data": {}}] * 3,
        }
        summary = _session_summary_from_data(data)

        assert summary.id == 5
        assert summary.events_count == 3
        assert summary.status == "completed"
        assert summary.issue_id == "ENG-74"
        assert summary.duration_seconds == 1800.0  # 30 minutes

    def test_minimal_data(self):
        """Builds summary from minimal session data."""
        data = {"session_id": 1, "started_at": "2026-02-09T10:00:00"}
        summary = _session_summary_from_data(data)

        assert summary.id == 1
        assert summary.events_count == 0
        assert summary.status == "unknown"
        assert summary.issue_id == ""
        assert summary.duration_seconds is None

    def test_missing_session_id(self):
        """Defaults session_id to 0 if missing."""
        data = {"started_at": "2026-02-09T10:00:00"}
        summary = _session_summary_from_data(data)
        assert summary.id == 0


class TestListSessionFiles:
    """Tests for _list_session_files helper."""

    def test_finds_session_files(self, sessions_dir):
        """Finds all session-N.json files sorted descending."""
        results = _list_session_files(sessions_dir)

        assert len(results) == 3
        # Newest first (descending by ID)
        assert results[0][0] == 3
        assert results[1][0] == 2
        assert results[2][0] == 1

    def test_ignores_non_session_files(self, sessions_dir):
        """Ignores files that don't match session-N.json pattern."""
        (sessions_dir / "notes.txt").write_text("not a session")
        (sessions_dir / "session-abc.json").write_text("{}")

        results = _list_session_files(sessions_dir)
        assert len(results) == 3  # Only the 3 valid sessions

    def test_empty_directory(self, tmp_path):
        """Returns empty list for empty directory."""
        empty = tmp_path / "empty"
        empty.mkdir()
        results = _list_session_files(empty)
        assert results == []

    def test_nonexistent_directory(self, tmp_path):
        """Returns empty list for nonexistent directory."""
        missing = tmp_path / "does_not_exist"
        results = _list_session_files(missing)
        assert results == []


# =============================================================================
# Endpoint Tests
# =============================================================================


class TestListSessionsEndpoint:
    """Tests for GET /api/sessions."""

    def test_list_all_sessions(self, client, mock_sessions_dir):
        """Lists all sessions sorted newest first."""
        response = client.get("/api/sessions")

        assert response.status_code == 200
        data = response.json()
        assert "sessions" in data
        assert "total" in data
        assert data["total"] == 3
        assert len(data["sessions"]) == 3

        # Newest first
        assert data["sessions"][0]["id"] == 3
        assert data["sessions"][1]["id"] == 2
        assert data["sessions"][2]["id"] == 1

    def test_list_sessions_with_limit(self, client, mock_sessions_dir):
        """Respects limit parameter."""
        response = client.get("/api/sessions?limit=2")

        assert response.status_code == 200
        data = response.json()
        assert len(data["sessions"]) == 2
        assert data["total"] == 3  # Total is still 3
        assert data["limit"] == 2

    def test_list_sessions_with_offset(self, client, mock_sessions_dir):
        """Respects offset parameter."""
        response = client.get("/api/sessions?offset=1")

        assert response.status_code == 200
        data = response.json()
        assert len(data["sessions"]) == 2  # 3 total - 1 skipped
        assert data["offset"] == 1
        # First returned should be session 2 (skipped session 3)
        assert data["sessions"][0]["id"] == 2

    def test_list_sessions_with_limit_and_offset(self, client, mock_sessions_dir):
        """Respects both limit and offset for pagination."""
        response = client.get("/api/sessions?limit=1&offset=1")

        assert response.status_code == 200
        data = response.json()
        assert len(data["sessions"]) == 1
        assert data["sessions"][0]["id"] == 2

    def test_filter_by_status(self, client, mock_sessions_dir):
        """Filters sessions by status."""
        response = client.get("/api/sessions?status=completed")

        assert response.status_code == 200
        data = response.json()
        assert data["total"] == 1
        assert data["sessions"][0]["status"] == "completed"
        assert data["sessions"][0]["id"] == 1

    def test_filter_by_status_failed(self, client, mock_sessions_dir):
        """Filters sessions by failed status."""
        response = client.get("/api/sessions?status=failed")

        assert response.status_code == 200
        data = response.json()
        assert data["total"] == 1
        assert data["sessions"][0]["id"] == 2

    def test_filter_by_issue_id(self, client, mock_sessions_dir):
        """Filters sessions by issue_id."""
        response = client.get("/api/sessions?issue_id=ENG-74")

        assert response.status_code == 200
        data = response.json()
        assert data["total"] == 2
        assert all(s["issue_id"] == "ENG-74" for s in data["sessions"])

    def test_filter_combined(self, client, mock_sessions_dir):
        """Filters by both status and issue_id."""
        response = client.get("/api/sessions?status=completed&issue_id=ENG-74")

        assert response.status_code == 200
        data = response.json()
        assert data["total"] == 1
        assert data["sessions"][0]["id"] == 1

    def test_filter_no_matches(self, client, mock_sessions_dir):
        """Returns empty list when no sessions match filters."""
        response = client.get("/api/sessions?issue_id=ENG-999")

        assert response.status_code == 200
        data = response.json()
        assert data["total"] == 0
        assert data["sessions"] == []

    def test_session_summary_fields(self, client, mock_sessions_dir):
        """Session summaries contain all expected fields."""
        response = client.get("/api/sessions?status=completed")

        assert response.status_code == 200
        session = response.json()["sessions"][0]

        assert "id" in session
        assert "started_at" in session
        assert "ended_at" in session
        assert "duration_seconds" in session
        assert "events_count" in session
        assert "status" in session
        assert "issue_id" in session

        # Completed session should have duration
        assert session["duration_seconds"] is not None
        assert session["duration_seconds"] > 0
        assert session["events_count"] == 3

    def test_running_session_no_duration(self, client, mock_sessions_dir):
        """Running sessions have None duration."""
        response = client.get("/api/sessions?status=running")

        assert response.status_code == 200
        session = response.json()["sessions"][0]
        assert session["duration_seconds"] is None
        assert session["ended_at"] is None

    def test_empty_sessions_dir(self, client):
        """Returns empty list when sessions directory is empty."""
        with tempfile.TemporaryDirectory() as tmp:
            empty_dir = Path(tmp) / ".agent" / "sessions"
            empty_dir.mkdir(parents=True)
            with patch(
                "axon_agent.dashboard.sessions._get_sessions_dir",
                return_value=empty_dir,
            ):
                response = client.get("/api/sessions")

        assert response.status_code == 200
        data = response.json()
        assert data["total"] == 0
        assert data["sessions"] == []

    def test_nonexistent_sessions_dir(self, client):
        """Returns empty list when sessions directory does not exist."""
        with patch(
            "axon_agent.dashboard.sessions._get_sessions_dir",
            return_value=Path("/nonexistent/path"),
        ):
            response = client.get("/api/sessions")

        assert response.status_code == 200
        data = response.json()
        assert data["total"] == 0

    def test_invalid_limit(self, client, mock_sessions_dir):
        """Validates limit parameter range."""
        response = client.get("/api/sessions?limit=0")
        assert response.status_code == 422

        response = client.get("/api/sessions?limit=501")
        assert response.status_code == 422

    def test_invalid_offset(self, client, mock_sessions_dir):
        """Validates offset parameter range."""
        response = client.get("/api/sessions?offset=-1")
        assert response.status_code == 422


class TestGetSessionEndpoint:
    """Tests for GET /api/sessions/{session_id}."""

    def test_get_existing_session(self, client, mock_sessions_dir):
        """Returns full session data for valid ID."""
        response = client.get("/api/sessions/1")

        assert response.status_code == 200
        data = response.json()
        assert data["session_id"] == 1
        assert data["issue_id"] == "ENG-74"
        assert data["status"] == "completed"
        assert len(data["events"]) == 3
        assert data["events"][0]["type"] == "tool_call"

    def test_get_session_full_events(self, client, mock_sessions_dir):
        """Returns complete event data including payloads."""
        response = client.get("/api/sessions/1")

        assert response.status_code == 200
        events = response.json()["events"]
        assert events[0]["data"]["tool"] == "Read"
        assert events[1]["data"]["command"] == "git status"
        assert events[2]["data"]["path"] == "test.py"

    def test_get_nonexistent_session(self, client, mock_sessions_dir):
        """Returns 404 for nonexistent session ID."""
        response = client.get("/api/sessions/999")

        assert response.status_code == 404
        assert "not found" in response.json()["detail"].lower()

    def test_get_corrupted_session(self, client, mock_sessions_dir):
        """Returns 500 for corrupted session file."""
        corrupt = mock_sessions_dir / "session-99.json"
        corrupt.write_text("{{{{ not valid json")

        response = client.get("/api/sessions/99")

        assert response.status_code == 500
        assert "corrupted" in response.json()["detail"].lower()

    def test_get_running_session(self, client, mock_sessions_dir):
        """Returns running session (no ended_at)."""
        response = client.get("/api/sessions/3")

        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "running"
        assert data["ended_at"] is None
        assert data["events"] == []

    def test_get_different_sessions(self, client, mock_sessions_dir):
        """Can retrieve different sessions by ID."""
        for sid in [1, 2, 3]:
            response = client.get(f"/api/sessions/{sid}")
            assert response.status_code == 200
            assert response.json()["session_id"] == sid
