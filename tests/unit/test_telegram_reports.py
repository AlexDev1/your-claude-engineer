"""
Tests for TelegramReports (ENG-85, ENG-86, ENG-87)
=====================================================

Verifies:
1. Daily digest generation with all fields
2. Progress bar at 0%, 50%, 100%, and edge cases
3. HTML formatting uses only Telegram-supported tags
4. Completed-today list with dict and string items
5. Empty / missing fields handled gracefully
6. Session summary: full report generation (ENG-86)
7. Session summary: empty commits/errors (ENG-86)
8. Session summary: time formatting (ENG-86)
9. Session summary: token formatting with thousands separators (ENG-86)
10. Session summary: XSS protection (ENG-86)
11. Error alert: full report generation (ENG-87)
12. Error alert: action labels with icons (ENG-87)
13. Error alert: optional fields omitted when empty (ENG-87)
14. Error alert: XSS protection (ENG-87)
"""

import re

from telegram_reports import TelegramReports

# Telegram-supported HTML tags (subset used by reports)
ALLOWED_TAGS = {"b", "i", "code", "pre", "a"}

# Pattern that matches any HTML tag (opening or self-closing)
HTML_TAG_RE = re.compile(r"</?(\w+)(?:\s[^>]*)?>")


def _extract_tags(html: str) -> set[str]:
    """Extract unique HTML tag names from a string.

    Args:
        html: HTML-formatted string.

    Returns:
        Set of lowercase tag names found.
    """
    return {m.group(1).lower() for m in HTML_TAG_RE.finditer(html)}


# ---------------------------------------------------------------------------
# Progress bar tests
# ---------------------------------------------------------------------------


class TestFormatProgressBar:
    """Test TelegramReports.format_progress_bar."""

    def setup_method(self) -> None:
        """Create a TelegramReports instance for each test."""
        self.reports = TelegramReports()

    def test_zero_percent(self) -> None:
        """0 done out of N yields 0% with all empty blocks."""
        result = self.reports.format_progress_bar(0, 10)
        assert result == "[\u2591\u2591\u2591\u2591\u2591\u2591\u2591\u2591\u2591\u2591] 0%"

    def test_fifty_percent(self) -> None:
        """Half done yields 50% with half-filled bar."""
        result = self.reports.format_progress_bar(5, 10)
        assert result == "[\u2588\u2588\u2588\u2588\u2588\u2591\u2591\u2591\u2591\u2591] 50%"

    def test_hundred_percent(self) -> None:
        """All done yields 100% with fully-filled bar."""
        result = self.reports.format_progress_bar(10, 10)
        assert result == "[\u2588\u2588\u2588\u2588\u2588\u2588\u2588\u2588\u2588\u2588] 100%"

    def test_zero_total(self) -> None:
        """Zero total returns 0% bar without division error."""
        result = self.reports.format_progress_bar(0, 0)
        assert "0%" in result
        assert "[" in result and "]" in result

    def test_negative_total(self) -> None:
        """Negative total is treated as zero total."""
        result = self.reports.format_progress_bar(5, -1)
        assert "0%" in result

    def test_done_exceeds_total(self) -> None:
        """done > total caps at 100%."""
        result = self.reports.format_progress_bar(15, 10)
        assert "100%" in result

    def test_partial_percentage(self) -> None:
        """Non-round percentages are rendered correctly."""
        result = self.reports.format_progress_bar(1, 3)
        # 33% -> 3 filled blocks out of 10
        assert "\u2588" in result
        assert "33%" in result

    def test_bar_width_is_ten(self) -> None:
        """Bar body always has exactly 10 characters between brackets."""
        result = self.reports.format_progress_bar(7, 10)
        # Extract content between [ and ]
        inner = result.split("[")[1].split("]")[0]
        assert len(inner) == 10


# ---------------------------------------------------------------------------
# Daily digest generation tests
# ---------------------------------------------------------------------------


