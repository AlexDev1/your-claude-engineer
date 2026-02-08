"""
Tests for GitHub Integration Module
===================================

Unit tests for github_integration.py functionality.
Run with: python -m pytest test_github_integration.py -v
"""

import os
import subprocess
import tempfile
from pathlib import Path

import pytest
from unittest.mock import patch, MagicMock

from github_integration import (
    _sanitize_branch_name,
    _parse_github_remote,
    GitHubClient,
    LintGateResult,
    PushResult,
    auto_push_after_commit,
    auto_push_with_gate,
    is_github_configured,
    get_github_config_status,
    run_lint_gate,
    AGENT_BRANCH_PREFIX,
)


class TestBranchNameSanitization:
    """Tests for branch name sanitization."""

    def test_sanitize_simple_id(self):
        """Simple issue ID becomes lowercase."""
        assert _sanitize_branch_name("ENG-123") == "eng-123"

    def test_sanitize_with_spaces(self):
        """Spaces are replaced with dashes."""
        assert _sanitize_branch_name("ENG 123") == "eng-123"

    def test_sanitize_special_chars(self):
        """Special characters are replaced with dashes."""
        assert _sanitize_branch_name("ENG/123!@#") == "eng-123"

    def test_sanitize_consecutive_dashes(self):
        """Consecutive dashes are collapsed."""
        assert _sanitize_branch_name("ENG---123") == "eng-123"

    def test_sanitize_leading_trailing_dashes(self):
        """Leading and trailing dashes are removed."""
        assert _sanitize_branch_name("--ENG-123--") == "eng-123"

    def test_agent_branch_prefix(self):
        """Agent branch prefix is correct."""
        assert AGENT_BRANCH_PREFIX == "agent/"


class TestGitHubRemoteParsing:
    """Tests for GitHub remote URL parsing."""

    def test_parse_ssh_remote(self):
        """Parse SSH format remote URL."""
        owner, repo = _parse_github_remote("git@github.com:AxonCode/your-claude-engineer.git")
        assert owner == "AxonCode"
        assert repo == "your-claude-engineer"

    def test_parse_ssh_remote_no_git_suffix(self):
        """Parse SSH format without .git suffix."""
        owner, repo = _parse_github_remote("git@github.com:AxonCode/your-claude-engineer")
        assert owner == "AxonCode"
        assert repo == "your-claude-engineer"

    def test_parse_https_remote(self):
        """Parse HTTPS format remote URL."""
        owner, repo = _parse_github_remote("https://github.com/AxonCode/your-claude-engineer.git")
        assert owner == "AxonCode"
        assert repo == "your-claude-engineer"

    def test_parse_https_remote_no_git_suffix(self):
        """Parse HTTPS format without .git suffix."""
        owner, repo = _parse_github_remote("https://github.com/AxonCode/your-claude-engineer")
        assert owner == "AxonCode"
        assert repo == "your-claude-engineer"

    def test_parse_invalid_remote(self):
        """Invalid remote URL raises ValueError."""
        with pytest.raises(ValueError):
            _parse_github_remote("not-a-github-url")


class TestGitHubConfigCheck:
    """Tests for GitHub configuration checking."""

    def test_is_configured_with_token(self):
        """is_github_configured returns True when token is set."""
        with patch.dict(os.environ, {"GITHUB_TOKEN": "ghp_test_token"}):
            assert is_github_configured() is True

    def test_is_configured_without_token(self):
        """is_github_configured returns False when token is not set."""
        with patch.dict(os.environ, {"GITHUB_TOKEN": ""}, clear=False):
            # Need to ensure GITHUB_TOKEN is actually empty
            env = os.environ.copy()
            env.pop("GITHUB_TOKEN", None)
            with patch.dict(os.environ, env, clear=True):
                assert is_github_configured() is False

    def test_config_status_with_token(self):
        """get_github_config_status returns correct status with token."""
        with patch.dict(os.environ, {
            "GITHUB_TOKEN": "ghp_test_token",
            "GITHUB_REPO": "AxonCode/your-claude-engineer",
        }):
            status = get_github_config_status()
            assert status["configured"] is True
            assert status["token_set"] is True
            assert status["repo_set"] is True
            assert status["repo"] == "AxonCode/your-claude-engineer"


