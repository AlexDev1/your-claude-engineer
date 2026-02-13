#!/usr/bin/env python3
"""
Worker Tests
============

Unit tests for the team worker — task claiming, execution, and empty-queue exit.
Run with: pytest tests/unit/test_worker.py -v
"""

import asyncio
import json
import sys
from io import StringIO
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from axon_agent.team.protocol import TeamConfig, WorkerState, WorkerStatus
from axon_agent.team.task_queue import TaskQueue, PRIORITY_ORDER
from axon_agent.team.worker import (
    _emit,
    _emit_result,
    _emit_state,
    _execute_task,
    run_worker,
)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def team_config(tmp_path: Path) -> TeamConfig:
    """Create a test TeamConfig with fast polling."""
    return TeamConfig(
        team="TEST",
        project_dir=tmp_path,
        model="claude-haiku-4-5-20251001",
        num_workers=2,
        max_tasks=2,
        poll_interval=0.01,
    )


@pytest.fixture
def sample_issue() -> dict:
    """A minimal issue dict as returned by the MCP server."""
    return {
        "identifier": "ENG-42",
        "title": "Add login page",
        "description": "Create a login form with email and password fields.",
        "priority": "high",
        "state": "Todo",
    }


# ---------------------------------------------------------------------------
# JSON-line Emitter Tests
# ---------------------------------------------------------------------------

class TestEmitHelpers:
    """Tests for _emit, _emit_state, _emit_result."""

    def test_emit_writes_json_line(self) -> None:
        """_emit writes a valid JSON line to stdout."""
        buf = StringIO()
        with patch.object(sys, "stdout", buf):
            _emit("test_event", foo="bar", num=1)

        line = buf.getvalue().strip()
        data = json.loads(line)
        assert data["event"] == "test_event"
        assert data["foo"] == "bar"
        assert data["num"] == 1
        assert "ts" in data

    def test_emit_state(self) -> None:
        """_emit_state writes a state-change event."""
        buf = StringIO()
        with patch.object(sys, "stdout", buf):
            _emit_state(0, WorkerState.WORKING, task="ENG-1", message="busy")

        data = json.loads(buf.getvalue().strip())
        assert data["event"] == "state"
        assert data["worker_id"] == 0
        assert data["state"] == "working"
        assert data["task"] == "ENG-1"

    def test_emit_result(self) -> None:
        """_emit_result writes a task-completion event."""
        buf = StringIO()
        with patch.object(sys, "stdout", buf):
            _emit_result(1, "ENG-5", success=True, message="ok")

        data = json.loads(buf.getvalue().strip())
        assert data["event"] == "result"
        assert data["worker_id"] == 1
        assert data["task"] == "ENG-5"
        assert data["success"] is True


# ---------------------------------------------------------------------------
# TaskQueue Tests (mocked MCP session)
# ---------------------------------------------------------------------------

class TestTaskQueue:
    """Tests for TaskQueue claim / complete / fail with a mocked MCP session."""

    @pytest.fixture
    def mock_queue(self) -> TaskQueue:
        """TaskQueue with a stubbed MCP session."""
        q = TaskQueue(team="TEST", mcp_url="http://fake/sse", api_key="key")
        q._session = AsyncMock()
        return q

    @pytest.mark.asyncio
    async def test_claim_task_success(self, mock_queue: TaskQueue) -> None:
        """claim_task returns True when the issue is still Todo."""
        # Simulate _call_tool responses: GetIssue → AddComment → Transition
        mock_queue._call_tool = AsyncMock(side_effect=[
            {"state": "Todo"},  # GetIssue
            None,               # AddComment
            None,               # TransitionIssueState
        ])
        assert await mock_queue.claim_task("ENG-1", worker_id=0) is True

    @pytest.mark.asyncio
    async def test_claim_task_already_taken(self, mock_queue: TaskQueue) -> None:
        """claim_task returns False when the issue is no longer Todo."""
        mock_queue._call_tool = AsyncMock(return_value={"state": "In Progress"})
        assert await mock_queue.claim_task("ENG-1", worker_id=0) is False

    @pytest.mark.asyncio
    async def test_claim_task_none_issue(self, mock_queue: TaskQueue) -> None:
        """claim_task returns False when GetIssue returns None."""
        mock_queue._call_tool = AsyncMock(return_value=None)
        assert await mock_queue.claim_task("ENG-1", worker_id=0) is False

    @pytest.mark.asyncio
    async def test_complete_task(self, mock_queue: TaskQueue) -> None:
        """complete_task calls AddComment + Transition to Done."""
        mock_queue._call_tool = AsyncMock(return_value=None)
        assert await mock_queue.complete_task("ENG-1", worker_id=0) is True
        assert mock_queue._call_tool.call_count == 2

    @pytest.mark.asyncio
    async def test_fail_task(self, mock_queue: TaskQueue) -> None:
        """fail_task calls AddComment + Transition back to Todo."""
        mock_queue._call_tool = AsyncMock(return_value=None)
        assert await mock_queue.fail_task("ENG-1", worker_id=0, error="boom") is True
        assert mock_queue._call_tool.call_count == 2

    @pytest.mark.asyncio
    async def test_get_todo_tasks_sorted(self, mock_queue: TaskQueue) -> None:
        """get_todo_tasks returns issues sorted by priority."""
        mock_queue._call_tool = AsyncMock(return_value=[
            {"identifier": "A", "priority": "low"},
            {"identifier": "B", "priority": "urgent"},
            {"identifier": "C", "priority": "high"},
        ])
        tasks = await mock_queue.get_todo_tasks()
        assert [t["identifier"] for t in tasks] == ["B", "C", "A"]

    @pytest.mark.asyncio
    async def test_get_todo_tasks_empty(self, mock_queue: TaskQueue) -> None:
        """get_todo_tasks returns [] when no tasks available."""
        mock_queue._call_tool = AsyncMock(return_value=[])
        assert await mock_queue.get_todo_tasks() == []

    @pytest.mark.asyncio
    async def test_get_todo_tasks_non_list(self, mock_queue: TaskQueue) -> None:
        """get_todo_tasks returns [] when MCP returns unexpected type."""
        mock_queue._call_tool = AsyncMock(return_value="error string")
        assert await mock_queue.get_todo_tasks() == []

    def test_priority_order(self) -> None:
        """PRIORITY_ORDER maps all expected levels."""
        assert PRIORITY_ORDER["urgent"] < PRIORITY_ORDER["high"]
        assert PRIORITY_ORDER["high"] < PRIORITY_ORDER["medium"]
        assert PRIORITY_ORDER["medium"] < PRIORITY_ORDER["low"]


