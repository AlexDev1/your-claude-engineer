"""
Session Replay API Router
==========================

Provides endpoints for listing and retrieving recorded agent sessions.

Endpoints:
- GET /api/sessions - List all sessions with metadata
- GET /api/sessions/{session_id} - Get full session for replay

Reads session files from `.agent/sessions/session-{N}.json` produced
by the SessionRecorder (ENG-74).

ENG-75: Replay API endpoint
"""

import json
import logging
from datetime import datetime
from pathlib import Path
from typing import Any, Optional

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel

logger = logging.getLogger("sessions_router")

router = APIRouter(prefix="/api/sessions", tags=["sessions"])


class SessionSummary(BaseModel):
    """Summary metadata for a single session (used in list responses).

    Attributes:
        id: Numeric session identifier.
        started_at: ISO 8601 timestamp when the session began.
        ended_at: ISO 8601 timestamp when the session ended, or None.
        duration_seconds: Elapsed wall-clock time in seconds, or None.
        events_count: Number of events recorded in the session.
        status: Terminal status (running, completed, failed).
        issue_id: The issue the session was working on.
    """

    id: int
    started_at: str
    ended_at: Optional[str] = None
    duration_seconds: Optional[float] = None
    events_count: int = 0
    status: str = "unknown"
    issue_id: str = ""


def _get_sessions_dir() -> Path:
    """Return the sessions directory path relative to the project root.

    Uses the working directory's `.agent/sessions/` subdirectory, matching
    the convention established by SessionRecorder.

    Returns:
        Path to the sessions directory.
    """
    return Path(__file__).resolve().parent.parent / ".agent" / "sessions"


def _calculate_duration(started_at: Optional[str], ended_at: Optional[str]) -> Optional[float]:
    """Compute duration in seconds between two ISO 8601 timestamps.

    Args:
        started_at: ISO 8601 start timestamp.
        ended_at: ISO 8601 end timestamp.

    Returns:
        Duration in seconds rounded to one decimal, or None if either
        timestamp is missing or unparseable.
    """
    if not started_at or not ended_at:
        return None
    try:
        start = datetime.fromisoformat(started_at)
        end = datetime.fromisoformat(ended_at)
        return round((end - start).total_seconds(), 1)
    except (ValueError, TypeError):
        return None


def _load_session_file(filepath: Path) -> Optional[dict[str, Any]]:
    """Load and parse a single session JSON file.

    Args:
        filepath: Absolute path to the session JSON file.

    Returns:
        Parsed dictionary, or None if the file is missing or corrupt.
    """
    try:
        with open(filepath, "r") as f:
            return json.load(f)
    except (IOError, json.JSONDecodeError) as exc:
        logger.warning("Failed to load session file %s: %s", filepath.name, exc)
        return None


def _session_summary_from_data(data: dict[str, Any]) -> SessionSummary:
    """Build a SessionSummary from raw session data.

    Args:
        data: Parsed session JSON dictionary.

    Returns:
        SessionSummary with computed duration.
    """
    started_at = data.get("started_at", "")
    ended_at = data.get("ended_at")
    events = data.get("events", [])

    return SessionSummary(
        id=data.get("session_id", 0),
        started_at=started_at,
        ended_at=ended_at,
        duration_seconds=_calculate_duration(started_at, ended_at),
        events_count=len(events),
        status=data.get("status", "unknown"),
        issue_id=data.get("issue_id", ""),
    )


def _list_session_files(sessions_dir: Path) -> list[tuple[int, Path]]:
    """Scan the sessions directory for valid session JSON files.

    Args:
        sessions_dir: Directory to scan.

    Returns:
        List of (session_id, filepath) tuples sorted by session_id
        descending (newest first).
    """
    if not sessions_dir.exists():
        return []

    results: list[tuple[int, Path]] = []
    for entry in sessions_dir.iterdir():
        if (
            entry.is_file()
            and entry.name.startswith("session-")
            and entry.name.endswith(".json")
        ):
            try:
                num_str = entry.stem.removeprefix("session-")
                num = int(num_str)
                results.append((num, entry))
            except ValueError:
                continue

    # Sort by session_id descending (newest first)
    results.sort(key=lambda pair: pair[0], reverse=True)
    return results


@router.get("")
async def list_sessions(
    limit: int = Query(50, ge=1, le=500, description="Maximum sessions to return"),
    offset: int = Query(0, ge=0, description="Number of sessions to skip"),
    status: Optional[str] = Query(None, description="Filter by status (completed, failed, running)"),
    issue_id: Optional[str] = Query(None, description="Filter by issue ID (e.g. ENG-74)"),
) -> dict[str, Any]:
    """List all recorded sessions with metadata.

    Returns session summaries sorted by started_at descending (newest first).
    Supports pagination via limit/offset and optional filtering by status
    or issue_id.
    """
    sessions_dir = _get_sessions_dir()
    session_files = _list_session_files(sessions_dir)

    summaries: list[SessionSummary] = []
    for _sid, filepath in session_files:
        data = _load_session_file(filepath)
        if data is None:
            continue

        summary = _session_summary_from_data(data)

        # Apply filters
        if status is not None and summary.status != status:
            continue
        if issue_id is not None and summary.issue_id != issue_id:
            continue

        summaries.append(summary)

    total = len(summaries)
    page = summaries[offset: offset + limit]

    return {
        "sessions": [s.model_dump() for s in page],
        "total": total,
        "limit": limit,
        "offset": offset,
    }


@router.get("/{session_id}")
async def get_session(session_id: int) -> dict[str, Any]:
    """Get full session data for replay.

    Loads the complete session JSON including all events, suitable for
    feeding into a replay UI.

    Args:
        session_id: Numeric session identifier.

    Returns:
        Full session JSON with all events.

    Raises:
        HTTPException: 404 if the session file does not exist or is corrupt.
    """
    sessions_dir = _get_sessions_dir()
    filepath = sessions_dir / f"session-{session_id}.json"

    if not filepath.exists():
        raise HTTPException(
            status_code=404,
            detail=f"Session {session_id} not found",
        )

    data = _load_session_file(filepath)
    if data is None:
        raise HTTPException(
            status_code=500,
            detail=f"Session {session_id} file is corrupted",
        )

    return data
