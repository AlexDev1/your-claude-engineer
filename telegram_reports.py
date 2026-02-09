"""
Telegram Rich Reports
=====================

Structured report formatters for Telegram notifications.
Implements daily digests, session summaries, error alerts, and weekly reports.

All reports use HTML formatting compatible with Telegram's parse_mode="HTML".

Report Types:
- DailyDigest: Statistics and progress bar showing daily completion
- SessionSummary: Time, tokens spent, and git commits for each session
- ErrorAlert: File, line number, and attempt count context
- WeeklySummary: Cost and velocity trends
- ProgressBar: Visual percentage completion display

Usage:
    from telegram_reports import (
        format_daily_digest,
        format_session_summary,
        format_error_alert,
        format_weekly_summary,
        format_progress_bar,
    )

    # Create a daily digest
    report = format_daily_digest(
        completed=5,
        in_progress=2,
        todo=8,
        total=15,
        highlights=["Added auth system", "Fixed login bug"],
    )

    # Send via Telegram MCP
    Telegram_SendMessage(message=report, parse_mode="HTML")
"""

from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import Any


# =============================================================================
# Progress Bar
# =============================================================================


def format_progress_bar(
    current: int,
    total: int,
    width: int = 10,
    fill_char: str = "█",
    empty_char: str = "░",
) -> str:
    """
    Create a visual progress bar.

    Args:
        current: Current progress value
        total: Total value
        width: Number of characters in the bar
        fill_char: Character for filled portion
        empty_char: Character for empty portion

    Returns:
        Progress bar string like: "████░░░░░░ 40%"

    Example:
        >>> format_progress_bar(4, 10)
        '████░░░░░░ 40%'
    """
    if total <= 0:
        return f"{empty_char * width} 0%"

    percentage = min(100, max(0, (current / total) * 100))
    filled = int((percentage / 100) * width)
    empty = width - filled

    bar = fill_char * filled + empty_char * empty
    return f"{bar} {percentage:.0f}%"


def format_progress_bar_with_label(
    label: str,
    current: int,
    total: int,
    width: int = 10,
) -> str:
    """
    Create a progress bar with a label.

    Args:
        label: Label to display before the bar
        current: Current progress value
        total: Total value
        width: Number of characters in the bar

    Returns:
        Labeled progress bar like: "Tasks: ████░░░░░░ 40% (4/10)"
    """
    bar = format_progress_bar(current, total, width)
    return f"{label}: {bar} ({current}/{total})"


# =============================================================================
# Daily Digest Report
# =============================================================================


@dataclass
class DailyDigestData:
    """Data for daily digest report."""

    # Task counts
    completed_today: int = 0
    in_progress: int = 0
    todo: int = 0
    blocked: int = 0

    # Session stats
    sessions_count: int = 0
    total_duration_minutes: int = 0

    # Git stats
    commits_today: int = 0
    files_changed: int = 0
    lines_added: int = 0
    lines_removed: int = 0

    # Cost stats (optional)
    tokens_used: int = 0
    estimated_cost_usd: float = 0.0

    # Highlights
    highlights: list[str] = field(default_factory=list)

    # Date
    date: datetime = field(default_factory=datetime.now)


def format_daily_digest(data: DailyDigestData) -> str:
    """
    Format a daily digest report.

    Args:
        data: DailyDigestData with statistics

    Returns:
        HTML-formatted Telegram message
    """
    date_str = data.date.strftime("%Y-%m-%d")
    total_tasks = data.completed_today + data.in_progress + data.todo + data.blocked

    lines = [
        f"<b>📊 Daily Digest — {date_str}</b>",
        "",
    ]

    # Progress bar for completed vs total
    if total_tasks > 0:
        bar = format_progress_bar(data.completed_today, total_tasks, width=12)
        lines.append(f"<b>Progress:</b> {bar}")
        lines.append("")

    # Task breakdown
    lines.append("<b>Tasks:</b>")
    lines.append(f"  ✅ Completed: {data.completed_today}")
    lines.append(f"  🔄 In Progress: {data.in_progress}")
    lines.append(f"  📋 Todo: {data.todo}")
    if data.blocked > 0:
        lines.append(f"  ⚠️ Blocked: {data.blocked}")
    lines.append("")

    # Session stats
    if data.sessions_count > 0:
        hours = data.total_duration_minutes // 60
        minutes = data.total_duration_minutes % 60
        duration_str = f"{hours}h {minutes}m" if hours > 0 else f"{minutes}m"

        lines.append("<b>Sessions:</b>")
        lines.append(f"  ⏱️ Count: {data.sessions_count}")
        lines.append(f"  ⏰ Duration: {duration_str}")
        lines.append("")

    # Git stats
    if data.commits_today > 0:
        lines.append("<b>Git:</b>")
        lines.append(f"  📝 Commits: {data.commits_today}")
        lines.append(f"  📁 Files: {data.files_changed}")
        lines.append(f"  <code>+{data.lines_added} / -{data.lines_removed}</code>")
        lines.append("")

    # Cost stats (if available)
    if data.tokens_used > 0:
        lines.append("<b>Usage:</b>")
        lines.append(f"  🎫 Tokens: {data.tokens_used:,}")
        if data.estimated_cost_usd > 0:
            lines.append(f"  💵 Cost: ${data.estimated_cost_usd:.2f}")
        lines.append("")

    # Highlights
    if data.highlights:
        lines.append("<b>Highlights:</b>")
        for highlight in data.highlights[:5]:  # Limit to 5
            lines.append(f"  • {highlight}")
        lines.append("")

    return "\n".join(lines)


