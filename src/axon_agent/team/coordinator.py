"""Team coordinator — spawns and monitors parallel workers.

The coordinator is the top-level entry point for team mode.  It:
1. Spawns N worker subprocesses (``axon-agent worker ...``).
2. Reads JSON-line events from each worker's stdout to track progress.
3. Restarts crashed workers with exponential backoff.
4. When all tasks are done, sends a Telegram summary and shuts down.

Usage (called from the CLI):
    await run_team(TeamConfig(...))
"""

from __future__ import annotations

import asyncio
import json
import logging
import os
import sys
import time
from pathlib import Path
from typing import Any

from dotenv import load_dotenv

from axon_agent.team.protocol import TeamConfig, TeamResult, WorkerState, WorkerStatus

logger = logging.getLogger("axon_agent.team.coordinator")

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------
MAX_WORKER_RESTARTS = 3
INITIAL_RESTART_DELAY = 5.0    # seconds
MAX_RESTART_DELAY = 60.0       # seconds
RESTART_BACKOFF_FACTOR = 2.0


# ---------------------------------------------------------------------------
# Worker subprocess management
# ---------------------------------------------------------------------------

class WorkerProcess:
    """Wraps an ``asyncio.subprocess.Process`` for a single worker."""

    def __init__(self, worker_id: int, config: TeamConfig) -> None:
        self.worker_id = worker_id
        self.config = config
        self.process: asyncio.subprocess.Process | None = None
        self.status = WorkerStatus(worker_id=worker_id)
        self.restart_count = 0
        self._reader_task: asyncio.Task[None] | None = None

    @property
    def is_running(self) -> bool:
        return self.process is not None and self.process.returncode is None

    async def start(self) -> None:
        """Spawn the worker as a subprocess."""
        cmd = [
            sys.executable, "-m", "axon_agent.team.worker",
            "--worker-id", str(self.worker_id),
            "--team", self.config.team,
            "--model", self.config.model,
            "--project-dir", str(self.config.project_dir),
            "--num-workers", str(self.config.num_workers),
            "--poll-interval", str(self.config.poll_interval),
        ]
        if self.config.max_tasks is not None:
            cmd.extend(["--max-tasks", str(self.config.max_tasks)])

        logger.info("Starting worker %d: %s", self.worker_id, " ".join(cmd))

        self.process = await asyncio.create_subprocess_exec(
            *cmd,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
            cwd=str(self.config.project_dir),
        )
        self._reader_task = asyncio.create_task(
            self._read_events(),
            name=f"worker-{self.worker_id}-reader",
        )
        self.status.update(WorkerState.IDLE, message="Subprocess started")

    async def _read_events(self) -> None:
        """Read JSON-line events from the worker's stdout."""
        if not self.process or not self.process.stdout:
            return

        while True:
            try:
                line = await self.process.stdout.readline()
            except (asyncio.CancelledError, ConnectionError):
                break

            if not line:
                break  # EOF — process exited

            text = line.decode("utf-8", errors="replace").strip()
            if not text:
                continue

            try:
                event = json.loads(text)
            except json.JSONDecodeError:
                # Not a JSON-line — treat as plain log output
                logger.debug("Worker %d stdout: %s", self.worker_id, text)
                continue

            self._handle_event(event)

    def _handle_event(self, event: dict[str, Any]) -> None:
        """Process a single JSON-line event from the worker."""
        etype = event.get("event", "")

        if etype == "state":
            state_str = event.get("state", "idle")
            try:
                state = WorkerState(state_str)
            except ValueError:
                state = WorkerState.IDLE
            self.status.update(
                state=state,
                task=event.get("task"),
                message=event.get("message", ""),
            )

        elif etype == "result":
            success = event.get("success", False)
            task = event.get("task", "???")
            if success:
                self.status.tasks_completed += 1
                logger.info("Worker %d completed %s", self.worker_id, task)
            else:
                self.status.tasks_failed += 1
                logger.warning("Worker %d failed %s: %s",
                               self.worker_id, task, event.get("message", ""))

    async def wait(self) -> int:
        """Wait for the subprocess to exit and return its exit code."""
        if not self.process:
            return -1
        code = await self.process.wait()
        if self._reader_task and not self._reader_task.done():
            self._reader_task.cancel()
            try:
                await self._reader_task
            except asyncio.CancelledError:
                pass
        return code

    async def stop(self) -> None:
        """Gracefully terminate the worker subprocess."""
        if not self.is_running:
            return
        assert self.process is not None

        logger.info("Stopping worker %d (pid=%d)", self.worker_id, self.process.pid)
        try:
            self.process.terminate()
            try:
                await asyncio.wait_for(self.process.wait(), timeout=10.0)
            except asyncio.TimeoutError:
                logger.warning("Worker %d did not stop in time, killing", self.worker_id)
                self.process.kill()
                await self.process.wait()
        except ProcessLookupError:
            pass  # Already exited

        if self._reader_task and not self._reader_task.done():
            self._reader_task.cancel()
            try:
                await self._reader_task
            except asyncio.CancelledError:
                pass

        self.status.update(WorkerState.STOPPED, message="Terminated by coordinator")


