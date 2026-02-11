"""
Tests for Session Recording to JSON (ENG-74)
==============================================

Verifies:
1. SessionRecorder start/end lifecycle
2. Event recording with relative timestamps
3. Preview truncation at MAX_PREVIEW_LENGTH
4. Thread-safe concurrent event recording
5. Session serialization/deserialization (to_dict / from_dict)
6. get_next_session_id correctly scans existing files
7. rotate_sessions removes oldest files beyond MAX_SESSIONS
8. Atomic file write (no partial writes on error)
9. Edge cases: no active session, double start, double end
"""

import json
import threading
import time
from pathlib import Path
from unittest.mock import patch

import pytest

from axon_agent.monitoring.recorder import (
    MAX_PREVIEW_LENGTH,
    MAX_SESSIONS,
    Session,
    SessionEvent,
    SessionRecorder,
    _truncate_preview,
    get_next_session_id,
    rotate_sessions,
)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def sessions_dir(tmp_path: Path) -> Path:
    """Create a temporary sessions directory."""
    d = tmp_path / ".agent" / "sessions"
    d.mkdir(parents=True)
    return d


@pytest.fixture
def recorder(tmp_path: Path) -> SessionRecorder:
    """Create a SessionRecorder pointing at a temporary project dir."""
    return SessionRecorder(project_dir=tmp_path, issue_id="ENG-74")


# ---------------------------------------------------------------------------
# SessionEvent Tests
# ---------------------------------------------------------------------------

class TestSessionEvent:
    """Test SessionEvent dataclass."""

    def test_basic_construction(self) -> None:
        """Event can be created with required fields."""
        event = SessionEvent(t=1.5, type="tool_call")
        assert event.t == 1.5
        assert event.type == "tool_call"
        assert event.data == {}

    def test_with_data(self) -> None:
        """Event stores arbitrary data payload."""
        event = SessionEvent(
            t=0.0,
            type="bash",
            data={"command": "npm test", "exit_code": 0},
        )
        assert event.data["command"] == "npm test"
        assert event.data["exit_code"] == 0


# ---------------------------------------------------------------------------
# Session Tests
# ---------------------------------------------------------------------------

class TestSession:
    """Test Session dataclass serialization."""

    def test_to_dict_roundtrip(self) -> None:
        """to_dict produces valid dict, from_dict restores it."""
        session = Session(
            session_id=42,
            started_at="2026-02-09T10:00:00+00:00",
            ended_at="2026-02-09T10:15:00+00:00",
            issue_id="ENG-74",
            status="completed",
            events=[
                SessionEvent(t=0.0, type="tool_call", data={"tool": "Read"}),
                SessionEvent(t=1.2, type="bash", data={"command": "ls"}),
            ],
        )

        d = session.to_dict()
        restored = Session.from_dict(d)

        assert restored.session_id == 42
        assert restored.started_at == "2026-02-09T10:00:00+00:00"
        assert restored.ended_at == "2026-02-09T10:15:00+00:00"
        assert restored.issue_id == "ENG-74"
        assert restored.status == "completed"
        assert len(restored.events) == 2
        assert restored.events[0].type == "tool_call"
        assert restored.events[1].data["command"] == "ls"

    def test_to_dict_json_serializable(self) -> None:
        """to_dict output is JSON serializable."""
        session = Session(
            session_id=1,
            started_at="2026-02-09T10:00:00+00:00",
            events=[SessionEvent(t=0.0, type="tool_call", data={"key": "value"})],
        )
        serialized = json.dumps(session.to_dict())
        assert isinstance(serialized, str)

    def test_from_dict_defaults(self) -> None:
        """from_dict uses defaults for missing optional fields."""
        data = {
            "session_id": 1,
            "started_at": "2026-02-09T10:00:00+00:00",
        }
        session = Session.from_dict(data)
        assert session.ended_at is None
        assert session.issue_id == ""
        assert session.status == "completed"
        assert session.events == []

    def test_from_dict_preserves_event_data(self) -> None:
        """from_dict reconstructs event data correctly."""
        data = {
            "session_id": 5,
            "started_at": "2026-02-09T10:00:00+00:00",
            "events": [
                {"t": 3.5, "type": "bash", "data": {"command": "git status", "exit_code": 0}},
            ],
        }
        session = Session.from_dict(data)
        assert session.events[0].t == 3.5
        assert session.events[0].data["exit_code"] == 0


