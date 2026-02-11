"""
Tests for GitHub Integration — Auto-PR (ENG-63) + Issues Sync (ENG-64) + Status Checks (ENG-65)
================================================================================================

ENG-63 (Auto-PR) verifies:
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

ENG-64 (Issues Sync) verifies:
13. sync_issue_to_github() creates/updates GitHub Issues from Task MCP
14. sync_issue_from_github() reads GitHub Issue state for Task MCP
15. create_github_issue() creates via gh CLI
16. update_github_issue() updates title/body/state/labels via gh CLI
17. State mapping: Task MCP <-> GitHub (Todo, In Progress, Done, Canceled)
18. Sync marker: "[Task MCP: ENG-XX]" embedded in issue body
19. Conflict resolution: Task MCP is source of truth
20. SyncResult and GitHubIssueResult dataclass fields

ENG-65 (Status Checks) verifies:
21. set_commit_status() sets commit status via gh api
22. report_test_status() reports "agent/tests" check
23. report_quality_status() reports "agent/quality-gates" check
24. report_verification_status() reports "agent/verification" check
25. report_all_statuses() sets all three checks at once
26. Edge cases: gh CLI unavailable, repo detection failure, API errors, timeouts
27. Description truncation to 140 chars
28. target_url passed correctly when provided
"""

import json
import subprocess
from unittest.mock import MagicMock, patch

import pytest