def format_daily_digest_simple(
    completed: int,
    in_progress: int,
    todo: int,
    blocked: int = 0,
    highlights: list[str] | None = None,
) -> str:
    """
    Simplified daily digest formatter.

    Args:
        completed: Tasks completed today
        in_progress: Tasks in progress
        todo: Tasks in todo
        blocked: Blocked tasks (optional)
        highlights: List of highlight strings (optional)

    Returns:
        HTML-formatted Telegram message
    """
    data = DailyDigestData(
        completed_today=completed,
        in_progress=in_progress,
        todo=todo,
        blocked=blocked,
        highlights=highlights or [],
    )
    return format_daily_digest(data)


# =============================================================================
# Session Summary Report
# =============================================================================


@dataclass
class SessionSummaryData:
    """Data for session summary report."""

    # Session identification
    issue_id: str = ""
    issue_title: str = ""
    session_number: int = 1

    # Timing
    started_at: datetime = field(default_factory=datetime.now)
    ended_at: datetime | None = None
    duration_minutes: int = 0

    # Token usage
    input_tokens: int = 0
    output_tokens: int = 0
    total_tokens: int = 0

    # Cost estimate
    estimated_cost_usd: float = 0.0

    # Git changes
    commits: list[str] = field(default_factory=list)
    files_changed: list[str] = field(default_factory=list)

    # Status
    status: str = "completed"  # completed, error, partial
    error_message: str = ""

    # Next steps
    next_steps: list[str] = field(default_factory=list)


def format_session_summary(data: SessionSummaryData) -> str:
    """
    Format a session summary report.

    Args:
        data: SessionSummaryData with session info

    Returns:
        HTML-formatted Telegram message
    """
    # Status emoji
    status_emoji = {
        "completed": "✅",
        "error": "❌",
        "partial": "⚠️",
    }.get(data.status, "ℹ️")

    lines = [
        f"<b>📋 Session Summary</b>",
        "",
        f"<b>Issue:</b> {data.issue_id}",
        f"<b>Title:</b> {data.issue_title[:50]}{'...' if len(data.issue_title) > 50 else ''}",
        f"<b>Status:</b> {status_emoji} {data.status.title()}",
        "",
    ]

    # Timing
    if data.duration_minutes > 0:
        hours = data.duration_minutes // 60
        minutes = data.duration_minutes % 60
        if hours > 0:
            duration_str = f"{hours}h {minutes}m"
        else:
            duration_str = f"{minutes}m"
        lines.append(f"<b>Duration:</b> ⏱️ {duration_str}")

    # Tokens
    if data.total_tokens > 0:
        lines.append(f"<b>Tokens:</b> 🎫 {data.total_tokens:,}")
        if data.input_tokens > 0 and data.output_tokens > 0:
            lines.append(f"  <code>↓{data.input_tokens:,} ↑{data.output_tokens:,}</code>")

    # Cost
    if data.estimated_cost_usd > 0:
        lines.append(f"<b>Cost:</b> 💵 ${data.estimated_cost_usd:.4f}")

    lines.append("")

    # Git commits
    if data.commits:
        lines.append("<b>Commits:</b>")
        for commit in data.commits[:5]:
            # Truncate long commit messages
            msg = commit[:60] + "..." if len(commit) > 60 else commit
            lines.append(f"  <code>•</code> {msg}")
        if len(data.commits) > 5:
            lines.append(f"  <i>...and {len(data.commits) - 5} more</i>")
        lines.append("")

    # Files changed
    if data.files_changed:
        lines.append(f"<b>Files Changed:</b> {len(data.files_changed)}")
        for file in data.files_changed[:5]:
            lines.append(f"  <code>•</code> {file}")
        if len(data.files_changed) > 5:
            lines.append(f"  <i>...and {len(data.files_changed) - 5} more</i>")
        lines.append("")

    # Error message
    if data.status == "error" and data.error_message:
        lines.append(f"<b>Error:</b>")
        lines.append(f"<code>{data.error_message[:200]}</code>")
        lines.append("")

    # Next steps
    if data.next_steps:
        lines.append("<b>Next Steps:</b>")
        for step in data.next_steps[:3]:
            lines.append(f"  → {step}")
        lines.append("")

    return "\n".join(lines)


