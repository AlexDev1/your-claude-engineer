"""Team coordination protocol — shared data types."""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path


class WorkerState(str, Enum):
    """Worker lifecycle states."""
    IDLE = "idle"
    CLAIMING = "claiming"
    WORKING = "working"
    COMPLETED = "completed"
    FAILED = "failed"
    STOPPED = "stopped"


@dataclass(frozen=True)
class TeamConfig:
    """Immutable configuration for a team run."""
    team: str
    project_dir: Path
    model: str
    num_workers: int = 3
    max_tasks: int | None = None
    poll_interval: float = 10.0
    dashboard_port: int = 8003
    no_dashboard: bool = False


@dataclass
class WorkerStatus:
    """Mutable status of a single worker."""
    worker_id: int
    state: WorkerState = WorkerState.IDLE
    current_task: str | None = None
    message: str = ""
    tasks_completed: int = 0
    tasks_failed: int = 0
    started_at: float = field(default_factory=time.time)
    last_update: float = field(default_factory=time.time)

    def update(self, state: WorkerState, task: str | None = None, message: str = "") -> None:
        self.state = state
        self.current_task = task
        self.message = message
        self.last_update = time.time()


@dataclass
class TeamResult:
    """Summary of a team run."""
    completed: int = 0
    failed: int = 0
    skipped: int = 0
    duration_seconds: float = 0.0
    worker_results: list[WorkerStatus] = field(default_factory=list)

    @property
    def total(self) -> int:
        return self.completed + self.failed + self.skipped