# ---------------------------------------------------------------------------
# Telegram notification helper
# ---------------------------------------------------------------------------

async def _send_telegram_summary(config: TeamConfig, result: TeamResult) -> None:
    """Send a team run summary via Telegram MCP (best-effort)."""
    try:
        from mcp.client.session import ClientSession
        from mcp.client.sse import sse_client

        load_dotenv(config.project_dir / ".env")
        telegram_url = os.environ.get("TELEGRAM_MCP_URL", "")
        api_key = os.environ.get("MCP_API_KEY", "")

        if not telegram_url:
            logger.info("TELEGRAM_MCP_URL not set, skipping summary notification")
            return

        headers = {}
        if api_key:
            headers["Authorization"] = f"Bearer {api_key}"

        duration_min = result.duration_seconds / 60.0
        lines = [
            ":checkered_flag: <b>Team run complete</b>",
            "",
            f":white_check_mark: Completed: {result.completed}",
            f":x: Failed: {result.failed}",
            f":fast_forward: Skipped: {result.skipped}",
            f":stopwatch: Duration: {duration_min:.1f}min",
            f":busts_in_silhouette: Workers: {len(result.worker_results)}",
        ]

        # Per-worker breakdown
        for ws in result.worker_results:
            emoji = ":white_check_mark:" if ws.tasks_failed == 0 else ":warning:"
            lines.append(
                f"  {emoji} Worker {ws.worker_id}: "
                f"{ws.tasks_completed} done, {ws.tasks_failed} failed"
            )

        message = "\n".join(lines)

        async with sse_client(telegram_url, headers=headers) as (read_s, write_s):
            async with ClientSession(read_s, write_s) as session:
                await session.initialize()
                await session.call_tool("Telegram_SendMessage", {"message": message})

        logger.info("Telegram summary sent")
    except Exception as exc:
        logger.warning("Failed to send Telegram summary: %s", exc)


# ---------------------------------------------------------------------------
# Main coordinator
# ---------------------------------------------------------------------------

