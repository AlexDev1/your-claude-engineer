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
    fill_char: str = "\u2588",
    empty_char: str = "\u2591",
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
        f"<b>\U0001f4ca \u0414\u0430\u0439\u0434\u0436\u0435\u0441\u0442 \u0437\u0430 \u0434\u0435\u043d\u044c \u2014 {date_str}</b>",
        "",
    ]

    # Progress bar for completed vs total
    if total_tasks > 0:
        bar = format_progress_bar(data.completed_today, total_tasks, width=12)
        lines.append(f"<b>\u041f\u0440\u043e\u0433\u0440\u0435\u0441\u0441:</b> {bar}")
        lines.append("")

    # Task breakdown
    lines.append("<b>\u0417\u0430\u0434\u0430\u0447\u0438:</b>")
    lines.append(f"  \u2705 \u0417\u0430\u0432\u0435\u0440\u0448\u0435\u043d\u043e: {data.completed_today}")
    lines.append(f"  \U0001f504 \u0412 \u0440\u0430\u0431\u043e\u0442\u0435: {data.in_progress}")
    lines.append(f"  \U0001f4cb \u041a \u0432\u044b\u043f\u043e\u043b\u043d\u0435\u043d\u0438\u044e: {data.todo}")
    if data.blocked > 0:
        lines.append(f"  \u26a0\ufe0f \u0417\u0430\u0431\u043b\u043e\u043a\u0438\u0440\u043e\u0432\u0430\u043d\u043e: {data.blocked}")
    lines.append("")

    # Session stats
    if data.sessions_count > 0:
        hours = data.total_duration_minutes // 60
        minutes = data.total_duration_minutes % 60
        duration_str = f"{hours}\u0447 {minutes}\u043c" if hours > 0 else f"{minutes}\u043c"

        lines.append("<b>\u0421\u0435\u0441\u0441\u0438\u0438:</b>")
        lines.append(f"  \u23f1\ufe0f \u041a\u043e\u043b\u0438\u0447\u0435\u0441\u0442\u0432\u043e: {data.sessions_count}")
        lines.append(f"  \u23f0 \u0414\u043b\u0438\u0442\u0435\u043b\u044c\u043d\u043e\u0441\u0442\u044c: {duration_str}")
        lines.append("")

    # Git stats
    if data.commits_today > 0:
        lines.append("<b>Git:</b>")
        lines.append(f"  \U0001f4dd \u041a\u043e\u043c\u043c\u0438\u0442\u043e\u0432: {data.commits_today}")
        lines.append(f"  \U0001f4c1 \u0424\u0430\u0439\u043b\u043e\u0432: {data.files_changed}")
        lines.append(f"  <code>+{data.lines_added} / -{data.lines_removed}</code>")
        lines.append("")

    # Cost stats (if available)
    if data.tokens_used > 0:
        lines.append("<b>\u0418\u0441\u043f\u043e\u043b\u044c\u0437\u043e\u0432\u0430\u043d\u0438\u0435:</b>")
        lines.append(f"  \U0001f3ab \u0422\u043e\u043a\u0435\u043d\u043e\u0432: {data.tokens_used:,}")
        if data.estimated_cost_usd > 0:
            lines.append(f"  \U0001f4b5 \u0421\u0442\u043e\u0438\u043c\u043e\u0441\u0442\u044c: ${data.estimated_cost_usd:.2f}")
        lines.append("")

    # Highlights
    if data.highlights:
        lines.append("<b>\u0418\u0442\u043e\u0433\u0438:</b>")
        for highlight in data.highlights[:5]:  # Limit to 5
            lines.append(f"  \u2022 {highlight}")
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
        "completed": "\u2705",
        "error": "\u274c",
        "partial": "\u26a0\ufe0f",
    }.get(data.status, "\u2139\ufe0f")

    lines = [
        f"<b>\U0001f4cb \u0418\u0442\u043e\u0433\u0438 \u0441\u0435\u0441\u0441\u0438\u0438</b>",
        "",
        f"<b>\u0417\u0430\u0434\u0430\u0447\u0430:</b> {data.issue_id}",
        f"<b>\u0417\u0430\u0433\u043e\u043b\u043e\u0432\u043e\u043a:</b> {data.issue_title[:50]}{'...' if len(data.issue_title) > 50 else ''}",
        f"<b>\u0421\u0442\u0430\u0442\u0443\u0441:</b> {status_emoji} {data.status.title()}",
        "",
    ]

    # Timing
    if data.duration_minutes > 0:
        hours = data.duration_minutes // 60
        minutes = data.duration_minutes % 60
        if hours > 0:
            duration_str = f"{hours}\u0447 {minutes}\u043c"
        else:
            duration_str = f"{minutes}\u043c"
        lines.append(f"<b>\u0414\u043b\u0438\u0442\u0435\u043b\u044c\u043d\u043e\u0441\u0442\u044c:</b> \u23f1\ufe0f {duration_str}")

    # Tokens
    if data.total_tokens > 0:
        lines.append(f"<b>\u0422\u043e\u043a\u0435\u043d\u043e\u0432:</b> \U0001f3ab {data.total_tokens:,}")
        if data.input_tokens > 0 and data.output_tokens > 0:
            lines.append(f"  <code>\u2193{data.input_tokens:,} \u2191{data.output_tokens:,}</code>")

    # Cost
    if data.estimated_cost_usd > 0:
        lines.append(f"<b>\u0421\u0442\u043e\u0438\u043c\u043e\u0441\u0442\u044c:</b> \U0001f4b5 ${data.estimated_cost_usd:.4f}")

    lines.append("")

    # Git commits
    if data.commits:
        lines.append("<b>\u041a\u043e\u043c\u043c\u0438\u0442\u044b:</b>")
        for commit in data.commits[:5]:
            # Truncate long commit messages
            msg = commit[:60] + "..." if len(commit) > 60 else commit
            lines.append(f"  <code>\u2022</code> {msg}")
        if len(data.commits) > 5:
            lines.append(f"  <i>...\u0438 \u0435\u0449\u0451 {len(data.commits) - 5}</i>")
        lines.append("")

    # Files changed
    if data.files_changed:
        lines.append(f"<b>\u0418\u0437\u043c\u0435\u043d\u0435\u043d\u043e \u0444\u0430\u0439\u043b\u043e\u0432:</b> {len(data.files_changed)}")
        for file in data.files_changed[:5]:
            lines.append(f"  <code>\u2022</code> {file}")
        if len(data.files_changed) > 5:
            lines.append(f"  <i>...\u0438 \u0435\u0449\u0451 {len(data.files_changed) - 5}</i>")
        lines.append("")

    # Error message
    if data.status == "error" and data.error_message:
        lines.append(f"<b>\u041e\u0448\u0438\u0431\u043a\u0430:</b>")
        lines.append(f"<code>{data.error_message[:200]}</code>")
        lines.append("")

    # Next steps
    if data.next_steps:
        lines.append("<b>\u0421\u043b\u0435\u0434\u0443\u044e\u0449\u0438\u0435 \u0448\u0430\u0433\u0438:</b>")
        for step in data.next_steps[:3]:
            lines.append(f"  \u2192 {step}")
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
        "syntax": "\U0001f534",
        "runtime": "\U0001f4a5",
        "test": "\U0001f9ea",
        "mcp": "\U0001f50c",
        "network": "\U0001f310",
        "git": "\U0001f4e6",
        "timeout": "\u23f0",
    }.get(data.error_type, "\u274c")

    lines = [
        f"<b>{type_emoji} \u041e\u043f\u043e\u0432\u0435\u0449\u0435\u043d\u0438\u0435 \u043e\u0431 \u043e\u0448\u0438\u0431\u043a\u0435</b>",
        "",
        f"<b>\u0422\u0438\u043f:</b> {data.error_type.upper()}",
    ]

    # Issue context
    if data.issue_id:
        lines.append(f"<b>\u0417\u0430\u0434\u0430\u0447\u0430:</b> {data.issue_id}")

    if data.phase:
        lines.append(f"<b>\u0424\u0430\u0437\u0430:</b> {data.phase}")

    lines.append("")

    # Location
    if data.file_path:
        lines.append("<b>\u0420\u0430\u0441\u043f\u043e\u043b\u043e\u0436\u0435\u043d\u0438\u0435:</b>")
        lines.append(f"  \U0001f4c1 <code>{data.file_path}</code>")
        if data.line_number > 0:
            lines.append(f"  \U0001f4cd \u0421\u0442\u0440\u043e\u043a\u0430 {data.line_number}")
        if data.function_name:
            lines.append(f"  \U0001f527 <code>{data.function_name}()</code>")
        lines.append("")

    # Error message
    lines.append("<b>\u041e\u0448\u0438\u0431\u043a\u0430:</b>")
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
        lines.append("<b>\u0421\u0442\u0430\u0442\u0443\u0441 \u043f\u043e\u0432\u0442\u043e\u0440\u0430:</b>")
        lines.append(f"  \U0001f504 \u041f\u043e\u043f\u044b\u0442\u043a\u0430: {data.attempt_count}/{data.max_attempts}")
        if data.will_retry:
            lines.append(f"  \u23f3 \u0411\u0443\u0434\u0435\u0442 \u043f\u043e\u0432\u0442\u043e\u0440 \u0430\u0432\u0442\u043e\u043c\u0430\u0442\u0438\u0447\u0435\u0441\u043a\u0438")
        else:
            lines.append(f"  \u26d4 \u0414\u043e\u0441\u0442\u0438\u0433\u043d\u0443\u0442 \u043b\u0438\u043c\u0438\u0442 \u043f\u043e\u043f\u044b\u0442\u043e\u043a")
        lines.append("")

    # Stack trace (truncated)
    if data.stack_trace:
        lines.append("<b>\u0422\u0440\u0430\u0441\u0441\u0438\u0440\u043e\u0432\u043a\u0430:</b>")
        trace_lines = data.stack_trace.split("\n")[:5]
        for line in trace_lines:
            escaped = line.replace("<", "&lt;").replace(">", "&gt;")[:80]
            lines.append(f"<code>{escaped}</code>")
        if len(data.stack_trace.split("\n")) > 5:
            lines.append("<i>...\u043e\u0431\u0440\u0435\u0437\u0430\u043d\u043e</i>")
        lines.append("")

    # Timestamp
    time_str = data.timestamp.strftime("%H:%M:%S")
    lines.append(f"<i>\U0001f550 {time_str}</i>")

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
        f"<b>\U0001f4c5 \u041d\u0435\u0434\u0435\u043b\u044c\u043d\u044b\u0439 \u043e\u0442\u0447\u0451\u0442</b>",
        f"<i>{week_str}</i>",
        "",
    ]

    # Task metrics
    lines.append("<b>\U0001f4ca \u0417\u0430\u0434\u0430\u0447\u0438:</b>")
    lines.append(f"  \u2705 \u0417\u0430\u0432\u0435\u0440\u0448\u0435\u043d\u043e: {data.tasks_completed}")
    lines.append(f"  \u2795 \u0421\u043e\u0437\u0434\u0430\u043d\u043e: {data.tasks_created}")
    if data.average_completion_hours > 0:
        lines.append(f"  \u23f1\ufe0f \u0421\u0440\u0435\u0434\u043d\u0435\u0435 \u0432\u0440\u0435\u043c\u044f: {data.average_completion_hours:.1f}\u0447")
    lines.append("")

    # Velocity trend
    if data.velocity_current_week > 0:
        lines.append("<b>\U0001f4c8 \u0421\u043a\u043e\u0440\u043e\u0441\u0442\u044c:</b>")
        lines.append(f"  \u0422\u0435\u043a\u0443\u0449\u0430\u044f: {data.velocity_current_week:.1f} \u0437\u0430\u0434\u0430\u0447/\u0434\u0435\u043d\u044c")
        if data.velocity_previous_week > 0:
            trend_emoji = "\U0001f4c8" if data.velocity_change_percent >= 0 else "\U0001f4c9"
            sign = "+" if data.velocity_change_percent >= 0 else ""
            lines.append(f"  {trend_emoji} {sign}{data.velocity_change_percent:.0f}% \u043a \u043f\u0440\u043e\u0448\u043b\u043e\u0439 \u043d\u0435\u0434\u0435\u043b\u0435")
        lines.append("")

    # Daily sparkline
    if any(d > 0 for d in data.daily_completions):
        max_val = max(data.daily_completions) or 1
        sparkline = ""
        for val in data.daily_completions:
            # Use block characters for sparkline
            level = int((val / max_val) * 8) if max_val > 0 else 0
            blocks = "\u2581\u2582\u2583\u2584\u2585\u2586\u2587\u2588"
            sparkline += blocks[min(level, 7)]
        lines.append(f"<b>\u041f\u043e \u0434\u043d\u044f\u043c:</b> <code>{sparkline}</code>")
        lines.append(f"<i>       \u041f\u043d\u2192\u0412\u0441</i>")
        lines.append("")

    # Cost metrics
    if data.total_cost_usd > 0:
        lines.append("<b>\U0001f4b0 \u0421\u0442\u043e\u0438\u043c\u043e\u0441\u0442\u044c:</b>")
        lines.append(f"  \u042d\u0442\u0430 \u043d\u0435\u0434\u0435\u043b\u044f: ${data.total_cost_usd:.2f}")
        lines.append(f"  \u0422\u043e\u043a\u0435\u043d\u043e\u0432: {data.total_tokens:,}")
        if data.cost_previous_week > 0:
            trend_emoji = "\U0001f4c8" if data.cost_change_percent > 0 else "\U0001f4c9"
            sign = "+" if data.cost_change_percent >= 0 else ""
            lines.append(f"  {trend_emoji} {sign}{data.cost_change_percent:.0f}% \u043a \u043f\u0440\u043e\u0448\u043b\u043e\u0439 \u043d\u0435\u0434\u0435\u043b\u0435")
        lines.append("")

    # Session metrics
    if data.total_sessions > 0:
        lines.append("<b>\U0001f504 \u0421\u0435\u0441\u0441\u0438\u0438:</b>")
        lines.append(f"  \u041a\u043e\u043b\u0438\u0447\u0435\u0441\u0442\u0432\u043e: {data.total_sessions}")
        lines.append(f"  \u041e\u0431\u0449\u0435\u0435 \u0432\u0440\u0435\u043c\u044f: {data.total_duration_hours:.1f}\u0447")
        lines.append(f"  \u0421\u0440\u0435\u0434\u043d\u044f\u044f \u0441\u0435\u0441\u0441\u0438\u044f: {data.average_session_minutes:.0f}\u043c")
        lines.append("")

    # Git metrics
    if data.total_commits > 0:
        lines.append("<b>\U0001f4dd Git:</b>")
        lines.append(f"  \u041a\u043e\u043c\u043c\u0438\u0442\u043e\u0432: {data.total_commits}")
        lines.append(f"  \u0424\u0430\u0439\u043b\u043e\u0432: {data.total_files_changed}")
        lines.append(f"  <code>+{data.total_lines_added:,} / -{data.total_lines_removed:,}</code>")
        lines.append("")

    # Top issues
    if data.top_issues:
        lines.append("<b>\U0001f3c6 \u0422\u043e\u043f \u0437\u0430\u0434\u0430\u0447:</b>")
        for issue_id, title in data.top_issues[:3]:
            title_short = title[:40] + "..." if len(title) > 40 else title
            lines.append(f"  \u2022 <b>{issue_id}</b>: {title_short}")
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
        f"\U0001f528 <b>\u041d\u0430\u0447\u0438\u043d\u0430\u044e:</b> {title}\n"
        f"<code>{issue_id}</code>"
    )


