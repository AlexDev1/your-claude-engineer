"""Worker process for parallel task execution.

Each worker runs in its own subprocess, claims tasks from the shared TaskQueue,
executes them via a fresh Claude SDK session, and reports results back to the
coordinator via JSON-lines on stdout.

Usage (invoked by coordinator, not directly):
    axon-agent worker --worker-id 0 --team ENG --model claude-haiku-4-5-20251001 --project-dir /path
"""

from __future__ import annotations

import asyncio
import json
import logging
import os
import sys
import time
import traceback
from pathlib import Path
from typing import Any

from dotenv import load_dotenv

from axon_agent.team.protocol import TeamConfig, WorkerState, WorkerStatus
from axon_agent.team.task_queue import TaskQueue

logger = logging.getLogger("axon_agent.team.worker")

# ---------------------------------------------------------------------------
# JSON-line event helpers — coordinator reads these from subprocess stdout
# ---------------------------------------------------------------------------

def _emit(event: str, **data: Any) -> None:
    """Write a JSON-line event to stdout for the coordinator to consume."""
    payload = {"event": event, "ts": time.time(), **data}
    line = json.dumps(payload, ensure_ascii=False)
    sys.stdout.write(line + "\n")
    sys.stdout.flush()


def _emit_state(worker_id: int, state: WorkerState, task: str | None = None,
                message: str = "") -> None:
    """Emit a worker state-change event."""
    _emit("state", worker_id=worker_id, state=state.value, task=task, message=message)


def _emit_result(worker_id: int, task: str, success: bool, message: str = "") -> None:
    """Emit a task completion event."""
    _emit("result", worker_id=worker_id, task=task, success=success, message=message)


# ---------------------------------------------------------------------------
# Task execution via Claude SDK
# ---------------------------------------------------------------------------

async def _execute_task(
    issue: dict[str, Any],
    config: TeamConfig,
    worker_id: int,
) -> bool:
    """Execute a single task by running a Claude Agent SDK session.

    Creates a fresh ClaudeSDKClient for each task to avoid context-window
    exhaustion.  Uses the same session runner as the single-agent mode.

    Args:
        issue: Task issue dict from the MCP server (must contain 'identifier', 'title').
        config: Team configuration.
        worker_id: Numeric worker identifier.

    Returns:
        True if the task completed successfully, False otherwise.
    """
    # Lazy imports so that this module can be tested without the full SDK
    # installed — only the actual execution path pulls in heavy deps.
    from axon_agent.core.client import create_client  # noqa: WPS433
    from axon_agent.core.session import run_agent_session, COMPLETION_SIGNAL, SESSION_COMPLETE  # noqa: WPS433

    issue_id: str = issue.get("identifier", issue.get("id", "???"))
    title: str = issue.get("title", "Untitled")
    description: str = issue.get("description", "")

    _emit_state(worker_id, WorkerState.WORKING, task=issue_id,
                message=f"Executing: {title}")

    prompt = (
        f"Execute the following task for team {config.team}:\n"
        f"Working directory: {config.project_dir}\n\n"
        f"## Task\n"
        f"- ID: {issue_id}\n"
        f"- Title: {title}\n"
        f"- Description: {description}\n\n"
        f"## Instructions\n"
        f"1. Create branch agent/{issue_id.lower()}\n"
        f"2. Implement the task\n"
        f"3. Verify with browser_snapshot or tests\n"
        f"4. Commit with the task ID in the message\n"
        f"5. Report DONE when finished\n\n"
        f"When complete, output: {COMPLETION_SIGNAL}\n"
    )

    client = create_client(config.project_dir, config.model)
    try:
        async with client:
            result = await run_agent_session(client, prompt, config.project_dir)
            return result.status == SESSION_COMPLETE or COMPLETION_SIGNAL in result.response
    except Exception as exc:
        logger.error("Worker %d SDK error on %s: %s", worker_id, issue_id, exc)
        traceback.print_exc(file=sys.stderr)
        return False


# ---------------------------------------------------------------------------
# Main worker loop
# ---------------------------------------------------------------------------