# ---------------------------------------------------------------------------
# Truncation Tests
# ---------------------------------------------------------------------------

class TestTruncatePreview:
    """Test the _truncate_preview helper."""

    def test_short_string_unchanged(self) -> None:
        """Strings shorter than max_length are returned as-is."""
        assert _truncate_preview("hello", 500) == "hello"

    def test_exact_length_unchanged(self) -> None:
        """String exactly at max_length is not truncated."""
        text = "a" * MAX_PREVIEW_LENGTH
        assert _truncate_preview(text) == text

    def test_long_string_truncated(self) -> None:
        """Strings exceeding max_length are truncated with ellipsis."""
        text = "x" * (MAX_PREVIEW_LENGTH + 100)
        result = _truncate_preview(text)
        assert len(result) == MAX_PREVIEW_LENGTH + 3  # +3 for "..."
        assert result.endswith("...")

    def test_empty_string(self) -> None:
        """Empty string is returned unchanged."""
        assert _truncate_preview("") == ""

    def test_custom_max_length(self) -> None:
        """Custom max_length is respected."""
        result = _truncate_preview("abcdefgh", max_length=5)
        assert result == "abcde..."


# ---------------------------------------------------------------------------
# SessionRecorder Lifecycle Tests
# ---------------------------------------------------------------------------

class TestSessionRecorderLifecycle:
    """Test start/end session lifecycle."""

    def test_start_creates_session(self, recorder: SessionRecorder) -> None:
        """start() creates a Session with correct fields."""
        session = recorder.start()
        assert session.session_id == 1
        assert session.issue_id == "ENG-74"
        assert session.status == "running"
        assert session.started_at is not None
        assert session.events == []

    def test_start_with_override_issue_id(self, recorder: SessionRecorder) -> None:
        """start() accepts an override issue_id."""
        session = recorder.start(issue_id="ENG-99")
        assert session.issue_id == "ENG-99"
        recorder.end()

    def test_end_finalizes_session(self, recorder: SessionRecorder) -> None:
        """end() sets ended_at, status, and writes file."""
        recorder.start()
        session = recorder.end()
        assert session.status == "completed"
        assert session.ended_at is not None

    def test_end_with_failed_status(self, recorder: SessionRecorder) -> None:
        """end() accepts a custom status."""
        recorder.start()
        session = recorder.end(status="failed")
        assert session.status == "failed"

    def test_end_writes_json_file(self, recorder: SessionRecorder, tmp_path: Path) -> None:
        """end() persists a valid JSON file to disk."""
        recorder.start()
        recorder.record_event("tool_call", {"tool": "Read"})
        recorder.end()

        session_file = tmp_path / ".agent" / "sessions" / "session-1.json"
        assert session_file.exists()

        data = json.loads(session_file.read_text())
        assert data["session_id"] == 1
        assert data["issue_id"] == "ENG-74"
        assert data["status"] == "completed"
        assert len(data["events"]) == 1

    def test_double_start_raises(self, recorder: SessionRecorder) -> None:
        """start() raises RuntimeError if session already active."""
        recorder.start()
        with pytest.raises(RuntimeError, match="already in progress"):
            recorder.start()
        recorder.end()

    def test_end_without_start_raises(self, recorder: SessionRecorder) -> None:
        """end() raises RuntimeError if no session is active."""
        with pytest.raises(RuntimeError, match="No active session"):
            recorder.end()

    def test_session_property_none_before_start(self, recorder: SessionRecorder) -> None:
        """session property is None before start()."""
        assert recorder.session is None

    def test_session_property_none_after_end(self, recorder: SessionRecorder) -> None:
        """session property is None after end()."""
        recorder.start()
        recorder.end()
        assert recorder.session is None

    def test_sessions_dir_created(self, tmp_path: Path) -> None:
        """start() creates .agent/sessions/ directory if missing."""
        recorder = SessionRecorder(project_dir=tmp_path)
        recorder.start()
        assert (tmp_path / ".agent" / "sessions").is_dir()
        recorder.end()


