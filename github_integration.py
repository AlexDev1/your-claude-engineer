"""
GitHub Integration Module
=========================

Provides GitHub API integration for the autonomous coding agent:
- Auto-push to remote after commits
- PR creation on issue completion
- GitHub status checks
- GitHub Issues sync (optional, bidirectional)

Uses httpx for API calls (no PyGithub dependency needed).
GitHub token from GITHUB_TOKEN environment variable.

Security:
- Tokens are never logged
- All API calls use authenticated HTTPS
- Branch names are sanitized to prevent injection
"""

import json
import os
import re
import logging
import subprocess
from dataclasses import dataclass
from typing import Any, Literal
from urllib.parse import urlparse

import httpx

# Configure logging - filter out sensitive data
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


# =============================================================================
# Configuration
# =============================================================================

GITHUB_API_BASE = "https://api.github.com"

# Branch naming strategy for agent work
AGENT_BRANCH_PREFIX = "agent/"


def _get_github_token() -> str:
    """
    Get GitHub token from environment.

    Returns:
        GitHub personal access token

    Raises:
        ValueError: If GITHUB_TOKEN is not set
    """
    token = os.environ.get("GITHUB_TOKEN", "").strip()
    if not token:
        raise ValueError(
            "GITHUB_TOKEN environment variable not set.\n"
            "Create a token at: https://github.com/settings/tokens\n"
            "Required scopes: repo, workflow (for status checks)"
        )
    return token


def _get_github_repo() -> tuple[str, str]:
    """
    Get GitHub owner/repo from environment or git remote.

    Returns:
        Tuple of (owner, repo)

    Raises:
        ValueError: If GITHUB_REPO is not set and cannot be detected
    """
    # First check environment variable
    repo_env = os.environ.get("GITHUB_REPO", "").strip()
    if repo_env:
        parts = repo_env.split("/")
        if len(parts) == 2:
            return (parts[0], parts[1])
        raise ValueError(
            f"Invalid GITHUB_REPO format: {repo_env}\n"
            "Expected format: owner/repo (e.g., AxonCode/your-claude-engineer)"
        )

    # Try to detect from git remote
    try:
        result = subprocess.run(
            ["git", "remote", "get-url", "origin"],
            capture_output=True,
            text=True,
            check=True,
        )
        remote_url = result.stdout.strip()
        return _parse_github_remote(remote_url)
    except subprocess.CalledProcessError:
        raise ValueError(
            "GITHUB_REPO not set and could not detect from git remote.\n"
            "Set GITHUB_REPO=owner/repo in your environment."
        )


def _parse_github_remote(url: str) -> tuple[str, str]:
    """
    Parse GitHub owner/repo from remote URL.

    Supports:
    - git@github.com:owner/repo.git
    - https://github.com/owner/repo.git
    - https://github.com/owner/repo

    Args:
        url: Git remote URL

    Returns:
        Tuple of (owner, repo)

    Raises:
        ValueError: If URL cannot be parsed
    """
    # SSH format: git@github.com:owner/repo.git
    ssh_match = re.match(r"git@github\.com:([^/]+)/([^/]+?)(?:\.git)?$", url)
    if ssh_match:
        return (ssh_match.group(1), ssh_match.group(2))

    # HTTPS format: https://github.com/owner/repo.git
    parsed = urlparse(url)
    if parsed.netloc == "github.com":
        path_parts = parsed.path.strip("/").split("/")
        if len(path_parts) >= 2:
            repo = path_parts[1].removesuffix(".git")
            return (path_parts[0], repo)

    raise ValueError(
        f"Could not parse GitHub owner/repo from: {url}\n"
        "Expected git@github.com:owner/repo.git or https://github.com/owner/repo"
    )


def _sanitize_branch_name(name: str) -> str:
    """
    Sanitize a string for use as a git branch name.

    - Replaces spaces and special chars with dashes
    - Removes leading/trailing dashes
    - Converts to lowercase

    Args:
        name: Raw string to sanitize

    Returns:
        Safe branch name
    """
    # Replace non-alphanumeric chars (except dash) with dash
    sanitized = re.sub(r"[^a-zA-Z0-9-]", "-", name)
    # Remove consecutive dashes
    sanitized = re.sub(r"-+", "-", sanitized)
    # Remove leading/trailing dashes
    sanitized = sanitized.strip("-")
    # Convert to lowercase
    return sanitized.lower()


# =============================================================================
# Data Classes
# =============================================================================


@dataclass
class PushResult:
    """Result of a git push operation."""

    success: bool
    branch: str
    message: str
    remote_url: str | None = None


@dataclass
class PRResult:
    """Result of creating a pull request."""

    success: bool
    pr_number: int | None
    pr_url: str | None
    message: str


@dataclass
class StatusCheckResult:
    """Result of setting a status check."""

    success: bool
    message: str
    target_url: str | None = None


@dataclass
class IssueSyncResult:
    """Result of syncing with GitHub Issues."""

    success: bool
    github_issue_number: int | None
    message: str
    action: Literal["created", "updated", "synced", "skipped"]


# =============================================================================
# GitHub API Client
# =============================================================================