def format_task_completed(issue_id: str, title: str, duration_minutes: int = 0) -> str:
    """Format task completed notification."""
    lines = [
        f"\u2705 <b>\u0417\u0430\u0432\u0435\u0440\u0448\u0435\u043d\u043e:</b> {title}",
        f"<code>{issue_id}</code>",
    ]
    if duration_minutes > 0:
        hours = duration_minutes // 60
        mins = duration_minutes % 60
        if hours > 0:
            lines.append(f"\u23f1\ufe0f {hours}\u0447 {mins}\u043c")
        else:
            lines.append(f"\u23f1\ufe0f {mins}\u043c")
    return "\n".join(lines)


def format_task_blocked(issue_id: str, title: str, reason: str) -> str:
    """Format task blocked notification."""
    return (
        f"\u26a0\ufe0f <b>\u0417\u0430\u0431\u043b\u043e\u043a\u0438\u0440\u043e\u0432\u0430\u043d\u043e:</b> {title}\n"
        f"<code>{issue_id}</code>\n\n"
        f"<b>\u041f\u0440\u0438\u0447\u0438\u043d\u0430:</b> {reason}"
    )


def format_all_tasks_complete() -> str:
    """Format all tasks complete notification."""
    return (
        "\U0001f389 <b>\u0412\u0441\u0435 \u0437\u0430\u0434\u0430\u0447\u0438 \u0432\u044b\u043f\u043e\u043b\u043d\u0435\u043d\u044b!</b>\n\n"
        "\u041d\u0435 \u043e\u0441\u0442\u0430\u043b\u043e\u0441\u044c \u0437\u0430\u0434\u0430\u0447 \u0432 Todo.\n"
        "\u041e\u0442\u043b\u0438\u0447\u043d\u0430\u044f \u0440\u0430\u0431\u043e\u0442\u0430! \U0001f680"
    )