# ---------------------------------------------------------------------------
# _execute_task Tests
# ---------------------------------------------------------------------------

class TestExecuteTask:
    """Tests for _execute_task with mocked Claude SDK."""

    @pytest.mark.asyncio
    async def test_execute_task_success(self, team_config: TeamConfig, sample_issue: dict) -> None:
        """Successful execution returns True."""
        mock_result = MagicMock()
        mock_result.status = "SESSION_COMPLETE"
        mock_result.response = "ALL_TASKS_DONE:"

        mock_client = AsyncMock()
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=False)

        with patch("axon_agent.core.client.create_client", return_value=mock_client):
            with patch("axon_agent.core.session.run_agent_session", AsyncMock(return_value=mock_result)):
                buf = StringIO()
                with patch.object(sys, "stdout", buf):
                    result = await _execute_task(sample_issue, team_config, worker_id=0)

        assert result is True

    @pytest.mark.asyncio
    async def test_execute_task_sdk_exception(self, team_config: TeamConfig, sample_issue: dict) -> None:
        """SDK crash returns False."""
        mock_client = AsyncMock()
        mock_client.__aenter__ = AsyncMock(side_effect=RuntimeError("SDK boom"))
        mock_client.__aexit__ = AsyncMock(return_value=False)

        with patch("axon_agent.core.client.create_client", return_value=mock_client):
            buf = StringIO()
            with patch.object(sys, "stdout", buf):
                result = await _execute_task(sample_issue, team_config, worker_id=0)

        assert result is False


# ---------------------------------------------------------------------------
# run_worker Tests
# ---------------------------------------------------------------------------

