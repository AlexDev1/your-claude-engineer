"""
Tests for GitHub Integration — Auto-PR on Done (ENG-63)
========================================================

Verifies:
1. create_auto_pr() creates PR via gh CLI on issue Done transition
2. PR title follows "[Agent] {issue title}" format
3. PR body includes issue description and session summary
4. Edge case: no commits ahead of base returns informative message
5. Edge case: PR already exists returns existing PR info
6. Edge case: gh CLI not available returns graceful failure
7. Edge case: gh pr create timeout returns failure
8. Helper: _has_commits_ahead_of_base git rev-list check
9. Helper: _check_existing_pr_via_gh returns existing PR data
10. Helper: _extract_pr_number_from_url parses PR URLs
11. Helper: _is_gh_cli_available checks gh auth status
12. AutoPRResult dataclass fields
"""

import json
import subprocess
from unittest.mock import MagicMock, patch

import pytest

from github_integration import (
    AutoPRResult,
    _check_existing_pr_via_gh,
    _extract_pr_number_from_url,
    _has_commits_ahead_of_base,
    _is_gh_cli_available,
    _sanitize_branch_name,
    create_auto_pr,
)


# ---------------------------------------------------------------------------
# AutoPRResult dataclass
# ---------------------------------------------------------------------------


class TestAutoPRResult:
    """Test AutoPRResult dataclass fields."""

    def test_success_result(self) -> None:
        """Successful result stores PR URL and number."""
        result = AutoPRResult(
            success=True,
            pr_url="https://github.com/org/repo/pull/42",
            pr_number=42,
            message="Created PR for ENG-63",
        )
        assert result.success is True
        assert result.pr_url == "https://github.com/org/repo/pull/42"
        assert result.pr_number == 42
        assert "ENG-63" in result.message

    def test_failure_result(self) -> None:
        """Failure result has no PR URL or number."""
        result = AutoPRResult(
            success=False,
            pr_url=None,
            pr_number=None,
            message="gh CLI not available",
        )
        assert result.success is False
        assert result.pr_url is None
        assert result.pr_number is None


# ---------------------------------------------------------------------------
# _extract_pr_number_from_url
# ---------------------------------------------------------------------------


class TestExtractPRNumberFromUrl:
    """Test PR number extraction from GitHub URLs."""

    def test_standard_url(self) -> None:
        """Extracts number from standard GitHub PR URL."""
        url = "https://github.com/AxonCode/your-claude-engineer/pull/42"
        assert _extract_pr_number_from_url(url) == 42

    def test_url_with_trailing_content(self) -> None:
        """Handles URLs with extra path segments."""
        url = "https://github.com/org/repo/pull/123/files"
        assert _extract_pr_number_from_url(url) == 123

    def test_non_pr_url_returns_none(self) -> None:
        """Returns None for non-PR URLs."""
        url = "https://github.com/org/repo/issues/5"
        assert _extract_pr_number_from_url(url) is None

    def test_empty_string_returns_none(self) -> None:
        """Returns None for empty string."""
        assert _extract_pr_number_from_url("") is None

    def test_large_pr_number(self) -> None:
        """Handles large PR numbers."""
        url = "https://github.com/org/repo/pull/99999"
        assert _extract_pr_number_from_url(url) == 99999


# ---------------------------------------------------------------------------
# _has_commits_ahead_of_base
# ---------------------------------------------------------------------------