# =============================================================================
# Utility Functions
# =============================================================================


def escape_html(text: str) -> str:
    """Escape HTML special characters to prevent XSS in Telegram messages.

    Args:
        text: Raw text that may contain HTML special characters.

    Returns:
        Text with ``&``, ``<``, ``>``, and ``"`` replaced by HTML entities.
    """
    return (
        text
        .replace("&", "&amp;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
        .replace('"', "&quot;")
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
        "<b>\u0421\u0442\u0430\u0442\u0443\u0441</b>",
        "",
    ]

    # Task counts
    lines.append("<b>\u0417\u0430\u0434\u0430\u0447\u0438:</b>")
    lines.append(f"  \u041a \u0432\u044b\u043f\u043e\u043b\u043d\u0435\u043d\u0438\u044e: {data.todo_count}")
    lines.append(f"  \u0412 \u0440\u0430\u0431\u043e\u0442\u0435: {data.in_progress_count}")
    lines.append(f"  \u0417\u0430\u0432\u0435\u0440\u0448\u0435\u043d\u043e: {data.done_count}")
    lines.append("")

    # Progress bar
    if data.total_tasks > 0:
        bar = format_progress_bar(data.done_count, data.total_tasks, width=10)
        lines.append(f"<b>\u041f\u0440\u043e\u0433\u0440\u0435\u0441\u0441:</b> {bar}")
        lines.append("")

    # Current task
    if data.current_task_id:
        lines.append("<b>\u0422\u0435\u043a\u0443\u0449\u0430\u044f:</b>")
        title_display = data.current_task_title[:40]
        if len(data.current_task_title) > 40:
            title_display += "..."
        lines.append(f"  <code>{data.current_task_id}</code> {title_display}")
        lines.append("")
    elif data.in_progress_count > 0:
        lines.append("<b>\u0422\u0435\u043a\u0443\u0449\u0430\u044f:</b>")
        lines.append(f"  {data.in_progress_count} \u0437\u0430\u0434\u0430\u0447 \u0432 \u0440\u0430\u0431\u043e\u0442\u0435")
        lines.append("")

    # Session info
    if data.session_number > 0 or data.session_status != "idle":
        lines.append("<b>\u0421\u0435\u0441\u0441\u0438\u044f:</b>")

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
                lines.append(f"  \u0414\u043b\u0438\u0442\u0435\u043b\u044c\u043d\u043e\u0441\u0442\u044c: {hours}\u0447 {mins}\u043c")
            else:
                lines.append(f"  \u0414\u043b\u0438\u0442\u0435\u043b\u044c\u043d\u043e\u0441\u0442\u044c: {mins}\u043c")
        lines.append("")

    # Stale tasks warning
    if data.stale_count > 0:
        lines.append(f"<b>\u041f\u0440\u0435\u0434\u0443\u043f\u0440\u0435\u0436\u0434\u0435\u043d\u0438\u0435:</b> {data.stale_count} \u0443\u0441\u0442\u0430\u0440\u0435\u0432\u0448\u0438\u0445 \u0437\u0430\u0434\u0430\u0447")
        lines.append("")

    # All tasks done celebration
    if data.todo_count == 0 and data.in_progress_count == 0 and data.done_count > 0:
        lines.append("\u0412\u0441\u0435 \u0437\u0430\u0434\u0430\u0447\u0438 \u0432\u044b\u043f\u043e\u043b\u043d\u0435\u043d\u044b!")

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
        "<b>\u0421\u043b\u0435\u0434\u0443\u044e\u0449\u0430\u044f \u0437\u0430\u0434\u0430\u0447\u0430</b>",
        "",
        f"<code>{task_id}</code> {priority_emoji}{title}",
        f"<b>\u041f\u0440\u0438\u043e\u0440\u0438\u0442\u0435\u0442:</b> {priority}",
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
        lines.append(f"{total_todo} \u0437\u0430\u0434\u0430\u0447 \u043e\u0441\u0442\u0430\u043b\u043e\u0441\u044c \u0432 \u043e\u0447\u0435\u0440\u0435\u0434\u0438")
    else:
        lines.append("\u042d\u0442\u043e \u043f\u043e\u0441\u043b\u0435\u0434\u043d\u044f\u044f \u0437\u0430\u0434\u0430\u0447\u0430 \u0432 \u043e\u0447\u0435\u0440\u0435\u0434\u0438")

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
        return "<b>\u041f\u043e\u0441\u043b\u0435\u0434\u043d\u0438\u0435 \u0434\u0435\u0439\u0441\u0442\u0432\u0438\u044f</b>\n\n\u0414\u0435\u0439\u0441\u0442\u0432\u0438\u044f \u043d\u0435 \u0437\u0430\u0440\u0435\u0433\u0438\u0441\u0442\u0440\u0438\u0440\u043e\u0432\u0430\u043d\u044b."

    lines = [
        "<b>\u041f\u043e\u0441\u043b\u0435\u0434\u043d\u0438\u0435 \u0434\u0435\u0439\u0441\u0442\u0432\u0438\u044f</b>",
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
        "<b>\u0421\u0442\u0430\u0442\u0443\u0441 \u0431\u044e\u0434\u0436\u0435\u0442\u0430</b>",
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

        lines.append("<b>\u041a\u043e\u043d\u0442\u0435\u043a\u0441\u0442:</b>")
        lines.append(f"<code>[{bar}]</code> {usage_pct:.0f}%")
        lines.append(f"  {total_used:,} / {max_tokens:,} \u0442\u043e\u043a\u0435\u043d\u043e\u0432")

        # Mode indicator
        if mode == "critical":
            lines.append("  \u0420\u0435\u0436\u0438\u043c: \u041a\u0420\u0418\u0422\u0418\u0427\u0415\u0421\u041a\u0418\u0419")
        elif mode == "compact":
            lines.append("  \u0420\u0435\u0436\u0438\u043c: \u041a\u041e\u041c\u041f\u0410\u041a\u0422\u041d\u042b\u0419")
        else:
            lines.append(f"  \u0420\u0435\u0436\u0438\u043c: {mode}")

        lines.append("")

    # Cost section
    if cost_stats:
        lines.append("<b>\u0421\u0442\u043e\u0438\u043c\u043e\u0441\u0442\u044c:</b>")

        if "limit_usd" in cost_stats:
            # Budget with limit
            spent = cost_stats.get("spent_usd", 0)
            limit = cost_stats.get("limit_usd", 0)
            remaining = cost_stats.get("remaining_usd", limit - spent)

            lines.append(f"  ${spent:.2f} \u043f\u043e\u0442\u0440\u0430\u0447\u0435\u043d\u043e")
            if limit > 0:
                lines.append(f"  ${remaining:.2f} \u043e\u0441\u0442\u0430\u043b\u043e\u0441\u044c (\u0438\u0437 ${limit:.2f} \u043b\u0438\u043c\u0438\u0442\u0430)")

                # Add warning if over 80%
                if spent / limit > 0.8:
                    lines.append("  \u26a0\ufe0f \u0418\u0441\u043f\u043e\u043b\u044c\u0437\u043e\u0432\u0430\u043d\u043e \u0431\u043e\u043b\u0435\u0435 80% \u0431\u044e\u0434\u0436\u0435\u0442\u0430")
        else:
            # Just cost tracking without limit
            cost = cost_stats.get("cost_usd", 0)
            sessions = cost_stats.get("sessions", 0)
            tasks = cost_stats.get("tasks_completed", 0)

            lines.append(f"  ${cost:.2f} \u0437\u0430 \u044d\u0442\u0443 \u043d\u0435\u0434\u0435\u043b\u044e")
            if sessions > 0:
                lines.append(f"  {sessions} \u0441\u0435\u0441\u0441\u0438\u0439, {tasks} \u0437\u0430\u0434\u0430\u0447 \u0437\u0430\u0432\u0435\u0440\u0448\u0435\u043d\u043e")
    else:
        lines.append("<i>\u041e\u0442\u0441\u043b\u0435\u0436\u0438\u0432\u0430\u043d\u0438\u0435 \u0441\u0442\u043e\u0438\u043c\u043e\u0441\u0442\u0438 \u043d\u0435 \u043d\u0430\u0441\u0442\u0440\u043e\u0435\u043d\u043e</i>")
        lines.append("")
        lines.append("\u0414\u043b\u044f \u0432\u043a\u043b\u044e\u0447\u0435\u043d\u0438\u044f \u0441\u043e\u0437\u0434\u0430\u0439\u0442\u0435 <code>.agent/budget.json</code>:")
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
            "<b>\u0415\u0436\u0435\u0434\u043d\u0435\u0432\u043d\u044b\u0439 \u0434\u0430\u0439\u0434\u0436\u0435\u0441\u0442</b>",
            "",
            f"<b>\u041f\u0440\u043e\u0433\u0440\u0435\u0441\u0441:</b> {progress_bar}",
            "",
            "<b>\u0421\u0442\u0430\u0442\u0438\u0441\u0442\u0438\u043a\u0430:</b>",
            f"\u0417\u0430\u0432\u0435\u0440\u0448\u0435\u043d\u043e: {done}",
            f"\u0412 \u0440\u0430\u0431\u043e\u0442\u0435: {in_progress}",
            f"\u041a \u0432\u044b\u043f\u043e\u043b\u043d\u0435\u043d\u0438\u044e: {todo}",
        ]

        if completed_today:
            lines.append("")
            lines.append("<b>\u0417\u0430\u0432\u0435\u0440\u0448\u0435\u043d\u043e \u0441\u0435\u0433\u043e\u0434\u043d\u044f:</b>")
            for item in completed_today:
                if isinstance(item, dict):
                    task_id = escape_html(str(item.get("id", "")))
                    title = escape_html(str(item.get("title", "")))
                    lines.append(f"- {task_id}: {title}")
                else:
                    lines.append(f"- {escape_html(str(item))}")

        return "\n".join(lines)

    # -----------------------------------------------------------------
    # Session Summary (ENG-86)
    # -----------------------------------------------------------------

    def _format_duration(self, minutes: int) -> str:
        """Format duration in minutes as human-readable Russian string.

        Args:
            minutes: Duration in minutes (non-negative).

        Returns:
            Formatted string like ``1ч 30м`` or ``45м``.
            Returns ``0м`` when *minutes* is zero or negative.
        """
        if minutes <= 0:
            return "0\u043c"
        hours = minutes // 60
        mins = minutes % 60
        if hours > 0 and mins > 0:
            return f"{hours}\u0447 {mins}\u043c"
        if hours > 0:
            return f"{hours}\u0447"
        return f"{mins}\u043c"

    def _format_tokens(self, count: int) -> str:
        """Format token count with thousands separator.

        Args:
            count: Token count (non-negative integer).

        Returns:
            Comma-separated string like ``150,000``.
        """
        return f"{count:,}"

    def generate_session_summary(self, session_data: dict[str, object]) -> str:
        """Generate an HTML session summary report for Telegram.

        Sections with empty data are omitted automatically.
        All user-supplied strings are HTML-escaped for XSS protection.

        Args:
            session_data: Dictionary with session information containing:
                - ``start_time`` (str): ISO-format start timestamp, e.g. ``"2026-02-09T10:00:00"``.
                - ``end_time`` (str): ISO-format end timestamp.
                - ``duration_minutes`` (int): Session length in minutes.
                - ``tokens_used`` (int): Total tokens consumed.
                - ``cost_usd`` (float): Estimated cost in USD.
                - ``tool_calls`` (dict[str, int]): Counts by tool name.
                - ``commits`` (list[str]): Commit summaries (``"hash: message"``).
                - ``issues_completed`` (list[str]): Issue IDs completed.
                - ``retries`` (int): Number of retry attempts.
                - ``errors`` (list[str]): Error descriptions.

        Returns:
            HTML-formatted string ready for ``parse_mode="HTML"`` in Telegram.

        Example output::

            <b>Итоги сессии</b>

            <b>Время:</b> 10:00 -> 11:30 (1ч 30м)

            <b>Токены:</b> 150,000 (~$0.45)

            <b>Инструменты:</b>
            - Read: 25
            - Write: 10
            - Bash: 15

            <b>Коммиты:</b>
            - abc123: feat(ENG-85): add daily digest

            <b>Завершено:</b> ENG-85

            <b>Проблемы:</b> 2 retry
            - MCP timeout on first attempt
        """
        start_time = str(session_data.get("start_time", "") or "")
        end_time = str(session_data.get("end_time", "") or "")
        duration_minutes = int(session_data.get("duration_minutes", 0) or 0)
        tokens_used = int(session_data.get("tokens_used", 0) or 0)
        cost_usd = float(session_data.get("cost_usd", 0) or 0)
        tool_calls: dict[str, int] = dict(
            session_data.get("tool_calls", {}) or {}  # type: ignore[arg-type]
        )
        commits: list[str] = list(
            session_data.get("commits", []) or []  # type: ignore[arg-type]
        )
        issues_completed: list[str] = list(
            session_data.get("issues_completed", []) or []  # type: ignore[arg-type]
        )
        retries = int(session_data.get("retries", 0) or 0)
        errors: list[str] = list(
            session_data.get("errors", []) or []  # type: ignore[arg-type]
        )

        lines: list[str] = ["<b>\u0418\u0442\u043e\u0433\u0438 \u0441\u0435\u0441\u0441\u0438\u0438</b>"]

        # -- Time section --
        self._append_time_section(lines, start_time, end_time, duration_minutes)

        # -- Tokens section --
        if tokens_used > 0:
            lines.append("")
            token_str = self._format_tokens(tokens_used)
            if cost_usd > 0:
                lines.append(f"<b>\u0422\u043e\u043a\u0435\u043d\u044b:</b> {token_str} (~${cost_usd:.2f})")
            else:
                lines.append(f"<b>\u0422\u043e\u043a\u0435\u043d\u044b:</b> {token_str}")

        # -- Tool calls section --
        if tool_calls:
            lines.append("")
            lines.append("<b>\u0418\u043d\u0441\u0442\u0440\u0443\u043c\u0435\u043d\u0442\u044b:</b>")
            for tool_name, count in tool_calls.items():
                safe_name = escape_html(str(tool_name))
                lines.append(f"- {safe_name}: {count}")

        # -- Commits section --
        if commits:
            lines.append("")
            lines.append("<b>\u041a\u043e\u043c\u043c\u0438\u0442\u044b:</b>")
            for commit in commits:
                lines.append(f"- {escape_html(str(commit))}")

        # -- Issues completed section --
        if issues_completed:
            lines.append("")
            safe_issues = ", ".join(escape_html(str(i)) for i in issues_completed)
            lines.append(f"<b>\u0417\u0430\u0432\u0435\u0440\u0448\u0435\u043d\u043e:</b> {safe_issues}")

        # -- Problems / retries section --
        if retries > 0 or errors:
            lines.append("")
            if retries > 0:
                lines.append(f"<b>\u041f\u0440\u043e\u0431\u043b\u0435\u043c\u044b:</b> {retries} retry")
            else:
                lines.append("<b>\u041f\u0440\u043e\u0431\u043b\u0435\u043c\u044b:</b>")
            for error in errors:
                lines.append(f"- {escape_html(str(error))}")

        return "\n".join(lines)

    def _append_time_section(
        self,
        lines: list[str],
        start_time: str,
        end_time: str,
        duration_minutes: int,
    ) -> None:
        """Append the time section to report lines.

        Builds the time line from start/end timestamps and duration.
        Skips the section entirely when no time data is available.

        Args:
            lines: Accumulator list of report lines (mutated in place).
            start_time: ISO-format start timestamp string.
            end_time: ISO-format end timestamp string.
            duration_minutes: Duration in minutes.
        """
        has_times = bool(start_time and end_time)
        has_duration = duration_minutes > 0

        if not has_times and not has_duration:
            return

        lines.append("")

        if has_times:
            start_short = self._extract_time_hhmm(start_time)
            end_short = self._extract_time_hhmm(end_time)
            duration_str = self._format_duration(duration_minutes)

            if has_duration:
                lines.append(
                    f"<b>\u0412\u0440\u0435\u043c\u044f:</b> {start_short} -> {end_short} ({duration_str})"
                )
            else:
                lines.append(f"<b>\u0412\u0440\u0435\u043c\u044f:</b> {start_short} -> {end_short}")
        elif has_duration:
            duration_str = self._format_duration(duration_minutes)
            lines.append(f"<b>\u0412\u0440\u0435\u043c\u044f:</b> {duration_str}")

    @staticmethod
    def _extract_time_hhmm(iso_timestamp: str) -> str:
        """Extract HH:MM from an ISO-format timestamp string.

        Falls back to the raw string (HTML-escaped) if parsing fails.

        Args:
            iso_timestamp: Timestamp like ``"2026-02-09T10:00:00"``.

        Returns:
            Time portion as ``"HH:MM"`` or escaped fallback.
        """
        try:
            dt = datetime.fromisoformat(iso_timestamp)
            return dt.strftime("%H:%M")
        except (ValueError, TypeError):
            return escape_html(iso_timestamp)

    # -----------------------------------------------------------------
    # Error Alert (ENG-87)
    # -----------------------------------------------------------------

    def generate_error_alert(self, error_data: dict[str, object]) -> str:
        """Generate an HTML error alert for Telegram.

        Builds a structured error notification containing the error type,
        message, file location, attempt counter, and chosen recovery action.
        All user-supplied strings are HTML-escaped for XSS protection.
        Sections with missing or empty data are omitted automatically.

        Args:
            error_data: Dictionary with error details containing:
                - ``error_type`` (str): Exception class name,
                  e.g. ``"MCPTimeoutError"``, ``"ValueError"``.
                - ``message`` (str): Human-readable error description.
                - ``file`` (str): Source file where the error occurred.
                - ``line`` (int): Line number in the source file.
                - ``attempt`` (int): Current attempt number.
                - ``max_attempts`` (int): Maximum retry attempts allowed.
                - ``action`` (str): Recovery action --
                  ``"retry"``, ``"fallback"``, or ``"escalate"``.
                - ``context`` (str): What the agent was doing when the
                  error occurred, e.g. ``"Calling Task_ListIssues"``.

        Returns:
            HTML-formatted string ready for ``parse_mode="HTML"`` in
            Telegram.

        Example output::

            <b>Warning: Ошибка</b>

            <b>Тип:</b> MCPTimeoutError
            <b>Сообщение:</b> Connection timeout after 30s

            <b>Расположение:</b> <code>client.py:142</code>
            <b>Контекст:</b> Calling Task_ListIssues

            <b>Попытка:</b> 2/3
            <b>Действие:</b> Repeat Повтор
        """
        error_type = str(error_data.get("error_type", "") or "")
        message = str(error_data.get("message", "") or "")
        file_path = str(error_data.get("file", "") or "")
        line_number = int(error_data.get("line", 0) or 0)
        attempt = int(error_data.get("attempt", 0) or 0)
        max_attempts = int(error_data.get("max_attempts", 0) or 0)
        action = str(error_data.get("action", "") or "")
        context = str(error_data.get("context", "") or "")

        lines: list[str] = ["\u26a0\ufe0f <b>\u041e\u0448\u0438\u0431\u043a\u0430</b>"]

        # -- Type section --
        if error_type:
            lines.append("")
            lines.append(f"<b>\u0422\u0438\u043f:</b> {escape_html(error_type)}")

        # -- Message section --
        if message:
            lines.append(f"<b>\u0421\u043e\u043e\u0431\u0449\u0435\u043d\u0438\u0435:</b> {escape_html(message)}")

        # -- Location section --
        if file_path:
            lines.append("")
            safe_file = escape_html(file_path)
            if line_number > 0:
                lines.append(
                    f"<b>\u0420\u0430\u0441\u043f\u043e\u043b\u043e\u0436\u0435\u043d\u0438\u0435:</b> <code>{safe_file}:{line_number}</code>"
                )
            else:
                lines.append(
                    f"<b>\u0420\u0430\u0441\u043f\u043e\u043b\u043e\u0436\u0435\u043d\u0438\u0435:</b> <code>{safe_file}</code>"
                )

        # -- Context section --
        if context:
            lines.append(f"<b>\u041a\u043e\u043d\u0442\u0435\u043a\u0441\u0442:</b> {escape_html(context)}")

        # -- Attempt section --
        if attempt > 0 and max_attempts > 0:
            lines.append("")
            lines.append(f"<b>\u041f\u043e\u043f\u044b\u0442\u043a\u0430:</b> {attempt}/{max_attempts}")

        # -- Action section --
        action_label = self._get_action_label(action)
        if action_label:
            lines.append(f"<b>\u0414\u0435\u0439\u0441\u0442\u0432\u0438\u0435:</b> {action_label}")

        return "\n".join(lines)

    @staticmethod
    def _get_action_label(action: str) -> str:
        """Map an action keyword to a localised label with icon.

        Args:
            action: One of ``"retry"``, ``"fallback"``, or ``"escalate"``.
                    Empty string or unknown values return ``""``.

        Returns:
            Localised label like ``"Repeat Повтор"`` or empty string.
        """
        mapping: dict[str, str] = {
            "retry": "\U0001f504 \u041f\u043e\u0432\u0442\u043e\u0440",
            "fallback": "\u21a9\ufe0f \u041e\u0442\u043a\u0430\u0442",
            "escalate": "\U0001f6a8 \u042d\u0441\u043a\u0430\u043b\u0430\u0446\u0438\u044f",
        }
        return mapping.get(action.lower(), "") if action else ""

    # -----------------------------------------------------------------
    # Weekly Summary (ENG-88)
    # -----------------------------------------------------------------

    VELOCITY_TREND_ICONS: dict[str, str] = {
        "up": "\U0001f4c8",       # chart increasing
        "down": "\U0001f4c9",     # chart decreasing
        "stable": "\u27a1\ufe0f", # right arrow
    }

    def _format_date_ddmmyyyy(self, iso_date: str) -> str:
        """Parse an ISO date string and return DD.MM.YYYY format.

        Falls back to HTML-escaped raw string if parsing fails.

        Args:
            iso_date: Date string like ``"2026-02-09"`` or ISO datetime.

        Returns:
            Formatted date like ``"09.02.2026"`` or escaped fallback.
        """
        try:
            dt = datetime.fromisoformat(iso_date)
            return dt.strftime("%d.%m.%Y")
        except (ValueError, TypeError):
            return escape_html(str(iso_date))

    def _format_short_date(self, iso_date: str) -> str:
        """Parse an ISO date string and return DD.MM format (no year).

        Falls back to HTML-escaped raw string if parsing fails.

        Args:
            iso_date: Date string like ``"2026-02-03"``.

        Returns:
            Formatted date like ``"03.02"`` or escaped fallback.
        """
        try:
            dt = datetime.fromisoformat(iso_date)
            return dt.strftime("%d.%m")
        except (ValueError, TypeError):
            return escape_html(str(iso_date))

    def _format_cost(self, cost_usd: float) -> str:
        """Format a USD cost value for display.

        Args:
            cost_usd: Cost in US dollars.

        Returns:
            String like ``"$7.50"`` or ``"$0.00"``.
        """
        return f"${cost_usd:.2f}"

    def generate_weekly_summary(self, weekly_data: dict[str, object]) -> str:
        """Generate an HTML weekly summary report for Telegram.

        Builds a structured weekly report containing task progress,
        cost breakdown, velocity trends, top errors, and estimated
        completion date.  Sections with empty data are omitted
        automatically.  All user-supplied strings are HTML-escaped
        for XSS protection.

        Args:
            weekly_data: Dictionary with weekly statistics containing:
                - ``week_start`` (str): ISO-format start date, e.g.
                  ``"2026-02-03"``.
                - ``week_end`` (str): ISO-format end date, e.g.
                  ``"2026-02-09"``.
                - ``tasks_completed`` (int): Tasks completed this week.
                - ``tasks_total`` (int): Total tasks in the project.
                - ``tokens_used`` (int): Total tokens consumed.
                - ``cost_usd`` (float): Total cost in USD.
                - ``top_errors`` (list[dict]): Most frequent errors, each
                  with ``"error"`` (str) and ``"count"`` (int) keys.
                - ``velocity`` (float): Tasks completed per day.
                - ``velocity_trend`` (str): One of ``"up"``, ``"down"``,
                  or ``"stable"``.
                - ``estimated_completion`` (str): ISO-format estimated
                  completion date, e.g. ``"2026-03-15"``.

        Returns:
            HTML-formatted string ready for ``parse_mode="HTML"``
            in Telegram.

        Example output::

            <b>Итоги недели</b>
            <i>03.02 -- 09.02.2026</i>

            <b>Прогресс:</b> [......] 30%
            Завершено: 15 из 50 задач

            <b>Стоимость:</b> $7.50 (2,500,000 токенов)

            <b>Скорость:</b> 2.1 задач/день (chart icon)
            <i>Прогноз завершения: 15.03.2026</i>

            <b>Частые ошибки:</b>
            - MCPTimeoutError: 5
            - ValueError: 2
        """
        week_start = str(weekly_data.get("week_start", "") or "")
        week_end = str(weekly_data.get("week_end", "") or "")
        tasks_completed = int(weekly_data.get("tasks_completed", 0) or 0)
        tasks_total = int(weekly_data.get("tasks_total", 0) or 0)
        tokens_used = int(weekly_data.get("tokens_used", 0) or 0)
        cost_usd = float(weekly_data.get("cost_usd", 0) or 0)
        top_errors: list[dict[str, object]] = list(
            weekly_data.get("top_errors", []) or []  # type: ignore[arg-type]
        )
        velocity = float(weekly_data.get("velocity", 0) or 0)
        velocity_trend = str(weekly_data.get("velocity_trend", "") or "")
        estimated_completion = str(
            weekly_data.get("estimated_completion", "") or ""
        )

        lines: list[str] = ["\U0001f4c8 <b>\u0418\u0442\u043e\u0433\u0438 \u043d\u0435\u0434\u0435\u043b\u0438</b>"]

        # -- Date range header --
        self._append_week_range(lines, week_start, week_end)

        # -- Progress section --
        if tasks_total > 0:
            progress_bar = self.format_progress_bar(tasks_completed, tasks_total)
            lines.append("")
            lines.append(f"<b>\u041f\u0440\u043e\u0433\u0440\u0435\u0441\u0441:</b> {progress_bar}")
            lines.append(f"\u0417\u0430\u0432\u0435\u0440\u0448\u0435\u043d\u043e: {tasks_completed} \u0438\u0437 {tasks_total} \u0437\u0430\u0434\u0430\u0447")

        # -- Cost section --
        if cost_usd > 0 or tokens_used > 0:
            lines.append("")
            cost_str = self._format_cost(cost_usd)
            token_str = self._format_tokens(tokens_used)
            lines.append(f"<b>\u0421\u0442\u043e\u0438\u043c\u043e\u0441\u0442\u044c:</b> {cost_str} ({token_str} \u0442\u043e\u043a\u0435\u043d\u043e\u0432)")

        # -- Velocity section --
        if velocity > 0:
            trend_icon = self.VELOCITY_TREND_ICONS.get(
                velocity_trend.lower(), ""
            )
            lines.append("")
            lines.append(
                f"<b>\u0421\u043a\u043e\u0440\u043e\u0441\u0442\u044c:</b> {velocity:.1f} \u0437\u0430\u0434\u0430\u0447/\u0434\u0435\u043d\u044c {trend_icon}"
            )
            if estimated_completion:
                est_date = self._format_date_ddmmyyyy(estimated_completion)
                lines.append(f"<i>\u041f\u0440\u043e\u0433\u043d\u043e\u0437 \u0437\u0430\u0432\u0435\u0440\u0448\u0435\u043d\u0438\u044f: {est_date}</i>")

        # -- Top errors section --
        if top_errors:
            lines.append("")
            lines.append("<b>\u0427\u0430\u0441\u0442\u044b\u0435 \u043e\u0448\u0438\u0431\u043a\u0438:</b>")
            for entry in top_errors:
                error_name = escape_html(str(entry.get("error", "")))
                error_count = int(entry.get("count", 0) or 0)
                lines.append(f"\u2022 {error_name}: {error_count}")

        return "\n".join(lines)

    def _append_week_range(
        self,
        lines: list[str],
        week_start: str,
        week_end: str,
    ) -> None:
        """Append the week date range as an italic subtitle.

        Formats dates as ``DD.MM -- DD.MM.YYYY`` using the year from
        ``week_end``.  Skipped entirely when both dates are empty.

        Args:
            lines: Accumulator list of report lines (mutated in place).
            week_start: ISO-format start date string.
            week_end: ISO-format end date string.
        """
        if not week_start and not week_end:
            return

        start_short = self._format_short_date(week_start) if week_start else "?"
        end_full = self._format_date_ddmmyyyy(week_end) if week_end else "?"

        lines.append(f"<i>{start_short} \u2014 {end_full}</i>")