class TestGenerateDailyDigest:
    """Test TelegramReports.generate_daily_digest."""

    def setup_method(self) -> None:
        """Create a TelegramReports instance for each test."""
        self.reports = TelegramReports()

    def test_basic_digest(self) -> None:
        """Digest includes header, progress, statistics sections."""
        stats = {
            "done": 5,
            "in_progress": 2,
            "todo": 10,
            "completed_today": ["ENG-1", "ENG-2"],
        }
        result = self.reports.generate_daily_digest(stats)

        assert "<b>Ежедневный дайджест</b>" in result
        assert "<b>Прогресс:</b>" in result
        assert "<b>Статистика:</b>" in result
        assert "Завершено: 5" in result
        assert "В работе: 2" in result
        assert "К выполнению: 10" in result

    def test_completed_today_strings(self) -> None:
        """Completed-today items as plain strings are listed."""
        stats = {
            "done": 2,
            "in_progress": 0,
            "todo": 0,
            "completed_today": ["ENG-79", "ENG-80"],
        }
        result = self.reports.generate_daily_digest(stats)

        assert "<b>Завершено сегодня:</b>" in result
        assert "- ENG-79" in result
        assert "- ENG-80" in result

    def test_completed_today_dicts(self) -> None:
        """Completed-today items as dicts render id and title."""
        stats = {
            "done": 2,
            "in_progress": 1,
            "todo": 3,
            "completed_today": [
                {"id": "ENG-79", "title": "Перевод промптов"},
                {"id": "ENG-80", "title": "Русификация Telegram"},
            ],
        }
        result = self.reports.generate_daily_digest(stats)

        assert "- ENG-79: Перевод промптов" in result
        assert "- ENG-80: Русификация Telegram" in result

    def test_empty_completed_today(self) -> None:
        """No completed-today section when list is empty."""
        stats = {
            "done": 0,
            "in_progress": 1,
            "todo": 5,
            "completed_today": [],
        }
        result = self.reports.generate_daily_digest(stats)

        assert "Завершено сегодня" not in result

    def test_missing_keys_use_defaults(self) -> None:
        """Missing keys default to 0 / empty list without error."""
        result = self.reports.generate_daily_digest({})

        assert "Завершено: 0" in result
        assert "В работе: 0" in result
        assert "К выполнению: 0" in result
        assert "0%" in result

    def test_progress_bar_in_digest(self) -> None:
        """Progress bar matches expected percentage."""
        stats = {"done": 6, "in_progress": 2, "todo": 2}
        result = self.reports.generate_daily_digest(stats)

        # 6 out of 10 = 60%
        assert "60%" in result

    def test_all_done(self) -> None:
        """When everything is done, progress shows 100%."""
        stats = {"done": 8, "in_progress": 0, "todo": 0}
        result = self.reports.generate_daily_digest(stats)

        assert "100%" in result

    def test_xss_prevention_in_completed_today(self) -> None:
        """Verify HTML special characters in task_id and title are escaped."""
        stats = {
            "done": 1,
            "in_progress": 0,
            "todo": 0,
            "completed_today": [
                {"id": "<script>alert(1)</script>", "title": "Test"},
                {"id": "ENG-1", "title": "<img src=x onerror=alert(1)>"},
            ],
        }
        result = self.reports.generate_daily_digest(stats)

        # Dangerous tags must be escaped
        assert "<script>" not in result
        assert "&lt;script&gt;" in result
        assert "<img" not in result
        assert "&lt;img" in result


# ---------------------------------------------------------------------------
# HTML validation tests
# ---------------------------------------------------------------------------


class TestHtmlFormatting:
    """Verify HTML uses only Telegram-supported tags."""

    def setup_method(self) -> None:
        """Create a TelegramReports instance for each test."""
        self.reports = TelegramReports()

    def test_only_allowed_tags_in_digest(self) -> None:
        """Daily digest uses only Telegram-allowed HTML tags."""
        stats = {
            "done": 5,
            "in_progress": 2,
            "todo": 3,
            "completed_today": [
                {"id": "ENG-1", "title": "Task one"},
            ],
        }
        result = self.reports.generate_daily_digest(stats)

        used_tags = _extract_tags(result)
        assert used_tags.issubset(ALLOWED_TAGS), (
            f"Found disallowed tags: {used_tags - ALLOWED_TAGS}"
        )

    def test_tags_are_properly_closed(self) -> None:
        """Every opening tag has a matching closing tag."""
        stats = {"done": 3, "in_progress": 1, "todo": 2}
        result = self.reports.generate_daily_digest(stats)

        for tag in _extract_tags(result):
            open_count = result.count(f"<{tag}>") + result.count(f"<{tag} ")
            close_count = result.count(f"</{tag}>")
            assert open_count == close_count, (
                f"Tag <{tag}> opened {open_count} times but closed {close_count} times"
            )

    def test_no_unescaped_ampersands(self) -> None:
        """Report text should not contain bare '&' outside entities."""
        stats = {"done": 1, "in_progress": 0, "todo": 0}
        result = self.reports.generate_daily_digest(stats)

        # Remove known HTML entities before checking
        cleaned = result.replace("&amp;", "").replace("&lt;", "").replace("&gt;", "")
        assert "&" not in cleaned, "Found unescaped '&' in output"


