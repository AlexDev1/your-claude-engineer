"""
Team Workflow Integration Tests
================================

Integration tests for the full team mode workflow:
- Coordinator spawning and monitoring workers
- Parallel task execution with result aggregation
- Worker crash handling and restart logic
- Telegram summary report generation

These tests mock subprocess spawning and MCP connections but exercise the
full coordinator → worker → result pipeline.

Run with: pytest tests/integration/test_team_workflow.py -v
"""

import asyncio
import json
import time
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from axon_agent.team.coordinator import (
    WorkerProcess,
    _send_telegram_summary,
    run_team,
)
from axon_agent.team.protocol import (
    TeamConfig,
    TeamResult,
    WorkerState,
    WorkerStatus,
)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def team_config(tmp_path: Path) -> TeamConfig:
    """TeamConfig with fast polling for tests."""
    env_file = tmp_path / ".env"
    env_file.write_text(
        "TASK_MCP_URL=http://localhost:8001/sse\n"
        "TELEGRAM_MCP_URL=http://localhost:8002/sse\n"
        "MCP_API_KEY=test-key\n"
    )
    return TeamConfig(
        team="TEST",
        project_dir=tmp_path,
        model="claude-haiku-4-5-20251001",
        num_workers=2,
        max_tasks=4,
        poll_interval=0.01,
    )


def _make_worker_events(
    worker_id: int,
    tasks: list[tuple[str, bool]],
) -> list[bytes]:
    """Build JSON-line stdout bytes simulating worker events.

    Args:
        worker_id: Worker numeric ID.
        tasks: List of (task_id, success) tuples.

    Returns:
        List of encoded JSON-line bytes (each ending with newline).
    """
    lines: list[bytes] = []
    ts = time.time()

    # Initial idle
    lines.append(json.dumps({
        "event": "state", "ts": ts,
        "worker_id": worker_id, "state": "idle", "message": "Starting",
    }).encode() + b"\n")

    for task_id, success in tasks:
        # Claiming
        lines.append(json.dumps({
            "event": "state", "ts": ts,
            "worker_id": worker_id, "state": "claiming",
            "task": task_id, "message": f"Claiming {task_id}",
        }).encode() + b"\n")

        # Working
        lines.append(json.dumps({
            "event": "state", "ts": ts,
            "worker_id": worker_id, "state": "working",
            "task": task_id, "message": f"Executing: {task_id}",
        }).encode() + b"\n")

        # Result
        lines.append(json.dumps({
            "event": "result", "ts": ts,
            "worker_id": worker_id, "task": task_id,
            "success": success, "message": "Done" if success else "Failed",
        }).encode() + b"\n")

    # Stopped
    lines.append(json.dumps({
        "event": "state", "ts": ts,
        "worker_id": worker_id, "state": "stopped",
        "message": "Worker finished",
    }).encode() + b"\n")

    return lines


# ---------------------------------------------------------------------------
# WorkerProcess event pipeline tests
# ---------------------------------------------------------------------------

class TestWorkerEventPipeline:
    """Test that WorkerProcess correctly processes a stream of JSON events."""

    @pytest.mark.asyncio
    async def test_processes_full_task_lifecycle(self, team_config: TeamConfig) -> None:
        """WorkerProcess tracks state through claim → work → result → stop."""
        wp = WorkerProcess(worker_id=0, config=team_config)
        events = _make_worker_events(0, [("ENG-10", True), ("ENG-11", False)])

        for line in events:
            text = line.decode().strip()
            if text:
                event = json.loads(text)
                wp._handle_event(event)

        assert wp.status.tasks_completed == 1
        assert wp.status.tasks_failed == 1
        assert wp.status.state == WorkerState.STOPPED

    @pytest.mark.asyncio
    async def test_multiple_successes(self, team_config: TeamConfig) -> None:
        """WorkerProcess accumulates completed counts."""
        wp = WorkerProcess(worker_id=1, config=team_config)
        events = _make_worker_events(1, [
            ("ENG-1", True), ("ENG-2", True), ("ENG-3", True),
        ])

        for line in events:
            text = line.decode().strip()
            if text:
                wp._handle_event(json.loads(text))

        assert wp.status.tasks_completed == 3
        assert wp.status.tasks_failed == 0


