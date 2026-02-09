"""
Session Recording to JSON
==========================

Records agent sessions to structured JSON files for later replay.

Each session captures timestamped events (tool calls, file writes, bash
commands, sub-agent invocations) and stores them in `.agent/sessions/`
as `session-{N}.json`. Old sessions are rotated when the count exceeds
MAX_SESSIONS.

ENG-74: Session Recording to JSON
"""

import json
import logging
import os
import tempfile
import threading
import time
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Final

logger = logging.getLogger("session_recorder")

# Maximum number of session files to keep before rotating the oldest
MAX_SESSIONS: Final[int] = 100

# Maximum length for preview strings (result_preview, output_preview)
MAX_PREVIEW_LENGTH: Final[int] = 500

# Subdirectory under .agent/ where session JSON files are stored
SESSIONS_DIR_NAME: Final[str] = "sessions"


@dataclass
class SessionEvent:
    """A single recorded event within an agent session.

    Attributes:
        t: Seconds elapsed since the session started.
        type: Event category (tool_call, file_write, bash, agent_call).
        data: Arbitrary payload specific to the event type.
    """

    t: float
    type: str
    data: dict[str, Any] = field(default_factory=dict)


@dataclass
class Session:
    """Full session record containing metadata and a list of events.

    Attributes:
        session_id: Incrementing integer identifier.
        started_at: ISO 8601 UTC timestamp when the session began.
        ended_at: ISO 8601 UTC timestamp when the session ended (or None).
        issue_id: The issue being worked on (e.g., "ENG-74").
        status: Current session status (running, completed, failed).
        events: Ordered list of session events.
    """

    session_id: int
    started_at: str
    ended_at: str | None = None
    issue_id: str = ""
    status: str = "running"
    events: list[SessionEvent] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        """Serialize the session to a JSON-compatible dictionary."""
        return {
            "session_id": self.session_id,
            "started_at": self.started_at,
            "ended_at": self.ended_at,
            "issue_id": self.issue_id,
            "status": self.status,
            "events": [asdict(e) for e in self.events],
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "Session":
        """Deserialize a session from a dictionary.

        Args:
            data: Dictionary with session fields including an 'events' list.

        Returns:
            Reconstructed Session instance.
        """
        events = [
            SessionEvent(
                t=e["t"],
                type=e["type"],
                data=e.get("data", {}),
            )
            for e in data.get("events", [])
        ]
        return cls(
            session_id=data["session_id"],
            started_at=data["started_at"],
            ended_at=data.get("ended_at"),
            issue_id=data.get("issue_id", ""),
            status=data.get("status", "completed"),
            events=events,
        )


def _truncate_preview(text: str, max_length: int = MAX_PREVIEW_LENGTH) -> str:
    """Truncate a string to max_length, appending '...' if trimmed.

    Args:
        text: The input string to truncate.
        max_length: Maximum allowed character count.

    Returns:
        The original string if short enough, otherwise truncated with
        an ellipsis suffix.
    """
    if len(text) <= max_length:
        return text
    return text[:max_length] + "..."


def _utc_now_iso() -> str:
    """Return the current UTC time as an ISO 8601 string.

    Returns:
        ISO-formatted timestamp with timezone info.
    """
    return datetime.now(timezone.utc).isoformat()


class SessionRecorder:
    """Records agent session events and persists them to JSON files.

    Thread-safe: all mutating operations on the event list are guarded
    by an internal lock so concurrent callers can safely record events.

    Args:
        project_dir: Root directory of the project (must contain or will
                     create a `.agent/sessions/` subdirectory).
        issue_id: The issue being worked on (e.g., "ENG-74").
    """

    def __init__(self, project_dir: Path, issue_id: str = "") -> None:
        self._project_dir = project_dir
        self._sessions_dir = project_dir / ".agent" / SESSIONS_DIR_NAME
        self._lock = threading.Lock()
        self._session: Session | None = None
        self._start_time: float = 0.0
        self._issue_id = issue_id

    @property
    def session(self) -> Session | None:
        """Return the current session, or None if not started."""
        return self._session

    @property
    def sessions_dir(self) -> Path:
        """Return the sessions storage directory path."""
        return self._sessions_dir

    def _ensure_sessions_dir(self) -> None:
        """Create the sessions directory if it does not exist."""
        self._sessions_dir.mkdir(parents=True, exist_ok=True)

    def start(self, issue_id: str | None = None) -> Session:
        """Begin a new recording session.

        Creates the session directory, determines the next session ID,
        and initialises the internal Session object.

        Args:
            issue_id: Override issue ID for this session. Falls back to
                      the value provided at construction time.

        Returns:
            The newly created Session instance.

        Raises:
            RuntimeError: If a session is already in progress.
        """
        if self._session is not None:
            raise RuntimeError("Session already in progress; call end() first")

        self._ensure_sessions_dir()

        resolved_issue = issue_id if issue_id is not None else self._issue_id
        session_id = get_next_session_id(self._sessions_dir)

        self._start_time = time.monotonic()
        self._session = Session(
            session_id=session_id,
            started_at=_utc_now_iso(),
            issue_id=resolved_issue,
            status="running",
        )

        logger.info(
            "Session %d started for issue %s",
            session_id,
            resolved_issue,
        )
        return self._session

    def record_event(
        self,
        event_type: str,
        data: dict[str, Any] | None = None,
    ) -> SessionEvent | None:
        """Record a single event in the current session.

        The event timestamp is computed relative to the session start
        time. Preview fields in *data* are automatically truncated to
        MAX_PREVIEW_LENGTH characters.

        Args:
            event_type: Category string (tool_call, file_write, bash,
                        agent_call).
            data: Payload dictionary for the event. Keys named
                  ``result_preview`` or ``output_preview`` are truncated.

        Returns:
            The recorded SessionEvent, or None if no session is active.
        """
        elapsed = time.monotonic() - self._start_time
        safe_data = dict(data) if data else {}

        # Truncate known preview fields
        for preview_key in ("result_preview", "output_preview"):
            if preview_key in safe_data and isinstance(safe_data[preview_key], str):
                safe_data[preview_key] = _truncate_preview(safe_data[preview_key])

        event = SessionEvent(t=round(elapsed, 3), type=event_type, data=safe_data)

        with self._lock:
            if self._session is None:
                logger.warning("No active session to record event")
                return None
            self._session.events.append(event)

        return event

    def end(self, status: str = "completed") -> Session:
        """Finalise the current session, write JSON to disk, and rotate.

        Args:
            status: Final session status (e.g., "completed", "failed").

        Returns:
            The completed Session instance.

        Raises:
            RuntimeError: If no session is in progress.
        """
        if self._session is None:
            raise RuntimeError("No active session to end")

        self._session.ended_at = _utc_now_iso()
        self._session.status = status

        self._save_session()
        rotate_sessions(self._sessions_dir)

        session = self._session
        logger.info(
            "Session %d ended with status '%s' (%d events)",
            session.session_id,
            status,
            len(session.events),
        )

        self._session = None
        self._start_time = 0.0

        return session

    def _save_session(self) -> None:
        """Persist the current session to a JSON file atomically.

        Writes to a temporary file first, then renames to prevent
        corrupt partial writes on crash.
        """
        if self._session is None:
            return

        self._ensure_sessions_dir()
        target = self._sessions_dir / f"session-{self._session.session_id}.json"

        try:
            fd, tmp_path = tempfile.mkstemp(
                suffix=".tmp",
                prefix="session_",
                dir=str(self._sessions_dir),
            )
            try:
                with os.fdopen(fd, "w") as f:
                    json.dump(self._session.to_dict(), f, indent=2)
                os.replace(tmp_path, str(target))
            except BaseException:
                try:
                    os.unlink(tmp_path)
                except OSError:
                    pass
                raise
        except IOError as exc:
            logger.error("Failed to save session %d: %s", self._session.session_id, exc)


def get_next_session_id(sessions_dir: Path) -> int:
    """Determine the next session ID by scanning existing files.

    Looks for files matching ``session-{N}.json`` in *sessions_dir* and
    returns the highest N + 1. If no files exist, returns 1.

    Args:
        sessions_dir: Directory containing session JSON files.

    Returns:
        The next available integer session ID.
    """
    max_id = 0

    if not sessions_dir.exists():
        return 1

    for entry in sessions_dir.iterdir():
        if entry.is_file() and entry.name.startswith("session-") and entry.name.endswith(".json"):
            try:
                num_str = entry.stem.removeprefix("session-")
                num = int(num_str)
                if num > max_id:
                    max_id = num
            except ValueError:
                continue

    return max_id + 1


def rotate_sessions(sessions_dir: Path, max_sessions: int = MAX_SESSIONS) -> int:
    """Remove oldest session files when the count exceeds max_sessions.

    Files are sorted by the numeric ID embedded in their filename; the
    lowest IDs (oldest sessions) are deleted first.

    Args:
        sessions_dir: Directory containing session JSON files.
        max_sessions: Maximum number of files to retain.

    Returns:
        Number of files deleted.
    """
    if not sessions_dir.exists():
        return 0

    session_files: list[tuple[int, Path]] = []
    for entry in sessions_dir.iterdir():
        if entry.is_file() and entry.name.startswith("session-") and entry.name.endswith(".json"):
            try:
                num_str = entry.stem.removeprefix("session-")
                num = int(num_str)
                session_files.append((num, entry))
            except ValueError:
                continue

    if len(session_files) <= max_sessions:
        return 0

    # Sort by ID ascending (oldest first)
    session_files.sort(key=lambda pair: pair[0])
    to_remove = len(session_files) - max_sessions
    deleted = 0

    for _, filepath in session_files[:to_remove]:
        try:
            filepath.unlink()
            deleted += 1
            logger.info("Rotated old session file: %s", filepath.name)
        except OSError as exc:
            logger.warning("Failed to delete session file %s: %s", filepath.name, exc)

    return deleted