# ---------------------------------------------------------------------------
# Session summary generation tests (ENG-86)
# ---------------------------------------------------------------------------


class TestGenerateSessionSummary:
    """Test TelegramReports.generate_session_summary."""

    def setup_method(self) -> None:
        """Create a TelegramReports instance for each test."""
        self.reports = TelegramReports()

    def _full_session_data(self) -> dict:
        """Return a complete session data dictionary for reuse.

        Returns:
            Dict with all supported session_data keys populated.
        """
        return {
            "start_time": "2026-02-09T10:00:00",
            "end_time": "2026-02-09T11:30:00",
            "duration_minutes": 90,
            "tokens_used": 150000,
            "cost_usd": 0.45,
            "tool_calls": {"Read": 25, "Write": 10, "Bash": 15},
            "commits": ["abc123: feat(ENG-85): add daily digest"],
            "issues_completed": ["ENG-85"],
            "retries": 2,
            "errors": ["MCP timeout on first attempt"],
        }

    def test_full_report_header(self) -> None:
        """Full report starts with the session summary header."""
        result = self.reports.generate_session_summary(self._full_session_data())
        assert "<b>Итоги сессии</b>" in result

    def test_full_report_time_section(self) -> None:
        """Time section shows start, end, and duration."""
        result = self.reports.generate_session_summary(self._full_session_data())
        assert "10:00" in result
        assert "11:30" in result
        assert "1ч 30м" in result

    def test_full_report_tokens_section(self) -> None:
        """Tokens section shows formatted count and cost."""
        result = self.reports.generate_session_summary(self._full_session_data())
        assert "150,000" in result
        assert "~$0.45" in result

    def test_full_report_tool_calls_section(self) -> None:
        """Tool calls section lists each tool with its count."""
        result = self.reports.generate_session_summary(self._full_session_data())
        assert "<b>Инструменты:</b>" in result
        assert "- Read: 25" in result
        assert "- Write: 10" in result
        assert "- Bash: 15" in result

    def test_full_report_commits_section(self) -> None:
        """Commits section lists each commit."""
        result = self.reports.generate_session_summary(self._full_session_data())
        assert "<b>Коммиты:</b>" in result
        assert "abc123: feat(ENG-85): add daily digest" in result

    def test_full_report_issues_completed(self) -> None:
        """Issues completed section lists finished issues."""
        result = self.reports.generate_session_summary(self._full_session_data())
        assert "<b>Завершено:</b>" in result
        assert "ENG-85" in result

    def test_full_report_problems_section(self) -> None:
        """Problems section shows retry count and error messages."""
        result = self.reports.generate_session_summary(self._full_session_data())
        assert "<b>Проблемы:</b> 2 retry" in result
        assert "- MCP timeout on first attempt" in result

    def test_empty_commits_and_errors(self) -> None:
        """Sections with empty lists are omitted from the report."""
        data = {
            "start_time": "2026-02-09T10:00:00",
            "end_time": "2026-02-09T10:45:00",
            "duration_minutes": 45,
            "tokens_used": 50000,
            "cost_usd": 0.15,
            "tool_calls": {"Read": 5},
            "commits": [],
            "issues_completed": [],
            "retries": 0,
            "errors": [],
        }
        result = self.reports.generate_session_summary(data)

        assert "Коммиты" not in result
        assert "Завершено" not in result
        assert "Проблемы" not in result

    def test_empty_session_data(self) -> None:
        """Empty dict produces only the header without crashing."""
        result = self.reports.generate_session_summary({})

        assert "<b>Итоги сессии</b>" in result
        # No optional sections should appear
        assert "Время" not in result
        assert "Токены" not in result
        assert "Инструменты" not in result
        assert "Коммиты" not in result
        assert "Завершено" not in result
        assert "Проблемы" not in result

    def test_none_values_treated_as_defaults(self) -> None:
        """None values for optional fields default safely."""
        data = {
            "start_time": None,
            "end_time": None,
            "duration_minutes": None,
            "tokens_used": None,
            "cost_usd": None,
            "tool_calls": None,
            "commits": None,
            "issues_completed": None,
            "retries": None,
            "errors": None,
        }
        result = self.reports.generate_session_summary(data)
        assert "<b>Итоги сессии</b>" in result

    def test_multiple_issues_completed(self) -> None:
        """Multiple issues are listed comma-separated."""
        data = {
            "issues_completed": ["ENG-85", "ENG-86", "ENG-87"],
        }
        result = self.reports.generate_session_summary(data)
        assert "ENG-85, ENG-86, ENG-87" in result

    def test_errors_without_retries(self) -> None:
        """Errors section appears even when retries is 0."""
        data = {
            "retries": 0,
            "errors": ["Unexpected timeout"],
        }
        result = self.reports.generate_session_summary(data)
        assert "<b>Проблемы:</b>" in result
        assert "- Unexpected timeout" in result
        # Should not show "0 retry"
        assert "0 retry" not in result

    def test_retries_without_errors(self) -> None:
        """Retry count shown even when error list is empty."""
        data = {"retries": 3, "errors": []}
        result = self.reports.generate_session_summary(data)
        assert "<b>Проблемы:</b> 3 retry" in result


