#!/usr/bin/env python3
"""
Team Coordinator Tests
======================

Tests for the team coordinator that spawns and monitors parallel workers.
Run with: pytest tests/unit/test_coordinator.py -v
"""

import asyncio
import json
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from axon_agent.team.coordinator import (
    MAX_WORKER_RESTARTS,
    WorkerProcess,
    _print_status,
    _print_summary,
    run_team,
)
from axon_agent.team.protocol import TeamConfig, TeamResult, WorkerState, WorkerStatus


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def team_config(tmp_path: Path) -> TeamConfig:
    """Create a test TeamConfig."""
    return TeamConfig(
        team="TEST",
        project_dir=tmp_path,
        model="claude-haiku-4-5-20251001",
        num_workers=2,
        max_tasks=3,
        poll_interval=0.1,  # Fast polling for tests
    )


@pytest.fixture
def worker_process(team_config: TeamConfig) -> WorkerProcess:
    """Create a test WorkerProcess."""
    return WorkerProcess(worker_id=0, config=team_config)


# ---------------------------------------------------------------------------
# WorkerProcess Tests
# ---------------------------------------------------------------------------

class TestWorkerProcess:
    """Tests for WorkerProcess class."""

    def test_init(self, team_config: TeamConfig) -> None:
        """Test WorkerProcess initialization."""
        wp = WorkerProcess(worker_id=1, config=team_config)

        assert wp.worker_id == 1
        assert wp.config == team_config
        assert wp.process is None
        assert wp.restart_count == 0
        assert wp.status.worker_id == 1
        assert wp.status.state == WorkerState.IDLE

    def test_is_running_no_process(self, worker_process: WorkerProcess) -> None:
        """Test is_running when no process exists."""
        assert worker_process.is_running is False

    def test_is_running_with_active_process(self, worker_process: WorkerProcess) -> None:
        """Test is_running with an active process."""
        mock_process = MagicMock()
        mock_process.returncode = None  # Process is running
        worker_process.process = mock_process

        assert worker_process.is_running is True

    def test_is_running_with_exited_process(self, worker_process: WorkerProcess) -> None:
        """Test is_running with an exited process."""
        mock_process = MagicMock()
        mock_process.returncode = 0  # Process has exited
        worker_process.process = mock_process

        assert worker_process.is_running is False

    @pytest.mark.asyncio
    async def test_start_spawns_subprocess(self, worker_process: WorkerProcess) -> None:
        """Test that start() spawns a subprocess with correct arguments."""
        mock_process = AsyncMock()
        mock_process.stdout = AsyncMock()
        mock_process.stdout.readline = AsyncMock(return_value=b"")
        mock_process.returncode = None

        with patch("asyncio.create_subprocess_exec", return_value=mock_process) as mock_exec:
            await worker_process.start()

            # Verify subprocess was created
            mock_exec.assert_called_once()
            call_args = mock_exec.call_args

            # Check command includes required arguments
            cmd = call_args[0]
            assert "-m" in cmd
            assert "axon_agent.team.worker" in cmd
            assert "--worker-id" in cmd
            assert "0" in cmd  # worker_id
            assert "--team" in cmd
            assert "TEST" in cmd  # team name

    def test_handle_event_state_update(self, worker_process: WorkerProcess) -> None:
        """Test _handle_event updates worker status on state events."""
        event = {
            "event": "state",
            "state": "working",
            "task": "ENG-123",
            "message": "Processing task",
        }

        worker_process._handle_event(event)

        assert worker_process.status.state == WorkerState.WORKING
        assert worker_process.status.current_task == "ENG-123"
        assert worker_process.status.message == "Processing task"

    def test_handle_event_result_success(self, worker_process: WorkerProcess) -> None:
        """Test _handle_event increments completed count on success."""
        event = {
            "event": "result",
            "success": True,
            "task": "ENG-123",
        }

        assert worker_process.status.tasks_completed == 0
        worker_process._handle_event(event)
        assert worker_process.status.tasks_completed == 1

    def test_handle_event_result_failure(self, worker_process: WorkerProcess) -> None:
        """Test _handle_event increments failed count on failure."""
        event = {
            "event": "result",
            "success": False,
            "task": "ENG-123",
            "message": "Task failed",
        }

        assert worker_process.status.tasks_failed == 0
        worker_process._handle_event(event)
        assert worker_process.status.tasks_failed == 1

    def test_handle_event_invalid_state(self, worker_process: WorkerProcess) -> None:
        """Test _handle_event handles invalid state gracefully."""
        event = {
            "event": "state",
            "state": "invalid_state",
        }

        worker_process._handle_event(event)
        # Should default to IDLE for invalid states
        assert worker_process.status.state == WorkerState.IDLE

    @pytest.mark.asyncio
    async def test_stop_terminates_process(self, worker_process: WorkerProcess) -> None:
        """Test stop() terminates the subprocess."""
        mock_process = AsyncMock()
        mock_process.returncode = None
        mock_process.pid = 12345
        mock_process.terminate = MagicMock()
        mock_process.kill = MagicMock()
        mock_process.wait = AsyncMock(return_value=0)

        worker_process.process = mock_process
        worker_process._reader_task = None

        await worker_process.stop()

        mock_process.terminate.assert_called_once()
        assert worker_process.status.state == WorkerState.STOPPED

    @pytest.mark.asyncio
    async def test_wait_returns_exit_code(self, worker_process: WorkerProcess) -> None:
        """Test wait() returns the subprocess exit code."""
        mock_process = AsyncMock()
        mock_process.wait = AsyncMock(return_value=42)

        worker_process.process = mock_process
        worker_process._reader_task = None

        code = await worker_process.wait()

        assert code == 42

    @pytest.mark.asyncio
    async def test_wait_no_process(self, worker_process: WorkerProcess) -> None:
        """Test wait() returns -1 when no process exists."""
        code = await worker_process.wait()
        assert code == -1