class TestRunWorker:
    """Tests for the main run_worker loop."""

    @pytest.mark.asyncio
    async def test_exits_on_empty_queue(self, team_config: TeamConfig) -> None:
        """Worker exits after max_consecutive_empty polls with no tasks."""
        mock_queue = AsyncMock(spec=TaskQueue)
        mock_queue.connect = AsyncMock()
        mock_queue.disconnect = AsyncMock()
        mock_queue.get_todo_tasks = AsyncMock(return_value=[])

        with patch("axon_agent.team.worker.TaskQueue", return_value=mock_queue):
            with patch("axon_agent.team.worker.load_dotenv"):
                buf = StringIO()
                with patch.object(sys, "stdout", buf):
                    status = await run_worker(team_config, worker_id=0)

        assert status.state == WorkerState.STOPPED
        assert status.tasks_completed == 0
        assert mock_queue.get_todo_tasks.call_count == 3  # max_consecutive_empty

    @pytest.mark.asyncio
    async def test_claims_and_executes_task(self, team_config: TeamConfig, sample_issue: dict) -> None:
        """Worker claims a task, executes it, and marks it done."""
        call_count = 0

        async def get_tasks():
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                return [sample_issue]
            return []  # Empty on subsequent polls

        mock_queue = AsyncMock(spec=TaskQueue)
        mock_queue.connect = AsyncMock()
        mock_queue.disconnect = AsyncMock()
        mock_queue.get_todo_tasks = AsyncMock(side_effect=get_tasks)
        mock_queue.claim_task = AsyncMock(return_value=True)
        mock_queue.complete_task = AsyncMock(return_value=True)

        with patch("axon_agent.team.worker.TaskQueue", return_value=mock_queue):
            with patch("axon_agent.team.worker.load_dotenv"):
                with patch("axon_agent.team.worker._execute_task", AsyncMock(return_value=True)):
                    buf = StringIO()
                    with patch.object(sys, "stdout", buf):
                        status = await run_worker(team_config, worker_id=0)

        assert status.tasks_completed == 1
        mock_queue.claim_task.assert_called_once_with("ENG-42", 0)
        mock_queue.complete_task.assert_called_once_with("ENG-42", 0)

    @pytest.mark.asyncio
    async def test_handles_failed_task(self, team_config: TeamConfig, sample_issue: dict) -> None:
        """Worker increments tasks_failed on execution failure."""
        call_count = 0

        async def get_tasks():
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                return [sample_issue]
            return []

        mock_queue = AsyncMock(spec=TaskQueue)
        mock_queue.connect = AsyncMock()
        mock_queue.disconnect = AsyncMock()
        mock_queue.get_todo_tasks = AsyncMock(side_effect=get_tasks)
        mock_queue.claim_task = AsyncMock(return_value=True)
        mock_queue.fail_task = AsyncMock(return_value=True)

        with patch("axon_agent.team.worker.TaskQueue", return_value=mock_queue):
            with patch("axon_agent.team.worker.load_dotenv"):
                with patch("axon_agent.team.worker._execute_task", AsyncMock(return_value=False)):
                    buf = StringIO()
                    with patch.object(sys, "stdout", buf):
                        status = await run_worker(team_config, worker_id=0)

        assert status.tasks_failed == 1
        assert status.tasks_completed == 0
        mock_queue.fail_task.assert_called_once()

    @pytest.mark.asyncio
    async def test_skips_claimed_tasks(self, team_config: TeamConfig) -> None:
        """Worker skips tasks that were already claimed by others."""
        issues = [
            {"identifier": "ENG-10", "title": "A", "priority": "high", "state": "Todo"},
            {"identifier": "ENG-11", "title": "B", "priority": "medium", "state": "Todo"},
        ]
        poll = 0

        async def get_tasks():
            nonlocal poll
            poll += 1
            if poll <= 2:
                return issues
            return []

        mock_queue = AsyncMock(spec=TaskQueue)
        mock_queue.connect = AsyncMock()
        mock_queue.disconnect = AsyncMock()
        mock_queue.get_todo_tasks = AsyncMock(side_effect=get_tasks)
        # First claim fails (race condition), second succeeds
        mock_queue.claim_task = AsyncMock(side_effect=[False, False, True])
        mock_queue.complete_task = AsyncMock(return_value=True)

        with patch("axon_agent.team.worker.TaskQueue", return_value=mock_queue):
            with patch("axon_agent.team.worker.load_dotenv"):
                with patch("axon_agent.team.worker._execute_task", AsyncMock(return_value=True)):
                    buf = StringIO()
                    with patch.object(sys, "stdout", buf):
                        status = await run_worker(team_config, worker_id=0)

        assert status.tasks_completed == 1

    @pytest.mark.asyncio
    async def test_respects_max_tasks(self, team_config: TeamConfig, sample_issue: dict) -> None:
        """Worker stops after reaching max_tasks."""
        config = TeamConfig(
            team="TEST",
            project_dir=team_config.project_dir,
            model=team_config.model,
            max_tasks=1,
            poll_interval=0.01,
        )

        mock_queue = AsyncMock(spec=TaskQueue)
        mock_queue.connect = AsyncMock()
        mock_queue.disconnect = AsyncMock()
        mock_queue.get_todo_tasks = AsyncMock(return_value=[sample_issue])
        mock_queue.claim_task = AsyncMock(return_value=True)
        mock_queue.complete_task = AsyncMock(return_value=True)

        with patch("axon_agent.team.worker.TaskQueue", return_value=mock_queue):
            with patch("axon_agent.team.worker.load_dotenv"):
                with patch("axon_agent.team.worker._execute_task", AsyncMock(return_value=True)):
                    buf = StringIO()
                    with patch.object(sys, "stdout", buf):
                        status = await run_worker(config, worker_id=0)

        assert status.tasks_completed == 1
        # Should not try to get more tasks after reaching max
        assert mock_queue.get_todo_tasks.call_count == 1

    @pytest.mark.asyncio
    async def test_connect_failure(self, team_config: TeamConfig) -> None:
        """Worker returns FAILED status if MCP connection fails."""
        mock_queue = AsyncMock(spec=TaskQueue)
        mock_queue.connect = AsyncMock(side_effect=ConnectionError("refused"))

        with patch("axon_agent.team.worker.TaskQueue", return_value=mock_queue):
            with patch("axon_agent.team.worker.load_dotenv"):
                buf = StringIO()
                with patch.object(sys, "stdout", buf):
                    status = await run_worker(team_config, worker_id=0)

        assert status.state == WorkerState.FAILED
        assert "refused" in status.message