# ---------------------------------------------------------------------------
# Session summary: time formatting (ENG-86)
# ---------------------------------------------------------------------------


class TestSessionSummaryTimeFormatting:
    """Test duration and time formatting in session summary."""

    def setup_method(self) -> None:
        """Create a TelegramReports instance for each test."""
        self.reports = TelegramReports()

    def test_format_duration_hours_and_minutes(self) -> None:
        """90 minutes formats as '1ч 30м'."""
        assert self.reports._format_duration(90) == "1ч 30м"

    def test_format_duration_only_minutes(self) -> None:
        """45 minutes formats as '45м'."""
        assert self.reports._format_duration(45) == "45м"

    def test_format_duration_only_hours(self) -> None:
        """120 minutes (exact hours) formats as '2ч'."""
        assert self.reports._format_duration(120) == "2ч"

    def test_format_duration_zero(self) -> None:
        """Zero minutes formats as '0м'."""
        assert self.reports._format_duration(0) == "0м"

    def test_format_duration_negative(self) -> None:
        """Negative minutes treated as zero."""
        assert self.reports._format_duration(-5) == "0м"

    def test_format_duration_one_minute(self) -> None:
        """Single minute."""
        assert self.reports._format_duration(1) == "1м"

    def test_format_duration_large(self) -> None:
        """Large durations like 300 minutes = 5 hours."""
        assert self.reports._format_duration(300) == "5ч"

    def test_time_only_duration_no_timestamps(self) -> None:
        """When only duration is given, show just duration."""
        data = {"duration_minutes": 45}
        result = self.reports.generate_session_summary(data)
        assert "<b>Время:</b> 45м" in result

    def test_time_with_start_end_no_duration(self) -> None:
        """When timestamps given but no duration, show times only."""
        data = {
            "start_time": "2026-02-09T14:00:00",
            "end_time": "2026-02-09T15:00:00",
            "duration_minutes": 0,
        }
        result = self.reports.generate_session_summary(data)
        assert "14:00" in result
        assert "15:00" in result
        # No duration parenthetical
        assert "0м" not in result

    def test_time_section_omitted_when_all_empty(self) -> None:
        """No time section when no time data is provided."""
        data = {"tokens_used": 1000}
        result = self.reports.generate_session_summary(data)
        assert "Время" not in result


# ---------------------------------------------------------------------------
# Session summary: token formatting (ENG-86)
# ---------------------------------------------------------------------------


