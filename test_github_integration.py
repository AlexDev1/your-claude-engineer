"""
Tests for GitHub Integration Module
===================================

Unit tests for github_integration.py functionality.
Run with: python -m pytest test_github_integration.py -v
"""

import os
import pytest
from unittest.mock import patch, MagicMock

from github_integration import (
    _sanitize_branch_name,
    _parse_github_remote,
    GitHubClient,
    is_github_configured,
    get_github_config_status,
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


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
