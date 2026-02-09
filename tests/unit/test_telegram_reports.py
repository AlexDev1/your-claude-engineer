"""
Tests for TelegramReports daily digest (ENG-85)
=================================================

Verifies:
1. Daily digest generation with all fields
2. Progress bar at 0%, 50%, 100%, and edge cases
3. HTML formatting uses only Telegram-supported tags
4. Completed-today list with dict and string items
5. Empty / missing fields handled gracefully
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