class TestSessionSummaryTokenFormatting:
    """Test token count formatting with thousands separators."""

    def setup_method(self) -> None:
        """Create a TelegramReports instance for each test."""
        self.reports = TelegramReports()

    def test_format_tokens_thousands(self) -> None:
        """150000 formats as '150,000'."""
        assert self.reports._format_tokens(150000) == "150,000"

    def test_format_tokens_millions(self) -> None:
        """1500000 formats as '1,500,000'."""
        assert self.reports._format_tokens(1500000) == "1,500,000"

    def test_format_tokens_small(self) -> None:
        """999 formats without separator."""
        assert self.reports._format_tokens(999) == "999"

    def test_format_tokens_zero(self) -> None:
        """Zero formats as '0'."""
        assert self.reports._format_tokens(0) == "0"

    def test_tokens_without_cost(self) -> None:
        """Tokens shown without cost when cost_usd is 0."""
        data = {"tokens_used": 50000, "cost_usd": 0}
        result = self.reports.generate_session_summary(data)
        assert "50,000" in result
        assert "$" not in result

    def test_tokens_with_cost(self) -> None:
        """Tokens shown with cost when both provided."""
        data = {"tokens_used": 150000, "cost_usd": 0.45}
        result = self.reports.generate_session_summary(data)
        assert "150,000" in result
        assert "~$0.45" in result

    def test_zero_tokens_omitted(self) -> None:
        """Token section omitted when tokens_used is 0."""
        data = {"tokens_used": 0}
        result = self.reports.generate_session_summary(data)
        assert "Токены" not in result


# ---------------------------------------------------------------------------
# Session summary: XSS protection (ENG-86)
# ---------------------------------------------------------------------------


class TestSessionSummaryXssProtection:
    """Test that user-supplied data is HTML-escaped."""

    def setup_method(self) -> None:
        """Create a TelegramReports instance for each test."""
        self.reports = TelegramReports()

    def test_xss_in_commit_message(self) -> None:
        """HTML in commit messages is escaped."""
        data = {
            "commits": ['abc: <script>alert("xss")</script>'],
        }
        result = self.reports.generate_session_summary(data)
        assert "<script>" not in result
        assert "&lt;script&gt;" in result

    def test_xss_in_tool_name(self) -> None:
        """HTML in tool names is escaped."""
        data = {
            "tool_calls": {"<b>evil</b>": 5},
        }
        result = self.reports.generate_session_summary(data)
        # The literal <b>evil</b> should not appear as HTML tag
        assert "&lt;b&gt;evil&lt;/b&gt;" in result

    def test_xss_in_error_message(self) -> None:
        """HTML in error messages is escaped."""
        data = {
            "retries": 1,
            "errors": ["<img src=x onerror=alert(1)>"],
        }
        result = self.reports.generate_session_summary(data)
        assert "<img" not in result
        assert "&lt;img" in result

    def test_xss_in_issue_id(self) -> None:
        """HTML in issue IDs is escaped."""
        data = {
            "issues_completed": ['<a href="evil">click</a>'],
        }
        result = self.reports.generate_session_summary(data)
        assert 'href="evil"' not in result
        assert "&lt;a" in result

    def test_only_allowed_tags_in_session_summary(self) -> None:
        """Session summary uses only Telegram-allowed HTML tags."""
        data = {
            "start_time": "2026-02-09T10:00:00",
            "end_time": "2026-02-09T11:30:00",
            "duration_minutes": 90,
            "tokens_used": 150000,
            "cost_usd": 0.45,
            "tool_calls": {"Read": 25},
            "commits": ["abc123: feat: test"],
            "issues_completed": ["ENG-85"],
            "retries": 1,
            "errors": ["timeout"],
        }
        result = self.reports.generate_session_summary(data)
        used_tags = _extract_tags(result)
        assert used_tags.issubset(ALLOWED_TAGS), (
            f"Found disallowed tags: {used_tags - ALLOWED_TAGS}"
        )

    def test_tags_properly_closed_in_session_summary(self) -> None:
        """Every opening tag in session summary has a matching close."""
        data = self._full_session_data()
        result = self.reports.generate_session_summary(data)

        for tag in _extract_tags(result):
            open_count = result.count(f"<{tag}>") + result.count(f"<{tag} ")
            close_count = result.count(f"</{tag}>")
            assert open_count == close_count, (
                f"Tag <{tag}> opened {open_count} but closed {close_count} times"
            )

    def _full_session_data(self) -> dict:
        """Return complete session data for XSS test.

        Returns:
            Dict with all supported session_data keys populated.
        """
        return {
            "start_time": "2026-02-09T10:00:00",
            "end_time": "2026-02-09T11:30:00",
            "duration_minutes": 90,
            "tokens_used": 150000,
            "cost_usd": 0.45,
            "tool_calls": {"Read": 25, "Write": 10},
            "commits": ["abc123: feat(ENG-85): add digest"],
            "issues_completed": ["ENG-85"],
            "retries": 2,
            "errors": ["MCP timeout"],
        }