def format_session_summary_simple(
    issue_id: str,
    issue_title: str,
    duration_minutes: int,
    tokens_used: int,
    commits: list[str] | None = None,
    files_changed: list[str] | None = None,
    status: str = "completed",
) -> str:
    """
    Simplified session summary formatter.

    Args:
        issue_id: Issue identifier (e.g., "ENG-123")
        issue_title: Issue title
        duration_minutes: Session duration in minutes
        tokens_used: Total tokens used
        commits: List of commit messages
        files_changed: List of changed file paths
        status: completed, error, or partial

    Returns:
        HTML-formatted Telegram message
    """
    data = SessionSummaryData(
        issue_id=issue_id,
        issue_title=issue_title,
        duration_minutes=duration_minutes,
        total_tokens=tokens_used,
        commits=commits or [],
        files_changed=files_changed or [],
        status=status,
    )
    return format_session_summary(data)


# =============================================================================
# Error Alert Report
# =============================================================================


@dataclass
class ErrorAlertData:
    """Data for error alert report."""

    # Error details
    error_type: str = "unknown"  # syntax, runtime, test, mcp, network, git
    error_message: str = ""

    # Location (if available)
    file_path: str = ""
    line_number: int = 0
    function_name: str = ""

    # Context
    issue_id: str = ""
    phase: str = ""  # implement, test, commit, etc.

    # Retry info
    attempt_count: int = 1
    max_attempts: int = 3
    will_retry: bool = True

    # Stack trace (optional, truncated)
    stack_trace: str = ""

    # Timestamp
    timestamp: datetime = field(default_factory=datetime.now)


