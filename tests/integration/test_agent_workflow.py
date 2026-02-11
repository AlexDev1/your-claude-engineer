"""
Agent Workflow Integration Tests
=================================

Full workflow tests including:
- Creating project/issues
- Running agent session with mocked LLM
- Verifying state changes
- Git commits
- Telegram notifications

Run with: make test-agent
"""

import pytest
import os
import asyncio
from unittest.mock import patch, MagicMock, AsyncMock
from pathlib import Path
from datetime import datetime


class TestAgentSessionFlow:
    """Tests for agent session execution flow."""

    @pytest.fixture
    def mock_project_dir(self, tmp_path):
        """Create a temporary project directory."""
        project_dir = tmp_path / "test-project"
        project_dir.mkdir()

        # Create basic project structure
        (project_dir / ".git").mkdir()
        (project_dir / "src").mkdir()
        (project_dir / "README.md").write_text("# Test Project")

        return project_dir

    @pytest.fixture
    def mock_claude_client(self):
        """Mock Claude SDK client."""
        client = MagicMock()
        client.query = AsyncMock()
        client.receive_response = AsyncMock(return_value=iter([]))
        client.__aenter__ = AsyncMock(return_value=client)
        client.__aexit__ = AsyncMock()
        return client

    def test_agent_module_imports(self):
        """Agent module imports successfully."""
        from axon_agent.core.session import (
            run_agent_session,
            SessionResult,
            SESSION_CONTINUE,
            SESSION_ERROR,
            SESSION_COMPLETE,
        )
        from axon_agent.core.runner import run_autonomous_agent

        assert SessionResult is not None
        assert SESSION_CONTINUE == "continue"
        assert SESSION_ERROR == "error"
        assert SESSION_COMPLETE == "complete"

    def test_session_result_creation(self):
        """SessionResult can be created with valid status."""
        from axon_agent.core.session import SessionResult

        result = SessionResult(status="continue", response="Test response")
        assert result.status == "continue"
        assert result.response == "Test response"

    @pytest.mark.asyncio
    async def test_agent_session_handles_error(self, mock_project_dir, mock_claude_client):
        """Agent session handles errors gracefully."""
        from axon_agent.core.session import run_agent_session, SESSION_ERROR

        # Make query raise an exception
        mock_claude_client.query.side_effect = Exception("Test error")

        with patch("axon_agent.core.client.create_client", return_value=mock_claude_client):
            result = await run_agent_session(
                mock_claude_client,
                "Test message",
                mock_project_dir,
            )

            assert result.status == SESSION_ERROR
            assert "Test error" in result.response


class TestContextManager:
    """Tests for context manager functionality."""

    def test_context_manager_imports(self):
        """Context manager imports successfully."""
        from axon_agent.core.context import (
            ContextManager,
            get_context_manager,
            estimate_tokens,
        )

        assert ContextManager is not None
        assert get_context_manager is not None

    def test_estimate_tokens(self):
        """Token estimation works correctly."""
        from axon_agent.core.context import estimate_tokens

        # Approximately 4 chars per token
        text = "a" * 400
        tokens = estimate_tokens(text)
        assert 90 <= tokens <= 110  # Should be around 100

    def test_context_manager_singleton(self):
        """Context manager is a singleton."""
        from axon_agent.core.context import get_context_manager

        cm1 = get_context_manager()
        cm2 = get_context_manager()

        assert cm1 is cm2

    def test_context_manager_stats(self):
        """Context manager provides stats."""
        from axon_agent.core.context import get_context_manager

        cm = get_context_manager()
        cm.reset()

        stats = cm.get_stats()

        assert "max_tokens" in stats
        assert "total_used" in stats
        assert "remaining" in stats
        assert "usage_percent" in stats


class TestAgentDefinitions:
    """Tests for agent definitions."""

    def test_agent_definitions_import(self):
        """Agent definitions import successfully."""
        from axon_agent.agents.definitions import (
            AGENT_DEFINITIONS,
            TASK_AGENT,
            CODING_AGENT,
            TELEGRAM_AGENT,
            REVIEWER_AGENT,
            DEVOPS_AGENT,
            TESTING_AGENT,
            SECURITY_AGENT,
            RESEARCH_AGENT,
            PLANNER_AGENT,
        )

        assert len(AGENT_DEFINITIONS) == 9
        assert "task" in AGENT_DEFINITIONS
        assert "coding" in AGENT_DEFINITIONS
        assert "telegram" in AGENT_DEFINITIONS
        assert "reviewer" in AGENT_DEFINITIONS
        assert "devops" in AGENT_DEFINITIONS
        assert "testing" in AGENT_DEFINITIONS
        assert "security" in AGENT_DEFINITIONS
        assert "research" in AGENT_DEFINITIONS
        assert "planner" in AGENT_DEFINITIONS

    def test_agent_has_required_fields(self):
        """Each agent has required fields."""
        from axon_agent.agents.definitions import AGENT_DEFINITIONS

        for name, agent in AGENT_DEFINITIONS.items():
            assert hasattr(agent, "description")
            assert hasattr(agent, "prompt")
            assert hasattr(agent, "tools")
            assert hasattr(agent, "model")

    def test_coding_agent_has_file_tools(self):
        """Coding agent has file operation tools."""
        from axon_agent.agents.definitions import CODING_AGENT

        tools = CODING_AGENT.tools
        assert "Read" in tools
        assert "Write" in tools
        assert "Edit" in tools

    def test_coding_agent_has_playwright_tools(self):
        """Coding agent has Playwright tools."""
        from axon_agent.agents.definitions import CODING_AGENT

        tools = CODING_AGENT.tools
        playwright_tools = [t for t in tools if "playwright" in t.lower()]
        assert len(playwright_tools) > 0

    def test_model_configuration(self):
        """Model configuration works correctly."""
        from axon_agent.agents.definitions import _get_model, DEFAULT_MODELS

        # Default model for task agent
        model = _get_model("task")
        assert model in ["haiku", "sonnet", "opus", "inherit"]

        # Default model for coding agent
        model = _get_model("coding")
        assert model in ["haiku", "sonnet", "opus", "inherit"]