# ---------------------------------------------------------------------------
# Error alert generation tests (ENG-87)
# ---------------------------------------------------------------------------


class TestGenerateErrorAlert:
    """Test TelegramReports.generate_error_alert."""

    def setup_method(self) -> None:
        """Create a TelegramReports instance for each test."""
        self.reports = TelegramReports()

    def _full_error_data(self) -> dict:
        """Return a complete error data dictionary for reuse.

        Returns:
            Dict with all supported error_data keys populated.
        """
        return {
            "error_type": "MCPTimeoutError",
            "message": "Connection timeout after 30s",
            "file": "client.py",
            "line": 142,
            "attempt": 2,
            "max_attempts": 3,
            "action": "retry",
            "context": "Calling Task_ListIssues",
        }

    def test_full_alert_header(self) -> None:
        """Full alert starts with the error header."""
        result = self.reports.generate_error_alert(self._full_error_data())
        assert "<b>Ошибка</b>" in result

    def test_full_alert_error_type(self) -> None:
        """Error type is shown."""
        result = self.reports.generate_error_alert(self._full_error_data())
        assert "<b>Тип:</b> MCPTimeoutError" in result

    def test_full_alert_message(self) -> None:
        """Error message is shown."""
        result = self.reports.generate_error_alert(self._full_error_data())
        assert "<b>Сообщение:</b> Connection timeout after 30s" in result

    def test_full_alert_location_with_line(self) -> None:
        """Location shows file:line format."""
        result = self.reports.generate_error_alert(self._full_error_data())
        assert "<b>Расположение:</b> <code>client.py:142</code>" in result

    def test_full_alert_context(self) -> None:
        """Context is shown."""
        result = self.reports.generate_error_alert(self._full_error_data())
        assert "<b>Контекст:</b> Calling Task_ListIssues" in result

    def test_full_alert_attempt(self) -> None:
        """Attempt counter shows current/max."""
        result = self.reports.generate_error_alert(self._full_error_data())
        assert "<b>Попытка:</b> 2/3" in result

    def test_full_alert_action_retry(self) -> None:
        """Retry action shows correct icon and label."""
        result = self.reports.generate_error_alert(self._full_error_data())
        assert "<b>Действие:</b>" in result
        assert "Повтор" in result

    def test_action_fallback(self) -> None:
        """Fallback action shows correct icon and label."""
        data = self._full_error_data()
        data["action"] = "fallback"
        result = self.reports.generate_error_alert(data)
        assert "Откат" in result

    def test_action_escalate(self) -> None:
        """Escalate action shows correct icon and label."""
        data = self._full_error_data()
        data["action"] = "escalate"
        result = self.reports.generate_error_alert(data)
        assert "Эскалация" in result

    def test_action_case_insensitive(self) -> None:
        """Action matching is case-insensitive."""
        data = self._full_error_data()
        data["action"] = "RETRY"
        result = self.reports.generate_error_alert(data)
        assert "Повтор" in result

    def test_unknown_action_omitted(self) -> None:
        """Unknown action value does not produce an action line."""
        data = self._full_error_data()
        data["action"] = "unknown_action"
        result = self.reports.generate_error_alert(data)
        assert "Действие" not in result

    def test_no_file_no_location_section(self) -> None:
        """Location section omitted when file is empty."""
        data = {
            "error_type": "ValueError",
            "message": "Invalid input",
            "attempt": 1,
            "max_attempts": 3,
            "action": "retry",
        }
        result = self.reports.generate_error_alert(data)
        assert "Расположение" not in result

    def test_file_without_line(self) -> None:
        """Location shown without line number when line is 0."""
        data = {
            "error_type": "ImportError",
            "message": "Module not found",
            "file": "agent.py",
            "line": 0,
        }
        result = self.reports.generate_error_alert(data)
        assert "<b>Расположение:</b> <code>agent.py</code>" in result
        # No "agent.py:NNN" pattern -- just plain "agent.py"
        assert "agent.py:" not in result

    def test_empty_error_data(self) -> None:
        """Empty dict produces only the header without crashing."""
        result = self.reports.generate_error_alert({})
        assert "<b>Ошибка</b>" in result
        assert "Тип" not in result
        assert "Сообщение" not in result
        assert "Расположение" not in result
        assert "Попытка" not in result
        assert "Действие" not in result

    def test_none_values_treated_as_defaults(self) -> None:
        """None values for optional fields default safely."""
        data = {
            "error_type": None,
            "message": None,
            "file": None,
            "line": None,
            "attempt": None,
            "max_attempts": None,
            "action": None,
            "context": None,
        }
        result = self.reports.generate_error_alert(data)
        assert "<b>Ошибка</b>" in result

    def test_no_attempt_section_when_zero(self) -> None:
        """Attempt section omitted when attempt or max_attempts is 0."""
        data = {
            "error_type": "RuntimeError",
            "message": "Something broke",
            "attempt": 0,
            "max_attempts": 0,
        }
        result = self.reports.generate_error_alert(data)
        assert "Попытка" not in result

    def test_context_omitted_when_empty(self) -> None:
        """Context section omitted when context is empty string."""
        data = {
            "error_type": "ValueError",
            "message": "Bad value",
            "context": "",
        }
        result = self.reports.generate_error_alert(data)
        assert "Контекст" not in result