# ---------------------------------------------------------------------------
# Event Recording Tests
# ---------------------------------------------------------------------------

class TestEventRecording:
    """Test record_event behavior."""

    def test_record_tool_call(self, recorder: SessionRecorder) -> None:
        """Records a tool_call event with relative timestamp."""
        recorder.start()
        event = recorder.record_event("tool_call", {"tool": "Read", "args": {"file": "main.py"}})
        assert event is not None
        assert event.type == "tool_call"
        assert event.t >= 0.0
        assert event.data["tool"] == "Read"
        recorder.end()

    def test_record_file_write(self, recorder: SessionRecorder) -> None:
        """Records a file_write event."""
        recorder.start()
        event = recorder.record_event("file_write", {"path": "src/App.jsx", "diff": "+import React"})
        assert event is not None
        assert event.type == "file_write"
        assert event.data["path"] == "src/App.jsx"
        recorder.end()

    def test_record_bash(self, recorder: SessionRecorder) -> None:
        """Records a bash event with exit code."""
        recorder.start()
        event = recorder.record_event("bash", {"command": "npm test", "exit_code": 0})
        assert event is not None
        assert event.type == "bash"
        assert event.data["exit_code"] == 0
        recorder.end()

    def test_record_agent_call(self, recorder: SessionRecorder) -> None:
        """Records an agent_call event."""
        recorder.start()
        event = recorder.record_event("agent_call", {"agent": "code-reviewer"})
        assert event is not None
        assert event.type == "agent_call"
        recorder.end()

    def test_timestamps_are_monotonically_increasing(self, recorder: SessionRecorder) -> None:
        """Event timestamps increase over time."""
        recorder.start()
        e1 = recorder.record_event("tool_call", {"tool": "Read"})
        time.sleep(0.01)
        e2 = recorder.record_event("tool_call", {"tool": "Write"})
        assert e1 is not None and e2 is not None
        assert e2.t >= e1.t
        recorder.end()

    def test_record_without_data(self, recorder: SessionRecorder) -> None:
        """record_event works with no data argument."""
        recorder.start()
        event = recorder.record_event("tool_call")
        assert event is not None
        assert event.data == {}
        recorder.end()

    def test_record_without_active_session_returns_none(self, recorder: SessionRecorder) -> None:
        """record_event returns None when no session is active."""
        result = recorder.record_event("tool_call", {"tool": "Read"})
        assert result is None

    def test_preview_truncation_result_preview(self, recorder: SessionRecorder) -> None:
        """result_preview field is truncated to MAX_PREVIEW_LENGTH."""
        recorder.start()
        long_text = "x" * (MAX_PREVIEW_LENGTH + 200)
        event = recorder.record_event("tool_call", {"result_preview": long_text})
        assert event is not None
        assert len(event.data["result_preview"]) == MAX_PREVIEW_LENGTH + 3
        assert event.data["result_preview"].endswith("...")
        recorder.end()

    def test_preview_truncation_output_preview(self, recorder: SessionRecorder) -> None:
        """output_preview field is truncated to MAX_PREVIEW_LENGTH."""
        recorder.start()
        long_text = "y" * (MAX_PREVIEW_LENGTH + 50)
        event = recorder.record_event("bash", {"output_preview": long_text, "exit_code": 0})
        assert event is not None
        assert len(event.data["output_preview"]) == MAX_PREVIEW_LENGTH + 3
        assert event.data["exit_code"] == 0
        recorder.end()

    def test_short_preview_not_truncated(self, recorder: SessionRecorder) -> None:
        """Short preview fields are left unchanged."""
        recorder.start()
        event = recorder.record_event("tool_call", {"result_preview": "short"})
        assert event is not None
        assert event.data["result_preview"] == "short"
        recorder.end()


# ---------------------------------------------------------------------------
# Thread Safety Tests
# ---------------------------------------------------------------------------