def format_error_alert(data: ErrorAlertData) -> str:
    """
    Format an error alert report.

    Args:
        data: ErrorAlertData with error info

    Returns:
        HTML-formatted Telegram message
    """
    # Error type emoji
    type_emoji = {
        "syntax": "🔴",
        "runtime": "💥",
        "test": "🧪",
        "mcp": "🔌",
        "network": "🌐",
        "git": "📦",
        "timeout": "⏰",
    }.get(data.error_type, "❌")

    lines = [
        f"<b>{type_emoji} Error Alert</b>",
        "",
        f"<b>Type:</b> {data.error_type.upper()}",
    ]

    # Issue context
    if data.issue_id:
        lines.append(f"<b>Issue:</b> {data.issue_id}")

    if data.phase:
        lines.append(f"<b>Phase:</b> {data.phase}")

    lines.append("")

    # Location
    if data.file_path:
        lines.append("<b>Location:</b>")
        lines.append(f"  📁 <code>{data.file_path}</code>")
        if data.line_number > 0:
            lines.append(f"  📍 Line {data.line_number}")
        if data.function_name:
            lines.append(f"  🔧 <code>{data.function_name}()</code>")
        lines.append("")

    # Error message
    lines.append("<b>Error:</b>")
    # Escape HTML entities in error message
    escaped_msg = (
        data.error_message
        .replace("&", "&amp;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
    )[:300]
    lines.append(f"<code>{escaped_msg}</code>")
    lines.append("")

    # Retry info
    if data.attempt_count > 1 or data.will_retry:
        lines.append("<b>Retry Status:</b>")
        lines.append(f"  🔄 Attempt: {data.attempt_count}/{data.max_attempts}")
        if data.will_retry:
            lines.append(f"  ⏳ Will retry automatically")
        else:
            lines.append(f"  ⛔ Max retries reached")
        lines.append("")

    # Stack trace (truncated)
    if data.stack_trace:
        lines.append("<b>Trace:</b>")
        trace_lines = data.stack_trace.split("\n")[:5]
        for line in trace_lines:
            escaped = line.replace("<", "&lt;").replace(">", "&gt;")[:80]
            lines.append(f"<code>{escaped}</code>")
        if len(data.stack_trace.split("\n")) > 5:
            lines.append("<i>...truncated</i>")
        lines.append("")

    # Timestamp
    time_str = data.timestamp.strftime("%H:%M:%S")
    lines.append(f"<i>🕐 {time_str}</i>")

    return "\n".join(lines)


def format_error_alert_simple(
    error_type: str,
    error_message: str,
    file_path: str = "",
    line_number: int = 0,
    attempt_count: int = 1,
    issue_id: str = "",
    phase: str = "",
) -> str:
    """
    Simplified error alert formatter.

    Args:
        error_type: Type of error (syntax, runtime, test, mcp, etc.)
        error_message: Error message
        file_path: Path to file with error (optional)
        line_number: Line number of error (optional)
        attempt_count: Current retry attempt
        issue_id: Related issue ID (optional)
        phase: Current phase (optional)

    Returns:
        HTML-formatted Telegram message
    """
    data = ErrorAlertData(
        error_type=error_type,
        error_message=error_message,
        file_path=file_path,
        line_number=line_number,
        attempt_count=attempt_count,
        issue_id=issue_id,
        phase=phase,
    )
    return format_error_alert(data)


# =============================================================================
# Weekly Summary Report
# =============================================================================


@dataclass
class WeeklySummaryData:
    """Data for weekly summary report."""

    # Week identification
    week_start: datetime = field(default_factory=lambda: datetime.now() - timedelta(days=7))
    week_end: datetime = field(default_factory=datetime.now)

    # Task metrics
    tasks_completed: int = 0
    tasks_created: int = 0
    average_completion_hours: float = 0.0

    # Velocity (tasks per day)
    velocity_current_week: float = 0.0
    velocity_previous_week: float = 0.0
    velocity_change_percent: float = 0.0

    # Cost metrics
    total_tokens: int = 0
    total_cost_usd: float = 0.0
    cost_previous_week: float = 0.0
    cost_change_percent: float = 0.0

    # Session metrics
    total_sessions: int = 0
    total_duration_hours: float = 0.0
    average_session_minutes: float = 0.0

    # Git metrics
    total_commits: int = 0
    total_files_changed: int = 0
    total_lines_added: int = 0
    total_lines_removed: int = 0

    # Daily breakdown
    daily_completions: list[int] = field(default_factory=lambda: [0] * 7)

    # Top contributors (issues)
    top_issues: list[tuple[str, str]] = field(default_factory=list)  # (id, title)


def format_weekly_summary(data: WeeklySummaryData) -> str:
    """
    Format a weekly summary report.

    Args:
        data: WeeklySummaryData with weekly stats

    Returns:
        HTML-formatted Telegram message
    """
    week_str = f"{data.week_start.strftime('%b %d')} - {data.week_end.strftime('%b %d, %Y')}"

    lines = [
        f"<b>📅 Weekly Summary</b>",
        f"<i>{week_str}</i>",
        "",
    ]

    # Task metrics
    lines.append("<b>📊 Tasks:</b>")
    lines.append(f"  ✅ Completed: {data.tasks_completed}")
    lines.append(f"  ➕ Created: {data.tasks_created}")
    if data.average_completion_hours > 0:
        lines.append(f"  ⏱️ Avg Time: {data.average_completion_hours:.1f}h")
    lines.append("")

    # Velocity trend
    if data.velocity_current_week > 0:
        lines.append("<b>📈 Velocity:</b>")
        lines.append(f"  Current: {data.velocity_current_week:.1f} tasks/day")
        if data.velocity_previous_week > 0:
            trend_emoji = "📈" if data.velocity_change_percent >= 0 else "📉"
            sign = "+" if data.velocity_change_percent >= 0 else ""
            lines.append(f"  {trend_emoji} {sign}{data.velocity_change_percent:.0f}% vs last week")
        lines.append("")

    # Daily sparkline
    if any(d > 0 for d in data.daily_completions):
        max_val = max(data.daily_completions) or 1
        sparkline = ""
        for val in data.daily_completions:
            # Use block characters for sparkline
            level = int((val / max_val) * 8) if max_val > 0 else 0
            blocks = "▁▂▃▄▅▆▇█"
            sparkline += blocks[min(level, 7)]
        lines.append(f"<b>Daily:</b> <code>{sparkline}</code>")
        lines.append(f"<i>       Mon→Sun</i>")
        lines.append("")

    # Cost metrics
    if data.total_cost_usd > 0:
        lines.append("<b>💰 Cost:</b>")
        lines.append(f"  This week: ${data.total_cost_usd:.2f}")
        lines.append(f"  Tokens: {data.total_tokens:,}")
        if data.cost_previous_week > 0:
            trend_emoji = "📈" if data.cost_change_percent > 0 else "📉"
            sign = "+" if data.cost_change_percent >= 0 else ""
            lines.append(f"  {trend_emoji} {sign}{data.cost_change_percent:.0f}% vs last week")
        lines.append("")

    # Session metrics
    if data.total_sessions > 0:
        lines.append("<b>🔄 Sessions:</b>")
        lines.append(f"  Count: {data.total_sessions}")
        lines.append(f"  Total Time: {data.total_duration_hours:.1f}h")
        lines.append(f"  Avg Session: {data.average_session_minutes:.0f}m")
        lines.append("")

    # Git metrics
    if data.total_commits > 0:
        lines.append("<b>📝 Git:</b>")
        lines.append(f"  Commits: {data.total_commits}")
        lines.append(f"  Files: {data.total_files_changed}")
        lines.append(f"  <code>+{data.total_lines_added:,} / -{data.total_lines_removed:,}</code>")
        lines.append("")

    # Top issues
    if data.top_issues:
        lines.append("<b>🏆 Top Issues:</b>")
        for issue_id, title in data.top_issues[:3]:
            title_short = title[:40] + "..." if len(title) > 40 else title
            lines.append(f"  • <b>{issue_id}</b>: {title_short}")
        lines.append("")

    return "\n".join(lines)


def format_weekly_summary_simple(
    tasks_completed: int,
    tasks_created: int,
    total_cost_usd: float,
    total_sessions: int,
    total_commits: int,
    velocity_current: float = 0.0,
    velocity_previous: float = 0.0,
) -> str:
    """
    Simplified weekly summary formatter.

    Args:
        tasks_completed: Tasks completed this week
        tasks_created: Tasks created this week
        total_cost_usd: Total cost in USD
        total_sessions: Number of sessions
        total_commits: Number of commits
        velocity_current: Current week tasks/day
        velocity_previous: Previous week tasks/day

    Returns:
        HTML-formatted Telegram message
    """
    velocity_change = 0.0
    if velocity_previous > 0:
        velocity_change = ((velocity_current - velocity_previous) / velocity_previous) * 100

    data = WeeklySummaryData(
        tasks_completed=tasks_completed,
        tasks_created=tasks_created,
        total_cost_usd=total_cost_usd,
        total_sessions=total_sessions,
        total_commits=total_commits,
        velocity_current_week=velocity_current,
        velocity_previous_week=velocity_previous,
        velocity_change_percent=velocity_change,
    )
    return format_weekly_summary(data)


# =============================================================================
# Quick Status Reports
# =============================================================================


def format_task_started(issue_id: str, title: str) -> str:
    """Format task started notification."""
    return (
        f"🔨 <b>Starting:</b> {title}\n"
        f"<code>{issue_id}</code>"
    )


def format_task_completed(issue_id: str, title: str, duration_minutes: int = 0) -> str:
    """Format task completed notification."""
    lines = [
        f"✅ <b>Completed:</b> {title}",
        f"<code>{issue_id}</code>",
    ]
    if duration_minutes > 0:
        hours = duration_minutes // 60
        mins = duration_minutes % 60
        if hours > 0:
            lines.append(f"⏱️ {hours}h {mins}m")
        else:
            lines.append(f"⏱️ {mins}m")
    return "\n".join(lines)


def format_task_blocked(issue_id: str, title: str, reason: str) -> str:
    """Format task blocked notification."""
    return (
        f"⚠️ <b>Blocked:</b> {title}\n"
        f"<code>{issue_id}</code>\n\n"
        f"<b>Reason:</b> {reason}"
    )


def format_all_tasks_complete() -> str:
    """Format all tasks complete notification."""
    return (
        "🎉 <b>All Tasks Complete!</b>\n\n"
        "No remaining tasks in Todo.\n"
        "Great work! 🚀"
    )


# =============================================================================
# Utility Functions
# =============================================================================


def escape_html(text: str) -> str:
    """Escape HTML entities for Telegram."""
    return (
        text
        .replace("&", "&amp;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
    )


def truncate_message(message: str, max_length: int = 4096) -> str:
    """
    Truncate message to fit Telegram's max length.

    Args:
        message: Message to truncate
        max_length: Maximum length (Telegram limit is 4096)

    Returns:
        Truncated message with ellipsis if needed
    """
    if len(message) <= max_length:
        return message

    # Find last complete line before limit
    truncated = message[:max_length - 50]  # Leave room for truncation notice
    last_newline = truncated.rfind("\n")
    if last_newline > max_length // 2:
        truncated = truncated[:last_newline]

    return truncated + "\n\n<i>...message truncated</i>"


# =============================================================================
# Status Command Report (ENG-51)
# =============================================================================


@dataclass
class StatusData:
    """Data for /status command response."""

    # Task counts by state
    todo_count: int = 0
    in_progress_count: int = 0
    done_count: int = 0

    # Current in-progress task
    current_task_id: str = ""
    current_task_title: str = ""

    # Session info
    session_number: int = 0
    session_status: str = "idle"  # idle, active, paused
    session_start_time: str = ""
    elapsed_minutes: int = 0

    # Additional info
    total_tasks: int = 0
    stale_count: int = 0


def format_status(data: StatusData) -> str:
    """
    Format a status report for the /status command.

    Args:
        data: StatusData with current status

    Returns:
        HTML-formatted Telegram message

    Example output:
        <b>Status</b>

        <b>Tasks:</b>
          Todo: 5
          In Progress: 2
          Done: 12

        <b>Current:</b>
        <code>ENG-42</code> Add user authentication

        <b>Session:</b>
          #8  Active
          Duration: 45m
    """
    lines = [
        "<b>Status</b>",
        "",
    ]

    # Task counts
    lines.append("<b>Tasks:</b>")
    lines.append(f"  Todo: {data.todo_count}")
    lines.append(f"  In Progress: {data.in_progress_count}")
    lines.append(f"  Done: {data.done_count}")
    lines.append("")

    # Progress bar
    if data.total_tasks > 0:
        bar = format_progress_bar(data.done_count, data.total_tasks, width=10)
        lines.append(f"<b>Progress:</b> {bar}")
        lines.append("")

    # Current task
    if data.current_task_id:
        lines.append("<b>Current:</b>")
        title_display = data.current_task_title[:40]
        if len(data.current_task_title) > 40:
            title_display += "..."
        lines.append(f"  <code>{data.current_task_id}</code> {title_display}")
        lines.append("")
    elif data.in_progress_count > 0:
        lines.append("<b>Current:</b>")
        lines.append(f"  {data.in_progress_count} task(s) in progress")
        lines.append("")

    # Session info
    if data.session_number > 0 or data.session_status != "idle":
        lines.append("<b>Session:</b>")

        status_emoji = {
            "idle": "",
            "active": "",
            "paused": "",
        }.get(data.session_status, "")

        lines.append(f"  #{data.session_number} {status_emoji} {data.session_status.title()}")

        if data.elapsed_minutes > 0:
            hours = data.elapsed_minutes // 60
            mins = data.elapsed_minutes % 60
            if hours > 0:
                lines.append(f"  Duration: {hours}h {mins}m")
            else:
                lines.append(f"  Duration: {mins}m")
        lines.append("")

    # Stale tasks warning
    if data.stale_count > 0:
        lines.append(f"<b>Warning:</b> {data.stale_count} stale task(s)")
        lines.append("")

    # All tasks done celebration
    if data.todo_count == 0 and data.in_progress_count == 0 and data.done_count > 0:
        lines.append("All tasks complete!")

    return "\n".join(lines)


def format_status_simple(
    todo: int,
    in_progress: int,
    done: int,
    current_task_id: str = "",
    current_task_title: str = "",
    session_number: int = 0,
    session_status: str = "idle",
    elapsed_minutes: int = 0,
    stale_count: int = 0,
) -> str:
    """
    Simplified status formatter for the /status command.

    Args:
        todo: Number of todo tasks
        in_progress: Number of in-progress tasks
        done: Number of done tasks
        current_task_id: ID of current task (e.g., "ENG-42")
        current_task_title: Title of current task
        session_number: Current session number
        session_status: Session status (idle, active, paused)
        elapsed_minutes: Session elapsed time in minutes
        stale_count: Number of stale tasks

    Returns:
        HTML-formatted Telegram message
    """
    data = StatusData(
        todo_count=todo,
        in_progress_count=in_progress,
        done_count=done,
        current_task_id=current_task_id,
        current_task_title=current_task_title,
        session_number=session_number,
        session_status=session_status,
        elapsed_minutes=elapsed_minutes,
        total_tasks=todo + in_progress + done,
        stale_count=stale_count,
    )
    return format_status(data)


# =============================================================================
# Info Commands (ENG-56): /next, /log, /budget
# =============================================================================


def format_next_task(
    task_id: str,
    title: str,
    priority: str,
    description: str = "",
    total_todo: int = 0,
) -> str:
    """
    Format the next task message for /next command (ENG-56).

    Args:
        task_id: Task identifier (e.g., "ENG-42")
        title: Task title
        priority: Priority level (urgent, high, medium, low, none)
        description: Task description (will be truncated)
        total_todo: Total number of tasks in Todo queue

    Returns:
        HTML-formatted Telegram message

    Example output:
        <b>Next Task</b>

        <code>ENG-42</code> Add user authentication
        <b>Priority:</b> high

        <i>Description:</i>
        Implement OAuth2 login flow with...

        5 tasks remaining in queue
    """
    # Priority emoji
    priority_emoji = {
        "urgent": "!!!",
        "high": "!",
        "medium": "",
        "low": "",
        "none": "",
    }.get(priority.lower(), "")

    lines = [
        "<b>Next Task</b>",
        "",
        f"<code>{task_id}</code> {priority_emoji}{title}",
        f"<b>Priority:</b> {priority}",
    ]

    # Add truncated description if available
    if description:
        desc_truncated = description[:150]
        if len(description) > 150:
            desc_truncated += "..."
        lines.append("")
        lines.append(f"<i>{desc_truncated}</i>")

    # Add queue count
    lines.append("")
    if total_todo > 1:
        lines.append(f"{total_todo} tasks remaining in queue")
    else:
        lines.append("This is the last task in queue")

    return "\n".join(lines)


def format_action_log(actions: list[dict]) -> str:
    """
    Format agent action log for /log command (ENG-56).

    Args:
        actions: List of action dictionaries with keys:
            - type: Action type (tool_call, file_change, test_result, etc.)
            - title: Action title/description
            - description: Additional details (optional)
            - timestamp: When action occurred (optional)
            - task_id: Related task ID (optional)

    Returns:
        HTML-formatted Telegram message

    Example output:
        <b>Recent Actions</b>

          file_change: Modified agent.py
          test_result: All tests passed
          tool_call: Read config file
          commit: feat: Add new feature
          tool_call: Updated task status
    """
    if not actions:
        return "<b>Recent Actions</b>\n\nNo recent actions logged."

    lines = [
        "<b>Recent Actions</b>",
        "",
    ]

    # Type emoji mapping
    type_emoji = {
        "tool_call": "",
        "file_change": "",
        "test_result": "",
        "commit": "",
        "error": "",
        "session": "",
        "action": "",
        "default": "",
    }

    for action in actions:
        action_type = action.get("type", "action")
        title = action.get("title", "Unknown action")[:60]
        emoji = type_emoji.get(action_type, type_emoji["default"])

        # Add task reference if available
        task_ref = ""
        if action.get("task_id"):
            task_ref = f" [{action['task_id']}]"

        lines.append(f"  {emoji} {title}{task_ref}")

    return "\n".join(lines)


def format_budget_status(
    context_stats: dict | None = None,
    cost_stats: dict | None = None,
) -> str:
    """
    Format budget status for /budget command (ENG-56).

    Args:
        context_stats: Context token usage stats with keys:
            - total_used: Tokens used
            - max_tokens: Token limit
            - usage_percent: Usage percentage
            - mode: Current mode (normal, compact, critical)
        cost_stats: Cost tracking stats with keys:
            - limit_usd: Budget limit in USD (optional)
            - spent_usd: Amount spent in USD
            - remaining_usd: Remaining budget (optional)
            - cost_usd: Session/weekly cost (alternative)

    Returns:
        HTML-formatted Telegram message

    Example output:
        <b>Budget Status</b>

        <b>Context:</b>
        <code>|||||     </code> 47%
        84,600 / 180,000 tokens
        Mode: normal

        <b>Cost:</b>
        $12.45 spent
        $87.55 remaining (of $100 limit)
    """
    lines = [
        "<b>Budget Status</b>",
        "",
    ]

    # Context usage section
    if context_stats:
        usage_pct = context_stats.get("usage_percent", 0)
        total_used = context_stats.get("total_used", 0)
        max_tokens = context_stats.get("max_tokens", 180000)
        mode = context_stats.get("mode", "normal")

        # Create visual progress bar
        bar_width = 10
        filled = int((usage_pct / 100) * bar_width)
        bar = "|" * filled + " " * (bar_width - filled)

        lines.append("<b>Context:</b>")
        lines.append(f"<code>[{bar}]</code> {usage_pct:.0f}%")
        lines.append(f"  {total_used:,} / {max_tokens:,} tokens")

        # Mode indicator
        if mode == "critical":
            lines.append("  Mode: CRITICAL")
        elif mode == "compact":
            lines.append("  Mode: COMPACT")
        else:
            lines.append(f"  Mode: {mode}")

        lines.append("")

    # Cost section
    if cost_stats:
        lines.append("<b>Cost:</b>")

        if "limit_usd" in cost_stats:
            # Budget with limit
            spent = cost_stats.get("spent_usd", 0)
            limit = cost_stats.get("limit_usd", 0)
            remaining = cost_stats.get("remaining_usd", limit - spent)

            lines.append(f"  ${spent:.2f} spent")
            if limit > 0:
                lines.append(f"  ${remaining:.2f} remaining (of ${limit:.2f} limit)")

                # Add warning if over 80%
                if spent / limit > 0.8:
                    lines.append("  Over 80% of budget used")
        else:
            # Just cost tracking without limit
            cost = cost_stats.get("cost_usd", 0)
            sessions = cost_stats.get("sessions", 0)
            tasks = cost_stats.get("tasks_completed", 0)

            lines.append(f"  ${cost:.2f} this week")
            if sessions > 0:
                lines.append(f"  {sessions} sessions, {tasks} tasks completed")
    else:
        lines.append("<i>Cost tracking not configured</i>")
        lines.append("")
        lines.append("To enable, create <code>.agent/budget.json</code>:")
        lines.append('<code>{"limit_usd": 100}</code>')

    return "\n".join(lines)


# =============================================================================
# TelegramReports Class (ENG-85): Class-based API for report generation
# =============================================================================


class TelegramReports:
    """Class-based API for generating Telegram reports.

    Provides methods for generating structured HTML reports compatible
    with Telegram's parse_mode="HTML".

    Supported HTML tags: <b>, <i>, <code>, <pre>, <a>

    Usage:
        reports = TelegramReports()
        digest = reports.generate_daily_digest({
            "done": 5,
            "in_progress": 2,
            "todo": 10,
            "completed_today": [
                {"id": "ENG-1", "title": "Add auth"},
                {"id": "ENG-2", "title": "Fix login"},
            ],
        })
    """

    PROGRESS_BAR_WIDTH: int = 10
    FILL_CHAR: str = "\u2588"      # Full block
    EMPTY_CHAR: str = "\u2591"     # Light shade

    def format_progress_bar(self, done: int, total: int) -> str:
        """Create a textual progress bar showing completion percentage.

        Args:
            done: Number of completed items.
            total: Total number of items.

        Returns:
            Progress bar string like ``[█████░░░░░] 50%``.
            Returns ``[░░░░░░░░░░] 0%`` when *total* is zero or negative.

        Examples:
            >>> TelegramReports().format_progress_bar(5, 10)
            '[█████░░░░░] 50%'
            >>> TelegramReports().format_progress_bar(0, 10)
            '[░░░░░░░░░░] 0%'
        """
        if total <= 0:
            bar = self.EMPTY_CHAR * self.PROGRESS_BAR_WIDTH
            return f"[{bar}] 0%"

        percentage = min(100, max(0, (done / total) * 100))
        filled = int((percentage / 100) * self.PROGRESS_BAR_WIDTH)
        empty = self.PROGRESS_BAR_WIDTH - filled

        bar = self.FILL_CHAR * filled + self.EMPTY_CHAR * empty
        return f"[{bar}] {percentage:.0f}%"

    def generate_daily_digest(self, tasks_stats: dict[str, object]) -> str:
        """Generate a daily digest report in Telegram-compatible HTML.

        Args:
            tasks_stats: Dictionary with task statistics containing:
                - ``done`` (int): Number of completed tasks.
                - ``in_progress`` (int): Number of tasks in progress.
                - ``todo`` (int): Number of tasks still to do.
                - ``completed_today`` (list): Tasks finished today.
                  Each element can be either a plain string (task ID) or a
                  dict with ``id`` and ``title`` keys.

        Returns:
            HTML-formatted string ready for ``parse_mode="HTML"`` in Telegram.

        Example output::

            <b>Ежедневный дайджест</b>

            <b>Прогресс:</b> [██████░░░░] 60%

            <b>Статистика:</b>
            Завершено: 12
            В работе: 3
            К выполнению: 5

            <b>Завершено сегодня:</b>
            - ENG-79: Перевод промптов
            - ENG-80: Русификация Telegram
        """
        done = int(tasks_stats.get("done", 0) or 0)
        in_progress = int(tasks_stats.get("in_progress", 0) or 0)
        todo = int(tasks_stats.get("todo", 0) or 0)
        completed_today: list[object] = list(
            tasks_stats.get("completed_today", []) or []  # type: ignore[arg-type]
        )

        total = done + in_progress + todo
        progress_bar = self.format_progress_bar(done, total)

        lines: list[str] = [
            "<b>Ежедневный дайджест</b>",
            "",
            f"<b>Прогресс:</b> {progress_bar}",
            "",
            "<b>Статистика:</b>",
            f"Завершено: {done}",
            f"В работе: {in_progress}",
            f"К выполнению: {todo}",
        ]

        if completed_today:
            lines.append("")
            lines.append("<b>Завершено сегодня:</b>")
            for item in completed_today:
                if isinstance(item, dict):
                    task_id = item.get("id", "")
                    title = item.get("title", "")
                    lines.append(f"- {task_id}: {title}")
                else:
                    lines.append(f"- {item}")

        return "\n".join(lines)