# ---------------------------------------------------------------------------
# run_team integration tests
# ---------------------------------------------------------------------------

class TestRunTeamWorkflow:
    """Integration tests for the full run_team pipeline."""

    @pytest.mark.asyncio
    async def test_parallel_workers_aggregate_results(self, team_config: TeamConfig) -> None:
        """Two workers complete tasks in parallel; results are aggregated."""
        # Worker 0: completes 2 tasks
        # Worker 1: completes 1 task, fails 1
        w0_events = _make_worker_events(0, [("ENG-1", True), ("ENG-2", True)])
        w1_events = _make_worker_events(1, [("ENG-3", True), ("ENG-4", False)])

        spawn_count = 0

        async def mock_start(self: WorkerProcess) -> None:
            nonlocal spawn_count
            events = w0_events if self.worker_id == 0 else w1_events

            # Feed events synchronously (simulates stdout reading)
            for line in events:
                text = line.decode().strip()
                if text:
                    self._handle_event(json.loads(text))

            # Mark process as exited (code 0)
            mock_proc = MagicMock()
            mock_proc.returncode = 0
            mock_proc.pid = 10000 + self.worker_id
            self.process = mock_proc
            spawn_count += 1

        with patch.object(WorkerProcess, "start", mock_start):
            with patch.object(WorkerProcess, "stop", AsyncMock()):
                with patch(
                    "axon_agent.team.coordinator._send_telegram_summary",
                    AsyncMock(),
                ) as mock_tg:
                    result = await run_team(team_config)

        assert spawn_count == 2
        assert result.completed == 3  # 2 + 1
        assert result.failed == 1
        assert len(result.worker_results) == 2
        assert result.duration_seconds > 0
        mock_tg.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_single_worker_mode(self, team_config: TeamConfig) -> None:
        """Team with num_workers=1 still works correctly."""
        config = TeamConfig(
            team=team_config.team,
            project_dir=team_config.project_dir,
            model=team_config.model,
            num_workers=1,
            poll_interval=0.01,
        )

        events = _make_worker_events(0, [("ENG-99", True)])

        async def mock_start(self: WorkerProcess) -> None:
            for line in events:
                text = line.decode().strip()
                if text:
                    self._handle_event(json.loads(text))
            mock_proc = MagicMock()
            mock_proc.returncode = 0
            mock_proc.pid = 10000
            self.process = mock_proc

        with patch.object(WorkerProcess, "start", mock_start):
            with patch.object(WorkerProcess, "stop", AsyncMock()):
                with patch(
                    "axon_agent.team.coordinator._send_telegram_summary",
                    AsyncMock(),
                ):
                    result = await run_team(config)

        assert result.completed == 1
        assert result.failed == 0
        assert len(result.worker_results) == 1

    @pytest.mark.asyncio
    async def test_all_tasks_fail(self, team_config: TeamConfig) -> None:
        """All tasks failing is reflected in TeamResult."""
        events = _make_worker_events(0, [("ENG-1", False), ("ENG-2", False)])

        async def mock_start(self: WorkerProcess) -> None:
            for line in events:
                text = line.decode().strip()
                if text:
                    self._handle_event(json.loads(text))
            mock_proc = MagicMock()
            mock_proc.returncode = 0
            mock_proc.pid = 10000 + self.worker_id
            self.process = mock_proc

        with patch.object(WorkerProcess, "start", mock_start):
            with patch.object(WorkerProcess, "stop", AsyncMock()):
                with patch(
                    "axon_agent.team.coordinator._send_telegram_summary",
                    AsyncMock(),
                ):
                    result = await run_team(team_config)

        assert result.completed == 0
        assert result.failed >= 2  # Both workers report failures

    @pytest.mark.asyncio
    async def test_empty_run_no_tasks(self, team_config: TeamConfig) -> None:
        """Workers that find no tasks exit cleanly."""
        events = _make_worker_events(0, [])  # No tasks

        async def mock_start(self: WorkerProcess) -> None:
            for line in events:
                text = line.decode().strip()
                if text:
                    self._handle_event(json.loads(text))
            mock_proc = MagicMock()
            mock_proc.returncode = 0
            mock_proc.pid = 10000 + self.worker_id
            self.process = mock_proc

        with patch.object(WorkerProcess, "start", mock_start):
            with patch.object(WorkerProcess, "stop", AsyncMock()):
                with patch(
                    "axon_agent.team.coordinator._send_telegram_summary",
                    AsyncMock(),
                ):
                    result = await run_team(team_config)

        assert result.completed == 0
        assert result.failed == 0


