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
