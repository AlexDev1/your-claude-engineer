"""
Database Functions for Task Analytics
======================================

Provides SQL aggregation queries for project statistics, stale issue detection,
and session timeline parsing.

These functions can work with:
1. In-memory data store (for development/testing)
2. PostgreSQL database (for production deployment)

Configuration:
- STALE_THRESHOLD_HOURS: Hours without activity to consider task stale (default: 2)
- DATABASE_URL: PostgreSQL connection string (optional, falls back to in-memory)
"""

import os
import re
from datetime import datetime, timedelta
from typing import Any, Optional
from dataclasses import dataclass, field


# =============================================================================
# Configuration
# =============================================================================

# Stale threshold from environment (default: 2 hours)
STALE_THRESHOLD_HOURS = float(os.environ.get("STALE_THRESHOLD_HOURS", "2"))


# =============================================================================
# Data Models
# =============================================================================


@dataclass
class ProjectStats:
    """Aggregated project statistics."""

    # Task counts by state
    todo_count: int = 0
    in_progress_count: int = 0
    done_count: int = 0
    cancelled_count: int = 0

    # Task counts by priority
    urgent_count: int = 0
    high_count: int = 0
    medium_count: int = 0
    low_count: int = 0
    none_count: int = 0

    # Time metrics (in hours)
    avg_completion_time_hours: float = 0.0
    avg_in_progress_time_hours: float = 0.0

    # Comment metrics
    avg_comments_per_task: float = 0.0
    total_comments: int = 0

    # Stale tasks
    stale_tasks: list = field(default_factory=list)
    stale_count: int = 0

    # Metadata
    total_tasks: int = 0
    team: str = ""
    project: Optional[str] = None
    calculated_at: str = ""
    stale_threshold_hours: float = STALE_THRESHOLD_HOURS

    def to_dict(self) -> dict:
        """Convert to dictionary for JSON serialization."""
        return {
            "counts_by_state": {
                "todo": self.todo_count,
                "in_progress": self.in_progress_count,
                "done": self.done_count,
                "cancelled": self.cancelled_count,
            },
            "counts_by_priority": {
                "urgent": self.urgent_count,
                "high": self.high_count,
                "medium": self.medium_count,
                "low": self.low_count,
                "none": self.none_count,
            },
            "time_metrics": {
                "avg_completion_time_hours": round(self.avg_completion_time_hours, 2),
                "avg_in_progress_time_hours": round(self.avg_in_progress_time_hours, 2),
            },
            "comment_metrics": {
                "avg_comments_per_task": round(self.avg_comments_per_task, 2),
                "total_comments": self.total_comments,
            },
            "stale_tasks": {
                "count": self.stale_count,
                "threshold_hours": self.stale_threshold_hours,
                "issues": self.stale_tasks,
            },
            "metadata": {
                "total_tasks": self.total_tasks,
                "team": self.team,
                "project": self.project,
                "calculated_at": self.calculated_at,
            },
        }


@dataclass
class SessionEntry:
    """A single session entry parsed from META issue comments."""

    session_number: int
    summary: str
    tasks_mentioned: list = field(default_factory=list)
    tasks_completed: int = 0
    timestamp: Optional[str] = None
    author: str = "Agent"
    raw_content: str = ""

    def to_dict(self) -> dict:
        """Convert to dictionary for JSON serialization."""
        return {
            "session_number": self.session_number,
            "summary": self.summary,
            "tasks_mentioned": self.tasks_mentioned,
            "tasks_completed": self.tasks_completed,
            "timestamp": self.timestamp,
            "author": self.author,
        }


@dataclass
class SessionTimeline:
    """Timeline of sessions parsed from META issue."""

    meta_issue_id: str = ""
    sessions: list = field(default_factory=list)
    total_sessions: int = 0
    total_tasks_completed: int = 0
    last_session_at: Optional[str] = None

    def to_dict(self) -> dict:
        """Convert to dictionary for JSON serialization."""
        return {
            "meta_issue_id": self.meta_issue_id,
            "total_sessions": self.total_sessions,
            "total_tasks_completed": self.total_tasks_completed,
            "last_session_at": self.last_session_at,
            "sessions": [s.to_dict() for s in self.sessions],
        }


# =============================================================================
# In-Memory Data Store (Development/Demo)
# =============================================================================

# This simulates a database for development. In production, replace with
# actual PostgreSQL queries.

_ISSUES_STORE: dict[str, dict] = {}


def set_issues_store(store: dict[str, dict]) -> None:
    """Set the issues store (for integration with analytics_server)."""
    global _ISSUES_STORE
    _ISSUES_STORE = store


def get_issues_store() -> dict[str, dict]:
    """Get the current issues store."""
    return _ISSUES_STORE