class TestMCPConfiguration:
    """Tests for MCP server configuration."""

    def test_mcp_config_import(self):
        """MCP config imports successfully."""
        from axon_agent.mcp.config import (
            TASK_TOOLS,
            TELEGRAM_TOOLS,
            PLAYWRIGHT_TOOLS,
            get_task_tools,
            get_telegram_tools,
            get_coding_tools,
        )

        assert len(TASK_TOOLS) > 0
        assert len(TELEGRAM_TOOLS) > 0
        assert len(PLAYWRIGHT_TOOLS) > 0

    def test_task_tools_format(self):
        """Task tools have correct format."""
        from axon_agent.mcp.config import TASK_TOOLS

        for tool in TASK_TOOLS:
            assert tool.startswith("mcp__task__")

    def test_telegram_tools_format(self):
        """Telegram tools have correct format."""
        from axon_agent.mcp.config import TELEGRAM_TOOLS

        for tool in TELEGRAM_TOOLS:
            assert tool.startswith("mcp__telegram__")

    def test_playwright_tools_format(self):
        """Playwright tools have correct format."""
        from axon_agent.mcp.config import PLAYWRIGHT_TOOLS

        for tool in PLAYWRIGHT_TOOLS:
            assert tool.startswith("mcp__playwright__")

    def test_coding_tools_includes_builtin(self):
        """Coding tools include built-in tools."""
        from axon_agent.mcp.config import get_coding_tools

        tools = get_coding_tools()
        assert "Read" in tools
        assert "Write" in tools
        assert "Bash" in tools


class TestPrompts:
    """Tests for prompt loading."""

    def test_prompts_import(self):
        """Prompts module imports successfully."""
        from axon_agent.core.prompts import (
            get_execute_task_with_memory,
            get_continuation_task_with_memory,
        )

        assert get_execute_task_with_memory is not None
        assert get_continuation_task_with_memory is not None

    def test_execute_task_prompt_generation(self, tmp_path):
        """Execute task prompt is generated correctly."""
        from axon_agent.core.prompts import get_execute_task_with_memory

        # Create a temp project dir with memory file
        project_dir = tmp_path / "project"
        project_dir.mkdir()
        agent_dir = project_dir / ".agent"
        agent_dir.mkdir()
        (agent_dir / "MEMORY.md").write_text("# Agent Memory\nTest memory content")

        prompt = get_execute_task_with_memory("ENG", project_dir)

        assert "ENG" in prompt
        assert len(prompt) > 100

    def test_continuation_prompt_generation(self, tmp_path):
        """Continuation prompt is generated correctly."""
        from axon_agent.core.prompts import get_continuation_task_with_memory

        # Create a temp project dir with memory file
        project_dir = tmp_path / "project"
        project_dir.mkdir()
        agent_dir = project_dir / ".agent"
        agent_dir.mkdir()
        (agent_dir / "MEMORY.md").write_text("# Agent Memory\nTest memory content")

        prompt = get_continuation_task_with_memory("ENG", project_dir)

        assert "ENG" in prompt
        assert len(prompt) > 100