# ---------------------------------------------------------------------------
# Worker crash and restart tests
# ---------------------------------------------------------------------------

class TestWorkerCrashRecovery:
    """Test coordinator's handling of worker crashes and restarts."""

    @pytest.mark.asyncio
    async def test_crashed_worker_is_restarted(self, team_config: TeamConfig) -> None:
        """A worker that crashes (non-zero exit) is restarted by coordinator.

        The coordinator checks ``is_running`` (returncode is None) before
        entering the crash-detection block.  We simulate this by having the
        mock's ``returncode`` property return None on the first access (so
        ``is_running`` is True), then 1 on subsequent accesses (so the inner
        crash check triggers).
        """
        from unittest.mock import PropertyMock

        start_calls: list[int] = []

        async def mock_start(self: WorkerProcess) -> None:
            start_calls.append(self.worker_id)
            call_num = len([c for c in start_calls if c == self.worker_id])

            mock_proc = MagicMock()
            mock_proc.pid = (call_num * 10000) + self.worker_id
            mock_proc.wait = AsyncMock(return_value=0)

            if call_num == 1:
                # First start: return None once (is_running → True),
                # then 1 for crash detection
                type(mock_proc).returncode = PropertyMock(
                    side_effect=[None, 1] + [1] * 20,
                )
            else:
                # Restart: exit normally (return 0)
                type(mock_proc).returncode = PropertyMock(
                    side_effect=[None, 0] + [0] * 20,
                )

            self.process = mock_proc
            self._reader_task = None

        with patch.object(WorkerProcess, "start", mock_start):
            with patch.object(WorkerProcess, "stop", AsyncMock()):
                with patch(
                    "axon_agent.team.coordinator._send_telegram_summary",
                    AsyncMock(),
                ):
                    config = TeamConfig(
                        team=team_config.team,
                        project_dir=team_config.project_dir,
                        model=team_config.model,
                        num_workers=1,
                        poll_interval=0.01,
                    )
                    result = await run_team(config)

        # Worker 0 should have been started at least twice (initial + restart)
        w0_starts = [c for c in start_calls if c == 0]
        assert len(w0_starts) >= 2


# ---------------------------------------------------------------------------
# Telegram summary tests
# ---------------------------------------------------------------------------