# =============================================================================
# Core Database Functions
# =============================================================================


def get_project_stats(
    team: str,
    project: Optional[str] = None,
    issues: Optional[list[dict]] = None,
) -> ProjectStats:
    """
    Get comprehensive project statistics.

    This function performs SQL-style aggregations on task data:
    - Count of tasks by each state (Todo, In Progress, Done, Cancelled)
    - Count of tasks by priority (urgent, high, medium, low, none)
    - Average time from creation to Done (in hours)
    - Average time in "In Progress" state (in hours)
    - Average number of comments per task
    - List of stale tasks (In Progress longer than threshold)

    Args:
        team: Team identifier (e.g., "ENG")
        project: Optional project filter
        issues: Optional list of issues (if None, uses internal store)

    Returns:
        ProjectStats with all aggregated metrics

    Example SQL equivalent:
    ```sql
    SELECT
        SUM(CASE WHEN state = 'Todo' THEN 1 ELSE 0 END) as todo_count,
        SUM(CASE WHEN state = 'In Progress' THEN 1 ELSE 0 END) as in_progress_count,
        SUM(CASE WHEN state = 'Done' THEN 1 ELSE 0 END) as done_count,
        SUM(CASE WHEN state = 'Cancelled' THEN 1 ELSE 0 END) as cancelled_count,
        AVG(EXTRACT(EPOCH FROM (completed_at - created_at))/3600) as avg_completion_hours
    FROM issues
    WHERE team = :team
    ```
    """
    now = datetime.now()
    stats = ProjectStats(
        team=team,
        project=project,
        calculated_at=now.isoformat(),
        stale_threshold_hours=STALE_THRESHOLD_HOURS,
    )

    # Get issues from store or use provided list
    if issues is None:
        issues = list(_ISSUES_STORE.values())

    # Filter by team
    filtered_issues = [i for i in issues if i.get("team", "ENG") == team]

    # Filter by project if specified
    if project:
        filtered_issues = [i for i in filtered_issues if i.get("project") == project]

    if not filtered_issues:
        return stats

    stats.total_tasks = len(filtered_issues)

    # Aggregation variables
    completion_times: list[float] = []
    in_progress_times: list[float] = []
    total_comments = 0

    for issue in filtered_issues:
        state = issue.get("state", "Todo")
        priority = issue.get("priority", "none").lower()

        # Count by state
        if state == "Todo":
            stats.todo_count += 1
        elif state == "In Progress":
            stats.in_progress_count += 1

            # Calculate time in progress
            updated_at = issue.get("updated_at") or issue.get("created_at")
            if updated_at:
                try:
                    updated = datetime.fromisoformat(updated_at.replace("Z", "+00:00"))
                    if updated.tzinfo:
                        updated = updated.replace(tzinfo=None)
                    hours_in_progress = (now - updated).total_seconds() / 3600
                    in_progress_times.append(hours_in_progress)

                    # Check if stale
                    if hours_in_progress >= STALE_THRESHOLD_HOURS:
                        stats.stale_tasks.append({
                            "identifier": issue.get("identifier", ""),
                            "title": issue.get("title", ""),
                            "hours_stale": round(hours_in_progress, 1),
                            "priority": priority,
                            "updated_at": updated_at,
                        })
                except (ValueError, TypeError):
                    pass

        elif state == "Done":
            stats.done_count += 1

            # Calculate completion time
            created_at = issue.get("created_at")
            completed_at = issue.get("completed_at")
            if created_at and completed_at:
                try:
                    created = datetime.fromisoformat(created_at.replace("Z", "+00:00"))
                    completed = datetime.fromisoformat(completed_at.replace("Z", "+00:00"))
                    if created.tzinfo:
                        created = created.replace(tzinfo=None)
                    if completed.tzinfo:
                        completed = completed.replace(tzinfo=None)
                    hours = (completed - created).total_seconds() / 3600
                    completion_times.append(hours)
                except (ValueError, TypeError):
                    pass

        elif state == "Cancelled":
            stats.cancelled_count += 1

        # Count by priority
        if priority == "urgent":
            stats.urgent_count += 1
        elif priority == "high":
            stats.high_count += 1
        elif priority == "medium":
            stats.medium_count += 1
        elif priority == "low":
            stats.low_count += 1
        else:
            stats.none_count += 1

        # Count comments
        comments = issue.get("comments", [])
        total_comments += len(comments)

    # Calculate averages
    if completion_times:
        stats.avg_completion_time_hours = sum(completion_times) / len(completion_times)

    if in_progress_times:
        stats.avg_in_progress_time_hours = sum(in_progress_times) / len(in_progress_times)

    stats.total_comments = total_comments
    if stats.total_tasks > 0:
        stats.avg_comments_per_task = total_comments / stats.total_tasks

    # Sort stale tasks by hours (most stale first)
    stats.stale_tasks.sort(key=lambda x: x.get("hours_stale", 0), reverse=True)
    stats.stale_count = len(stats.stale_tasks)

    return stats