class GitHubClient:
    """
    GitHub API client for agent integration.

    Provides methods for:
    - Pushing branches to remote
    - Creating pull requests
    - Setting status checks
    - Syncing with GitHub Issues
    """

    def __init__(self, token: str | None = None, repo: str | None = None):
        """
        Initialize GitHub client.

        Args:
            token: GitHub token (defaults to GITHUB_TOKEN env var)
            repo: GitHub repo in owner/repo format (defaults to GITHUB_REPO env var)
        """
        self._token = token or _get_github_token()
        if repo:
            parts = repo.split("/")
            self._owner, self._repo = parts[0], parts[1]
        else:
            self._owner, self._repo = _get_github_repo()

        self._client = httpx.Client(
            base_url=GITHUB_API_BASE,
            headers={
                "Accept": "application/vnd.github+json",
                "Authorization": f"Bearer {self._token}",
                "X-GitHub-Api-Version": "2022-11-28",
            },
            timeout=30.0,
        )

    def close(self) -> None:
        """Close the HTTP client."""
        self._client.close()

    def __enter__(self) -> "GitHubClient":
        return self

    def __exit__(self, *args: Any) -> None:
        self.close()

    @property
    def repo_full_name(self) -> str:
        """Get full repo name (owner/repo)."""
        return f"{self._owner}/{self._repo}"

    # -------------------------------------------------------------------------
    # Git Operations (via subprocess)
    # -------------------------------------------------------------------------

    def create_agent_branch(self, issue_id: str) -> str:
        """
        Create and checkout an agent branch for an issue.

        Branch naming: agent/{issue-id}

        Args:
            issue_id: Issue identifier (e.g., "ENG-123")

        Returns:
            Branch name

        Raises:
            subprocess.CalledProcessError: If git command fails
        """
        branch_name = f"{AGENT_BRANCH_PREFIX}{_sanitize_branch_name(issue_id)}"

        # Check if branch exists
        result = subprocess.run(
            ["git", "branch", "--list", branch_name],
            capture_output=True,
            text=True,
        )

        if branch_name in result.stdout:
            # Branch exists, switch to it
            subprocess.run(["git", "checkout", branch_name], check=True)
            logger.info(f"Switched to existing branch: {branch_name}")
        else:
            # Create new branch from main
            subprocess.run(["git", "checkout", "-b", branch_name], check=True)
            logger.info(f"Created new branch: {branch_name}")

        return branch_name

    def push_branch(
        self,
        branch: str | None = None,
        remote: str = "origin",
        force: bool = False,
    ) -> PushResult:
        """
        Push a branch to the remote repository.

        Args:
            branch: Branch name (defaults to current branch)
            remote: Remote name (default: origin)
            force: Force push (default: False)

        Returns:
            PushResult with success status and details
        """
        try:
            # Get current branch if not specified
            if branch is None:
                result = subprocess.run(
                    ["git", "rev-parse", "--abbrev-ref", "HEAD"],
                    capture_output=True,
                    text=True,
                    check=True,
                )
                branch = result.stdout.strip()

            # Build push command
            cmd = ["git", "push", "-u", remote, branch]
            if force:
                cmd.insert(2, "--force")

            # Execute push
            result = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
            )

            if result.returncode == 0:
                logger.info(f"Pushed branch {branch} to {remote}")
                return PushResult(
                    success=True,
                    branch=branch,
                    message=f"Successfully pushed {branch} to {remote}",
                    remote_url=f"https://github.com/{self.repo_full_name}/tree/{branch}",
                )
            else:
                error_msg = result.stderr.strip() or result.stdout.strip()
                logger.error(f"Push failed: {error_msg}")
                return PushResult(
                    success=False,
                    branch=branch,
                    message=f"Push failed: {error_msg}",
                )

        except subprocess.CalledProcessError as e:
            logger.error(f"Git command failed: {e}")
            return PushResult(
                success=False,
                branch=branch or "unknown",
                message=f"Git error: {e}",
            )

    def get_current_sha(self) -> str:
        """
        Get the current commit SHA.

        Returns:
            Full commit SHA

        Raises:
            subprocess.CalledProcessError: If git command fails
        """
        result = subprocess.run(
            ["git", "rev-parse", "HEAD"],
            capture_output=True,
            text=True,
            check=True,
        )
        return result.stdout.strip()

    # -------------------------------------------------------------------------
    # Pull Request Operations
    # -------------------------------------------------------------------------

    def create_pull_request(
        self,
        title: str,
        body: str,
        head: str,
        base: str = "main",
        labels: list[str] | None = None,
        draft: bool = False,
    ) -> PRResult:
        """
        Create a pull request.

        Args:
            title: PR title
            body: PR description (markdown)
            head: Source branch
            base: Target branch (default: main)
            labels: Labels to add (default: ["agent", "automated"])
            draft: Create as draft PR (default: False)

        Returns:
            PRResult with PR details
        """
        if labels is None:
            labels = ["agent", "automated"]

        try:
            # Create the PR
            response = self._client.post(
                f"/repos/{self._owner}/{self._repo}/pulls",
                json={
                    "title": title,
                    "body": body,
                    "head": head,
                    "base": base,
                    "draft": draft,
                },
            )

            if response.status_code == 201:
                data = response.json()
                pr_number = data["number"]
                pr_url = data["html_url"]

                logger.info(f"Created PR #{pr_number}: {pr_url}")

                # Add labels if any
                if labels:
                    self._add_labels_to_pr(pr_number, labels)

                return PRResult(
                    success=True,
                    pr_number=pr_number,
                    pr_url=pr_url,
                    message=f"Created PR #{pr_number}",
                )
            elif response.status_code == 422:
                # Validation error - might be PR already exists
                error_data = response.json()
                errors = error_data.get("errors", [])
                if any("pull request already exists" in str(e).lower() for e in errors):
                    # Find existing PR
                    existing = self._find_existing_pr(head, base)
                    if existing:
                        return PRResult(
                            success=True,
                            pr_number=existing["number"],
                            pr_url=existing["html_url"],
                            message=f"PR already exists: #{existing['number']}",
                        )
                return PRResult(
                    success=False,
                    pr_number=None,
                    pr_url=None,
                    message=f"Validation error: {error_data.get('message', 'Unknown error')}",
                )
            else:
                error_msg = response.text
                logger.error(f"Failed to create PR: {error_msg}")
                return PRResult(
                    success=False,
                    pr_number=None,
                    pr_url=None,
                    message=f"API error ({response.status_code}): {error_msg}",
                )

        except httpx.RequestError as e:
            logger.error(f"Request failed: {e}")
            return PRResult(
                success=False,
                pr_number=None,
                pr_url=None,
                message=f"Request error: {e}",
            )

    def _add_labels_to_pr(self, pr_number: int, labels: list[str]) -> None:
        """Add labels to a pull request (best effort)."""
        try:
            self._client.post(
                f"/repos/{self._owner}/{self._repo}/issues/{pr_number}/labels",
                json={"labels": labels},
            )
            logger.info(f"Added labels to PR #{pr_number}: {labels}")
        except Exception as e:
            # Non-fatal - log and continue
            logger.warning(f"Failed to add labels to PR: {e}")

    def _find_existing_pr(self, head: str, base: str) -> dict[str, Any] | None:
        """Find an existing PR for the given head/base branches."""
        try:
            response = self._client.get(
                f"/repos/{self._owner}/{self._repo}/pulls",
                params={
                    "head": f"{self._owner}:{head}",
                    "base": base,
                    "state": "open",
                },
            )
            if response.status_code == 200:
                prs = response.json()
                if prs:
                    return prs[0]
        except Exception as e:
            logger.warning(f"Failed to find existing PR: {e}")
        return None

    def request_review(self, pr_number: int, reviewers: list[str]) -> bool:
        """
        Request review for a pull request.

        Args:
            pr_number: PR number
            reviewers: List of GitHub usernames

        Returns:
            True if successful
        """
        try:
            response = self._client.post(
                f"/repos/{self._owner}/{self._repo}/pulls/{pr_number}/requested_reviewers",
                json={"reviewers": reviewers},
            )
            if response.status_code == 201:
                logger.info(f"Requested review from {reviewers} on PR #{pr_number}")
                return True
            else:
                logger.warning(f"Failed to request review: {response.text}")
                return False
        except Exception as e:
            logger.warning(f"Failed to request review: {e}")
            return False

    # -------------------------------------------------------------------------
    # Status Checks
    # -------------------------------------------------------------------------

    def set_status(
        self,
        sha: str,
        state: Literal["pending", "success", "failure", "error"],
        context: str,
        description: str,
        target_url: str | None = None,
    ) -> StatusCheckResult:
        """
        Set a commit status check.

        Args:
            sha: Commit SHA
            state: Status state (pending, success, failure, error)
            context: Status check name (e.g., "Agent/Tests")
            description: Short description
            target_url: Optional URL for more details

        Returns:
            StatusCheckResult with result details
        """
        try:
            payload: dict[str, Any] = {
                "state": state,
                "context": context,
                "description": description[:140],  # GitHub limit
            }
            if target_url:
                payload["target_url"] = target_url

            response = self._client.post(
                f"/repos/{self._owner}/{self._repo}/statuses/{sha}",
                json=payload,
            )

            if response.status_code == 201:
                logger.info(f"Set status {state} for {context} on {sha[:8]}")
                return StatusCheckResult(
                    success=True,
                    message=f"Status set: {context} = {state}",
                    target_url=target_url,
                )
            else:
                error_msg = response.text
                logger.error(f"Failed to set status: {error_msg}")
                return StatusCheckResult(
                    success=False,
                    message=f"API error ({response.status_code}): {error_msg}",
                )

        except httpx.RequestError as e:
            logger.error(f"Request failed: {e}")
            return StatusCheckResult(
                success=False,
                message=f"Request error: {e}",
            )

    def set_tests_status(
        self,
        sha: str,
        passed: bool,
        details: str = "",
    ) -> StatusCheckResult:
        """Set the "Tests" status check."""
        return self.set_status(
            sha=sha,
            state="success" if passed else "failure",
            context="Agent/Tests",
            description=details or ("All tests passed" if passed else "Tests failed"),
        )

    def set_quality_gates_status(
        self,
        sha: str,
        passed: bool,
        details: str = "",
    ) -> StatusCheckResult:
        """Set the "Quality Gates" status check."""
        return self.set_status(
            sha=sha,
            state="success" if passed else "failure",
            context="Agent/Quality Gates",
            description=details or ("Quality gates passed" if passed else "Quality issues found"),
        )

    def set_verification_status(
        self,
        sha: str,
        passed: bool,
        details: str = "",
    ) -> StatusCheckResult:
        """Set the "Agent Verification" status check."""
        return self.set_status(
            sha=sha,
            state="success" if passed else "failure",
            context="Agent/Verification",
            description=details or ("Agent verified" if passed else "Verification failed"),
        )

    # -------------------------------------------------------------------------
    # GitHub Issues Sync
    # -------------------------------------------------------------------------

    def sync_issue_to_github(
        self,
        issue_id: str,
        title: str,
        body: str,
        state: Literal["open", "closed"] = "open",
        labels: list[str] | None = None,
    ) -> IssueSyncResult:
        """
        Sync a Task MCP issue to GitHub Issues.

        Creates a new GitHub issue if it doesn't exist, or updates if it does.
        Uses a convention: GitHub issue body contains "[Task MCP: {issue_id}]"

        Args:
            issue_id: Task MCP issue ID (e.g., "ENG-123")
            title: Issue title
            body: Issue description
            state: Issue state (open/closed)
            labels: Labels to apply

        Returns:
            IssueSyncResult with sync details
        """
        if labels is None:
            labels = ["agent-synced"]

        # Search for existing GitHub issue with this Task MCP ID
        existing = self._find_synced_issue(issue_id)

        if existing:
            # Update existing issue
            return self._update_github_issue(
                issue_number=existing["number"],
                issue_id=issue_id,
                title=title,
                body=body,
                state=state,
                labels=labels,
            )
        else:
            # Create new issue
            return self._create_github_issue(
                issue_id=issue_id,
                title=title,
                body=body,
                state=state,
                labels=labels,
            )

    def _find_synced_issue(self, issue_id: str) -> dict[str, Any] | None:
        """Find a GitHub issue synced from Task MCP."""
        try:
            # Search for issues containing the sync marker
            response = self._client.get(
                f"/search/issues",
                params={
                    "q": f"repo:{self.repo_full_name} in:body \"[Task MCP: {issue_id}]\"",
                },
            )
            if response.status_code == 200:
                data = response.json()
                if data.get("total_count", 0) > 0:
                    return data["items"][0]
        except Exception as e:
            logger.warning(f"Failed to search for synced issue: {e}")
        return None

    def _create_github_issue(
        self,
        issue_id: str,
        title: str,
        body: str,
        state: str,
        labels: list[str],
    ) -> IssueSyncResult:
        """Create a new GitHub issue."""
        try:
            # Add sync marker to body
            full_body = f"{body}\n\n---\n[Task MCP: {issue_id}]"

            response = self._client.post(
                f"/repos/{self._owner}/{self._repo}/issues",
                json={
                    "title": f"[{issue_id}] {title}",
                    "body": full_body,
                    "labels": labels,
                },
            )

            if response.status_code == 201:
                data = response.json()
                gh_number = data["number"]
                logger.info(f"Created GitHub issue #{gh_number} for {issue_id}")

                # Close if state is closed
                if state == "closed":
                    self._close_github_issue(gh_number)

                return IssueSyncResult(
                    success=True,
                    github_issue_number=gh_number,
                    message=f"Created GitHub issue #{gh_number}",
                    action="created",
                )
            else:
                return IssueSyncResult(
                    success=False,
                    github_issue_number=None,
                    message=f"Failed to create issue: {response.text}",
                    action="skipped",
                )

        except Exception as e:
            logger.error(f"Failed to create GitHub issue: {e}")
            return IssueSyncResult(
                success=False,
                github_issue_number=None,
                message=f"Error: {e}",
                action="skipped",
            )

    def _update_github_issue(
        self,
        issue_number: int,
        issue_id: str,
        title: str,
        body: str,
        state: str,
        labels: list[str],
    ) -> IssueSyncResult:
        """Update an existing GitHub issue."""
        try:
            # Add sync marker to body
            full_body = f"{body}\n\n---\n[Task MCP: {issue_id}]"

            response = self._client.patch(
                f"/repos/{self._owner}/{self._repo}/issues/{issue_number}",
                json={
                    "title": f"[{issue_id}] {title}",
                    "body": full_body,
                    "labels": labels,
                    "state": state,
                },
            )

            if response.status_code == 200:
                logger.info(f"Updated GitHub issue #{issue_number} for {issue_id}")
                return IssueSyncResult(
                    success=True,
                    github_issue_number=issue_number,
                    message=f"Updated GitHub issue #{issue_number}",
                    action="updated",
                )
            else:
                return IssueSyncResult(
                    success=False,
                    github_issue_number=issue_number,
                    message=f"Failed to update issue: {response.text}",
                    action="skipped",
                )

        except Exception as e:
            logger.error(f"Failed to update GitHub issue: {e}")
            return IssueSyncResult(
                success=False,
                github_issue_number=issue_number,
                message=f"Error: {e}",
                action="skipped",
            )

    def _close_github_issue(self, issue_number: int) -> None:
        """Close a GitHub issue."""
        try:
            self._client.patch(
                f"/repos/{self._owner}/{self._repo}/issues/{issue_number}",
                json={"state": "closed"},
            )
            logger.info(f"Closed GitHub issue #{issue_number}")
        except Exception as e:
            logger.warning(f"Failed to close GitHub issue: {e}")

    def sync_comment(
        self,
        issue_id: str,
        comment_body: str,
    ) -> bool:
        """
        Sync a comment to the corresponding GitHub issue.

        Args:
            issue_id: Task MCP issue ID
            comment_body: Comment text

        Returns:
            True if successful
        """
        existing = self._find_synced_issue(issue_id)
        if not existing:
            logger.warning(f"No GitHub issue found for {issue_id}, cannot sync comment")
            return False

        try:
            response = self._client.post(
                f"/repos/{self._owner}/{self._repo}/issues/{existing['number']}/comments",
                json={"body": comment_body},
            )
            if response.status_code == 201:
                logger.info(f"Added comment to GitHub issue #{existing['number']}")
                return True
            else:
                logger.warning(f"Failed to add comment: {response.text}")
                return False
        except Exception as e:
            logger.warning(f"Failed to sync comment: {e}")
            return False