class TestGitSecurityValidation:
    """Tests for git command security validation."""

    def test_import_security_module(self):
        """Security module imports successfully."""
        from security import validate_git_command, ValidationResult
        assert validate_git_command is not None

    def test_allow_simple_git_status(self):
        """git status is allowed."""
        from security import validate_git_command
        result = validate_git_command("git status")
        assert result.allowed is True

    def test_allow_git_push(self):
        """git push to non-main branches is allowed."""
        from security import validate_git_command
        result = validate_git_command("git push -u origin agent/eng-123")
        assert result.allowed is True

    def test_block_force_push_main(self):
        """git push --force to main is blocked."""
        from security import validate_git_command
        result = validate_git_command("git push --force origin main")
        assert result.allowed is False
        assert "main" in result.reason.lower()

    def test_block_reset_hard(self):
        """git reset --hard is blocked."""
        from security import validate_git_command
        result = validate_git_command("git reset --hard HEAD~1")
        assert result.allowed is False
        assert "reset" in result.reason.lower()

    def test_block_clean_force(self):
        """git clean -f is blocked."""
        from security import validate_git_command
        result = validate_git_command("git clean -f")
        assert result.allowed is False
        assert "clean" in result.reason.lower()

    def test_block_checkout_dot(self):
        """git checkout . is blocked."""
        from security import validate_git_command
        result = validate_git_command("git checkout .")
        assert result.allowed is False
        assert "checkout" in result.reason.lower()

    def test_allow_checkout_branch(self):
        """git checkout <branch> is allowed."""
        from security import validate_git_command
        result = validate_git_command("git checkout agent/eng-123")
        assert result.allowed is True

    def test_allow_branch_delete_agent(self):
        """git branch -D agent/* is allowed."""
        from security import validate_git_command
        result = validate_git_command("git branch -D agent/eng-123")
        assert result.allowed is True

    def test_block_branch_delete_other(self):
        """git branch -D non-agent branches is blocked."""
        from security import validate_git_command
        result = validate_git_command("git branch -D feature/something")
        assert result.allowed is False


class TestGitHubClientMocked:
    """Tests for GitHubClient with mocked HTTP requests."""

    @pytest.fixture
    def mock_env(self):
        """Set up mock environment."""
        with patch.dict(os.environ, {
            "GITHUB_TOKEN": "ghp_test_token",
            "GITHUB_REPO": "AxonCode/your-claude-engineer",
        }):
            yield

    def test_client_initialization(self, mock_env):
        """GitHubClient initializes with environment variables."""
        with patch("github_integration.httpx.Client"):
            client = GitHubClient()
            assert client.repo_full_name == "AxonCode/your-claude-engineer"

    def test_push_result_dataclass(self):
        """PushResult dataclass works correctly."""
        from github_integration import PushResult
        result = PushResult(
            success=True,
            branch="agent/eng-123",
            message="Pushed successfully",
            remote_url="https://github.com/AxonCode/your-claude-engineer/tree/agent/eng-123",
        )
        assert result.success is True
        assert result.branch == "agent/eng-123"

    def test_pr_result_dataclass(self):
        """PRResult dataclass works correctly."""
        from github_integration import PRResult
        result = PRResult(
            success=True,
            pr_number=42,
            pr_url="https://github.com/AxonCode/your-claude-engineer/pull/42",
            message="Created PR #42",
        )
        assert result.success is True
        assert result.pr_number == 42


class TestRunLintGate:
    """Tests for run_lint_gate function (ENG-62)."""

    def test_lint_gate_missing_script(self):
        """Returns passed=True when lint-gate.sh is not found."""
        with tempfile.TemporaryDirectory() as tmpdir:
            result = run_lint_gate(tmpdir)
            assert result.passed is True
            assert "not found" in result.output

    def test_lint_gate_runs_script(self):
        """Runs lint-gate.sh and captures output."""
        with tempfile.TemporaryDirectory() as tmpdir:
            # Create a passing lint-gate script
            scripts_dir = Path(tmpdir) / "scripts"
            scripts_dir.mkdir()
            gate_script = scripts_dir / "lint-gate.sh"
            gate_script.write_text("#!/bin/bash\necho 'All checks passed!'\nexit 0\n")
            gate_script.chmod(0o755)

            result = run_lint_gate(tmpdir)
            assert result.passed is True
            assert result.exit_code == 0
            assert "All checks passed" in result.output

    def test_lint_gate_failure(self):
        """Returns passed=False when lint-gate fails."""
        with tempfile.TemporaryDirectory() as tmpdir:
            scripts_dir = Path(tmpdir) / "scripts"
            scripts_dir.mkdir()
            gate_script = scripts_dir / "lint-gate.sh"
            gate_script.write_text("#!/bin/bash\necho 'Lint errors found'\nexit 1\n")
            gate_script.chmod(0o755)

            result = run_lint_gate(tmpdir)
            assert result.passed is False
            assert result.exit_code == 1

    def test_lint_gate_timeout(self):
        """Returns passed=False on timeout."""
        with tempfile.TemporaryDirectory() as tmpdir:
            scripts_dir = Path(tmpdir) / "scripts"
            scripts_dir.mkdir()
            gate_script = scripts_dir / "lint-gate.sh"
            gate_script.write_text("#!/bin/bash\nsleep 300\n")
            gate_script.chmod(0o755)

            # Patch the timeout to be very short for testing
            with patch("github_integration.subprocess.run") as mock_run:
                mock_run.side_effect = subprocess.TimeoutExpired(
                    cmd=["bash", str(gate_script)],
                    timeout=120,
                )
                result = run_lint_gate(tmpdir)
                assert result.passed is False
                assert "timed out" in result.output

    def test_lint_gate_result_dataclass(self):
        """LintGateResult dataclass works correctly."""
        result = LintGateResult(passed=True, output="ok", exit_code=0)
        assert result.passed is True
        assert result.output == "ok"
        assert result.exit_code == 0