class TestHasCommitsAheadOfBase:
    """Test git rev-list commit count check."""

    def test_commits_ahead(self) -> None:
        """Returns True when branch has commits ahead of base."""
        mock_result = MagicMock(stdout="3\n")
        with patch("github_integration.subprocess.run", return_value=mock_result):
            assert _has_commits_ahead_of_base("agent/eng-63", "main") is True

    def test_no_commits_ahead(self) -> None:
        """Returns False when branch has zero commits ahead."""
        mock_result = MagicMock(stdout="0\n")
        with patch("github_integration.subprocess.run", return_value=mock_result):
            assert _has_commits_ahead_of_base("agent/eng-63", "main") is False

    def test_git_error_returns_false(self) -> None:
        """Returns False when git command fails."""
        with patch(
            "github_integration.subprocess.run",
            side_effect=subprocess.CalledProcessError(128, "git"),
        ):
            assert _has_commits_ahead_of_base("agent/eng-63", "main") is False

    def test_invalid_output_returns_false(self) -> None:
        """Returns False when git output cannot be parsed as int."""
        mock_result = MagicMock(stdout="not-a-number\n")
        with patch("github_integration.subprocess.run", return_value=mock_result):
            assert _has_commits_ahead_of_base("agent/eng-63", "main") is False

    def test_passes_correct_git_args(self) -> None:
        """Passes correct branch range to git rev-list."""
        mock_result = MagicMock(stdout="1\n")
        with patch("github_integration.subprocess.run", return_value=mock_result) as mock_run:
            _has_commits_ahead_of_base("agent/eng-63", "develop")

        mock_run.assert_called_once_with(
            ["git", "rev-list", "--count", "develop..agent/eng-63"],
            capture_output=True,
            text=True,
            check=True,
        )


# ---------------------------------------------------------------------------
# _check_existing_pr_via_gh
# ---------------------------------------------------------------------------


class TestCheckExistingPRViaGH:
    """Test checking for existing PRs via gh CLI."""

    def test_pr_exists(self) -> None:
        """Returns PR info when gh pr view succeeds."""
        pr_data = json.dumps({"number": 42, "url": "https://github.com/org/repo/pull/42"})
        mock_result = MagicMock(returncode=0, stdout=pr_data)
        with patch("github_integration.subprocess.run", return_value=mock_result):
            result = _check_existing_pr_via_gh("agent/eng-63")

        assert result is not None
        assert result["number"] == 42
        assert result["url"] == "https://github.com/org/repo/pull/42"

    def test_no_pr_exists(self) -> None:
        """Returns None when no PR exists for the branch."""
        mock_result = MagicMock(returncode=1, stdout="", stderr="no pull requests found")
        with patch("github_integration.subprocess.run", return_value=mock_result):
            result = _check_existing_pr_via_gh("agent/eng-99")

        assert result is None

    def test_gh_not_installed(self) -> None:
        """Returns None when gh CLI is not installed."""
        with patch(
            "github_integration.subprocess.run",
            side_effect=FileNotFoundError("gh not found"),
        ):
            result = _check_existing_pr_via_gh("agent/eng-63")

        assert result is None

    def test_invalid_json_returns_none(self) -> None:
        """Returns None when gh output is invalid JSON."""
        mock_result = MagicMock(returncode=0, stdout="not json")
        with patch("github_integration.subprocess.run", return_value=mock_result):
            result = _check_existing_pr_via_gh("agent/eng-63")

        assert result is None


# ---------------------------------------------------------------------------
# _is_gh_cli_available
# ---------------------------------------------------------------------------


class TestIsGHCLIAvailable:
    """Test gh CLI availability check."""

    def test_gh_available_and_authenticated(self) -> None:
        """Returns True when gh auth status succeeds."""
        mock_result = MagicMock(returncode=0)
        with patch("github_integration.subprocess.run", return_value=mock_result):
            assert _is_gh_cli_available() is True

    def test_gh_not_authenticated(self) -> None:
        """Returns False when gh auth status fails."""
        mock_result = MagicMock(returncode=1)
        with patch("github_integration.subprocess.run", return_value=mock_result):
            assert _is_gh_cli_available() is False

    def test_gh_not_installed(self) -> None:
        """Returns False when gh CLI is not on PATH."""
        with patch(
            "github_integration.subprocess.run",
            side_effect=FileNotFoundError("gh not found"),
        ):
            assert _is_gh_cli_available() is False


# ---------------------------------------------------------------------------
# create_auto_pr — main function
# ---------------------------------------------------------------------------