from axon_agent.integrations.github import (
    AutoPRResult,
    GitHubIssueResult,
    StatusCheckResult,
    SyncResult,
    STATUS_CONTEXT_QUALITY,
    STATUS_CONTEXT_TESTS,
    STATUS_CONTEXT_VERIFICATION,
    _build_sync_marker,
    _check_existing_pr_via_gh,
    _extract_issue_id_from_body,
    _extract_issue_number_from_url,
    _extract_pr_number_from_url,
    _get_repo_nwo,
    _has_commits_ahead_of_base,
    _is_gh_cli_available,
    _map_github_state_to_task,
    _map_task_state_to_github,
    _sanitize_branch_name,
    create_auto_pr,
    create_github_issue,
    report_all_statuses,
    report_quality_status,
    report_test_status,
    report_verification_status,
    set_commit_status,
    sync_issue_from_github,
    sync_issue_to_github,
    update_github_issue,
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
        with patch("axon_agent.integrations.github.subprocess.run", return_value=mock_result):
            assert _has_commits_ahead_of_base("agent/eng-63", "main") is True

    def test_no_commits_ahead(self) -> None:
        """Returns False when branch has zero commits ahead."""
        mock_result = MagicMock(stdout="0\n")
        with patch("axon_agent.integrations.github.subprocess.run", return_value=mock_result):
            assert _has_commits_ahead_of_base("agent/eng-63", "main") is False

    def test_git_error_returns_false(self) -> None:
        """Returns False when git command fails."""
        with patch(
            "axon_agent.integrations.github.subprocess.run",
            side_effect=subprocess.CalledProcessError(128, "git"),
        ):
            assert _has_commits_ahead_of_base("agent/eng-63", "main") is False

    def test_invalid_output_returns_false(self) -> None:
        """Returns False when git output cannot be parsed as int."""
        mock_result = MagicMock(stdout="not-a-number\n")
        with patch("axon_agent.integrations.github.subprocess.run", return_value=mock_result):
            assert _has_commits_ahead_of_base("agent/eng-63", "main") is False

    def test_passes_correct_git_args(self) -> None:
        """Passes correct branch range to git rev-list."""
        mock_result = MagicMock(stdout="1\n")
        with patch("axon_agent.integrations.github.subprocess.run", return_value=mock_result) as mock_run:
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
        with patch("axon_agent.integrations.github.subprocess.run", return_value=mock_result):
            result = _check_existing_pr_via_gh("agent/eng-63")

        assert result is not None
        assert result["number"] == 42
        assert result["url"] == "https://github.com/org/repo/pull/42"

    def test_no_pr_exists(self) -> None:
        """Returns None when no PR exists for the branch."""
        mock_result = MagicMock(returncode=1, stdout="", stderr="no pull requests found")
        with patch("axon_agent.integrations.github.subprocess.run", return_value=mock_result):
            result = _check_existing_pr_via_gh("agent/eng-99")

        assert result is None

    def test_gh_not_installed(self) -> None:
        """Returns None when gh CLI is not installed."""
        with patch(
            "axon_agent.integrations.github.subprocess.run",
            side_effect=FileNotFoundError("gh not found"),
        ):
            result = _check_existing_pr_via_gh("agent/eng-63")

        assert result is None

    def test_invalid_json_returns_none(self) -> None:
        """Returns None when gh output is invalid JSON."""
        mock_result = MagicMock(returncode=0, stdout="not json")
        with patch("axon_agent.integrations.github.subprocess.run", return_value=mock_result):
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
        with patch("axon_agent.integrations.github.subprocess.run", return_value=mock_result):
            assert _is_gh_cli_available() is True

    def test_gh_not_authenticated(self) -> None:
        """Returns False when gh auth status fails."""
        mock_result = MagicMock(returncode=1)
        with patch("axon_agent.integrations.github.subprocess.run", return_value=mock_result):
            assert _is_gh_cli_available() is False

    def test_gh_not_installed(self) -> None:
        """Returns False when gh CLI is not on PATH."""
        with patch(
            "axon_agent.integrations.github.subprocess.run",
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
        with patch("axon_agent.integrations.github._is_gh_cli_available", return_value=False):
            result = create_auto_pr(**issue_params)

        assert result.success is False
        assert "gh CLI not available" in result.message

    def test_pr_already_exists(self, issue_params: dict[str, str]) -> None:
        """Returns existing PR info when PR already exists."""
        existing = {"url": "https://github.com/org/repo/pull/10", "number": 10}
        with (
            patch("axon_agent.integrations.github._is_gh_cli_available", return_value=True),
            patch("axon_agent.integrations.github._check_existing_pr_via_gh", return_value=existing),
        ):
            result = create_auto_pr(**issue_params)

        assert result.success is True
        assert result.pr_url == "https://github.com/org/repo/pull/10"
        assert result.pr_number == 10
        assert "already exists" in result.message

    def test_no_commits_ahead(self, issue_params: dict[str, str]) -> None:
        """Returns failure when branch has no new commits."""
        with (
            patch("axon_agent.integrations.github._is_gh_cli_available", return_value=True),
            patch("axon_agent.integrations.github._check_existing_pr_via_gh", return_value=None),
            patch("axon_agent.integrations.github._has_commits_ahead_of_base", return_value=False),
        ):
            result = create_auto_pr(**issue_params)

        assert result.success is False
        assert "No commits ahead" in result.message

    def test_successful_pr_creation(self, issue_params: dict[str, str]) -> None:
        """Creates PR successfully via gh CLI."""
        pr_url = "https://github.com/AxonCode/your-claude-engineer/pull/7"
        mock_run_result = MagicMock(returncode=0, stdout=f"{pr_url}\n")

        with (
            patch("axon_agent.integrations.github._is_gh_cli_available", return_value=True),
            patch("axon_agent.integrations.github._check_existing_pr_via_gh", return_value=None),
            patch("axon_agent.integrations.github._has_commits_ahead_of_base", return_value=True),
            patch("axon_agent.integrations.github.subprocess.run", return_value=mock_run_result) as mock_run,
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
            patch("axon_agent.integrations.github._is_gh_cli_available", return_value=True),
            patch("axon_agent.integrations.github._check_existing_pr_via_gh", return_value=None),
            patch("axon_agent.integrations.github._has_commits_ahead_of_base", return_value=True),
            patch("axon_agent.integrations.github.subprocess.run", return_value=mock_run_result) as mock_run,
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
            patch("axon_agent.integrations.github._is_gh_cli_available", return_value=True),
            patch("axon_agent.integrations.github._check_existing_pr_via_gh", return_value=None),
            patch("axon_agent.integrations.github._has_commits_ahead_of_base", return_value=True),
            patch("axon_agent.integrations.github.subprocess.run", return_value=mock_run_result) as mock_run,
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
            patch("axon_agent.integrations.github._is_gh_cli_available", return_value=True),
            patch("axon_agent.integrations.github._check_existing_pr_via_gh", return_value=None),
            patch("axon_agent.integrations.github._has_commits_ahead_of_base", return_value=True),
            patch("axon_agent.integrations.github.subprocess.run", return_value=mock_run_result) as mock_run,
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
            patch("axon_agent.integrations.github._is_gh_cli_available", return_value=True),
            patch("axon_agent.integrations.github._check_existing_pr_via_gh", return_value=None),
            patch("axon_agent.integrations.github._has_commits_ahead_of_base", return_value=True),
            patch("axon_agent.integrations.github.subprocess.run", return_value=mock_run_result) as mock_run,
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
            patch("axon_agent.integrations.github._is_gh_cli_available", return_value=True),
            patch("axon_agent.integrations.github._check_existing_pr_via_gh", return_value=None),
            patch("axon_agent.integrations.github._has_commits_ahead_of_base", return_value=True),
            patch("axon_agent.integrations.github.subprocess.run", return_value=mock_run_result),
        ):
            result = create_auto_pr(**issue_params)

        assert result.success is False
        assert "gh pr create failed" in result.message

    def test_gh_create_timeout(self, issue_params: dict[str, str]) -> None:
        """Returns failure when gh pr create times out."""
        with (
            patch("axon_agent.integrations.github._is_gh_cli_available", return_value=True),
            patch("axon_agent.integrations.github._check_existing_pr_via_gh", return_value=None),
            patch("axon_agent.integrations.github._has_commits_ahead_of_base", return_value=True),
            patch(
                "axon_agent.integrations.github.subprocess.run",
                side_effect=subprocess.TimeoutExpired("gh", 60),
            ),
        ):
            result = create_auto_pr(**issue_params)

        assert result.success is False
        assert "timed out" in result.message

    def test_gh_not_found_during_create(self, issue_params: dict[str, str]) -> None:
        """Returns failure when gh binary disappears during creation."""
        with (
            patch("axon_agent.integrations.github._is_gh_cli_available", return_value=True),
            patch("axon_agent.integrations.github._check_existing_pr_via_gh", return_value=None),
            patch("axon_agent.integrations.github._has_commits_ahead_of_base", return_value=True),
            patch(
                "axon_agent.integrations.github.subprocess.run",
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
            patch("axon_agent.integrations.github._is_gh_cli_available", return_value=True),
            patch("axon_agent.integrations.github._check_existing_pr_via_gh", return_value=None),
            patch("axon_agent.integrations.github._has_commits_ahead_of_base", return_value=True),
            patch("axon_agent.integrations.github.subprocess.run", return_value=mock_run_result) as mock_run,
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
            patch("axon_agent.integrations.github._is_gh_cli_available", return_value=True),
            patch("axon_agent.integrations.github._check_existing_pr_via_gh", side_effect=_mock_check),
            patch("axon_agent.integrations.github._has_commits_ahead_of_base", return_value=True),
            patch("axon_agent.integrations.github.subprocess.run", return_value=mock_create),
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
            patch("axon_agent.integrations.github._is_gh_cli_available", return_value=True),
            patch("axon_agent.integrations.github._check_existing_pr_via_gh", return_value=None),
            patch("axon_agent.integrations.github._has_commits_ahead_of_base", return_value=True),
            patch("axon_agent.integrations.github.subprocess.run", return_value=mock_run_result) as mock_run,
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
            patch("axon_agent.integrations.github._is_gh_cli_available", return_value=True),
            patch(
                "axon_agent.integrations.github._check_existing_pr_via_gh", return_value=None
            ),
            patch(
                "axon_agent.integrations.github._has_commits_ahead_of_base", return_value=True
            ),
            patch("axon_agent.integrations.github.subprocess.run", return_value=mock_run_result) as mock_run,
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


# ===========================================================================
# ENG-64: GitHub Issues Sync — Bidirectional
# ===========================================================================


# ---------------------------------------------------------------------------
# SyncResult and GitHubIssueResult dataclasses
# ---------------------------------------------------------------------------


class TestSyncResult:
    """Test SyncResult dataclass fields."""

    def test_outbound_sync_result(self) -> None:
        """Outbound sync result stores GitHub issue number and direction."""
        result = SyncResult(
            success=True,
            github_issue_number=42,
            task_issue_id="ENG-64",
            action="created",
            message="Created GitHub issue #42 for ENG-64",
            direction="to_github",
        )
        assert result.success is True
        assert result.github_issue_number == 42
        assert result.task_issue_id == "ENG-64"
        assert result.action == "created"
        assert result.direction == "to_github"

    def test_inbound_sync_result(self) -> None:
        """Inbound sync result stores Task MCP issue ID and direction."""
        result = SyncResult(
            success=True,
            github_issue_number=10,
            task_issue_id="ENG-99",
            action="synced",
            message="GitHub issue #10 -> Task MCP state: Done",
            direction="from_github",
        )
        assert result.success is True
        assert result.direction == "from_github"
        assert result.task_issue_id == "ENG-99"

    def test_failure_result(self) -> None:
        """Failure result has skipped action."""
        result = SyncResult(
            success=False,
            github_issue_number=None,
            task_issue_id="ENG-64",
            action="skipped",
            message="gh CLI not available",
            direction="to_github",
        )
        assert result.success is False
        assert result.action == "skipped"


class TestGitHubIssueResult:
    """Test GitHubIssueResult dataclass fields."""

    def test_success_result(self) -> None:
        """Successful result stores issue number and URL."""
        result = GitHubIssueResult(
            success=True,
            issue_number=15,
            issue_url="https://github.com/org/repo/issues/15",
            message="Created GitHub issue #15",
        )
        assert result.success is True
        assert result.issue_number == 15
        assert result.issue_url == "https://github.com/org/repo/issues/15"

    def test_failure_result(self) -> None:
        """Failure result has no issue number or URL."""
        result = GitHubIssueResult(
            success=False,
            issue_number=None,
            issue_url=None,
            message="gh issue create failed",
        )
        assert result.success is False
        assert result.issue_number is None


# ---------------------------------------------------------------------------
# Sync marker helpers
# ---------------------------------------------------------------------------


class TestBuildSyncMarker:
    """Test sync marker construction."""

    def test_builds_marker(self) -> None:
        """Builds expected sync marker string."""
        assert _build_sync_marker("ENG-64") == "[Task MCP: ENG-64]"

    def test_preserves_case(self) -> None:
        """Preserves issue ID case."""
        assert _build_sync_marker("eng-99") == "[Task MCP: eng-99]"


class TestExtractIssueIdFromBody:
    """Test Task MCP issue ID extraction from GitHub Issue body."""

    def test_extracts_id_from_standard_body(self) -> None:
        """Extracts issue ID from body with sync marker."""
        body = "Some description\n\n---\n[Task MCP: ENG-64]"
        assert _extract_issue_id_from_body(body) == "ENG-64"

    def test_extracts_id_from_middle_of_body(self) -> None:
        """Extracts issue ID even when marker is in the middle."""
        body = "Before\n[Task MCP: ENG-99]\nAfter"
        assert _extract_issue_id_from_body(body) == "ENG-99"

    def test_returns_none_for_no_marker(self) -> None:
        """Returns None when body has no sync marker."""
        body = "Just a regular issue body"
        assert _extract_issue_id_from_body(body) is None

    def test_returns_none_for_empty_body(self) -> None:
        """Returns None for empty body."""
        assert _extract_issue_id_from_body("") is None

    def test_handles_different_team_prefix(self) -> None:
        """Handles different team prefixes like INFRA-."""
        body = "Description\n[Task MCP: INFRA-12]"
        assert _extract_issue_id_from_body(body) == "INFRA-12"


class TestExtractIssueNumberFromUrl:
    """Test GitHub Issue number extraction from URL."""

    def test_standard_url(self) -> None:
        """Extracts number from standard issue URL."""
        url = "https://github.com/org/repo/issues/42"
        assert _extract_issue_number_from_url(url) == 42

    def test_non_issue_url_returns_none(self) -> None:
        """Returns None for non-issue URLs."""
        url = "https://github.com/org/repo/pull/5"
        assert _extract_issue_number_from_url(url) is None

    def test_empty_string_returns_none(self) -> None:
        """Returns None for empty string."""
        assert _extract_issue_number_from_url("") is None


# ---------------------------------------------------------------------------
# State mapping
# ---------------------------------------------------------------------------


class TestMapTaskStateToGitHub:
    """Test Task MCP state to GitHub Issue state mapping."""

    def test_todo_maps_to_open(self) -> None:
        """Todo maps to open state with no extra labels."""
        state, labels = _map_task_state_to_github("Todo")
        assert state == "open"
        assert labels == []

    def test_in_progress_maps_to_open_with_label(self) -> None:
        """In Progress maps to open with 'in-progress' label."""
        state, labels = _map_task_state_to_github("In Progress")
        assert state == "open"
        assert "in-progress" in labels

    def test_done_maps_to_closed(self) -> None:
        """Done maps to closed state."""
        state, labels = _map_task_state_to_github("Done")
        assert state == "closed"
        assert labels == []

    def test_canceled_maps_to_closed_with_wontfix(self) -> None:
        """Canceled maps to closed with 'wontfix' label."""
        state, labels = _map_task_state_to_github("Canceled")
        assert state == "closed"
        assert "wontfix" in labels

    def test_unknown_state_defaults_to_open(self) -> None:
        """Unknown states default to open."""
        state, labels = _map_task_state_to_github("SomeUnknownState")
        assert state == "open"
        assert labels == []


class TestMapGitHubStateToTask:
    """Test GitHub Issue state to Task MCP state mapping."""

    def test_open_maps_to_todo(self) -> None:
        """Open without labels maps to Todo."""
        assert _map_github_state_to_task("open") == "Todo"

    def test_open_with_in_progress_label(self) -> None:
        """Open with 'in-progress' label maps to In Progress."""
        assert _map_github_state_to_task("open", ["in-progress"]) == "In Progress"

    def test_closed_maps_to_done(self) -> None:
        """Closed without labels maps to Done."""
        assert _map_github_state_to_task("closed") == "Done"

    def test_closed_with_wontfix_maps_to_canceled(self) -> None:
        """Closed with 'wontfix' label maps to Canceled."""
        assert _map_github_state_to_task("closed", ["wontfix"]) == "Canceled"

    def test_closed_with_other_labels_maps_to_done(self) -> None:
        """Closed with other labels (not wontfix) maps to Done."""
        assert _map_github_state_to_task("closed", ["bug", "urgent"]) == "Done"

    def test_none_labels_treated_as_empty(self) -> None:
        """None labels treated as empty list."""
        assert _map_github_state_to_task("open", None) == "Todo"


# ---------------------------------------------------------------------------
# create_github_issue
# ---------------------------------------------------------------------------


class TestCreateGitHubIssue:
    """Test GitHub Issue creation via gh CLI."""

    def test_gh_cli_not_available(self) -> None:
        """Returns failure when gh CLI is not available."""
        with patch("axon_agent.integrations.github._is_gh_cli_available", return_value=False):
            result = create_github_issue("Test", "Description")

        assert result.success is False
        assert "gh CLI not available" in result.message

    def test_successful_creation(self) -> None:
        """Creates issue and returns number and URL."""
        issue_url = "https://github.com/org/repo/issues/42"
        mock_result = MagicMock(returncode=0, stdout=f"{issue_url}\n")

        with (
            patch("axon_agent.integrations.github._is_gh_cli_available", return_value=True),
            patch("axon_agent.integrations.github._run_gh_command", return_value=mock_result),
        ):
            result = create_github_issue("Test Issue", "A description")

        assert result.success is True
        assert result.issue_number == 42
        assert result.issue_url == issue_url

    def test_creation_with_labels(self) -> None:
        """Passes labels to gh issue create."""
        issue_url = "https://github.com/org/repo/issues/5"
        mock_result = MagicMock(returncode=0, stdout=f"{issue_url}\n")

        with (
            patch("axon_agent.integrations.github._is_gh_cli_available", return_value=True),
            patch(
                "axon_agent.integrations.github._run_gh_command", return_value=mock_result
            ) as mock_cmd,
        ):
            create_github_issue("Test", "Desc", labels=["bug", "agent-synced"])

        call_args = mock_cmd.call_args[0][0]
        label_idx = call_args.index("--label") + 1
        assert call_args[label_idx] == "bug,agent-synced"

    def test_creation_failure(self) -> None:
        """Returns failure when gh issue create fails."""
        mock_result = MagicMock(
            returncode=1, stdout="", stderr="resource not accessible"
        )

        with (
            patch("axon_agent.integrations.github._is_gh_cli_available", return_value=True),
            patch("axon_agent.integrations.github._run_gh_command", return_value=mock_result),
        ):
            result = create_github_issue("Test", "Desc")

        assert result.success is False
        assert "gh issue create failed" in result.message

    def test_creation_timeout(self) -> None:
        """Returns failure when gh issue create times out."""
        with (
            patch("axon_agent.integrations.github._is_gh_cli_available", return_value=True),
            patch(
                "axon_agent.integrations.github._run_gh_command",
                side_effect=subprocess.TimeoutExpired("gh", 60),
            ),
        ):
            result = create_github_issue("Test", "Desc")

        assert result.success is False
        assert "timed out" in result.message

    def test_gh_not_found(self) -> None:
        """Returns failure when gh CLI binary is missing."""
        with (
            patch("axon_agent.integrations.github._is_gh_cli_available", return_value=True),
            patch(
                "axon_agent.integrations.github._run_gh_command",
                side_effect=FileNotFoundError("gh not found"),
            ),
        ):
            result = create_github_issue("Test", "Desc")

        assert result.success is False
        assert "gh CLI not found" in result.message


# ---------------------------------------------------------------------------
# update_github_issue
# ---------------------------------------------------------------------------


class TestUpdateGitHubIssue:
    """Test GitHub Issue update via gh CLI."""

    def test_gh_cli_not_available(self) -> None:
        """Returns failure when gh CLI is not available."""
        with patch("axon_agent.integrations.github._is_gh_cli_available", return_value=False):
            result = update_github_issue(42, title="New Title")

        assert result.success is False
        assert "gh CLI not available" in result.message

    def test_update_title(self) -> None:
        """Updates issue title via gh issue edit."""
        mock_result = MagicMock(returncode=0, stdout="", stderr="")

        with (
            patch("axon_agent.integrations.github._is_gh_cli_available", return_value=True),
            patch(
                "axon_agent.integrations.github._run_gh_command", return_value=mock_result
            ) as mock_cmd,
        ):
            result = update_github_issue(42, title="New Title")

        assert result.success is True
        call_args = mock_cmd.call_args[0][0]
        assert "--title" in call_args
        title_idx = call_args.index("--title") + 1
        assert call_args[title_idx] == "New Title"

    def test_update_body(self) -> None:
        """Updates issue body via gh issue edit."""
        mock_result = MagicMock(returncode=0, stdout="", stderr="")

        with (
            patch("axon_agent.integrations.github._is_gh_cli_available", return_value=True),
            patch(
                "axon_agent.integrations.github._run_gh_command", return_value=mock_result
            ) as mock_cmd,
        ):
            result = update_github_issue(42, description="New body")

        assert result.success is True
        call_args = mock_cmd.call_args[0][0]
        assert "--body" in call_args

    def test_close_issue(self) -> None:
        """Closes issue via gh issue close."""
        mock_result = MagicMock(returncode=0, stdout="", stderr="")

        with (
            patch("axon_agent.integrations.github._is_gh_cli_available", return_value=True),
            patch(
                "axon_agent.integrations.github._run_gh_command", return_value=mock_result
            ) as mock_cmd,
        ):
            result = update_github_issue(42, state="closed")

        assert result.success is True
        # Verify gh issue close was called
        call_args = mock_cmd.call_args[0][0]
        assert "close" in call_args

    def test_reopen_issue(self) -> None:
        """Reopens issue via gh issue reopen."""
        mock_result = MagicMock(returncode=0, stdout="", stderr="")

        with (
            patch("axon_agent.integrations.github._is_gh_cli_available", return_value=True),
            patch(
                "axon_agent.integrations.github._run_gh_command", return_value=mock_result
            ) as mock_cmd,
        ):
            result = update_github_issue(42, state="open")

        assert result.success is True
        call_args = mock_cmd.call_args[0][0]
        assert "reopen" in call_args

    def test_edit_failure(self) -> None:
        """Returns failure when gh issue edit fails."""
        mock_result = MagicMock(
            returncode=1, stdout="", stderr="could not edit issue"
        )

        with (
            patch("axon_agent.integrations.github._is_gh_cli_available", return_value=True),
            patch("axon_agent.integrations.github._run_gh_command", return_value=mock_result),
        ):
            result = update_github_issue(42, title="New Title")

        assert result.success is False
        assert "gh issue edit failed" in result.message

    def test_close_failure(self) -> None:
        """Returns failure when gh issue close fails."""
        # First call (edit with no fields) doesn't happen, second call (close) fails
        mock_close_fail = MagicMock(
            returncode=1, stdout="", stderr="could not close issue"
        )

        with (
            patch("axon_agent.integrations.github._is_gh_cli_available", return_value=True),
            patch(
                "axon_agent.integrations.github._run_gh_command", return_value=mock_close_fail
            ),
        ):
            result = update_github_issue(42, state="closed")

        assert result.success is False
        assert "gh issue close failed" in result.message

    def test_update_with_labels(self) -> None:
        """Adds labels via gh issue edit --add-label."""
        mock_result = MagicMock(returncode=0, stdout="", stderr="")

        with (
            patch("axon_agent.integrations.github._is_gh_cli_available", return_value=True),
            patch(
                "axon_agent.integrations.github._run_gh_command", return_value=mock_result
            ) as mock_cmd,
        ):
            result = update_github_issue(42, labels=["agent-synced", "in-progress"])

        assert result.success is True
        call_args = mock_cmd.call_args[0][0]
        assert "--add-label" in call_args
        label_idx = call_args.index("--add-label") + 1
        assert call_args[label_idx] == "agent-synced,in-progress"

    def test_timeout(self) -> None:
        """Returns failure when gh times out."""
        with (
            patch("axon_agent.integrations.github._is_gh_cli_available", return_value=True),
            patch(
                "axon_agent.integrations.github._run_gh_command",
                side_effect=subprocess.TimeoutExpired("gh", 60),
            ),
        ):
            result = update_github_issue(42, title="Test")

        assert result.success is False
        assert "timed out" in result.message

    def test_no_changes_requested(self) -> None:
        """Succeeds silently when no changes are requested."""
        with patch("axon_agent.integrations.github._is_gh_cli_available", return_value=True):
            result = update_github_issue(42)

        assert result.success is True
        assert result.issue_number == 42


# ---------------------------------------------------------------------------
# sync_issue_to_github (outbound)
# ---------------------------------------------------------------------------


class TestSyncIssueToGitHub:
    """Test outbound sync from Task MCP to GitHub Issues."""

    def test_creates_new_issue_for_todo(self) -> None:
        """Creates new GitHub Issue when no synced issue exists."""
        create_result = GitHubIssueResult(
            success=True,
            issue_number=50,
            issue_url="https://github.com/org/repo/issues/50",
            message="Created",
        )

        with (
            patch(
                "axon_agent.integrations.github._find_synced_github_issue", return_value=None
            ),
            patch(
                "axon_agent.integrations.github.create_github_issue", return_value=create_result
            ) as mock_create,
        ):
            result = sync_issue_to_github(
                issue_id="ENG-64",
                title="GitHub Issues sync",
                description="Implement bidirectional sync",
                state="Todo",
            )

        assert result.success is True
        assert result.action == "created"
        assert result.github_issue_number == 50
        assert result.direction == "to_github"

        # Verify title format and sync marker in body
        call_args = mock_create.call_args
        assert call_args[1]["title"] == "[ENG-64] GitHub Issues sync"
        assert "[Task MCP: ENG-64]" in call_args[1]["description"]

    def test_updates_existing_issue(self) -> None:
        """Updates existing GitHub Issue when sync marker found."""
        existing = {"number": 30, "title": "Old Title", "state": "OPEN"}
        update_result = GitHubIssueResult(
            success=True,
            issue_number=30,
            issue_url=None,
            message="Updated",
        )

        with (
            patch(
                "axon_agent.integrations.github._find_synced_github_issue", return_value=existing
            ),
            patch(
                "axon_agent.integrations.github.update_github_issue", return_value=update_result
            ),
        ):
            result = sync_issue_to_github(
                issue_id="ENG-64",
                title="Updated title",
                description="Updated desc",
                state="In Progress",
            )

        assert result.success is True
        assert result.action == "updated"
        assert result.github_issue_number == 30

    def test_closes_issue_for_done_state(self) -> None:
        """Closes newly created issue when Task MCP state is Done."""
        create_result = GitHubIssueResult(
            success=True,
            issue_number=60,
            issue_url="https://github.com/org/repo/issues/60",
            message="Created",
        )
        close_result = GitHubIssueResult(
            success=True,
            issue_number=60,
            issue_url=None,
            message="Closed",
        )

        with (
            patch(
                "axon_agent.integrations.github._find_synced_github_issue", return_value=None
            ),
            patch(
                "axon_agent.integrations.github.create_github_issue", return_value=create_result
            ),
            patch(
                "axon_agent.integrations.github.update_github_issue", return_value=close_result
            ) as mock_update,
        ):
            result = sync_issue_to_github(
                issue_id="ENG-64",
                title="Done issue",
                description="Completed",
                state="Done",
            )

        assert result.success is True
        assert result.action == "created"
        # Verify update_github_issue was called with state="closed"
        mock_update.assert_called_once_with(issue_number=60, state="closed")

    def test_canceled_state_adds_wontfix_label(self) -> None:
        """Canceled state adds wontfix label to GitHub Issue."""
        create_result = GitHubIssueResult(
            success=True,
            issue_number=70,
            issue_url="https://github.com/org/repo/issues/70",
            message="Created",
        )
        close_result = GitHubIssueResult(
            success=True, issue_number=70, issue_url=None, message="Closed"
        )

        with (
            patch(
                "axon_agent.integrations.github._find_synced_github_issue", return_value=None
            ),
            patch(
                "axon_agent.integrations.github.create_github_issue", return_value=create_result
            ) as mock_create,
            patch(
                "axon_agent.integrations.github.update_github_issue", return_value=close_result
            ),
        ):
            result = sync_issue_to_github(
                issue_id="ENG-64",
                title="Canceled issue",
                description="Not needed",
                state="Canceled",
            )

        assert result.success is True
        # Verify labels include wontfix
        call_args = mock_create.call_args
        assert "wontfix" in call_args[1]["labels"]

    def test_create_failure_returns_skipped(self) -> None:
        """Returns skipped when create_github_issue fails."""
        create_result = GitHubIssueResult(
            success=False,
            issue_number=None,
            issue_url=None,
            message="gh CLI error",
        )

        with (
            patch(
                "axon_agent.integrations.github._find_synced_github_issue", return_value=None
            ),
            patch(
                "axon_agent.integrations.github.create_github_issue", return_value=create_result
            ),
        ):
            result = sync_issue_to_github(
                issue_id="ENG-64",
                title="Test",
                description="Desc",
                state="Todo",
            )

        assert result.success is False
        assert result.action == "skipped"

    def test_update_failure_returns_skipped(self) -> None:
        """Returns skipped when update_github_issue fails."""
        existing = {"number": 30, "title": "Old", "state": "OPEN"}
        update_result = GitHubIssueResult(
            success=False,
            issue_number=30,
            issue_url=None,
            message="gh CLI error",
        )

        with (
            patch(
                "axon_agent.integrations.github._find_synced_github_issue", return_value=existing
            ),
            patch(
                "axon_agent.integrations.github.update_github_issue", return_value=update_result
            ),
        ):
            result = sync_issue_to_github(
                issue_id="ENG-64",
                title="Test",
                description="Desc",
                state="Todo",
            )

        assert result.success is False
        assert result.action == "skipped"

    def test_in_progress_includes_label(self) -> None:
        """In Progress state includes 'in-progress' label."""
        create_result = GitHubIssueResult(
            success=True,
            issue_number=80,
            issue_url="https://github.com/org/repo/issues/80",
            message="Created",
        )

        with (
            patch(
                "axon_agent.integrations.github._find_synced_github_issue", return_value=None
            ),
            patch(
                "axon_agent.integrations.github.create_github_issue", return_value=create_result
            ) as mock_create,
        ):
            sync_issue_to_github(
                issue_id="ENG-64",
                title="Test",
                description="Desc",
                state="In Progress",
            )

        call_args = mock_create.call_args
        assert "in-progress" in call_args[1]["labels"]
        assert "agent-synced" in call_args[1]["labels"]


# ---------------------------------------------------------------------------
# sync_issue_from_github (inbound)
# ---------------------------------------------------------------------------


class TestSyncIssueFromGitHub:
    """Test inbound sync from GitHub Issues to Task MCP."""

    def test_gh_cli_not_available(self) -> None:
        """Returns failure when gh CLI is not available."""
        with patch("axon_agent.integrations.github._is_gh_cli_available", return_value=False):
            result = sync_issue_from_github(42)

        assert result.success is False
        assert result.direction == "from_github"
        assert "gh CLI not available" in result.message

    def test_successful_sync_closed_issue(self) -> None:
        """Maps closed GitHub Issue to Done state."""
        issue_data = json.dumps({
            "number": 42,
            "title": "[ENG-64] Test",
            "state": "CLOSED",
            "body": "Description\n\n---\n[Task MCP: ENG-64]",
            "labels": [{"name": "agent-synced"}],
        })
        mock_result = MagicMock(returncode=0, stdout=issue_data)

        with (
            patch("axon_agent.integrations.github._is_gh_cli_available", return_value=True),
            patch("axon_agent.integrations.github._run_gh_command", return_value=mock_result),
        ):
            result = sync_issue_from_github(42)

        assert result.success is True
        assert result.task_issue_id == "ENG-64"
        assert result.action == "synced"
        assert "Done" in result.message

    def test_closed_with_wontfix_maps_to_canceled(self) -> None:
        """Maps closed issue with wontfix label to Canceled."""
        issue_data = json.dumps({
            "number": 42,
            "title": "[ENG-64] Test",
            "state": "CLOSED",
            "body": "Desc\n[Task MCP: ENG-64]",
            "labels": [{"name": "wontfix"}, {"name": "agent-synced"}],
        })
        mock_result = MagicMock(returncode=0, stdout=issue_data)

        with (
            patch("axon_agent.integrations.github._is_gh_cli_available", return_value=True),
            patch("axon_agent.integrations.github._run_gh_command", return_value=mock_result),
        ):
            result = sync_issue_from_github(42)

        assert result.success is True
        assert "Canceled" in result.message

    def test_open_with_in_progress_label(self) -> None:
        """Maps open issue with in-progress label to In Progress."""
        issue_data = json.dumps({
            "number": 42,
            "title": "[ENG-64] Test",
            "state": "OPEN",
            "body": "Desc\n[Task MCP: ENG-64]",
            "labels": [{"name": "in-progress"}],
        })
        mock_result = MagicMock(returncode=0, stdout=issue_data)

        with (
            patch("axon_agent.integrations.github._is_gh_cli_available", return_value=True),
            patch("axon_agent.integrations.github._run_gh_command", return_value=mock_result),
        ):
            result = sync_issue_from_github(42)

        assert result.success is True
        assert "In Progress" in result.message

    def test_open_without_labels_maps_to_todo(self) -> None:
        """Maps open issue without labels to Todo."""
        issue_data = json.dumps({
            "number": 42,
            "title": "[ENG-64] Test",
            "state": "OPEN",
            "body": "Desc\n[Task MCP: ENG-64]",
            "labels": [],
        })
        mock_result = MagicMock(returncode=0, stdout=issue_data)

        with (
            patch("axon_agent.integrations.github._is_gh_cli_available", return_value=True),
            patch("axon_agent.integrations.github._run_gh_command", return_value=mock_result),
        ):
            result = sync_issue_from_github(42)

        assert result.success is True
        assert "Todo" in result.message

    def test_no_sync_marker_returns_failure(self) -> None:
        """Returns failure when issue has no Task MCP sync marker."""
        issue_data = json.dumps({
            "number": 42,
            "title": "Regular issue",
            "state": "OPEN",
            "body": "Just a regular issue with no marker",
            "labels": [],
        })
        mock_result = MagicMock(returncode=0, stdout=issue_data)

        with (
            patch("axon_agent.integrations.github._is_gh_cli_available", return_value=True),
            patch("axon_agent.integrations.github._run_gh_command", return_value=mock_result),
        ):
            result = sync_issue_from_github(42)

        assert result.success is False
        assert "no Task MCP sync marker" in result.message

    def test_gh_view_failure(self) -> None:
        """Returns failure when gh issue view fails."""
        mock_result = MagicMock(
            returncode=1, stdout="", stderr="issue not found"
        )

        with (
            patch("axon_agent.integrations.github._is_gh_cli_available", return_value=True),
            patch("axon_agent.integrations.github._run_gh_command", return_value=mock_result),
        ):
            result = sync_issue_from_github(999)

        assert result.success is False
        assert "Failed to fetch" in result.message

    def test_invalid_json_response(self) -> None:
        """Returns failure when gh returns invalid JSON."""
        mock_result = MagicMock(returncode=0, stdout="not json")

        with (
            patch("axon_agent.integrations.github._is_gh_cli_available", return_value=True),
            patch("axon_agent.integrations.github._run_gh_command", return_value=mock_result),
        ):
            result = sync_issue_from_github(42)

        assert result.success is False
        assert "Invalid JSON" in result.message

    def test_timeout(self) -> None:
        """Returns failure when gh issue view times out."""
        with (
            patch("axon_agent.integrations.github._is_gh_cli_available", return_value=True),
            patch(
                "axon_agent.integrations.github._run_gh_command",
                side_effect=subprocess.TimeoutExpired("gh", 60),
            ),
        ):
            result = sync_issue_from_github(42)

        assert result.success is False
        assert "timed out" in result.message

    def test_gh_not_found(self) -> None:
        """Returns failure when gh CLI binary is missing."""
        with (
            patch("axon_agent.integrations.github._is_gh_cli_available", return_value=True),
            patch(
                "axon_agent.integrations.github._run_gh_command",
                side_effect=FileNotFoundError("gh not found"),
            ),
        ):
            result = sync_issue_from_github(42)

        assert result.success is False
        assert "gh CLI not found" in result.message


# ===========================================================================
# ENG-65: GitHub Commit Status Checks via gh CLI
# ===========================================================================


# ---------------------------------------------------------------------------
# StatusCheckResult dataclass
# ---------------------------------------------------------------------------


class TestStatusCheckResult:
    """Test StatusCheckResult dataclass fields."""

    def test_success_result(self) -> None:
        """Successful result stores message and optional target_url."""
        result = StatusCheckResult(
            success=True,
            message="Status set: agent/tests = success",
            target_url="https://example.com/logs",
        )
        assert result.success is True
        assert "agent/tests" in result.message
        assert result.target_url == "https://example.com/logs"

    def test_failure_result(self) -> None:
        """Failure result has no target_url by default."""
        result = StatusCheckResult(
            success=False,
            message="gh CLI not available",
        )
        assert result.success is False
        assert result.target_url is None

    def test_default_target_url_is_none(self) -> None:
        """target_url defaults to None when not provided."""
        result = StatusCheckResult(success=True, message="ok")
        assert result.target_url is None


# ---------------------------------------------------------------------------
# _get_repo_nwo
# ---------------------------------------------------------------------------


class TestGetRepoNWO:
    """Test repository name-with-owner detection."""

    def test_successful_detection(self) -> None:
        """Returns NWO string when gh repo view succeeds."""
        mock_result = MagicMock(returncode=0, stdout="AxonCode/your-claude-engineer\n")
        with patch("axon_agent.integrations.github._run_gh_command", return_value=mock_result):
            nwo = _get_repo_nwo()

        assert nwo == "AxonCode/your-claude-engineer"

    def test_gh_failure_returns_none(self) -> None:
        """Returns None when gh repo view fails."""
        mock_result = MagicMock(returncode=1, stdout="", stderr="not a git repo")
        with patch("axon_agent.integrations.github._run_gh_command", return_value=mock_result):
            nwo = _get_repo_nwo()

        assert nwo is None

    def test_empty_output_returns_none(self) -> None:
        """Returns None when gh repo view returns empty output."""
        mock_result = MagicMock(returncode=0, stdout="")
        with patch("axon_agent.integrations.github._run_gh_command", return_value=mock_result):
            nwo = _get_repo_nwo()

        assert nwo is None

    def test_gh_not_found_returns_none(self) -> None:
        """Returns None when gh CLI is not installed."""
        with patch(
            "axon_agent.integrations.github._run_gh_command",
            side_effect=FileNotFoundError("gh not found"),
        ):
            nwo = _get_repo_nwo()

        assert nwo is None

    def test_timeout_returns_none(self) -> None:
        """Returns None when gh repo view times out."""
        with patch(
            "axon_agent.integrations.github._run_gh_command",
            side_effect=subprocess.TimeoutExpired("gh", 60),
        ):
            nwo = _get_repo_nwo()

        assert nwo is None


# ---------------------------------------------------------------------------
# set_commit_status
# ---------------------------------------------------------------------------


class TestSetCommitStatus:
    """Test setting commit statuses via gh api."""

    SAMPLE_SHA = "abc123def456789012345678901234567890abcd"
    SAMPLE_NWO = "AxonCode/your-claude-engineer"

    def test_gh_cli_not_available(self) -> None:
        """Returns failure when gh CLI is not available."""
        with patch("axon_agent.integrations.github._is_gh_cli_available", return_value=False):
            result = set_commit_status(
                self.SAMPLE_SHA, "success", "agent/tests", "All tests passed"
            )

        assert result.success is False
        assert "gh CLI not available" in result.message

    def test_repo_detection_failure(self) -> None:
        """Returns failure when repo NWO cannot be determined."""
        with (
            patch("axon_agent.integrations.github._is_gh_cli_available", return_value=True),
            patch("axon_agent.integrations.github._get_repo_nwo", return_value=None),
        ):
            result = set_commit_status(
                self.SAMPLE_SHA, "success", "agent/tests", "All tests passed"
            )

        assert result.success is False
        assert "Could not determine repository" in result.message

    def test_successful_status_set(self) -> None:
        """Sets commit status successfully via gh api."""
        mock_result = MagicMock(returncode=0, stdout='{"state":"success"}')

        with (
            patch("axon_agent.integrations.github._is_gh_cli_available", return_value=True),
            patch("axon_agent.integrations.github._get_repo_nwo", return_value=self.SAMPLE_NWO),
            patch(
                "axon_agent.integrations.github._run_gh_command", return_value=mock_result
            ) as mock_cmd,
        ):
            result = set_commit_status(
                self.SAMPLE_SHA, "success", "agent/tests", "All tests passed"
            )

        assert result.success is True
        assert "agent/tests" in result.message
        assert "success" in result.message

        # Verify gh api was called with correct arguments
        call_args = mock_cmd.call_args[0][0]
        assert call_args[0] == "api"
        assert f"repos/{self.SAMPLE_NWO}/statuses/{self.SAMPLE_SHA}" in call_args[1]
        assert "-X" in call_args
        assert "POST" in call_args
        assert "state=success" in " ".join(call_args)
        assert "context=agent/tests" in " ".join(call_args)

    def test_target_url_included_when_provided(self) -> None:
        """Includes target_url in gh api call when provided."""
        mock_result = MagicMock(returncode=0, stdout='{}')

        with (
            patch("axon_agent.integrations.github._is_gh_cli_available", return_value=True),
            patch("axon_agent.integrations.github._get_repo_nwo", return_value=self.SAMPLE_NWO),
            patch(
                "axon_agent.integrations.github._run_gh_command", return_value=mock_result
            ) as mock_cmd,
        ):
            result = set_commit_status(
                self.SAMPLE_SHA,
                "success",
                "agent/tests",
                "Passed",
                target_url="https://example.com/logs/123",
            )

        assert result.success is True
        assert result.target_url == "https://example.com/logs/123"

        call_args = mock_cmd.call_args[0][0]
        joined = " ".join(call_args)
        assert "target_url=https://example.com/logs/123" in joined

    def test_target_url_omitted_when_none(self) -> None:
        """Does not include target_url in gh api call when not provided."""
        mock_result = MagicMock(returncode=0, stdout='{}')

        with (
            patch("axon_agent.integrations.github._is_gh_cli_available", return_value=True),
            patch("axon_agent.integrations.github._get_repo_nwo", return_value=self.SAMPLE_NWO),
            patch(
                "axon_agent.integrations.github._run_gh_command", return_value=mock_result
            ) as mock_cmd,
        ):
            set_commit_status(
                self.SAMPLE_SHA, "failure", "agent/tests", "Failed"
            )

        call_args = mock_cmd.call_args[0][0]
        joined = " ".join(call_args)
        assert "target_url" not in joined

    def test_description_truncated_to_140_chars(self) -> None:
        """Description is truncated to 140 characters (GitHub limit)."""
        long_desc = "x" * 200
        mock_result = MagicMock(returncode=0, stdout='{}')

        with (
            patch("axon_agent.integrations.github._is_gh_cli_available", return_value=True),
            patch("axon_agent.integrations.github._get_repo_nwo", return_value=self.SAMPLE_NWO),
            patch(
                "axon_agent.integrations.github._run_gh_command", return_value=mock_result
            ) as mock_cmd,
        ):
            set_commit_status(
                self.SAMPLE_SHA, "success", "agent/tests", long_desc
            )

        call_args = mock_cmd.call_args[0][0]
        # Find the description argument
        desc_args = [a for a in call_args if a.startswith("description=")]
        assert len(desc_args) == 1
        desc_value = desc_args[0].split("=", 1)[1]
        assert len(desc_value) == 140

    def test_api_failure(self) -> None:
        """Returns failure when gh api returns non-zero exit code."""
        mock_result = MagicMock(
            returncode=1, stdout="", stderr="HTTP 422: Validation Failed"
        )

        with (
            patch("axon_agent.integrations.github._is_gh_cli_available", return_value=True),
            patch("axon_agent.integrations.github._get_repo_nwo", return_value=self.SAMPLE_NWO),
            patch("axon_agent.integrations.github._run_gh_command", return_value=mock_result),
        ):
            result = set_commit_status(
                self.SAMPLE_SHA, "success", "agent/tests", "Passed"
            )

        assert result.success is False
        assert "gh api failed" in result.message

    def test_timeout(self) -> None:
        """Returns failure when gh api times out."""
        with (
            patch("axon_agent.integrations.github._is_gh_cli_available", return_value=True),
            patch("axon_agent.integrations.github._get_repo_nwo", return_value=self.SAMPLE_NWO),
            patch(
                "axon_agent.integrations.github._run_gh_command",
                side_effect=subprocess.TimeoutExpired("gh", 60),
            ),
        ):
            result = set_commit_status(
                self.SAMPLE_SHA, "success", "agent/tests", "Passed"
            )

        assert result.success is False
        assert "timed out" in result.message

    def test_gh_not_found(self) -> None:
        """Returns failure when gh CLI binary disappears."""
        with (
            patch("axon_agent.integrations.github._is_gh_cli_available", return_value=True),
            patch("axon_agent.integrations.github._get_repo_nwo", return_value=self.SAMPLE_NWO),
            patch(
                "axon_agent.integrations.github._run_gh_command",
                side_effect=FileNotFoundError("gh not found"),
            ),
        ):
            result = set_commit_status(
                self.SAMPLE_SHA, "success", "agent/tests", "Passed"
            )

        assert result.success is False
        assert "gh CLI not found" in result.message

    def test_pending_state(self) -> None:
        """Sets pending status correctly."""
        mock_result = MagicMock(returncode=0, stdout='{}')

        with (
            patch("axon_agent.integrations.github._is_gh_cli_available", return_value=True),
            patch("axon_agent.integrations.github._get_repo_nwo", return_value=self.SAMPLE_NWO),
            patch(
                "axon_agent.integrations.github._run_gh_command", return_value=mock_result
            ) as mock_cmd,
        ):
            result = set_commit_status(
                self.SAMPLE_SHA, "pending", "agent/tests", "Running tests..."
            )

        assert result.success is True
        call_args = mock_cmd.call_args[0][0]
        assert "state=pending" in " ".join(call_args)

    def test_error_state(self) -> None:
        """Sets error status correctly."""
        mock_result = MagicMock(returncode=0, stdout='{}')

        with (
            patch("axon_agent.integrations.github._is_gh_cli_available", return_value=True),
            patch("axon_agent.integrations.github._get_repo_nwo", return_value=self.SAMPLE_NWO),
            patch(
                "axon_agent.integrations.github._run_gh_command", return_value=mock_result
            ) as mock_cmd,
        ):
            result = set_commit_status(
                self.SAMPLE_SHA, "error", "agent/tests", "Internal error"
            )

        assert result.success is True
        call_args = mock_cmd.call_args[0][0]
        assert "state=error" in " ".join(call_args)


# ---------------------------------------------------------------------------
# report_test_status
# ---------------------------------------------------------------------------


class TestReportTestStatus:
    """Test the report_test_status convenience function."""

    SAMPLE_SHA = "abc123def456789012345678901234567890abcd"

    def test_passed(self) -> None:
        """Reports success status with default description."""
        with patch(
            "axon_agent.integrations.github.set_commit_status",
            return_value=StatusCheckResult(success=True, message="ok"),
        ) as mock_set:
            result = report_test_status(self.SAMPLE_SHA, passed=True)

        assert result.success is True
        mock_set.assert_called_once_with(
            sha=self.SAMPLE_SHA,
            state="success",
            context=STATUS_CONTEXT_TESTS,
            description="All tests passed",
        )

    def test_failed(self) -> None:
        """Reports failure status with default description."""
        with patch(
            "axon_agent.integrations.github.set_commit_status",
            return_value=StatusCheckResult(success=True, message="ok"),
        ) as mock_set:
            report_test_status(self.SAMPLE_SHA, passed=False)

        mock_set.assert_called_once_with(
            sha=self.SAMPLE_SHA,
            state="failure",
            context=STATUS_CONTEXT_TESTS,
            description="Tests failed",
        )

    def test_custom_details(self) -> None:
        """Reports status with custom description override."""
        with patch(
            "axon_agent.integrations.github.set_commit_status",
            return_value=StatusCheckResult(success=True, message="ok"),
        ) as mock_set:
            report_test_status(
                self.SAMPLE_SHA, passed=True, details="12/12 tests passed"
            )

        mock_set.assert_called_once_with(
            sha=self.SAMPLE_SHA,
            state="success",
            context=STATUS_CONTEXT_TESTS,
            description="12/12 tests passed",
        )

    def test_uses_correct_context(self) -> None:
        """Uses the agent/tests context name."""
        with patch(
            "axon_agent.integrations.github.set_commit_status",
            return_value=StatusCheckResult(success=True, message="ok"),
        ) as mock_set:
            report_test_status(self.SAMPLE_SHA, passed=True)

        assert mock_set.call_args[1]["context"] == "agent/tests"


# ---------------------------------------------------------------------------
# report_quality_status
# ---------------------------------------------------------------------------


class TestReportQualityStatus:
    """Test the report_quality_status convenience function."""

    SAMPLE_SHA = "abc123def456789012345678901234567890abcd"

    def test_passed(self) -> None:
        """Reports success status with default description."""
        with patch(
            "axon_agent.integrations.github.set_commit_status",
            return_value=StatusCheckResult(success=True, message="ok"),
        ) as mock_set:
            result = report_quality_status(self.SAMPLE_SHA, passed=True)

        assert result.success is True
        mock_set.assert_called_once_with(
            sha=self.SAMPLE_SHA,
            state="success",
            context=STATUS_CONTEXT_QUALITY,
            description="Quality gates passed",
        )

    def test_failed(self) -> None:
        """Reports failure status with default description."""
        with patch(
            "axon_agent.integrations.github.set_commit_status",
            return_value=StatusCheckResult(success=True, message="ok"),
        ) as mock_set:
            report_quality_status(self.SAMPLE_SHA, passed=False)

        mock_set.assert_called_once_with(
            sha=self.SAMPLE_SHA,
            state="failure",
            context=STATUS_CONTEXT_QUALITY,
            description="Quality issues found",
        )

    def test_custom_details(self) -> None:
        """Reports status with custom description override."""
        with patch(
            "axon_agent.integrations.github.set_commit_status",
            return_value=StatusCheckResult(success=True, message="ok"),
        ) as mock_set:
            report_quality_status(
                self.SAMPLE_SHA, passed=True, details="lint-gate passed"
            )

        mock_set.assert_called_once_with(
            sha=self.SAMPLE_SHA,
            state="success",
            context=STATUS_CONTEXT_QUALITY,
            description="lint-gate passed",
        )

    def test_uses_correct_context(self) -> None:
        """Uses the agent/quality-gates context name."""
        with patch(
            "axon_agent.integrations.github.set_commit_status",
            return_value=StatusCheckResult(success=True, message="ok"),
        ) as mock_set:
            report_quality_status(self.SAMPLE_SHA, passed=True)

        assert mock_set.call_args[1]["context"] == "agent/quality-gates"


# ---------------------------------------------------------------------------
# report_verification_status
# ---------------------------------------------------------------------------


class TestReportVerificationStatus:
    """Test the report_verification_status convenience function."""

    SAMPLE_SHA = "abc123def456789012345678901234567890abcd"

    def test_passed(self) -> None:
        """Reports success status with default description."""
        with patch(
            "axon_agent.integrations.github.set_commit_status",
            return_value=StatusCheckResult(success=True, message="ok"),
        ) as mock_set:
            result = report_verification_status(self.SAMPLE_SHA, passed=True)

        assert result.success is True
        mock_set.assert_called_once_with(
            sha=self.SAMPLE_SHA,
            state="success",
            context=STATUS_CONTEXT_VERIFICATION,
            description="Agent verification passed",
        )

    def test_failed(self) -> None:
        """Reports failure status with default description."""
        with patch(
            "axon_agent.integrations.github.set_commit_status",
            return_value=StatusCheckResult(success=True, message="ok"),
        ) as mock_set:
            report_verification_status(self.SAMPLE_SHA, passed=False)

        mock_set.assert_called_once_with(
            sha=self.SAMPLE_SHA,
            state="failure",
            context=STATUS_CONTEXT_VERIFICATION,
            description="Verification failed",
        )

    def test_custom_details(self) -> None:
        """Reports status with custom description override."""
        with patch(
            "axon_agent.integrations.github.set_commit_status",
            return_value=StatusCheckResult(success=True, message="ok"),
        ) as mock_set:
            report_verification_status(
                self.SAMPLE_SHA, passed=True, details="UI verified via snapshot"
            )

        mock_set.assert_called_once_with(
            sha=self.SAMPLE_SHA,
            state="success",
            context=STATUS_CONTEXT_VERIFICATION,
            description="UI verified via snapshot",
        )

    def test_uses_correct_context(self) -> None:
        """Uses the agent/verification context name."""
        with patch(
            "axon_agent.integrations.github.set_commit_status",
            return_value=StatusCheckResult(success=True, message="ok"),
        ) as mock_set:
            report_verification_status(self.SAMPLE_SHA, passed=True)

        assert mock_set.call_args[1]["context"] == "agent/verification"


# ---------------------------------------------------------------------------
# report_all_statuses
# ---------------------------------------------------------------------------


class TestReportAllStatuses:
    """Test the report_all_statuses convenience function."""

    SAMPLE_SHA = "abc123def456789012345678901234567890abcd"

    def test_all_passing(self) -> None:
        """Reports all three statuses as success."""
        success_result = StatusCheckResult(success=True, message="ok")

        with patch(
            "axon_agent.integrations.github.set_commit_status", return_value=success_result
        ):
            results = report_all_statuses(
                self.SAMPLE_SHA,
                tests_passed=True,
                quality_passed=True,
                verification_passed=True,
            )

        assert len(results) == 3
        assert "tests" in results
        assert "quality" in results
        assert "verification" in results
        assert all(r.success for r in results.values())

    def test_all_failing(self) -> None:
        """Reports all three statuses as failure."""
        failure_result = StatusCheckResult(success=True, message="ok")

        with patch(
            "axon_agent.integrations.github.set_commit_status", return_value=failure_result
        ) as mock_set:
            report_all_statuses(
                self.SAMPLE_SHA,
                tests_passed=False,
                quality_passed=False,
                verification_passed=False,
            )

        # Verify set_commit_status was called 3 times
        assert mock_set.call_count == 3

        # All three calls should have state="failure"
        for call in mock_set.call_args_list:
            assert call[1]["state"] == "failure"

    def test_mixed_results(self) -> None:
        """Reports mixed pass/fail statuses correctly."""
        success_result = StatusCheckResult(success=True, message="ok")

        with patch(
            "axon_agent.integrations.github.set_commit_status", return_value=success_result
        ) as mock_set:
            report_all_statuses(
                self.SAMPLE_SHA,
                tests_passed=True,
                quality_passed=False,
                verification_passed=True,
            )

        # Verify the correct states were passed
        calls = mock_set.call_args_list
        states_by_context = {
            call[1]["context"]: call[1]["state"] for call in calls
        }
        assert states_by_context["agent/tests"] == "success"
        assert states_by_context["agent/quality-gates"] == "failure"
        assert states_by_context["agent/verification"] == "success"

    def test_returns_dict_with_correct_keys(self) -> None:
        """Returns dict with 'tests', 'quality', 'verification' keys."""
        success_result = StatusCheckResult(success=True, message="ok")

        with patch(
            "axon_agent.integrations.github.set_commit_status", return_value=success_result
        ):
            results = report_all_statuses(
                self.SAMPLE_SHA,
                tests_passed=True,
                quality_passed=True,
                verification_passed=True,
            )

        assert set(results.keys()) == {"tests", "quality", "verification"}


# ---------------------------------------------------------------------------
# Status context constants
# ---------------------------------------------------------------------------


class TestStatusContextConstants:
    """Test that status context constants have expected values."""

    def test_tests_context(self) -> None:
        """Tests context is 'agent/tests'."""
        assert STATUS_CONTEXT_TESTS == "agent/tests"

    def test_quality_context(self) -> None:
        """Quality context is 'agent/quality-gates'."""
        assert STATUS_CONTEXT_QUALITY == "agent/quality-gates"

    def test_verification_context(self) -> None:
        """Verification context is 'agent/verification'."""
        assert STATUS_CONTEXT_VERIFICATION == "agent/verification"