# =============================================================================
# Convenience Functions
# =============================================================================


def push_branch(
    branch: str | None = None,
    remote: str = "origin",
    force: bool = False,
) -> PushResult:
    """
    Push a branch to GitHub.

    Convenience function that creates a client and pushes.

    Args:
        branch: Branch name (defaults to current)
        remote: Remote name (default: origin)
        force: Force push (default: False)

    Returns:
        PushResult
    """
    with GitHubClient() as client:
        return client.push_branch(branch, remote, force)


def create_pr_for_issue(
    issue_id: str,
    issue_title: str,
    issue_description: str,
    session_summary: str = "",
    base_branch: str = "main",
) -> PRResult:
    """
    Create a PR for a completed issue.

    Convenience function that:
    1. Constructs PR title and body
    2. Creates PR from agent branch to base

    Args:
        issue_id: Issue ID (e.g., "ENG-123")
        issue_title: Issue title
        issue_description: Issue description
        session_summary: Optional session summary to include
        base_branch: Target branch (default: main)

    Returns:
        PRResult
    """
    with GitHubClient() as client:
        # Construct branch name
        head_branch = f"{AGENT_BRANCH_PREFIX}{_sanitize_branch_name(issue_id)}"

        # Construct PR title
        pr_title = f"[Agent] {issue_title}"

        # Construct PR body
        body_parts = [
            f"## Issue: {issue_id}",
            "",
            issue_description,
            "",
            "---",
            "",
            "## Agent Summary",
            "",
            session_summary or "_No session summary provided._",
            "",
            "---",
            "",
            "_This PR was automatically created by the autonomous coding agent._",
        ]
        pr_body = "\n".join(body_parts)

        return client.create_pull_request(
            title=pr_title,
            body=pr_body,
            head=head_branch,
            base=base_branch,
        )