class TestAutoPushWithGate:
    """Tests for auto_push_with_gate function (ENG-62)."""

    def test_gate_fails_blocks_push(self):
        """Push is blocked when lint-gate fails."""
        with patch("github_integration.run_lint_gate") as mock_gate:
            mock_gate.return_value = LintGateResult(
                passed=False, output="Errors found", exit_code=1,
            )
            result = auto_push_with_gate(issue_id="ENG-62")
            assert result.success is False
            assert "lint-gate failed" in result.message

    def test_gate_passes_proceeds_to_push(self):
        """Push proceeds when lint-gate passes."""
        with patch("github_integration.run_lint_gate") as mock_gate, \
             patch("github_integration.auto_push_after_commit") as mock_push:
            mock_gate.return_value = LintGateResult(
                passed=True, output="All passed", exit_code=0,
            )
            mock_push.return_value = PushResult(
                success=True, branch="agent/eng-62", message="Pushed",
            )
            result = auto_push_with_gate(issue_id="ENG-62")
            assert result.success is True
            mock_push.assert_called_once_with("ENG-62")

    def test_skip_gate_bypasses_lint(self):
        """skip_gate=True bypasses lint-gate checks."""
        with patch("github_integration.run_lint_gate") as mock_gate, \
             patch("github_integration.auto_push_after_commit") as mock_push:
            mock_push.return_value = PushResult(
                success=True, branch="agent/eng-62", message="Pushed",
            )
            result = auto_push_with_gate(issue_id="ENG-62", skip_gate=True)
            assert result.success is True
            mock_gate.assert_not_called()

    def test_no_github_token_skips_push(self):
        """Push is skipped when GITHUB_TOKEN is not set."""
        with patch("github_integration.run_lint_gate") as mock_gate, \
             patch.dict(os.environ, {"GITHUB_TOKEN": ""}, clear=False):
            mock_gate.return_value = LintGateResult(
                passed=True, output="All passed", exit_code=0,
            )
            # Remove GITHUB_TOKEN entirely
            env = os.environ.copy()
            env.pop("GITHUB_TOKEN", None)
            with patch.dict(os.environ, env, clear=True):
                result = auto_push_with_gate(issue_id="ENG-62")
                assert result.success is False
                assert "GITHUB_TOKEN" in result.message


class TestAutoPushAfterCommit:
    """Tests for auto_push_after_commit function (ENG-62)."""

    def test_no_token_returns_skipped(self):
        """Returns skip result when no GITHUB_TOKEN."""
        env = os.environ.copy()
        env.pop("GITHUB_TOKEN", None)
        with patch.dict(os.environ, env, clear=True):
            result = auto_push_after_commit("ENG-62")
            assert result.success is False
            assert "GITHUB_TOKEN" in result.message

    def test_creates_branch_if_not_on_agent_branch(self):
        """Creates agent branch when on main."""
        with patch.dict(os.environ, {"GITHUB_TOKEN": "ghp_test"}), \
             patch("github_integration.subprocess.run") as mock_run, \
             patch("github_integration.push_to_github") as mock_push:

            # First call: git rev-parse (current branch = main)
            rev_parse_result = MagicMock()
            rev_parse_result.stdout = "main\n"
            rev_parse_result.returncode = 0

            # Second call: git branch --list (branch doesn't exist)
            branch_list_result = MagicMock()
            branch_list_result.stdout = ""
            branch_list_result.returncode = 0

            # Third call: git checkout -b
            checkout_result = MagicMock()
            checkout_result.returncode = 0

            mock_run.side_effect = [rev_parse_result, branch_list_result, checkout_result]
            mock_push.return_value = PushResult(
                success=True, branch="agent/eng-62", message="Pushed",
            )

            result = auto_push_after_commit("ENG-62")
            assert result.success is True


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