class TestThreadSafety:
    """Test concurrent event recording."""

    def test_concurrent_recording(self, recorder: SessionRecorder) -> None:
        """Multiple threads can record events without data corruption."""
        recorder.start()
        errors: list[str] = []

        def record_batch(batch_id: int) -> None:
            try:
                for i in range(50):
                    recorder.record_event(
                        "tool_call",
                        {"batch": batch_id, "index": i},
                    )
            except Exception as exc:
                errors.append(f"Batch {batch_id}: {exc}")

        threads = [threading.Thread(target=record_batch, args=(n,)) for n in range(4)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        assert errors == [], f"Thread errors: {errors}"
        # 4 threads x 50 events each = 200 events
        assert len(recorder.session.events) == 200  # type: ignore[union-attr]
        recorder.end()


# ---------------------------------------------------------------------------
# get_next_session_id Tests
# ---------------------------------------------------------------------------

class TestGetNextSessionId:
    """Test get_next_session_id."""

    def test_empty_directory(self, sessions_dir: Path) -> None:
        """Returns 1 when no session files exist."""
        assert get_next_session_id(sessions_dir) == 1

    def test_nonexistent_directory(self, tmp_path: Path) -> None:
        """Returns 1 when directory does not exist."""
        assert get_next_session_id(tmp_path / "nonexistent") == 1

    def test_sequential_files(self, sessions_dir: Path) -> None:
        """Returns max_id + 1 from existing files."""
        (sessions_dir / "session-1.json").write_text("{}")
        (sessions_dir / "session-2.json").write_text("{}")
        (sessions_dir / "session-3.json").write_text("{}")
        assert get_next_session_id(sessions_dir) == 4

    def test_gaps_in_sequence(self, sessions_dir: Path) -> None:
        """Returns max_id + 1 even with gaps."""
        (sessions_dir / "session-1.json").write_text("{}")
        (sessions_dir / "session-10.json").write_text("{}")
        assert get_next_session_id(sessions_dir) == 11

    def test_ignores_non_session_files(self, sessions_dir: Path) -> None:
        """Ignores files that do not match session-{N}.json."""
        (sessions_dir / "session-5.json").write_text("{}")
        (sessions_dir / "notes.txt").write_text("ignore me")
        (sessions_dir / "session-abc.json").write_text("{}")  # Non-numeric
        assert get_next_session_id(sessions_dir) == 6

    def test_ignores_directories(self, sessions_dir: Path) -> None:
        """Ignores subdirectories named like session files."""
        (sessions_dir / "session-99.json").mkdir()
        (sessions_dir / "session-3.json").write_text("{}")
        assert get_next_session_id(sessions_dir) == 4


# ---------------------------------------------------------------------------
# rotate_sessions Tests
# ---------------------------------------------------------------------------

class TestRotateSessions:
    """Test rotate_sessions."""

    def test_no_rotation_when_under_limit(self, sessions_dir: Path) -> None:
        """No files deleted when count is at or below max_sessions."""
        for i in range(1, 6):
            (sessions_dir / f"session-{i}.json").write_text("{}")
        deleted = rotate_sessions(sessions_dir, max_sessions=10)
        assert deleted == 0
        assert len(list(sessions_dir.glob("session-*.json"))) == 5

    def test_rotation_removes_oldest(self, sessions_dir: Path) -> None:
        """Oldest files (lowest IDs) are removed when over limit."""
        for i in range(1, 8):
            (sessions_dir / f"session-{i}.json").write_text("{}")

        deleted = rotate_sessions(sessions_dir, max_sessions=5)
        assert deleted == 2

        remaining = sorted(p.name for p in sessions_dir.glob("session-*.json"))
        assert remaining == [
            "session-3.json",
            "session-4.json",
            "session-5.json",
            "session-6.json",
            "session-7.json",
        ]

    def test_rotation_exactly_at_limit(self, sessions_dir: Path) -> None:
        """No deletion when count equals max_sessions."""
        for i in range(1, 4):
            (sessions_dir / f"session-{i}.json").write_text("{}")
        deleted = rotate_sessions(sessions_dir, max_sessions=3)
        assert deleted == 0

    def test_rotation_nonexistent_directory(self, tmp_path: Path) -> None:
        """Returns 0 when directory does not exist."""
        assert rotate_sessions(tmp_path / "nonexistent") == 0

    def test_rotation_with_gaps(self, sessions_dir: Path) -> None:
        """Rotation handles non-contiguous IDs correctly."""
        for i in [1, 5, 10, 20, 50]:
            (sessions_dir / f"session-{i}.json").write_text("{}")

        deleted = rotate_sessions(sessions_dir, max_sessions=3)
        assert deleted == 2

        remaining_ids = sorted(
            int(p.stem.removeprefix("session-"))
            for p in sessions_dir.glob("session-*.json")
        )
        assert remaining_ids == [10, 20, 50]

    def test_rotation_ignores_non_session_files(self, sessions_dir: Path) -> None:
        """Non-session files are not counted or deleted."""
        for i in range(1, 6):
            (sessions_dir / f"session-{i}.json").write_text("{}")
        (sessions_dir / "readme.txt").write_text("keep me")

        deleted = rotate_sessions(sessions_dir, max_sessions=3)
        assert deleted == 2
        assert (sessions_dir / "readme.txt").exists()


# ---------------------------------------------------------------------------
# File Persistence Tests
# ---------------------------------------------------------------------------

class TestFilePersistence:
    """Test JSON file writing and reading."""

    def test_written_json_is_valid(self, recorder: SessionRecorder, tmp_path: Path) -> None:
        """Session JSON file is valid and contains all events."""
        recorder.start()
        recorder.record_event("tool_call", {"tool": "Read", "args": {"file": "a.py"}})
        recorder.record_event("bash", {"command": "pytest", "exit_code": 0, "output_preview": "ok"})
        recorder.record_event("file_write", {"path": "b.py", "diff": "+line"})
        recorder.end()

        path = tmp_path / ".agent" / "sessions" / "session-1.json"
        assert path.exists()

        data = json.loads(path.read_text())
        assert data["session_id"] == 1
        assert data["status"] == "completed"
        assert len(data["events"]) == 3
        assert data["events"][0]["type"] == "tool_call"
        assert data["events"][1]["type"] == "bash"
        assert data["events"][2]["type"] == "file_write"

    def test_session_from_file_roundtrip(self, recorder: SessionRecorder, tmp_path: Path) -> None:
        """Session written to file can be reconstructed with from_dict."""
        recorder.start(issue_id="ENG-99")
        recorder.record_event("agent_call", {"agent": "reviewer"})
        recorder.end()

        path = tmp_path / ".agent" / "sessions" / "session-1.json"
        data = json.loads(path.read_text())
        restored = Session.from_dict(data)

        assert restored.session_id == 1
        assert restored.issue_id == "ENG-99"
        assert restored.status == "completed"
        assert len(restored.events) == 1
        assert restored.events[0].type == "agent_call"

    def test_multiple_sessions_increment_id(self, tmp_path: Path) -> None:
        """Consecutive sessions get incrementing IDs."""
        r1 = SessionRecorder(project_dir=tmp_path, issue_id="ENG-1")
        r1.start()
        r1.end()

        r2 = SessionRecorder(project_dir=tmp_path, issue_id="ENG-2")
        r2.start()
        r2.end()

        sessions_dir = tmp_path / ".agent" / "sessions"
        assert (sessions_dir / "session-1.json").exists()
        assert (sessions_dir / "session-2.json").exists()

    def test_atomic_write_no_partial_on_error(self, recorder: SessionRecorder, tmp_path: Path) -> None:
        """If JSON serialization fails, no partial file is left behind."""
        recorder.start()
        recorder.record_event("tool_call", {"tool": "Read"})

        # Inject an unserializable object into session data to trigger error
        recorder.session.events.append(  # type: ignore[union-attr]
            SessionEvent(t=0.0, type="bad", data={"obj": object()})
        )

        with pytest.raises(TypeError):
            recorder.end()

        # The file should not exist since json.dump would have failed
        path = tmp_path / ".agent" / "sessions" / "session-1.json"
        assert not path.exists()


# ---------------------------------------------------------------------------
# Integration: Rotation During End
# ---------------------------------------------------------------------------

class TestEndTriggersRotation:
    """Test that end() calls rotate_sessions."""

    def test_rotation_called_on_end(self, recorder: SessionRecorder) -> None:
        """end() invokes rotate_sessions after saving."""
        recorder.start()
        with patch("axon_agent.monitoring.recorder.rotate_sessions") as mock_rotate:
            recorder.end()
        mock_rotate.assert_called_once_with(recorder.sessions_dir)
