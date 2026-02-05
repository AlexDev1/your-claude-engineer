"""
Progress Tracking Utilities
===========================

Functions for tracking and displaying progress of the autonomous coding agent.
Progress is tracked via Task MCP Server, with local state cached in .task_project.json.
"""

import json
from pathlib import Path
from typing import TypedDict

# Local marker file to track project initialization
TASK_PROJECT_MARKER: str = ".task_project.json"


class TaskProjectState(TypedDict, total=False):
    """Structure of the .task_project.json state file."""

    initialized: bool
    created_at: str
    team_key: str
    project_id: str
    project_name: str
    project_slug: str
    meta_issue_id: str
    total_issues: int
    notes: str


def load_task_project_state(project_dir: Path) -> TaskProjectState | None:
    """
    Load the project state from the marker file.

    Args:
        project_dir: Directory containing .task_project.json

    Returns:
        Project state dict or None if not initialized

    Raises:
        ValueError: If the state file exists but is corrupted or malformed

    Note:
        Returns None if file doesn't exist. Raises ValueError if file exists
        but cannot be parsed, to prevent silent state corruption.
    """
    marker_file: Path = project_dir / TASK_PROJECT_MARKER

    if not marker_file.exists():
        return None

    try:
        with open(marker_file, "r") as f:
            data = json.load(f)
    except json.JSONDecodeError as e:
        raise ValueError(
            f"Corrupted state file at {marker_file}: {e}\n"
            f"Delete the file to restart initialization, or restore from backup."
        ) from e
    except IOError as e:
        raise ValueError(
            f"Cannot read state file at {marker_file}: {e}\n"
            f"Check file permissions."
        ) from e

    # Validate structure
    if not isinstance(data, dict):
        raise ValueError(
            f"Invalid state file at {marker_file}: expected object, got {type(data).__name__}"
        )

    return data  # type: ignore[return-value]


def is_project_initialized(project_dir: Path) -> bool:
    """
    Check if project has been initialized.

    Args:
        project_dir: Directory to check

    Returns:
        True if .task_project.json exists and is valid with initialized=True
    """
    try:
        state = load_task_project_state(project_dir)
        return state is not None and state.get("initialized", False)
    except ValueError:
        # Corrupted state file - treat as not initialized but log warning
        print(f"Warning: Corrupted state file in {project_dir}, treating as uninitialized")
        return False


def print_session_header(session_num: int, is_initializer: bool) -> None:
    """Print a formatted header for the session."""
    session_type: str = "ORCHESTRATOR (init)" if is_initializer else "ORCHESTRATOR (continue)"

    print("\n" + "=" * 70)
    print(f"  SESSION {session_num}: {session_type}")
    print("=" * 70)
    print()


def print_progress_summary(project_dir: Path) -> None:
    """
    Print a summary of current progress.

    Since actual progress is tracked in Task MCP Server, this reads the local
    state file for cached information. The agent updates the server directly
    and reports progress in session comments.
    """
    try:
        state = load_task_project_state(project_dir)
    except ValueError as e:
        print(f"\nProgress: Error loading state - {e}")
        return

    if state is None:
        print("\nProgress: Project not yet initialized")
        return

    total: int = state.get("total_issues", 0)
    meta_issue: str = state.get("meta_issue_id", "unknown")
    project_name: str = state.get("project_name", "Unknown")

    print(f"\nProject Status:")
    print(f"  Project: {project_name}")
    print(f"  Total issues created: {total}")
    print(f"  META issue ID: {meta_issue}")
    print(f"  (Check Task MCP Server for current Done/In Progress/Todo counts)")