class TestTelegramSummary:
    """Test Telegram summary report generation and sending."""

    @pytest.mark.asyncio
    async def test_summary_sent_on_completion(self, team_config: TeamConfig) -> None:
        """Telegram summary is sent after run_team completes."""
        async def mock_start(self: WorkerProcess) -> None:
            self.status.tasks_completed = 3
            self.status.update(WorkerState.STOPPED, message="Done")
            mock_proc = MagicMock()
            mock_proc.returncode = 0
            mock_proc.pid = 10000 + self.worker_id
            self.process = mock_proc

        with patch.object(WorkerProcess, "start", mock_start):
            with patch.object(WorkerProcess, "stop", AsyncMock()):
                with patch(
                    "axon_agent.team.coordinator._send_telegram_summary",
                    AsyncMock(),
                ) as mock_tg:
                    result = await run_team(team_config)

        mock_tg.assert_awaited_once()
        call_args = mock_tg.call_args
        passed_config = call_args[0][0]
        passed_result = call_args[0][1]
        assert passed_config.team == "TEST"
        assert isinstance(passed_result, TeamResult)
        assert passed_result.completed == 6  # 3 per worker * 2

    @pytest.mark.asyncio
    async def test_telegram_summary_format(self, team_config: TeamConfig) -> None:
        """_send_telegram_summary builds correct message content."""
        result = TeamResult(
            completed=5,
            failed=1,
            skipped=0,
            duration_seconds=300.0,
            worker_results=[
                WorkerStatus(worker_id=0, tasks_completed=3, tasks_failed=0),
                WorkerStatus(worker_id=1, tasks_completed=2, tasks_failed=1),
            ],
        )

        mock_session = AsyncMock()
        mock_session.initialize = AsyncMock()
        mock_session.call_tool = AsyncMock()
        mock_session.__aenter__ = AsyncMock(return_value=mock_session)
        mock_session.__aexit__ = AsyncMock(return_value=False)

        mock_streams = AsyncMock()
        mock_streams.__aenter__ = AsyncMock(return_value=(AsyncMock(), AsyncMock()))
        mock_streams.__aexit__ = AsyncMock(return_value=False)

        # sse_client and ClientSession are lazy-imported inside _send_telegram_summary
        with patch("mcp.client.sse.sse_client", return_value=mock_streams):
            with patch("mcp.client.session.ClientSession", return_value=mock_session):
                with patch("axon_agent.team.coordinator.load_dotenv"):
                    with patch.dict("os.environ", {
                        "TELEGRAM_MCP_URL": "http://localhost:8002/sse",
                        "MCP_API_KEY": "test-key",
                    }):
                        await _send_telegram_summary(team_config, result)

        # Verify Telegram_SendMessage was called with correct content
        mock_session.call_tool.assert_awaited_once()
        call_args = mock_session.call_tool.call_args
        assert call_args[0][0] == "Telegram_SendMessage"
        message = call_args[0][1]["message"]
        assert "Completed: 5" in message
        assert "Failed: 1" in message
        assert "Worker 0" in message
        assert "Worker 1" in message

    @pytest.mark.asyncio
    async def test_telegram_summary_skipped_without_url(self, team_config: TeamConfig) -> None:
        """Summary is skipped when TELEGRAM_MCP_URL is not set."""
        result = TeamResult(completed=1)

        with patch("axon_agent.team.coordinator.load_dotenv"):
            with patch.dict("os.environ", {"TELEGRAM_MCP_URL": ""}, clear=False):
                # Should not raise
                await _send_telegram_summary(team_config, result)

    @pytest.mark.asyncio
    async def test_telegram_summary_handles_connection_error(self, team_config: TeamConfig) -> None:
        """Summary gracefully handles MCP connection failure."""
        result = TeamResult(completed=1)

        with patch("axon_agent.team.coordinator.load_dotenv"):
            with patch.dict("os.environ", {
                "TELEGRAM_MCP_URL": "http://unreachable:9999/sse",
                "MCP_API_KEY": "key",
            }):
                with patch(
                    "mcp.client.sse.sse_client",
                    side_effect=ConnectionError("refused"),
                ):
                    # Should not raise — best-effort
                    await _send_telegram_summary(team_config, result)


# ---------------------------------------------------------------------------
# Result aggregation edge cases
# ---------------------------------------------------------------------------

class TestResultAggregation:
    """Test TeamResult aggregation from multiple workers."""

    def test_team_result_total(self) -> None:
        """TeamResult.total sums completed + failed + skipped."""
        r = TeamResult(completed=5, failed=2, skipped=1)
        assert r.total == 8

    def test_team_result_with_workers(self) -> None:
        """Worker results are correctly stored."""
        ws0 = WorkerStatus(worker_id=0, tasks_completed=3, tasks_failed=0)
        ws1 = WorkerStatus(worker_id=1, tasks_completed=2, tasks_failed=1)
        r = TeamResult(
            completed=5,
            failed=1,
            worker_results=[ws0, ws1],
        )
        assert len(r.worker_results) == 2
        assert r.worker_results[0].tasks_completed == 3
        assert r.worker_results[1].tasks_failed == 1

    def test_empty_team_result(self) -> None:
        """Empty TeamResult has sensible defaults."""
        r = TeamResult()
        assert r.total == 0
        assert r.duration_seconds == 0.0
        assert r.worker_results == []