def get_stale_issues(
    team: str = "ENG",
    threshold_hours: Optional[float] = None,
    issues: Optional[list[dict]] = None,
) -> dict[str, Any]:
    """
    Get tasks that have been in "In Progress" longer than the threshold.

    Args:
        team: Team identifier
        threshold_hours: Override default threshold (uses STALE_THRESHOLD_HOURS if None)
        issues: Optional list of issues

    Returns:
        Dictionary with stale_count and list of stale issues

    Example SQL equivalent:
    ```sql
    SELECT identifier, title, priority, updated_at,
           EXTRACT(EPOCH FROM (NOW() - updated_at))/3600 as hours_stale
    FROM issues
    WHERE team = :team
      AND state = 'In Progress'
      AND updated_at < NOW() - INTERVAL ':threshold hours'
    ORDER BY updated_at ASC
    ```
    """
    threshold = threshold_hours if threshold_hours is not None else STALE_THRESHOLD_HOURS
    now = datetime.now()

    # Get issues
    if issues is None:
        issues = list(_ISSUES_STORE.values())

    # Filter for in-progress tasks
    in_progress = [
        i for i in issues
        if i.get("team", "ENG") == team and i.get("state") == "In Progress"
    ]

    stale_issues = []
    for issue in in_progress:
        updated_at = issue.get("updated_at") or issue.get("created_at")
        if not updated_at:
            continue

        try:
            updated = datetime.fromisoformat(updated_at.replace("Z", "+00:00"))
            if updated.tzinfo:
                updated = updated.replace(tzinfo=None)
            hours_stale = (now - updated).total_seconds() / 3600

            if hours_stale >= threshold:
                stale_issues.append({
                    "identifier": issue.get("identifier", ""),
                    "title": issue.get("title", ""),
                    "priority": issue.get("priority", "none"),
                    "hours_stale": round(hours_stale, 1),
                    "updated_at": updated_at,
                })
        except (ValueError, TypeError):
            pass

    # Sort by most stale first
    stale_issues.sort(key=lambda x: x.get("hours_stale", 0), reverse=True)

    return {
        "stale_count": len(stale_issues),
        "threshold_hours": threshold,
        "team": team,
        "issues": stale_issues,
    }


def get_session_timeline(
    meta_issue_id: str,
    issues: Optional[list[dict]] = None,
) -> SessionTimeline:
    """
    Parse session summaries from META issue comments.

    META issues track agent sessions with comments like:
    - "Session 1: Completed ENG-1, ENG-2. Set up project structure."
    - "Session 2: Fixed bug in ENG-3. Added tests."

    This function parses these comments and returns a timeline.

    Args:
        meta_issue_id: Identifier of the META issue (e.g., "ENG-META" or "ENG-0")
        issues: Optional list of issues

    Returns:
        SessionTimeline with parsed session entries

    Session comment patterns recognized:
    - "Session N: <summary>"
    - "Session #N: <summary>"
    - "#N <summary>"
    - Task references: ENG-123, TASK-456, etc.
    """
    timeline = SessionTimeline(meta_issue_id=meta_issue_id)

    # Get issues
    if issues is None:
        issues = list(_ISSUES_STORE.values())

    # Find META issue
    meta_issue = None
    for issue in issues:
        identifier = issue.get("identifier", "")
        if identifier == meta_issue_id or identifier.upper() == meta_issue_id.upper():
            meta_issue = issue
            break

    if not meta_issue:
        return timeline

    # Parse comments
    comments = meta_issue.get("comments", [])
    sessions: list[SessionEntry] = []

    # Patterns for session detection
    session_pattern = re.compile(
        r"(?:Session\s*#?\s*(\d+)|#(\d+))\s*[:\-]?\s*(.+)",
        re.IGNORECASE | re.DOTALL
    )

    # Pattern for task references (ENG-123, TASK-456, etc.)
    task_ref_pattern = re.compile(r"([A-Z]+-\d+)", re.IGNORECASE)

    # Pattern for completed task indicators
    completed_pattern = re.compile(
        r"(?:completed?|done|finished|closed|resolved)\s+([A-Z]+-\d+)",
        re.IGNORECASE
    )

    for comment in comments:
        content = comment.get("content", "")
        timestamp = comment.get("created_at")
        author = comment.get("author", "Agent")

        # Try to match session pattern
        match = session_pattern.search(content)
        if match:
            session_num = int(match.group(1) or match.group(2))
            summary = match.group(3).strip()

            # Find all task references
            task_refs = task_ref_pattern.findall(content)
            task_refs = [ref.upper() for ref in task_refs]

            # Count completed tasks
            completed_matches = completed_pattern.findall(content)
            completed_count = len(completed_matches)

            # If no explicit completed markers, count unique task refs
            if completed_count == 0 and task_refs:
                # Heuristic: count tasks mentioned with positive verbs
                positive_verbs = ["completed", "done", "finished", "closed", "fixed", "resolved", "implemented"]
                for verb in positive_verbs:
                    if verb in content.lower():
                        completed_count = len(set(task_refs))
                        break

            entry = SessionEntry(
                session_number=session_num,
                summary=summary[:500],  # Limit summary length
                tasks_mentioned=list(set(task_refs)),
                tasks_completed=completed_count,
                timestamp=timestamp,
                author=author,
                raw_content=content,
            )
            sessions.append(entry)

    # Sort by session number
    sessions.sort(key=lambda x: x.session_number)

    # Build timeline
    timeline.sessions = sessions
    timeline.total_sessions = len(sessions)
    timeline.total_tasks_completed = sum(s.tasks_completed for s in sessions)

    if sessions:
        # Get latest session timestamp
        latest = max(
            (s for s in sessions if s.timestamp),
            key=lambda s: s.timestamp or "",
            default=None
        )
        if latest:
            timeline.last_session_at = latest.timestamp

    return timeline