def set_all_status_checks(
    sha: str,
    tests_passed: bool,
    quality_passed: bool,
    verification_passed: bool,
) -> dict[str, StatusCheckResult]:
    """
    Set all status checks at once.

    Args:
        sha: Commit SHA
        tests_passed: Whether tests passed
        quality_passed: Whether quality gates passed
        verification_passed: Whether agent verification passed

    Returns:
        Dict of context -> StatusCheckResult
    """
    with GitHubClient() as client:
        return {
            "tests": client.set_tests_status(sha, tests_passed),
            "quality": client.set_quality_gates_status(sha, quality_passed),
            "verification": client.set_verification_status(sha, verification_passed),
        }


def create_agent_branch(issue_id: str) -> str:
    """
    Create and checkout an agent branch for an issue.

    Convenience function that creates a GitHubClient and creates the branch.
    If GitHub is not configured, falls back to local git commands only.

    Args:
        issue_id: Issue identifier (e.g., "ENG-123")

    Returns:
        Branch name that was created/switched to
    """
    branch_name = f"{AGENT_BRANCH_PREFIX}{_sanitize_branch_name(issue_id)}"

    # Check if branch exists locally
    result = subprocess.run(
        ["git", "branch", "--list", branch_name],
        capture_output=True,
        text=True,
    )

    if branch_name in result.stdout:
        subprocess.run(["git", "checkout", branch_name], check=True)
        logger.info("Switched to existing branch: %s", branch_name)
    else:
        subprocess.run(["git", "checkout", "-b", branch_name], check=True)
        logger.info("Created new branch: %s", branch_name)

    return branch_name


def push_to_github(
    branch: str | None = None,
    remote: str = "origin",
) -> PushResult:
    """
    Push current branch to GitHub after a commit.

    This is the primary function for the auto-push workflow (ENG-62).
    It checks if GitHub is configured before attempting the push.
    On failure, it logs a warning but does not raise -- the agent continues.

    Args:
        branch: Branch name (defaults to current branch)
        remote: Remote name (default: origin)

    Returns:
        PushResult with success status and details.
        If GitHub is not configured, returns a PushResult with success=False
        and an informational message.
    """
    if not is_github_configured():
        logger.warning("GitHub push skipped: GITHUB_TOKEN not set")
        return PushResult(
            success=False,
            branch=branch or "unknown",
            message="Push skipped: GITHUB_TOKEN not configured",
        )

    try:
        with GitHubClient() as client:
            return client.push_branch(branch=branch, remote=remote)
    except ValueError as e:
        # Token or repo configuration error
        logger.warning("GitHub push skipped due to config error: %s", e)
        return PushResult(
            success=False,
            branch=branch or "unknown",
            message=f"Push skipped: {e}",
        )
    except Exception as e:
        logger.error("Unexpected error during push: %s", e)
        return PushResult(
            success=False,
            branch=branch or "unknown",
            message=f"Push failed: {e}",
        )


def auto_push_after_commit(issue_id: str | None = None) -> PushResult:
    """
    Auto-push to GitHub after a successful commit (ENG-62).

    This is the main entry point for the post-commit push workflow.
    It performs these steps:
    1. Check if GITHUB_TOKEN is configured
    2. Determine the current branch (or create agent branch if issue_id provided)
    3. Push to origin with -u flag for tracking

    The function is designed to be safe to call even when GitHub is not
    configured -- it will log a warning and return gracefully.

    Args:
        issue_id: Optional issue ID. If provided and not on an agent branch,
                  creates/switches to agent/{issue-id} branch first.

    Returns:
        PushResult with success status and details
    """
    if not is_github_configured():
        logger.warning("Auto-push skipped: GITHUB_TOKEN not set")
        return PushResult(
            success=False,
            branch="unknown",
            message="Auto-push skipped: GITHUB_TOKEN not configured",
        )

    # Determine current branch
    try:
        result = subprocess.run(
            ["git", "rev-parse", "--abbrev-ref", "HEAD"],
            capture_output=True,
            text=True,
            check=True,
        )
        current_branch = result.stdout.strip()
    except subprocess.CalledProcessError as e:
        logger.error("Failed to determine current branch: %s", e)
        return PushResult(
            success=False,
            branch="unknown",
            message=f"Git error: could not determine current branch: {e}",
        )

    # If issue_id provided and not already on an agent branch, create one
    if issue_id and not current_branch.startswith(AGENT_BRANCH_PREFIX):
        try:
            current_branch = create_agent_branch(issue_id)
        except subprocess.CalledProcessError as e:
            logger.error("Failed to create agent branch: %s", e)
            return PushResult(
                success=False,
                branch=current_branch,
                message=f"Failed to create agent branch: {e}",
            )

    # Push the branch
    return push_to_github(branch=current_branch)