class TestCreateAutoPR:
    """Test the main create_auto_pr function."""

    @pytest.fixture
    def issue_params(self) -> dict[str, str]:
        """Common issue parameters for test cases."""
        return {
            "issue_id": "ENG-63",
            "issue_title": "Auto-PR creation on Done",
            "issue_description": "Create automatic PR when issue transitions to Done.",
        }

    def test_gh_cli_not_available(self, issue_params: dict[str, str]) -> None:
        """Returns failure when gh CLI is not available."""
        with patch("github_integration._is_gh_cli_available", return_value=False):
            result = create_auto_pr(**issue_params)

        assert result.success is False
        assert "gh CLI not available" in result.message

    def test_pr_already_exists(self, issue_params: dict[str, str]) -> None:
        """Returns existing PR info when PR already exists."""
        existing = {"url": "https://github.com/org/repo/pull/10", "number": 10}
        with (
            patch("github_integration._is_gh_cli_available", return_value=True),
            patch("github_integration._check_existing_pr_via_gh", return_value=existing),
        ):
            result = create_auto_pr(**issue_params)

        assert result.success is True
        assert result.pr_url == "https://github.com/org/repo/pull/10"
        assert result.pr_number == 10
        assert "already exists" in result.message

    def test_no_commits_ahead(self, issue_params: dict[str, str]) -> None:
        """Returns failure when branch has no new commits."""
        with (
            patch("github_integration._is_gh_cli_available", return_value=True),
            patch("github_integration._check_existing_pr_via_gh", return_value=None),
            patch("github_integration._has_commits_ahead_of_base", return_value=False),
        ):
            result = create_auto_pr(**issue_params)

        assert result.success is False
        assert "No commits ahead" in result.message

    def test_successful_pr_creation(self, issue_params: dict[str, str]) -> None:
        """Creates PR successfully via gh CLI."""
        pr_url = "https://github.com/AxonCode/your-claude-engineer/pull/7"
        mock_run_result = MagicMock(returncode=0, stdout=f"{pr_url}\n")

        with (
            patch("github_integration._is_gh_cli_available", return_value=True),
            patch("github_integration._check_existing_pr_via_gh", return_value=None),
            patch("github_integration._has_commits_ahead_of_base", return_value=True),
            patch("github_integration.subprocess.run", return_value=mock_run_result) as mock_run,
        ):
            result = create_auto_pr(**issue_params)

        assert result.success is True
        assert result.pr_url == pr_url
        assert result.pr_number == 7
        assert "Created PR" in result.message

        # Verify gh CLI was called with correct arguments
        call_args = mock_run.call_args[0][0]
        assert call_args[0] == "gh"
        assert call_args[1] == "pr"
        assert call_args[2] == "create"
        assert "--title" in call_args
        title_idx = call_args.index("--title") + 1
        assert call_args[title_idx] == "[Agent] Auto-PR creation on Done"

    def test_pr_title_format(self, issue_params: dict[str, str]) -> None:
        """PR title follows [Agent] {issue title} format."""
        mock_run_result = MagicMock(
            returncode=0,
            stdout="https://github.com/org/repo/pull/1\n",
        )

        with (
            patch("github_integration._is_gh_cli_available", return_value=True),
            patch("github_integration._check_existing_pr_via_gh", return_value=None),
            patch("github_integration._has_commits_ahead_of_base", return_value=True),
            patch("github_integration.subprocess.run", return_value=mock_run_result) as mock_run,
        ):
            create_auto_pr(**issue_params)

        call_args = mock_run.call_args[0][0]
        title_idx = call_args.index("--title") + 1
        assert call_args[title_idx] == "[Agent] Auto-PR creation on Done"

    def test_pr_body_includes_issue_description(self, issue_params: dict[str, str]) -> None:
        """PR body includes the issue description."""
        mock_run_result = MagicMock(
            returncode=0,
            stdout="https://github.com/org/repo/pull/1\n",
        )

        with (
            patch("github_integration._is_gh_cli_available", return_value=True),
            patch("github_integration._check_existing_pr_via_gh", return_value=None),
            patch("github_integration._has_commits_ahead_of_base", return_value=True),
            patch("github_integration.subprocess.run", return_value=mock_run_result) as mock_run,
        ):
            create_auto_pr(**issue_params)

        call_args = mock_run.call_args[0][0]
        body_idx = call_args.index("--body") + 1
        body = call_args[body_idx]
        assert "ENG-63" in body
        assert "Create automatic PR when issue transitions to Done." in body

    def test_pr_body_includes_session_summary(self, issue_params: dict[str, str]) -> None:
        """PR body includes session summary when provided."""
        mock_run_result = MagicMock(
            returncode=0,
            stdout="https://github.com/org/repo/pull/1\n",
        )

        with (
            patch("github_integration._is_gh_cli_available", return_value=True),
            patch("github_integration._check_existing_pr_via_gh", return_value=None),
            patch("github_integration._has_commits_ahead_of_base", return_value=True),
            patch("github_integration.subprocess.run", return_value=mock_run_result) as mock_run,
        ):
            create_auto_pr(
                **issue_params,
                session_summary="Implemented auto-PR with gh CLI.",
            )

        call_args = mock_run.call_args[0][0]
        body_idx = call_args.index("--body") + 1
        body = call_args[body_idx]
        assert "Implemented auto-PR with gh CLI." in body

    def test_pr_body_no_session_summary_placeholder(self, issue_params: dict[str, str]) -> None:
        """PR body shows placeholder when no session summary."""
        mock_run_result = MagicMock(
            returncode=0,
            stdout="https://github.com/org/repo/pull/1\n",
        )

        with (
            patch("github_integration._is_gh_cli_available", return_value=True),
            patch("github_integration._check_existing_pr_via_gh", return_value=None),
            patch("github_integration._has_commits_ahead_of_base", return_value=True),
            patch("github_integration.subprocess.run", return_value=mock_run_result) as mock_run,
        ):
            create_auto_pr(**issue_params)

        call_args = mock_run.call_args[0][0]
        body_idx = call_args.index("--body") + 1
        body = call_args[body_idx]
        assert "_No session summary provided._" in body

    def test_gh_create_failure(self, issue_params: dict[str, str]) -> None:
        """Returns failure when gh pr create exits with error."""
        mock_run_result = MagicMock(
            returncode=1,
            stdout="",
            stderr="pull request create failed: GraphQL error",
        )

        with (
            patch("github_integration._is_gh_cli_available", return_value=True),
            patch("github_integration._check_existing_pr_via_gh", return_value=None),
            patch("github_integration._has_commits_ahead_of_base", return_value=True),
            patch("github_integration.subprocess.run", return_value=mock_run_result),
        ):
            result = create_auto_pr(**issue_params)

        assert result.success is False
        assert "gh pr create failed" in result.message

    def test_gh_create_timeout(self, issue_params: dict[str, str]) -> None:
        """Returns failure when gh pr create times out."""
        with (
            patch("github_integration._is_gh_cli_available", return_value=True),
            patch("github_integration._check_existing_pr_via_gh", return_value=None),
            patch("github_integration._has_commits_ahead_of_base", return_value=True),
            patch(
                "github_integration.subprocess.run",
                side_effect=subprocess.TimeoutExpired("gh", 60),
            ),
        ):
            result = create_auto_pr(**issue_params)

        assert result.success is False
        assert "timed out" in result.message

    def test_gh_not_found_during_create(self, issue_params: dict[str, str]) -> None:
        """Returns failure when gh binary disappears during creation."""
        with (
            patch("github_integration._is_gh_cli_available", return_value=True),
            patch("github_integration._check_existing_pr_via_gh", return_value=None),
            patch("github_integration._has_commits_ahead_of_base", return_value=True),
            patch(
                "github_integration.subprocess.run",
                side_effect=FileNotFoundError("gh not found"),
            ),
        ):
            result = create_auto_pr(**issue_params)

        assert result.success is False
        assert "gh CLI not found" in result.message

    def test_labels_passed_to_gh_cli(self, issue_params: dict[str, str]) -> None:
        """Labels 'agent,automated' are passed to gh pr create."""
        mock_run_result = MagicMock(
            returncode=0,
            stdout="https://github.com/org/repo/pull/5\n",
        )

        with (
            patch("github_integration._is_gh_cli_available", return_value=True),
            patch("github_integration._check_existing_pr_via_gh", return_value=None),
            patch("github_integration._has_commits_ahead_of_base", return_value=True),
            patch("github_integration.subprocess.run", return_value=mock_run_result) as mock_run,
        ):
            create_auto_pr(**issue_params)

        call_args = mock_run.call_args[0][0]
        label_idx = call_args.index("--label") + 1
        assert call_args[label_idx] == "agent,automated"

    def test_already_exists_error_falls_back_to_existing(
        self, issue_params: dict[str, str]
    ) -> None:
        """When gh reports 'already exists', finds and returns existing PR."""
        mock_create = MagicMock(
            returncode=1,
            stdout="",
            stderr="a pull request for branch already exists",
        )
        existing = {"url": "https://github.com/org/repo/pull/20", "number": 20}

        call_count = 0

        def _mock_check(branch: str) -> dict[str, str | int] | None:
            nonlocal call_count
            call_count += 1
            # First call (pre-create check) returns None, second returns existing
            if call_count <= 1:
                return None
            return existing

        with (
            patch("github_integration._is_gh_cli_available", return_value=True),
            patch("github_integration._check_existing_pr_via_gh", side_effect=_mock_check),
            patch("github_integration._has_commits_ahead_of_base", return_value=True),
            patch("github_integration.subprocess.run", return_value=mock_create),
        ):
            result = create_auto_pr(**issue_params)

        assert result.success is True
        assert result.pr_number == 20

    def test_branch_name_sanitization(self, issue_params: dict[str, str]) -> None:
        """Branch name is correctly sanitized from issue ID."""
        mock_run_result = MagicMock(
            returncode=0,
            stdout="https://github.com/org/repo/pull/1\n",
        )

        with (
            patch("github_integration._is_gh_cli_available", return_value=True),
            patch("github_integration._check_existing_pr_via_gh", return_value=None),
            patch("github_integration._has_commits_ahead_of_base", return_value=True),
            patch("github_integration.subprocess.run", return_value=mock_run_result) as mock_run,
        ):
            create_auto_pr(
                issue_id="ENG-63",
                issue_title="Test",
                issue_description="desc",
            )

        call_args = mock_run.call_args[0][0]
        head_idx = call_args.index("--head") + 1
        assert call_args[head_idx] == "agent/eng-63"

    def test_custom_base_branch(self, issue_params: dict[str, str]) -> None:
        """Respects custom base branch parameter."""
        mock_run_result = MagicMock(
            returncode=0,
            stdout="https://github.com/org/repo/pull/1\n",
        )

        with (
            patch("github_integration._is_gh_cli_available", return_value=True),
            patch(
                "github_integration._check_existing_pr_via_gh", return_value=None
            ),
            patch(
                "github_integration._has_commits_ahead_of_base", return_value=True
            ),
            patch("github_integration.subprocess.run", return_value=mock_run_result) as mock_run,
        ):
            create_auto_pr(**issue_params, base_branch="develop")

        call_args = mock_run.call_args[0][0]
        base_idx = call_args.index("--base") + 1
        assert call_args[base_idx] == "develop"


# ---------------------------------------------------------------------------
# _sanitize_branch_name (already exists, verify it works)
# ---------------------------------------------------------------------------


class TestSanitizeBranchName:
    """Test branch name sanitization helper."""

    def test_basic_issue_id(self) -> None:
        """Converts standard issue ID to lowercase."""
        assert _sanitize_branch_name("ENG-63") == "eng-63"

    def test_spaces_replaced(self) -> None:
        """Spaces are replaced with dashes."""
        assert _sanitize_branch_name("some feature") == "some-feature"

    def test_special_chars_removed(self) -> None:
        """Special characters are replaced with dashes."""
        assert _sanitize_branch_name("fix/bug#123") == "fix-bug-123"

    def test_consecutive_dashes_collapsed(self) -> None:
        """Multiple consecutive dashes are collapsed to one."""
        assert _sanitize_branch_name("a--b---c") == "a-b-c"

    def test_leading_trailing_dashes_stripped(self) -> None:
        """Leading and trailing dashes are removed."""
        assert _sanitize_branch_name("-abc-") == "abc"