# =============================================================================
# SQL Query Builders (for PostgreSQL production use)
# =============================================================================


def build_stats_query(team: str, project: Optional[str] = None) -> tuple[str, dict]:
    """
    Build SQL query for project statistics.

    Returns:
        Tuple of (SQL query string, parameters dict)
    """
    params = {"team": team}

    project_filter = ""
    if project:
        project_filter = "AND project = :project"
        params["project"] = project

    query = f"""
    SELECT
        -- State counts
        SUM(CASE WHEN state = 'Todo' THEN 1 ELSE 0 END) as todo_count,
        SUM(CASE WHEN state = 'In Progress' THEN 1 ELSE 0 END) as in_progress_count,
        SUM(CASE WHEN state = 'Done' THEN 1 ELSE 0 END) as done_count,
        SUM(CASE WHEN state = 'Cancelled' THEN 1 ELSE 0 END) as cancelled_count,

        -- Priority counts
        SUM(CASE WHEN priority = 'urgent' THEN 1 ELSE 0 END) as urgent_count,
        SUM(CASE WHEN priority = 'high' THEN 1 ELSE 0 END) as high_count,
        SUM(CASE WHEN priority = 'medium' THEN 1 ELSE 0 END) as medium_count,
        SUM(CASE WHEN priority = 'low' THEN 1 ELSE 0 END) as low_count,
        SUM(CASE WHEN priority IS NULL OR priority = 'none' THEN 1 ELSE 0 END) as none_count,

        -- Time metrics
        AVG(CASE
            WHEN state = 'Done' AND completed_at IS NOT NULL
            THEN EXTRACT(EPOCH FROM (completed_at - created_at)) / 3600
            ELSE NULL
        END) as avg_completion_hours,

        -- Comment count (requires join or subquery)
        COUNT(*) as total_tasks

    FROM issues
    WHERE team = :team
    {project_filter}
    """

    return query, params


def build_stale_issues_query(
    team: str,
    threshold_hours: float = STALE_THRESHOLD_HOURS,
) -> tuple[str, dict]:
    """
    Build SQL query for stale issues.

    Returns:
        Tuple of (SQL query string, parameters dict)
    """
    params = {
        "team": team,
        "threshold": f"{threshold_hours} hours",
    }

    query = """
    SELECT
        identifier,
        title,
        priority,
        updated_at,
        EXTRACT(EPOCH FROM (NOW() - updated_at)) / 3600 as hours_stale
    FROM issues
    WHERE team = :team
      AND state = 'In Progress'
      AND updated_at < NOW() - INTERVAL :threshold
    ORDER BY updated_at ASC
    """

    return query, params


def build_session_timeline_query(meta_issue_id: str) -> tuple[str, dict]:
    """
    Build SQL query for session timeline from META issue comments.

    Returns:
        Tuple of (SQL query string, parameters dict)
    """
    params = {"meta_issue_id": meta_issue_id}

    query = """
    SELECT
        c.id,
        c.content,
        c.author,
        c.created_at
    FROM comments c
    JOIN issues i ON c.issue_id = i.id
    WHERE i.identifier = :meta_issue_id
    ORDER BY c.created_at ASC
    """

    return query, params