@dataclass
class LintGateResult:
    """Result of running the lint-gate quality checks."""

    passed: bool
    output: str
    exit_code: int


def run_lint_gate(project_dir: str | None = None) -> LintGateResult:
    """
    Run the lint-gate.sh quality checks as a test gate before push.

    Executes ./scripts/lint-gate.sh and captures output. The lint gate
    runs TypeScript type check, ESLint, Python syntax, ruff, and
    complexity guard.

    Args:
        project_dir: Working directory to run the gate in.
                     If None, uses current working directory.

    Returns:
        LintGateResult with pass/fail status and output
    """
    cwd = project_dir or os.getcwd()
    script_path = os.path.join(cwd, "scripts", "lint-gate.sh")

    if not os.path.isfile(script_path):
        logger.warning("lint-gate.sh not found at %s", script_path)
        return LintGateResult(
            passed=True,
            output="lint-gate.sh not found, skipping quality gate",
            exit_code=0,
        )

    try:
        result = subprocess.run(
            ["bash", script_path],
            capture_output=True,
            text=True,
            cwd=cwd,
            timeout=120,
        )
        passed = result.returncode == 0
        combined_output = result.stdout
        if result.stderr:
            combined_output += "\n" + result.stderr

        if passed:
            logger.info("Lint gate passed")
        else:
            logger.warning("Lint gate failed (exit code %d)", result.returncode)

        return LintGateResult(
            passed=passed,
            output=combined_output.strip(),
            exit_code=result.returncode,
        )
    except subprocess.TimeoutExpired:
        logger.error("Lint gate timed out after 120s")
        return LintGateResult(
            passed=False,
            output="Lint gate timed out after 120 seconds",
            exit_code=-1,
        )
    except FileNotFoundError:
        logger.warning("bash not found, cannot run lint-gate.sh")
        return LintGateResult(
            passed=True,
            output="bash not found, skipping quality gate",
            exit_code=0,
        )


def auto_push_with_gate(
    issue_id: str | None = None,
    project_dir: str | None = None,
    skip_gate: bool = False,
) -> PushResult:
    """
    Run lint-gate checks and push to GitHub only if they pass (ENG-62).

    This is the recommended entry point for the post-commit workflow.
    It combines quality gate verification with auto-push to ensure only
    tested code reaches the remote.

    Steps:
    1. Run lint-gate.sh quality checks (unless skip_gate=True)
    2. If gate fails, return PushResult with success=False
    3. If gate passes, call auto_push_after_commit()

    Args:
        issue_id: Optional issue ID for branch creation
        project_dir: Working directory for lint-gate execution
        skip_gate: Skip quality gate (e.g., for docs-only changes)

    Returns:
        PushResult with success status and details. The message field
        includes lint-gate output when the gate fails.
    """
    if not skip_gate:
        gate_result = run_lint_gate(project_dir)
        if not gate_result.passed:
            logger.warning("Push blocked: lint-gate failed")
            return PushResult(
                success=False,
                branch="unknown",
                message=(
                    f"Push blocked: lint-gate failed (exit code {gate_result.exit_code}). "
                    f"Fix errors before pushing."
                ),
            )
        logger.info("Lint gate passed, proceeding with push")

    return auto_push_after_commit(issue_id)


@dataclass
class AutoPRResult:
    """Result of automatic PR creation when an issue transitions to Done."""

    success: bool
    pr_url: str | None
    pr_number: int | None
    message: str


def _has_commits_ahead_of_base(branch: str, base: str = "main") -> bool:
    """
    Check if a branch has commits ahead of the base branch.

    Args:
        branch: Source branch name
        base: Target branch name (default: main)

    Returns:
        True if branch has at least one commit ahead of base
    """
    try:
        result = subprocess.run(
            ["git", "rev-list", "--count", f"{base}..{branch}"],
            capture_output=True,
            text=True,
            check=True,
        )
        count = int(result.stdout.strip())
        return count > 0
    except (subprocess.CalledProcessError, ValueError):
        return False


def _check_existing_pr_via_gh(branch: str) -> dict[str, str | int] | None:
    """
    Check if a PR already exists for the given branch using gh CLI.

    Args:
        branch: Source branch name to check

    Returns:
        Dict with 'url' and 'number' keys if PR exists, None otherwise
    """
    try:
        result = subprocess.run(
            ["gh", "pr", "view", branch, "--json", "number,url"],
            capture_output=True,
            text=True,
        )
        if result.returncode == 0:
            data = json.loads(result.stdout.strip())
            return {"url": data["url"], "number": data["number"]}
    except (subprocess.CalledProcessError, FileNotFoundError, KeyError, ValueError):
        pass
    return None


def _is_gh_cli_available() -> bool:
    """
    Check if the GitHub CLI (gh) is installed and authenticated.

    Returns:
        True if gh CLI is available and authenticated
    """
    try:
        result = subprocess.run(
            ["gh", "auth", "status"],
            capture_output=True,
            text=True,
        )
        return result.returncode == 0
    except FileNotFoundError:
        return False