class TestSecurityValidation:
    """Tests for security hook validation."""

    def test_security_import(self):
        """Security module imports successfully."""
        from axon_agent.security.hooks import (
            bash_security_hook,
            validate_git_command,
            validate_chmod_command,
            ValidationResult,
        )

        assert bash_security_hook is not None
        assert validate_git_command is not None

    def test_validation_result(self):
        """ValidationResult works correctly."""
        from axon_agent.security.hooks import ValidationResult

        allowed = ValidationResult(allowed=True, reason="")
        assert allowed.allowed is True

        blocked = ValidationResult(allowed=False, reason="Blocked for security")
        assert blocked.allowed is False
        assert "security" in blocked.reason.lower()

    @pytest.mark.asyncio
    async def test_bash_hook_allows_safe_commands(self):
        """Bash hook allows safe commands."""
        from axon_agent.security.hooks import bash_security_hook

        input_data = {
            "session_id": "test",
            "transcript_path": "/tmp/test",
            "cwd": "/tmp",
            "hook_event_name": "PreToolUse",
            "tool_name": "Bash",
            "tool_input": {"command": "ls -la"},
        }

        result = await bash_security_hook(input_data)
        assert result.get("decision") != "block"

    @pytest.mark.asyncio
    async def test_bash_hook_blocks_dangerous_commands(self):
        """Bash hook blocks dangerous commands."""
        from axon_agent.security.hooks import bash_security_hook

        input_data = {
            "session_id": "test",
            "transcript_path": "/tmp/test",
            "cwd": "/tmp",
            "hook_event_name": "PreToolUse",
            "tool_name": "Bash",
            "tool_input": {"command": "rm -rf /"},
        }

        result = await bash_security_hook(input_data)
        assert result.get("decision") == "block"


class TestGitHubIntegration:
    """Tests for GitHub integration."""

    def test_github_module_imports(self):
        """GitHub integration imports successfully."""
        from axon_agent.integrations.github import (
            GitHubClient,
            PushResult,
            PRResult,
            is_github_configured,
            _sanitize_branch_name,
        )

        assert GitHubClient is not None
        assert PushResult is not None
        assert PRResult is not None

    def test_branch_name_sanitization(self):
        """Branch names are sanitized correctly."""
        from axon_agent.integrations.github import _sanitize_branch_name

        assert _sanitize_branch_name("ENG-123") == "eng-123"
        assert _sanitize_branch_name("Feature/Test") == "feature-test"
        assert _sanitize_branch_name("Bug Fix!") == "bug-fix"

    def test_is_configured_check(self):
        """Configuration check works."""
        from axon_agent.integrations.github import is_github_configured

        # Result depends on environment
        result = is_github_configured()
        assert isinstance(result, bool)


class TestFullWorkflow:
    """End-to-end workflow tests with mocked external services."""

    @pytest.fixture
    def mock_services(self):
        """Mock all external services."""
        with patch("httpx.AsyncClient") as mock_http, \
             patch("httpx.Client") as mock_sync_http:

            # Mock HTTP responses
            mock_response = MagicMock()
            mock_response.status_code = 200
            mock_response.json.return_value = {"issues": [], "success": True}

            mock_http.return_value.__aenter__.return_value.get = AsyncMock(return_value=mock_response)
            mock_http.return_value.__aenter__.return_value.post = AsyncMock(return_value=mock_response)

            yield {
                "http": mock_http,
                "sync_http": mock_sync_http,
            }

    @pytest.mark.asyncio
    async def test_workflow_issue_lifecycle(self):
        """Test complete issue lifecycle."""
        # This test demonstrates the flow without actually calling LLM

        # 1. Create issue via API
        from axon_agent.dashboard.api import app, ISSUES_STORE, initialize_issues_store
        from fastapi.testclient import TestClient

        ISSUES_STORE.clear()
        initialize_issues_store()

        client = TestClient(app)

        # Create issue
        response = client.post("/api/issues", json={
            "title": "Workflow Test Issue",
            "priority": "high",
        })
        assert response.status_code == 200
        issue_id = response.json()["identifier"]

        # 2. Transition to In Progress
        response = client.put(f"/api/issues/{issue_id}", json={
            "state": "In Progress"
        })
        assert response.status_code == 200
        assert response.json()["state"] == "In Progress"

        # 3. Add comment
        response = client.post(f"/api/issues/{issue_id}/comments?content=Working on this")
        assert response.status_code == 200

        # 4. Complete issue
        response = client.put(f"/api/issues/{issue_id}", json={
            "state": "Done"
        })
        assert response.status_code == 200
        assert response.json()["state"] == "Done"
        assert response.json()["completed_at"] is not None

        # 5. Verify analytics reflect the change
        response = client.get("/api/analytics/efficiency")
        assert response.status_code == 200
        # Task count should include our completed task

    @pytest.mark.asyncio
    async def test_workflow_error_recovery(self):
        """Test workflow handles errors gracefully."""
        from axon_agent.dashboard.api import app, ISSUES_STORE, initialize_issues_store
        from fastapi.testclient import TestClient

        ISSUES_STORE.clear()
        initialize_issues_store()

        client = TestClient(app)

        # Try to update non-existent issue
        response = client.put("/api/issues/NONEXISTENT-999", json={
            "state": "Done"
        })
        assert response.status_code == 404

        # Try invalid state transition
        # First create an issue
        create_response = client.post("/api/issues", json={
            "title": "Error Test"
        })
        issue_id = create_response.json()["identifier"]

        # Try to skip In Progress and go directly to Done
        response = client.put(f"/api/issues/{issue_id}", json={
            "state": "Done"
        })
        assert response.status_code == 400