# ---------------------------------------------------------------------------
# Error alert: XSS protection (ENG-87)
# ---------------------------------------------------------------------------


class TestErrorAlertXssProtection:
    """Test that user-supplied data in error alerts is HTML-escaped."""

    def setup_method(self) -> None:
        """Create a TelegramReports instance for each test."""
        self.reports = TelegramReports()

    def test_xss_in_error_type(self) -> None:
        """HTML in error_type is escaped."""
        data = {"error_type": "<script>alert(1)</script>"}
        result = self.reports.generate_error_alert(data)
        assert "<script>" not in result
        assert "&lt;script&gt;" in result

    def test_xss_in_message(self) -> None:
        """HTML in message is escaped."""
        data = {
            "error_type": "Error",
            "message": '<img src=x onerror="alert(1)">',
        }
        result = self.reports.generate_error_alert(data)
        assert "<img" not in result
        assert "&lt;img" in result

    def test_xss_in_file(self) -> None:
        """HTML in file path is escaped."""
        data = {
            "error_type": "Error",
            "file": '<script>alert("xss")</script>',
            "line": 1,
        }
        result = self.reports.generate_error_alert(data)
        assert "<script>" not in result
        assert "&lt;script&gt;" in result

    def test_xss_in_context(self) -> None:
        """HTML in context is escaped."""
        data = {
            "error_type": "Error",
            "context": "<b>evil</b> injection",
        }
        result = self.reports.generate_error_alert(data)
        # The literal <b>evil</b> should be escaped, not rendered as bold
        assert "&lt;b&gt;evil&lt;/b&gt;" in result

    def test_ampersand_in_message(self) -> None:
        """Ampersands in message are properly escaped."""
        data = {
            "error_type": "Error",
            "message": "x < y && z > w",
        }
        result = self.reports.generate_error_alert(data)
        assert "&amp;&amp;" in result
        assert "&lt;" in result
        assert "&gt;" in result

    def test_only_allowed_tags_in_error_alert(self) -> None:
        """Error alert uses only Telegram-allowed HTML tags."""
        data = {
            "error_type": "MCPTimeoutError",
            "message": "Connection timeout",
            "file": "client.py",
            "line": 142,
            "attempt": 2,
            "max_attempts": 3,
            "action": "retry",
            "context": "Calling MCP",
        }
        result = self.reports.generate_error_alert(data)
        used_tags = _extract_tags(result)
        assert used_tags.issubset(ALLOWED_TAGS), (
            f"Found disallowed tags: {used_tags - ALLOWED_TAGS}"
        )

    def test_tags_properly_closed_in_error_alert(self) -> None:
        """Every opening tag in error alert has a matching close."""
        data = {
            "error_type": "MCPTimeoutError",
            "message": "Connection timeout",
            "file": "client.py",
            "line": 142,
            "attempt": 2,
            "max_attempts": 3,
            "action": "retry",
            "context": "Calling MCP",
        }
        result = self.reports.generate_error_alert(data)

        for tag in _extract_tags(result):
            open_count = result.count(f"<{tag}>") + result.count(f"<{tag} ")
            close_count = result.count(f"</{tag}>")
            assert open_count == close_count, (
                f"Tag <{tag}> opened {open_count} but closed {close_count} times"
            )