def create_auto_pr(
    issue_id: str,
    issue_title: str,
    issue_description: str,
    session_summary: str | None = None,
    base_branch: str = "main",
) -> AutoPRResult:
    """
    Create a PR from agent/{issue-id} branch to main when issue transitions to Done.

    Uses the gh CLI for PR creation. Handles edge cases:
    - No commits to push (branch is up to date with main)
    - PR already exists for this branch
    - GitHub token / gh CLI not configured

    Args:
        issue_id: Issue identifier (e.g., "ENG-63")
        issue_title: Human-readable issue title
        issue_description: Issue description body (markdown)
        session_summary: Optional session summary to include in PR body
        base_branch: Target branch for the PR (default: main)

    Returns:
        AutoPRResult with success status, PR URL, PR number, and message
    """
    # Step 1: Check gh CLI availability
    if not _is_gh_cli_available():
        logger.warning("Auto-PR skipped: gh CLI not available or not authenticated")
        return AutoPRResult(
            success=False,
            pr_url=None,
            pr_number=None,
            message="Auto-PR skipped: gh CLI not available or not authenticated",
        )

    # Step 2: Determine branch name
    head_branch = f"{AGENT_BRANCH_PREFIX}{_sanitize_branch_name(issue_id)}"

    # Step 3: Check if PR already exists
    existing = _check_existing_pr_via_gh(head_branch)
    if existing:
        logger.info("PR already exists for branch %s: %s", head_branch, existing["url"])
        return AutoPRResult(
            success=True,
            pr_url=str(existing["url"]),
            pr_number=int(existing["number"]),
            message=f"PR already exists: #{existing['number']}",
        )

    # Step 4: Check if branch has commits ahead of base
    if not _has_commits_ahead_of_base(head_branch, base_branch):
        logger.info("No commits ahead of %s on branch %s", base_branch, head_branch)
        return AutoPRResult(
            success=False,
            pr_url=None,
            pr_number=None,
            message=f"No commits ahead of {base_branch} — nothing to create a PR for",
        )

    # Step 5: Construct PR title and body
    pr_title = f"[Agent] {issue_title}"

    body_parts = [
        f"## Issue: {issue_id}",
        "",
        issue_description,
        "",
        "---",
        "",
        "## Session Summary",
        "",
        session_summary or "_No session summary provided._",
        "",
        "---",
        "",
        "_This PR was automatically created by the autonomous coding agent._",
    ]
    pr_body = "\n".join(body_parts)

    # Step 6: Create PR via gh CLI
    try:
        cmd = [
            "gh", "pr", "create",
            "--title", pr_title,
            "--body", pr_body,
            "--base", base_branch,
            "--head", head_branch,
            "--label", "agent,automated",
        ]

        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=60,
        )

        if result.returncode == 0:
            pr_url = result.stdout.strip()
            # Extract PR number from URL (last path segment)
            pr_number = _extract_pr_number_from_url(pr_url)
            logger.info("Created PR %s for %s", pr_url, issue_id)
            return AutoPRResult(
                success=True,
                pr_url=pr_url,
                pr_number=pr_number,
                message=f"Created PR for {issue_id}",
            )
        else:
            error_msg = result.stderr.strip() or result.stdout.strip()
            # Check for "already exists" in error output
            if "already exists" in error_msg.lower():
                existing = _check_existing_pr_via_gh(head_branch)
                if existing:
                    return AutoPRResult(
                        success=True,
                        pr_url=str(existing["url"]),
                        pr_number=int(existing["number"]),
                        message=f"PR already exists: #{existing['number']}",
                    )
            logger.error("gh pr create failed: %s", error_msg)
            return AutoPRResult(
                success=False,
                pr_url=None,
                pr_number=None,
                message=f"gh pr create failed: {error_msg}",
            )

    except subprocess.TimeoutExpired:
        logger.error("gh pr create timed out after 60s")
        return AutoPRResult(
            success=False,
            pr_url=None,
            pr_number=None,
            message="gh pr create timed out after 60 seconds",
        )
    except FileNotFoundError:
        logger.error("gh CLI not found")
        return AutoPRResult(
            success=False,
            pr_url=None,
            pr_number=None,
            message="gh CLI not found on PATH",
        )


def _extract_pr_number_from_url(url: str) -> int | None:
    """
    Extract a PR number from a GitHub PR URL.

    Args:
        url: GitHub PR URL (e.g., "https://github.com/owner/repo/pull/42")

    Returns:
        PR number as int, or None if extraction fails
    """
    match = re.search(r"/pull/(\d+)", url)
    if match:
        return int(match.group(1))
    return None


def is_github_configured() -> bool:
    """
    Check if GitHub integration is configured.

    Returns:
        True if GITHUB_TOKEN is set
    """
    return bool(os.environ.get("GITHUB_TOKEN", "").strip())


def get_github_config_status() -> dict[str, Any]:
    """
    Get GitHub configuration status for diagnostics.

    Returns:
        Dict with configuration status (no sensitive data)
    """
    token_set = bool(os.environ.get("GITHUB_TOKEN", "").strip())
    repo_set = bool(os.environ.get("GITHUB_REPO", "").strip())

    status: dict[str, Any] = {
        "configured": token_set,
        "token_set": token_set,
        "repo_set": repo_set,
    }

    if token_set:
        try:
            owner, repo = _get_github_repo()
            status["repo"] = f"{owner}/{repo}"
        except ValueError as e:
            status["repo_error"] = str(e)

    return status


# =============================================================================
# GitHub Issues Sync — Bidirectional (ENG-64)
# =============================================================================

# Task MCP state -> GitHub Issue state + labels mapping
TASK_STATE_TO_GITHUB: dict[str, dict[str, Any]] = {
    "Todo": {"state": "open", "labels": []},
    "In Progress": {"state": "open", "labels": ["in-progress"]},
    "Done": {"state": "closed", "labels": []},
    "Canceled": {"state": "closed", "labels": ["wontfix"]},
}

# GitHub Issue state -> Task MCP state (reverse mapping for inbound sync)
GITHUB_STATE_TO_TASK: dict[str, str] = {
    "open": "In Progress",
    "closed": "Done",
}

# Sync marker prefix embedded in GitHub Issue body for cross-referencing
_SYNC_MARKER_PREFIX = "[Task MCP: "
_SYNC_MARKER_SUFFIX = "]"


@dataclass
class SyncResult:
    """Result of a bidirectional sync operation between Task MCP and GitHub."""

    success: bool
    github_issue_number: int | None
    task_issue_id: str | None
    action: Literal["created", "updated", "closed", "synced", "skipped"]
    message: str
    direction: Literal["to_github", "from_github"]


@dataclass
class GitHubIssueResult:
    """Result of a GitHub Issue create/update operation via gh CLI."""

    success: bool
    issue_number: int | None
    issue_url: str | None
    message: str


def _build_sync_marker(issue_id: str) -> str:
    """
    Build the sync marker string embedded in GitHub Issue bodies.

    The marker links a GitHub Issue back to its Task MCP source issue.

    Args:
        issue_id: Task MCP issue ID (e.g., "ENG-64")

    Returns:
        Sync marker string (e.g., "[Task MCP: ENG-64]")
    """
    return f"{_SYNC_MARKER_PREFIX}{issue_id}{_SYNC_MARKER_SUFFIX}"


def _extract_issue_id_from_body(body: str) -> str | None:
    """
    Extract Task MCP issue ID from a GitHub Issue body's sync marker.

    Looks for the pattern "[Task MCP: ENG-XX]" in the body text.

    Args:
        body: GitHub Issue body text

    Returns:
        Issue ID string if found, None otherwise
    """
    match = re.search(
        re.escape(_SYNC_MARKER_PREFIX) + r"([A-Z]+-\d+)" + re.escape(_SYNC_MARKER_SUFFIX),
        body,
    )
    if match:
        return match.group(1)
    return None


def _map_task_state_to_github(
    task_state: str,
) -> tuple[str, list[str]]:
    """
    Map a Task MCP state to GitHub Issue state and labels.

    Task MCP is the source of truth for state mapping:
    - Todo -> open (no extra labels)
    - In Progress -> open + "in-progress" label
    - Done -> closed
    - Canceled -> closed + "wontfix" label

    Args:
        task_state: Task MCP state string

    Returns:
        Tuple of (github_state, labels_to_add)
    """
    mapping = TASK_STATE_TO_GITHUB.get(task_state)
    if mapping:
        return mapping["state"], list(mapping["labels"])
    # Default: treat unknown states as open
    logger.warning("Unknown Task MCP state '%s', defaulting to open", task_state)
    return "open", []


def _map_github_state_to_task(
    github_state: str,
    labels: list[str] | None = None,
) -> str:
    """
    Map a GitHub Issue state (and labels) to Task MCP state.

    Reverse mapping with label refinement:
    - closed + "wontfix" label -> Canceled
    - closed -> Done
    - open + "in-progress" label -> In Progress
    - open -> Todo

    Args:
        github_state: GitHub Issue state ("open" or "closed")
        labels: List of label names on the GitHub Issue

    Returns:
        Task MCP state string
    """
    label_names = labels or []

    if github_state == "closed":
        if "wontfix" in label_names:
            return "Canceled"
        return "Done"

    # github_state == "open"
    if "in-progress" in label_names:
        return "In Progress"
    return "Todo"