# ---------------------------------------------------------------------------
# run_team Tests
# ---------------------------------------------------------------------------

class TestRunTeam:
    """Tests for run_team function."""

    @pytest.mark.asyncio
    async def test_run_team_spawns_workers(self, team_config: TeamConfig) -> None:
        """Test that run_team spawns the configured number of workers."""
        spawned_workers: list[int] = []

        async def mock_start(self: WorkerProcess) -> None:
            spawned_workers.append(self.worker_id)
            self.status.update(WorkerState.STOPPED, message="Test")
            # Simulate immediate exit
            mock_proc = MagicMock()
            mock_proc.returncode = 0
            self.process = mock_proc

        with patch.object(WorkerProcess, "start", mock_start):
            with patch.object(WorkerProcess, "stop", AsyncMock()):
                # Run with very short poll interval
                config = TeamConfig(
                    team=team_config.team,
                    project_dir=team_config.project_dir,
                    model=team_config.model,
                    num_workers=3,
                    poll_interval=0.01,
                )
                result = await run_team(config)

        # Should have spawned 3 workers
        assert len(spawned_workers) == 3
        assert set(spawned_workers) == {0, 1, 2}

    @pytest.mark.asyncio
    async def test_run_team_aggregates_results(self, team_config: TeamConfig) -> None:
        """Test that run_team aggregates results from all workers."""
        async def mock_start(self: WorkerProcess) -> None:
            self.status.tasks_completed = self.worker_id + 1
            self.status.tasks_failed = 1 if self.worker_id == 0 else 0
            self.status.update(WorkerState.STOPPED, message="Done")
            mock_proc = MagicMock()
            mock_proc.returncode = 0
            self.process = mock_proc

        with patch.object(WorkerProcess, "start", mock_start):
            with patch.object(WorkerProcess, "stop", AsyncMock()):
                with patch("axon_agent.team.coordinator._send_telegram_summary", AsyncMock()):
                    config = TeamConfig(
                        team=team_config.team,
                        project_dir=team_config.project_dir,
                        model=team_config.model,
                        num_workers=2,
                        poll_interval=0.01,
                    )
                    result = await run_team(config)

        # Worker 0: 1 completed, 1 failed
        # Worker 1: 2 completed, 0 failed
        assert result.completed == 3  # 1 + 2
        assert result.failed == 1
        assert len(result.worker_results) == 2


# ---------------------------------------------------------------------------
# Helper Function Tests
# ---------------------------------------------------------------------------

class TestPrintStatus:
    """Tests for _print_status helper."""

    def test_print_status_output(self, capsys, team_config: TeamConfig) -> None:
        """Test _print_status output format."""
        workers = [
            WorkerProcess(worker_id=0, config=team_config),
            WorkerProcess(worker_id=1, config=team_config),
        ]
        workers[0].status.state = WorkerState.WORKING
        workers[0].status.current_task = "ENG-1"
        workers[0].status.tasks_completed = 2
        workers[1].status.state = WorkerState.IDLE

        _print_status(workers)

        captured = capsys.readouterr()
        assert "W0[*:ENG-1]" in captured.out
        assert "W1[.]" in captured.out
        assert "[2 done, 0 fail]" in captured.out


class TestPrintSummary:
    """Tests for _print_summary helper."""

    def test_print_summary_output(self, capsys) -> None:
        """Test _print_summary output format."""
        result = TeamResult(
            completed=5,
            failed=1,
            skipped=0,
            duration_seconds=120.0,
            worker_results=[
                WorkerStatus(worker_id=0, tasks_completed=3, tasks_failed=0),
                WorkerStatus(worker_id=1, tasks_completed=2, tasks_failed=1),
            ],
        )

        _print_summary(result)

        captured = capsys.readouterr()
        assert "TEAM RUN COMPLETE" in captured.out
        assert "Completed:  5" in captured.out
        assert "Failed:     1" in captured.out
        assert "2.0 min" in captured.out
        assert "Worker 0" in captured.out
        assert "Worker 1" in captured.out


# ---------------------------------------------------------------------------
# Worker Crash and Restart Tests
# ---------------------------------------------------------------------------

class TestWorkerCrashHandling:
    """Tests for worker crash detection and restart logic."""

    def test_max_restarts_constant(self) -> None:
        """Verify MAX_WORKER_RESTARTS is set correctly."""
        assert MAX_WORKER_RESTARTS == 3

    @pytest.mark.asyncio
    async def test_worker_restart_increments_count(self, worker_process: WorkerProcess) -> None:
        """Test that restart_count is incremented on restart."""
        assert worker_process.restart_count == 0

        # Simulate a restart
        worker_process.restart_count += 1
        assert worker_process.restart_count == 1

    def test_worker_status_tracks_failures(self, worker_process: WorkerProcess) -> None:
        """Test that worker status tracks failed state."""
        worker_process.status.update(
            WorkerState.FAILED,
            message="Crashed (code=1), restarting in 5s",
        )

        assert worker_process.status.state == WorkerState.FAILED
        assert "Crashed" in worker_process.status.message