async def run_worker(config: TeamConfig, worker_id: int) -> WorkerStatus:
    """Main worker loop: claim tasks, execute, report, repeat.

    Args:
        config: Shared team configuration.
        worker_id: Unique numeric worker ID (0-based).

    Returns:
        Final WorkerStatus summarizing the work done by this worker.
    """
    status = WorkerStatus(worker_id=worker_id)
    _emit_state(worker_id, WorkerState.IDLE, message="Starting")

    # Load env and connect to Task MCP
    load_dotenv(config.project_dir / ".env")
    mcp_url = os.environ.get("TASK_MCP_URL", "http://localhost:8001/sse")
    api_key = os.environ.get("MCP_API_KEY", "")

    queue = TaskQueue(team=config.team, mcp_url=mcp_url, api_key=api_key)
    try:
        await queue.connect()
    except Exception as exc:
        msg = f"Failed to connect to Task MCP: {exc}"
        logger.error("Worker %d: %s", worker_id, msg)
        _emit_state(worker_id, WorkerState.FAILED, message=msg)
        status.update(WorkerState.FAILED, message=msg)
        return status

    consecutive_empty = 0
    max_consecutive_empty = 3  # Exit after N consecutive poll cycles with no tasks

    try:
        while True:
            # Check max tasks limit
            if config.max_tasks is not None and status.tasks_completed >= config.max_tasks:
                logger.info("Worker %d reached max_tasks=%d", worker_id, config.max_tasks)
                break

            # Poll for available tasks
            _emit_state(worker_id, WorkerState.IDLE, message="Polling for tasks")
            try:
                tasks = await queue.get_todo_tasks()
            except Exception as exc:
                logger.warning("Worker %d poll error: %s", worker_id, exc)
                await asyncio.sleep(config.poll_interval)
                continue

            if not tasks:
                consecutive_empty += 1
                if consecutive_empty >= max_consecutive_empty:
                    logger.info("Worker %d: no tasks after %d polls, exiting",
                                worker_id, consecutive_empty)
                    break
                _emit_state(worker_id, WorkerState.IDLE,
                            message=f"No tasks (poll {consecutive_empty}/{max_consecutive_empty})")
                await asyncio.sleep(config.poll_interval)
                continue

            consecutive_empty = 0

            # Try to claim the highest-priority task
            claimed = False
            for task in tasks:
                task_id = task.get("identifier", task.get("id", ""))
                if not task_id:
                    continue

                _emit_state(worker_id, WorkerState.CLAIMING, task=task_id,
                            message=f"Claiming {task_id}")
                if await queue.claim_task(task_id, worker_id):
                    claimed = True
                    break

            if not claimed:
                # All tasks were claimed by other workers — wait and retry
                _emit_state(worker_id, WorkerState.IDLE,
                            message="All tasks claimed by others, waiting")
                await asyncio.sleep(config.poll_interval)
                continue

            # Execute the claimed task
            task_id = task.get("identifier", task.get("id", "???"))
            title = task.get("title", "Untitled")
            logger.info("Worker %d executing %s: %s", worker_id, task_id, title)

            try:
                success = await _execute_task(task, config, worker_id)
            except Exception as exc:
                logger.error("Worker %d task %s crashed: %s", worker_id, task_id, exc)
                traceback.print_exc(file=sys.stderr)
                success = False

            if success:
                status.tasks_completed += 1
                await queue.complete_task(task_id, worker_id)
                _emit_result(worker_id, task_id, success=True, message=f"Done: {title}")
                status.update(WorkerState.COMPLETED, task=task_id,
                              message=f"Done: {title}")
            else:
                status.tasks_failed += 1
                error_msg = f"Worker-{worker_id} failed to execute"
                await queue.fail_task(task_id, worker_id, error_msg)
                _emit_result(worker_id, task_id, success=False, message=error_msg)
                status.update(WorkerState.FAILED, task=task_id, message=error_msg)

            # Brief pause between tasks
            await asyncio.sleep(2.0)

    except asyncio.CancelledError:
        logger.info("Worker %d cancelled", worker_id)
    finally:
        await queue.disconnect()

    status.update(WorkerState.STOPPED, message="Worker finished")
    _emit_state(worker_id, WorkerState.STOPPED, message="Worker finished")
    return status


# ---------------------------------------------------------------------------
# Subprocess entry point
# ---------------------------------------------------------------------------

def _parse_worker_args() -> tuple[TeamConfig, int]:
    """Parse CLI args when running as a subprocess."""
    import argparse

    parser = argparse.ArgumentParser(description="Axon Agent worker process")
    parser.add_argument("--worker-id", type=int, required=True)
    parser.add_argument("--team", type=str, required=True)
    parser.add_argument("--model", type=str, required=True)
    parser.add_argument("--project-dir", type=str, required=True)
    parser.add_argument("--num-workers", type=int, default=3)
    parser.add_argument("--max-tasks", type=int, default=None)
    parser.add_argument("--poll-interval", type=float, default=10.0)
    args = parser.parse_args()

    config = TeamConfig(
        team=args.team,
        project_dir=Path(args.project_dir),
        model=args.model,
        num_workers=args.num_workers,
        max_tasks=args.max_tasks,
        poll_interval=args.poll_interval,
    )
    return config, args.worker_id


def main() -> int:
    """Subprocess entry point for ``axon-agent worker``."""
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [worker] %(levelname)s %(message)s",
        stream=sys.stderr,  # Logs go to stderr; JSON events go to stdout
    )

    config, worker_id = _parse_worker_args()
    logger.info("Worker %d starting (team=%s, model=%s)", worker_id, config.team, config.model)

    try:
        status = asyncio.run(run_worker(config, worker_id))
        if status.tasks_failed > 0 and status.tasks_completed == 0:
            return 1
        return 0
    except KeyboardInterrupt:
        logger.info("Worker %d interrupted", worker_id)
        return 130
    except Exception as exc:
        logger.error("Worker %d fatal: %s", worker_id, exc)
        traceback.print_exc(file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