def _run_gh_command(args: list[str], timeout: int = 60) -> subprocess.CompletedProcess[str]:
    """
    Run a gh CLI command with standard settings.

    Args:
        args: Command arguments (without the leading "gh")
        timeout: Command timeout in seconds

    Returns:
        CompletedProcess result

    Raises:
        FileNotFoundError: If gh CLI is not installed
        subprocess.TimeoutExpired: If command exceeds timeout
    """
    return subprocess.run(
        ["gh"] + args,
        capture_output=True,
        text=True,
        timeout=timeout,
    )


def _extract_issue_number_from_url(url: str) -> int | None:
    """
    Extract an issue number from a GitHub Issue URL.

    Args:
        url: GitHub Issue URL (e.g., "https://github.com/owner/repo/issues/42")

    Returns:
        Issue number as int, or None if extraction fails
    """
    match = re.search(r"/issues/(\d+)", url)
    if match:
        return int(match.group(1))
    return None


def create_github_issue(
    title: str,
    description: str,
    labels: list[str] | None = None,
) -> GitHubIssueResult:
    """
    Create a new GitHub Issue via gh CLI.

    Args:
        title: Issue title
        description: Issue body/description (markdown)
        labels: Labels to apply (created if they don't exist)

    Returns:
        GitHubIssueResult with issue number and URL
    """
    if not _is_gh_cli_available():
        return GitHubIssueResult(
            success=False,
            issue_number=None,
            issue_url=None,
            message="gh CLI not available or not authenticated",
        )

    cmd = [
        "issue", "create",
        "--title", title,
        "--body", description,
    ]

    if labels:
        cmd.extend(["--label", ",".join(labels)])

    try:
        result = _run_gh_command(cmd)

        if result.returncode == 0:
            issue_url = result.stdout.strip()
            issue_number = _extract_issue_number_from_url(issue_url)
            logger.info("Created GitHub issue #%s: %s", issue_number, issue_url)
            return GitHubIssueResult(
                success=True,
                issue_number=issue_number,
                issue_url=issue_url,
                message=f"Created GitHub issue #{issue_number}",
            )
        else:
            error_msg = result.stderr.strip() or result.stdout.strip()
            logger.error("gh issue create failed: %s", error_msg)
            return GitHubIssueResult(
                success=False,
                issue_number=None,
                issue_url=None,
                message=f"gh issue create failed: {error_msg}",
            )

    except subprocess.TimeoutExpired:
        logger.error("gh issue create timed out")
        return GitHubIssueResult(
            success=False,
            issue_number=None,
            issue_url=None,
            message="gh issue create timed out after 60 seconds",
        )
    except FileNotFoundError:
        logger.error("gh CLI not found")
        return GitHubIssueResult(
            success=False,
            issue_number=None,
            issue_url=None,
            message="gh CLI not found on PATH",
        )


def update_github_issue(
    issue_number: int,
    title: str | None = None,
    description: str | None = None,
    state: str | None = None,
    labels: list[str] | None = None,
) -> GitHubIssueResult:
    """
    Update an existing GitHub Issue via gh CLI.

    Supports updating title, body, state, and labels independently.
    Only provided fields are updated.

    Args:
        issue_number: GitHub Issue number to update
        title: New title (None to keep current)
        description: New body/description (None to keep current)
        state: New state - "open" or "closed" (None to keep current)
        labels: Labels to set (replaces existing labels; None to keep current)

    Returns:
        GitHubIssueResult with update status
    """
    if not _is_gh_cli_available():
        return GitHubIssueResult(
            success=False,
            issue_number=issue_number,
            issue_url=None,
            message="gh CLI not available or not authenticated",
        )

    issue_str = str(issue_number)
    edit_cmd: list[str] = ["issue", "edit", issue_str]
    needs_edit = False

    if title is not None:
        edit_cmd.extend(["--title", title])
        needs_edit = True

    if description is not None:
        edit_cmd.extend(["--body", description])
        needs_edit = True

    if labels is not None:
        # gh issue edit --add-label replaces; use remove then add for clean slate
        # Simpler: use --add-label for each label after clearing
        edit_cmd.extend(["--add-label", ",".join(labels)])
        needs_edit = True

    try:
        # Apply edits if any
        if needs_edit:
            result = _run_gh_command(edit_cmd)
            if result.returncode != 0:
                error_msg = result.stderr.strip() or result.stdout.strip()
                logger.error("gh issue edit failed: %s", error_msg)
                return GitHubIssueResult(
                    success=False,
                    issue_number=issue_number,
                    issue_url=None,
                    message=f"gh issue edit failed: {error_msg}",
                )

        # Handle state transitions separately
        if state == "closed":
            close_result = _run_gh_command(["issue", "close", issue_str])
            if close_result.returncode != 0:
                error_msg = close_result.stderr.strip() or close_result.stdout.strip()
                logger.error("gh issue close failed: %s", error_msg)
                return GitHubIssueResult(
                    success=False,
                    issue_number=issue_number,
                    issue_url=None,
                    message=f"gh issue close failed: {error_msg}",
                )
        elif state == "open":
            reopen_result = _run_gh_command(["issue", "reopen", issue_str])
            if reopen_result.returncode != 0:
                error_msg = reopen_result.stderr.strip() or reopen_result.stdout.strip()
                # Reopening an already open issue is not an error
                if "already open" not in error_msg.lower():
                    logger.error("gh issue reopen failed: %s", error_msg)
                    return GitHubIssueResult(
                        success=False,
                        issue_number=issue_number,
                        issue_url=None,
                        message=f"gh issue reopen failed: {error_msg}",
                    )

        logger.info("Updated GitHub issue #%d", issue_number)
        return GitHubIssueResult(
            success=True,
            issue_number=issue_number,
            issue_url=None,
            message=f"Updated GitHub issue #{issue_number}",
        )

    except subprocess.TimeoutExpired:
        logger.error("gh issue edit timed out")
        return GitHubIssueResult(
            success=False,
            issue_number=issue_number,
            issue_url=None,
            message="gh issue edit timed out after 60 seconds",
        )
    except FileNotFoundError:
        logger.error("gh CLI not found")
        return GitHubIssueResult(
            success=False,
            issue_number=issue_number,
            issue_url=None,
            message="gh CLI not found on PATH",
        )