async def run_team(config: TeamConfig) -> TeamResult:
    """Run a team of parallel workers.

    This is the main entry point for team mode.  It spawns ``config.num_workers``
    worker subprocesses and monitors them until all tasks are done or all
    workers have stopped.

    Args:
        config: Team configuration (immutable for the entire run).

    Returns:
        TeamResult summarizing completed / failed / skipped tasks.
    """
    start_time = time.time()
    result = TeamResult()

    print()
    print("=" * 70)
    print("  TEAM MODE — PARALLEL TASK EXECUTION")
    print("=" * 70)
    print(f"  Team:       {config.team}")
    print(f"  Workers:    {config.num_workers}")
    print(f"  Model:      {config.model}")
    print(f"  Project:    {config.project_dir}")
    print(f"  Max tasks:  {config.max_tasks or 'unlimited'}")
    print(f"  Poll:       {config.poll_interval}s")
    print("=" * 70)
    print()

    # Spawn workers
    workers: list[WorkerProcess] = []
    for i in range(config.num_workers):
        wp = WorkerProcess(worker_id=i, config=config)
        workers.append(wp)
        await wp.start()
        # Stagger worker starts to reduce MCP contention
        if i < config.num_workers - 1:
            await asyncio.sleep(2.0)

    # Monitor loop — wait for all workers to finish, restarting on crash
    restart_delays: dict[int, float] = {i: INITIAL_RESTART_DELAY for i in range(config.num_workers)}

    try:
        while True:
            all_stopped = True

            for wp in workers:
                if not wp.is_running:
                    continue
                all_stopped = False

                # Check if the process has exited
                if wp.process and wp.process.returncode is not None:
                    code = wp.process.returncode
                    logger.info("Worker %d exited with code %d", wp.worker_id, code)

                    # Drain remaining events
                    if wp._reader_task and not wp._reader_task.done():
                        try:
                            await asyncio.wait_for(wp._reader_task, timeout=2.0)
                        except (asyncio.TimeoutError, asyncio.CancelledError):
                            pass

                    if code == 0:
                        # Normal exit — worker found no more tasks
                        wp.status.update(WorkerState.STOPPED, message="No more tasks")
                    elif wp.restart_count < MAX_WORKER_RESTARTS:
                        # Abnormal exit — restart with backoff
                        wp.restart_count += 1
                        delay = restart_delays[wp.worker_id]
                        logger.warning(
                            "Worker %d crashed (code=%d), restart %d/%d in %.1fs",
                            wp.worker_id, code, wp.restart_count,
                            MAX_WORKER_RESTARTS, delay,
                        )
                        wp.status.update(
                            WorkerState.FAILED,
                            message=f"Crashed (code={code}), restarting in {delay:.0f}s",
                        )
                        await asyncio.sleep(delay)

                        # Exponential backoff for next restart
                        restart_delays[wp.worker_id] = min(
                            delay * RESTART_BACKOFF_FACTOR, MAX_RESTART_DELAY,
                        )

                        await wp.start()
                        all_stopped = False
                    else:
                        logger.error(
                            "Worker %d exhausted restarts (%d), giving up",
                            wp.worker_id, MAX_WORKER_RESTARTS,
                        )
                        wp.status.update(
                            WorkerState.STOPPED,
                            message=f"Exhausted {MAX_WORKER_RESTARTS} restarts",
                        )

            if all_stopped:
                break

            # Print periodic status
            _print_status(workers)
            await asyncio.sleep(config.poll_interval)

    except asyncio.CancelledError:
        logger.info("Coordinator cancelled, stopping workers...")
    except KeyboardInterrupt:
        logger.info("Keyboard interrupt, stopping workers...")
    finally:
        # Graceful shutdown of all workers
        stop_tasks = [wp.stop() for wp in workers if wp.is_running]
        if stop_tasks:
            await asyncio.gather(*stop_tasks, return_exceptions=True)

    # Aggregate results
    elapsed = time.time() - start_time
    result.duration_seconds = elapsed
    for wp in workers:
        result.completed += wp.status.tasks_completed
        result.failed += wp.status.tasks_failed
        result.worker_results.append(wp.status)

    # Print final summary
    _print_summary(result)

    # Send Telegram notification (best-effort)
    await _send_telegram_summary(config, result)

    return result


def _print_status(workers: list[WorkerProcess]) -> None:
    """Print a compact status line for all workers."""
    parts: list[str] = []
    for wp in workers:
        s = wp.status
        state_char = {
            WorkerState.IDLE: ".",
            WorkerState.CLAIMING: "?",
            WorkerState.WORKING: "*",
            WorkerState.COMPLETED: "+",
            WorkerState.FAILED: "!",
            WorkerState.STOPPED: "x",
        }.get(s.state, "?")

        task_str = f":{s.current_task}" if s.current_task else ""
        parts.append(f"W{wp.worker_id}[{state_char}{task_str}]")

    line = "  ".join(parts)
    total_done = sum(wp.status.tasks_completed for wp in workers)
    total_fail = sum(wp.status.tasks_failed for wp in workers)
    print(f"  [{total_done} done, {total_fail} fail] {line}")


def _print_summary(result: TeamResult) -> None:
    """Print the final team run summary."""
    print()
    print("=" * 70)
    print("  TEAM RUN COMPLETE")
    print("=" * 70)
    print(f"  Completed:  {result.completed}")
    print(f"  Failed:     {result.failed}")
    print(f"  Skipped:    {result.skipped}")
    duration_min = result.duration_seconds / 60.0
    print(f"  Duration:   {duration_min:.1f} min")
    print()
    for ws in result.worker_results:
        status_icon = "OK" if ws.tasks_failed == 0 else "WARN"
        print(f"  Worker {ws.worker_id} [{status_icon}]: "
              f"{ws.tasks_completed} completed, {ws.tasks_failed} failed, "
              f"restarts={ws.message}")
    print("=" * 70)
    print()