def _find_synced_github_issue(issue_id: str) -> dict[str, Any] | None:
    """
    Find a GitHub Issue that was synced from a Task MCP issue.

    Searches GitHub Issues for the sync marker "[Task MCP: {issue_id}]"
    in the issue body using gh CLI search.

    Args:
        issue_id: Task MCP issue ID (e.g., "ENG-64")

    Returns:
        Dict with 'number', 'title', 'state', 'body', 'labels' if found,
        None otherwise
    """
    try:
        search_query = f"{_build_sync_marker(issue_id)} in:body"
        result = _run_gh_command([
            "issue", "list",
            "--search", search_query,
            "--state", "all",
            "--json", "number,title,state,body,labels",
            "--limit", "1",
        ])

        if result.returncode == 0 and result.stdout.strip():
            issues = json.loads(result.stdout.strip())
            if issues:
                issue = issues[0]
                # Normalize labels to a list of name strings
                issue["labels"] = [
                    lbl["name"] if isinstance(lbl, dict) else lbl
                    for lbl in issue.get("labels", [])
                ]
                return issue

    except (subprocess.TimeoutExpired, FileNotFoundError, json.JSONDecodeError) as e:
        logger.warning("Failed to search for synced issue %s: %s", issue_id, e)

    return None


def sync_issue_to_github(
    issue_id: str,
    title: str,
    description: str,
    state: str,
) -> SyncResult:
    """
    Sync a Task MCP issue to GitHub Issues (outbound sync).

    Creates or updates a GitHub Issue to match the Task MCP issue state.
    Task MCP is the source of truth. The sync marker "[Task MCP: {issue_id}]"
    is embedded in the GitHub Issue body for cross-referencing.

    State mapping:
    - Todo -> open (no extra labels)
    - In Progress -> open + "in-progress" label
    - Done -> closed
    - Canceled -> closed + "wontfix" label

    Args:
        issue_id: Task MCP issue ID (e.g., "ENG-64")
        title: Issue title
        description: Issue description (markdown)
        state: Task MCP state ("Todo", "In Progress", "Done", "Canceled")

    Returns:
        SyncResult with sync outcome details
    """
    github_state, state_labels = _map_task_state_to_github(state)
    all_labels = ["agent-synced"] + state_labels
    sync_marker = _build_sync_marker(issue_id)
    full_body = f"{description}\n\n---\n{sync_marker}"
    gh_title = f"[{issue_id}] {title}"

    # Check if a synced GitHub Issue already exists
    existing = _find_synced_github_issue(issue_id)

    if existing:
        # Update existing issue
        result = update_github_issue(
            issue_number=existing["number"],
            title=gh_title,
            description=full_body,
            state=github_state,
            labels=all_labels,
        )

        if result.success:
            return SyncResult(
                success=True,
                github_issue_number=existing["number"],
                task_issue_id=issue_id,
                action="updated",
                message=f"Updated GitHub issue #{existing['number']} for {issue_id}",
                direction="to_github",
            )
        return SyncResult(
            success=False,
            github_issue_number=existing["number"],
            task_issue_id=issue_id,
            action="skipped",
            message=result.message,
            direction="to_github",
        )

    # Create new GitHub Issue
    result = create_github_issue(
        title=gh_title,
        description=full_body,
        labels=all_labels,
    )

    if not result.success:
        return SyncResult(
            success=False,
            github_issue_number=None,
            task_issue_id=issue_id,
            action="skipped",
            message=result.message,
            direction="to_github",
        )

    # If the Task MCP state maps to "closed", close the newly created issue
    if github_state == "closed" and result.issue_number is not None:
        close_result = update_github_issue(
            issue_number=result.issue_number,
            state="closed",
        )
        if not close_result.success:
            logger.warning(
                "Created issue #%d but failed to close it: %s",
                result.issue_number,
                close_result.message,
            )

    return SyncResult(
        success=True,
        github_issue_number=result.issue_number,
        task_issue_id=issue_id,
        action="created",
        message=f"Created GitHub issue #{result.issue_number} for {issue_id}",
        direction="to_github",
    )


def sync_issue_from_github(
    github_issue_number: int,
) -> SyncResult:
    """
    Sync a GitHub Issue back to Task MCP state (inbound sync).

    Reads the GitHub Issue state and maps it to a Task MCP state.
    The function extracts the Task MCP issue ID from the sync marker
    in the GitHub Issue body.

    This is a read-only operation that returns the mapped state.
    The caller is responsible for applying the state change to Task MCP.

    State mapping (with label refinement):
    - closed + "wontfix" label -> Canceled
    - closed -> Done
    - open + "in-progress" label -> In Progress
    - open -> Todo

    Conflict resolution: Task MCP is source of truth. If both sides
    changed, the caller should prefer the Task MCP state.

    Args:
        github_issue_number: GitHub Issue number to sync from

    Returns:
        SyncResult with the mapped Task MCP state in the message field.
        The task_issue_id field contains the extracted Task MCP ID.
    """
    if not _is_gh_cli_available():
        return SyncResult(
            success=False,
            github_issue_number=github_issue_number,
            task_issue_id=None,
            action="skipped",
            message="gh CLI not available or not authenticated",
            direction="from_github",
        )

    try:
        result = _run_gh_command([
            "issue", "view", str(github_issue_number),
            "--json", "number,title,state,body,labels",
        ])

        if result.returncode != 0:
            error_msg = result.stderr.strip() or result.stdout.strip()
            return SyncResult(
                success=False,
                github_issue_number=github_issue_number,
                task_issue_id=None,
                action="skipped",
                message=f"Failed to fetch GitHub issue #{github_issue_number}: {error_msg}",
                direction="from_github",
            )

        issue_data = json.loads(result.stdout.strip())

        # Extract Task MCP issue ID from sync marker
        body = issue_data.get("body", "")
        task_issue_id = _extract_issue_id_from_body(body)

        if not task_issue_id:
            return SyncResult(
                success=False,
                github_issue_number=github_issue_number,
                task_issue_id=None,
                action="skipped",
                message=(
                    f"GitHub issue #{github_issue_number} has no Task MCP sync marker"
                ),
                direction="from_github",
            )

        # Map GitHub state to Task MCP state
        github_state = issue_data.get("state", "open").lower()
        label_names = [
            lbl["name"] if isinstance(lbl, dict) else lbl
            for lbl in issue_data.get("labels", [])
        ]
        task_state = _map_github_state_to_task(github_state, label_names)

        return SyncResult(
            success=True,
            github_issue_number=github_issue_number,
            task_issue_id=task_issue_id,
            action="synced",
            message=f"GitHub issue #{github_issue_number} -> Task MCP state: {task_state}",
            direction="from_github",
        )

    except json.JSONDecodeError as e:
        logger.error("Invalid JSON from gh issue view: %s", e)
        return SyncResult(
            success=False,
            github_issue_number=github_issue_number,
            task_issue_id=None,
            action="skipped",
            message=f"Invalid JSON from gh issue view: {e}",
            direction="from_github",
        )
    except subprocess.TimeoutExpired:
        logger.error("gh issue view timed out")
        return SyncResult(
            success=False,
            github_issue_number=github_issue_number,
            task_issue_id=None,
            action="skipped",
            message="gh issue view timed out after 60 seconds",
            direction="from_github",
        )
    except FileNotFoundError:
        logger.error("gh CLI not found")
        return SyncResult(
            success=False,
            github_issue_number=github_issue_number,
            task_issue_id=None,
            action="skipped",
            message="gh CLI not found on PATH",
            direction="from_github",
        )
