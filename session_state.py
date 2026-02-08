"""
Session State Machine for Granular Error Recovery
==================================================

Implements checkpoint-based recovery with:
- SessionPhase enum for clear session states
- Phase-level retry with smart restart logic
- Graceful degradation matrix for different error types
- Crash recovery from .agent/session_state.json

ENG-35: Granular Error Recovery
"""

import asyncio
import json
import logging
import os
import tempfile
import time
import traceback
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from pathlib import Path
from typing import Any, Callable, Coroutine, TypeAlias

# Configure logging
logger = logging.getLogger("session_state")


class SessionPhase(Enum):
    """Session phases for checkpoint-based recovery.

    Phases are ordered by their typical execution sequence.
    The numeric value indicates the phase order for comparison.
    """

    ORIENT = ("orient", 1)  # Step 1: read project state
    STATUS_CHECK = ("status", 2)  # Step 2: get task status
    VERIFICATION = ("verify", 3)  # Step 3: run verification
    IMPLEMENTATION = ("implement", 4)  # Step 4: coding
    COMMIT = ("commit", 5)  # Step 5: git commit
    MARK_DONE = ("mark_done", 6)  # Step 6: update task status
    NOTIFY = ("notify", 7)  # Step 7: telegram
    MEMORY_FLUSH = ("flush", 8)  # Step 8: save context

    def __init__(self, phase_name: str, order: int):
        self.phase_name = phase_name
        self.order = order

    @classmethod
    def from_string(cls, name: str) -> "SessionPhase":
        """Create phase from string name.

        Accepts:
        - Exact phase_name match (e.g., "orient", "implement")
        - Enum name match (e.g., "ORIENT", "IMPLEMENTATION")
        - Case-insensitive enum name (e.g., "implementation")
        """
        name_lower = name.lower()
        for phase in cls:
            if phase.phase_name == name:
                return phase
            if phase.name == name:
                return phase
            if phase.name.lower() == name_lower:
                return phase
        raise ValueError(f"Unknown phase: {name}")

    def is_before_or_equal(self, other: "SessionPhase") -> bool:
        """Check if this phase is before or equal to another."""
        return self.order <= other.order

    def is_after(self, other: "SessionPhase") -> bool:
        """Check if this phase is after another."""
        return self.order > other.order


class RetryStrategy(Enum):
    """Strategy for retrying a failed phase (ENG-67).

    Determines how far back the session should rewind after a phase failure:
    - RETRY_CURRENT: Retry just the failed phase (late phases where code is written)
    - RETRY_FROM_ORIENT: Restart from ORIENT (cheap early phases)
    - RETRY_IMPLEMENTATION: Retry from IMPLEMENTATION (code needs rework)
    - ESCALATE: Give up and mark the issue as blocked
    """

    RETRY_CURRENT = "retry_current"
    RETRY_FROM_ORIENT = "retry_from_orient"
    RETRY_IMPLEMENTATION = "retry_implementation"
    ESCALATE = "escalate"


# Maximum retry attempts per phase before escalation (ENG-67)
MAX_PHASE_RETRIES: int = 2

# Maximum age (hours) for a recovery state before it is considered stale (ENG-69)
STALE_RECOVERY_HOURS: float = 24.0


class ErrorType(Enum):
    """Categories of errors for graceful degradation."""

    MCP_TIMEOUT = "mcp_timeout"
    PLAYWRIGHT_CRASH = "playwright_crash"
    GIT_ERROR = "git_error"
    RATE_LIMIT = "rate_limit"
    NETWORK_ERROR = "network_error"
    UNKNOWN = "unknown"


@dataclass
class PhaseAttempt:
    """Track attempts for a specific phase."""

    phase: SessionPhase
    attempt: int = 0
    max_attempts: int = 2
    last_error: str | None = None
    last_attempt_time: float | None = None

    @property
    def can_retry(self) -> bool:
        """Check if more retries are available."""
        return self.attempt < self.max_attempts

    def record_attempt(self, error: str | None = None) -> None:
        """Record an attempt."""
        self.attempt += 1
        self.last_error = error
        self.last_attempt_time = time.time()


@dataclass
class SessionState:
    """Persistent session state for crash recovery.

    Tracks the current phase, completed phases, timing, retry counts,
    and a running error log for full session observability (ENG-66).

    Attributes:
        phase: Current session phase
        issue_id: Issue being worked on (e.g., "ENG-35")
        attempt: Overall session attempt number
        started_at: ISO timestamp when session started
        last_updated: ISO timestamp of last phase transition
        completed_phases: List of phase names that completed successfully
        phase_history: Chronological log of phase transitions with timestamps (ENG-66)
        phase_attempts: Per-phase retry counts (phase_name -> attempt count)
        error_log: Running log of error messages with timestamps
        uncommitted_changes: Whether git has uncommitted changes
        degraded_services: List of services operating in degraded mode
        last_error: Most recent error message
        last_error_type: Classification of most recent error
    """

    phase: SessionPhase
    issue_id: str
    attempt: int = 1
    started_at: str = field(default_factory=lambda: datetime.now().isoformat())
    last_updated: str = field(default_factory=lambda: datetime.now().isoformat())
    completed_phases: list[str] = field(default_factory=list)
    phase_history: list[dict[str, str]] = field(default_factory=list)
    phase_attempts: dict[str, int] = field(default_factory=dict)
    error_log: list[str] = field(default_factory=list)
    uncommitted_changes: bool = False
    degraded_services: list[str] = field(default_factory=list)
    last_error: str | None = None
    last_error_type: ErrorType | None = None

    def to_dict(self) -> dict[str, Any]:
        """Serialize to dictionary for JSON storage."""
        return {
            "phase": self.phase.phase_name,
            "issue_id": self.issue_id,
            "attempt": self.attempt,
            "started_at": self.started_at,
            "last_updated": self.last_updated,
            "completed_phases": self.completed_phases,
            "phase_history": self.phase_history,
            "phase_attempts": self.phase_attempts,
            "error_log": self.error_log,
            "uncommitted_changes": self.uncommitted_changes,
            "degraded_services": self.degraded_services,
            "last_error": self.last_error,
            "last_error_type": self.last_error_type.value if self.last_error_type else None,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "SessionState":
        """Deserialize from dictionary."""
        return cls(
            phase=SessionPhase.from_string(data["phase"]),
            issue_id=data["issue_id"],
            attempt=data.get("attempt", 1),
            started_at=data.get("started_at", datetime.now().isoformat()),
            last_updated=data.get("last_updated", datetime.now().isoformat()),
            completed_phases=data.get("completed_phases", []),
            phase_history=data.get("phase_history", []),
            phase_attempts=data.get("phase_attempts", {}),
            error_log=data.get("error_log", []),
            uncommitted_changes=data.get("uncommitted_changes", False),
            degraded_services=data.get("degraded_services", []),
            last_error=data.get("last_error"),
            last_error_type=ErrorType(data["last_error_type"]) if data.get("last_error_type") else None,
        )


class GracefulDegradation:
    """Graceful degradation strategies for different error types."""

    # Maximum retries before degradation
    MAX_RETRIES: dict[ErrorType, int] = {
        ErrorType.MCP_TIMEOUT: 3,
        ErrorType.PLAYWRIGHT_CRASH: 2,
        ErrorType.GIT_ERROR: 3,
        ErrorType.RATE_LIMIT: 3,
        ErrorType.NETWORK_ERROR: 3,
        ErrorType.UNKNOWN: 2,
    }

    # Exponential backoff delays in seconds for rate limits
    RATE_LIMIT_DELAYS: list[int] = [30, 60, 120]

    @classmethod
    def get_max_retries(cls, error_type: ErrorType) -> int:
        """Get maximum retries for an error type."""
        return cls.MAX_RETRIES.get(error_type, 2)

    @classmethod
    def get_backoff_delay(cls, attempt: int, error_type: ErrorType) -> float:
        """Get backoff delay for retry attempt.

        Args:
            attempt: Current attempt number (1-based)
            error_type: Type of error

        Returns:
            Delay in seconds before retry
        """
        if error_type == ErrorType.RATE_LIMIT:
            index = min(attempt - 1, len(cls.RATE_LIMIT_DELAYS) - 1)
            return cls.RATE_LIMIT_DELAYS[index]
        elif error_type == ErrorType.MCP_TIMEOUT:
            return 5.0 * attempt  # 5s, 10s, 15s
        elif error_type == ErrorType.NETWORK_ERROR:
            return 3.0 * attempt  # 3s, 6s, 9s
        else:
            return 2.0 * attempt  # Default: 2s, 4s, 6s

    @classmethod
    def should_skip_service(cls, error_type: ErrorType, phase: SessionPhase) -> bool:
        """Determine if a service should be skipped after max retries.

        Some services can be skipped without blocking the workflow:
        - MCP timeout -> skip notification/status update, continue coding
        - Playwright crash -> skip screenshot, add comment
        """
        if error_type == ErrorType.MCP_TIMEOUT:
            # Can skip notification and status update phases
            return phase in (SessionPhase.NOTIFY, SessionPhase.MARK_DONE)
        elif error_type == ErrorType.PLAYWRIGHT_CRASH:
            # Playwright is used in VERIFICATION phase - can skip screenshots
            return phase == SessionPhase.VERIFICATION
        return False

    @classmethod
    def get_degradation_message(cls, error_type: ErrorType, phase: SessionPhase) -> str:
        """Get human-readable degradation message."""
        if error_type == ErrorType.MCP_TIMEOUT:
            if phase == SessionPhase.NOTIFY:
                return "Telegram notification skipped due to MCP timeout"
            elif phase == SessionPhase.MARK_DONE:
                return "Task status update skipped due to MCP timeout"
        elif error_type == ErrorType.PLAYWRIGHT_CRASH:
            return "Screenshot unavailable due to Playwright crash"
        elif error_type == ErrorType.GIT_ERROR:
            return "Git operation failed - changes saved to diff file"
        return f"Service degraded: {error_type.value}"


class SessionStateManager:
    """Manages session state persistence and recovery."""

    STATE_FILE = ".agent/session_state.json"

    def __init__(self, project_dir: Path):
        self.project_dir = project_dir
        self.state_file = project_dir / self.STATE_FILE
        self._current_state: SessionState | None = None
        self._phase_attempts: dict[SessionPhase, PhaseAttempt] = {}

    @property
    def current_state(self) -> SessionState | None:
        """Get current session state."""
        return self._current_state

    def _ensure_agent_dir(self) -> None:
        """Ensure .agent directory exists."""
        agent_dir = self.project_dir / ".agent"
        agent_dir.mkdir(parents=True, exist_ok=True)

    def save_state(self) -> None:
        """Save current state to file using atomic write.

        Writes to a temporary file in the same directory, then renames
        to the target path. This prevents corrupt/partial writes if the
        process crashes mid-write.
        """
        if self._current_state is None:
            return

        self._ensure_agent_dir()

        try:
            # Write to temp file in the same directory, then atomic rename
            parent_dir = self.state_file.parent
            fd, tmp_path = tempfile.mkstemp(
                suffix=".tmp",
                prefix="session_state_",
                dir=str(parent_dir),
            )
            try:
                with os.fdopen(fd, "w") as f:
                    json.dump(self._current_state.to_dict(), f, indent=2)
                os.replace(tmp_path, str(self.state_file))
            except BaseException:
                # Clean up temp file on any error
                try:
                    os.unlink(tmp_path)
                except OSError:
                    pass
                raise
            logger.debug(f"Session state saved: {self._current_state.phase.phase_name}")
        except IOError as e:
            logger.error(f"Failed to save session state: {e}")

    def load_state(self) -> SessionState | None:
        """Load state from file if exists."""
        if not self.state_file.exists():
            return None

        try:
            with open(self.state_file, "r") as f:
                data = json.load(f)
            state = SessionState.from_dict(data)
            logger.info(f"Loaded session state: phase={state.phase.phase_name}, issue={state.issue_id}")
            return state
        except (IOError, json.JSONDecodeError, ValueError) as e:
            logger.warning(f"Failed to load session state: {e}")
            return None

    def clear_state(self) -> None:
        """Clear saved state (called on successful completion)."""
        if self.state_file.exists():
            try:
                self.state_file.unlink()
                logger.debug("Session state cleared")
            except IOError as e:
                logger.warning(f"Failed to clear session state: {e}")
        self._current_state = None
        self._phase_attempts.clear()

    def start_session(self, issue_id: str) -> SessionState:
        """Start a new session.

        Creates a fresh SessionState at the ORIENT phase and records
        the initial phase in phase_history (ENG-66).

        Args:
            issue_id: The issue being worked on (e.g., "ENG-66")

        Returns:
            The newly created SessionState
        """
        now = datetime.now().isoformat()
        self._current_state = SessionState(
            phase=SessionPhase.ORIENT,
            issue_id=issue_id,
            started_at=now,
            last_updated=now,
            phase_history=[{"phase": "orient", "timestamp": now}],
        )
        self._phase_attempts.clear()
        self.save_state()
        return self._current_state

    def transition_to(self, phase: SessionPhase) -> None:
        """Transition to a new phase.

        Records the old phase as completed, appends a phase_history entry
        with phase name and ISO timestamp, updates last_updated,
        and persists state to disk (ENG-66).

        Args:
            phase: The new phase to transition to

        Raises:
            RuntimeError: If no active session exists
        """
        if self._current_state is None:
            raise RuntimeError("No active session")

        old_phase = self._current_state.phase
        now = datetime.now().isoformat()

        # Mark old phase as completed if not already tracked
        if old_phase.phase_name not in self._current_state.completed_phases:
            self._current_state.completed_phases.append(old_phase.phase_name)

        # Append to phase_history log (ENG-66)
        self._current_state.phase_history.append({
            "phase": phase.phase_name,
            "timestamp": now,
        })

        self._current_state.phase = phase
        self._current_state.last_updated = now
        logger.info(f"Phase transition: {old_phase.phase_name} -> {phase.phase_name}")
        self.save_state()

    def record_error(
        self,
        error: Exception,
        error_type: ErrorType = ErrorType.UNKNOWN,
    ) -> None:
        """Record an error in current phase.

        Updates the error log with a timestamped entry, increments
        the per-phase retry counter, and persists state (ENG-66).

        Args:
            error: The exception that occurred
            error_type: Classification of the error for degradation logic
        """
        if self._current_state is None:
            return

        phase = self._current_state.phase
        self._current_state.last_error = str(error)
        self._current_state.last_error_type = error_type
        self._current_state.last_updated = datetime.now().isoformat()

        # Append to error log with timestamp and phase context
        timestamp = datetime.now().isoformat()
        log_entry = f"[{timestamp}] {phase.phase_name}: {error_type.value} - {error}"
        self._current_state.error_log.append(log_entry)

        # Track phase attempts
        if phase not in self._phase_attempts:
            self._phase_attempts[phase] = PhaseAttempt(phase=phase)
        self._phase_attempts[phase].record_attempt(str(error))

        # Update serializable phase attempts
        self._current_state.phase_attempts[phase.phase_name] = self._phase_attempts[phase].attempt

        self.save_state()

    def get_phase_attempt(self, phase: SessionPhase) -> PhaseAttempt:
        """Get attempt tracker for a phase."""
        if phase not in self._phase_attempts:
            self._phase_attempts[phase] = PhaseAttempt(phase=phase)
        return self._phase_attempts[phase]

    def reset_phase_attempts(self, phase: SessionPhase) -> None:
        """Reset attempt counter for a phase after successful completion (ENG-67).

        Called when a phase completes successfully so that future retries
        (e.g., in a subsequent iteration) start from zero.

        Args:
            phase: The phase whose attempt counter should be reset
        """
        if phase in self._phase_attempts:
            self._phase_attempts[phase] = PhaseAttempt(phase=phase)
        if self._current_state and phase.phase_name in self._current_state.phase_attempts:
            self._current_state.phase_attempts[phase.phase_name] = 0
            self.save_state()

    def mark_degraded(self, service: str) -> None:
        """Mark a service as degraded."""
        if self._current_state and service not in self._current_state.degraded_services:
            self._current_state.degraded_services.append(service)
            self.save_state()

    def has_uncommitted_changes(self) -> bool:
        """Check git status for uncommitted changes."""
        import subprocess

        try:
            result = subprocess.run(
                ["git", "status", "--porcelain"],
                cwd=str(self.project_dir),
                capture_output=True,
                text=True,
                timeout=10,
            )
            has_changes = bool(result.stdout.strip())
            if self._current_state:
                self._current_state.uncommitted_changes = has_changes
                self.save_state()
            return has_changes
        except (subprocess.SubprocessError, FileNotFoundError):
            return False

    def get_resume_phase(self, saved_state: SessionState) -> SessionPhase:
        """Determine which phase to resume from.

        Logic:
        - If phase <= VERIFICATION -> restart from ORIENT (cheap)
        - If phase == IMPLEMENTATION -> retry only implementation
        - If phase >= COMMIT -> retry only this phase (code already written!)
        """
        phase = saved_state.phase

        if phase.is_before_or_equal(SessionPhase.VERIFICATION):
            logger.info("Restarting from ORIENT (early phase, cheap to restart)")
            return SessionPhase.ORIENT
        elif phase == SessionPhase.IMPLEMENTATION:
            logger.info("Retrying IMPLEMENTATION phase")
            return SessionPhase.IMPLEMENTATION
        else:
            # COMMIT, MARK_DONE, NOTIFY, MEMORY_FLUSH
            logger.info(f"Retrying phase {phase.phase_name} (code already written)")
            return phase


# Type alias for phase handler functions
PhaseHandler: TypeAlias = Callable[[], Coroutine[Any, Any, None]]


class SessionRecovery:
    """Handles crash recovery and phase-level retry logic."""

    def __init__(self, state_manager: SessionStateManager):
        self.state_manager = state_manager
        self.degradation = GracefulDegradation()

    async def check_recovery(self) -> tuple[bool, SessionState | None]:
        """Check if recovery is needed on startup.

        Detects interrupted sessions from .agent/session_state.json and
        determines whether they are fresh enough to resume. Sessions older
        than STALE_RECOVERY_HOURS are considered stale and cleared (ENG-69).

        Returns:
            Tuple of (recovery_needed, saved_state).
            If stale or completed, returns (False, None) and clears state.
        """
        saved_state = self.state_manager.load_state()
        if saved_state is None:
            return False, None

        # Check if session is incomplete
        if saved_state.phase != SessionPhase.MEMORY_FLUSH:
            # Check staleness -- sessions older than 24 hours are stale (ENG-69)
            if self.is_recovery_stale(saved_state):
                logger.info(
                    f"Stale recovery detected (>{STALE_RECOVERY_HOURS}h old), "
                    f"issue={saved_state.issue_id}, phase={saved_state.phase.phase_name}. "
                    "Clearing state."
                )
                self.state_manager.clear_state()
                return False, None

            logger.info(
                f"Recovering from interrupted session, "
                f"resuming at phase: {saved_state.phase.phase_name}"
            )

            # Check for uncommitted changes if we were in IMPLEMENTATION
            if saved_state.phase.is_after(SessionPhase.VERIFICATION):
                has_changes = self.state_manager.has_uncommitted_changes()
                if has_changes:
                    logger.info("Found uncommitted changes from interrupted session")

            return True, saved_state

        # Session completed successfully, clear state
        self.state_manager.clear_state()
        return False, None

    @staticmethod
    def is_recovery_stale(
        saved_state: SessionState,
        max_age_hours: float = STALE_RECOVERY_HOURS,
    ) -> bool:
        """Determine if a saved recovery state is too old to resume.

        A session is considered stale if its last_updated timestamp is older
        than max_age_hours. This prevents resuming sessions from days ago
        where the project context may have changed significantly.

        Args:
            saved_state: The loaded session state to check
            max_age_hours: Maximum age in hours before state is stale

        Returns:
            True if the state is stale and should be discarded
        """
        try:
            last_updated = datetime.fromisoformat(saved_state.last_updated)
            age_hours = (datetime.now() - last_updated).total_seconds() / 3600
            return age_hours > max_age_hours
        except (ValueError, TypeError):
            # If timestamp is unparseable, treat as stale
            logger.warning(
                f"Unparseable last_updated timestamp: {saved_state.last_updated}"
            )
            return True

    def get_recovery_info(self, saved_state: SessionState) -> dict[str, Any]:
        """Extract detailed recovery information from saved state (ENG-69).

        Returns a dictionary with structured recovery context suitable for
        injection into the agent prompt.

        Args:
            saved_state: The loaded session state

        Returns:
            Dictionary with keys: issue_id, last_phase, resume_phase,
            completed_phases, timestamp, uncommitted_changes, degraded_services,
            last_error, error_count
        """
        resume_phase = self.state_manager.get_resume_phase(saved_state)
        return {
            "issue_id": saved_state.issue_id,
            "last_phase": saved_state.phase.phase_name,
            "resume_phase": resume_phase.phase_name,
            "completed_phases": saved_state.completed_phases,
            "timestamp": saved_state.last_updated,
            "uncommitted_changes": saved_state.uncommitted_changes,
            "degraded_services": saved_state.degraded_services,
            "last_error": saved_state.last_error,
            "error_count": len(saved_state.error_log),
        }

    def get_retry_strategy(self, phase: SessionPhase, attempts: int) -> RetryStrategy:
        """Determine the retry strategy for a failed phase (ENG-67).

        The strategy depends on how far into the session the failure occurred
        and how many times this phase has already been retried:

        - Early phases (ORIENT, STATUS_CHECK, VERIFICATION): cheap to redo,
          so restart from ORIENT to get a clean slate.
        - IMPLEMENTATION: expensive but self-contained, retry just that phase.
        - Late phases (COMMIT, MARK_DONE, NOTIFY, MEMORY_FLUSH): code is
          already written, retry only the failed phase.
        - Any phase after MAX_PHASE_RETRIES: escalate to blocked.

        Args:
            phase: The phase that failed
            attempts: Number of attempts already made for this phase

        Returns:
            RetryStrategy indicating what the caller should do next
        """
        if attempts >= MAX_PHASE_RETRIES:
            return RetryStrategy.ESCALATE

        # Early phases: restart from beginning (cheap)
        early_phases = (
            SessionPhase.ORIENT,
            SessionPhase.STATUS_CHECK,
            SessionPhase.VERIFICATION,
        )
        if phase in early_phases:
            return RetryStrategy.RETRY_FROM_ORIENT

        # Implementation: retry just implementation
        if phase == SessionPhase.IMPLEMENTATION:
            return RetryStrategy.RETRY_IMPLEMENTATION

        # Late phases: retry current phase only (code already written)
        late_phases = (
            SessionPhase.COMMIT,
            SessionPhase.MARK_DONE,
            SessionPhase.NOTIFY,
            SessionPhase.MEMORY_FLUSH,
        )
        if phase in late_phases:
            return RetryStrategy.RETRY_CURRENT

        # Fallback for any unknown phase
        return RetryStrategy.RETRY_CURRENT

    def classify_error(self, error: Exception) -> ErrorType:
        """Classify an exception into an error type."""
        error_str = str(error).lower()
        error_type_name = type(error).__name__.lower()

        # MCP timeout
        if "timeout" in error_str or "timeout" in error_type_name:
            if "mcp" in error_str or "sse" in error_str:
                return ErrorType.MCP_TIMEOUT

        # Playwright crash
        if "playwright" in error_str or "browser" in error_str:
            return ErrorType.PLAYWRIGHT_CRASH

        # Git error
        if "git" in error_str:
            return ErrorType.GIT_ERROR

        # Rate limit
        if "rate" in error_str or "limit" in error_str or "429" in error_str:
            return ErrorType.RATE_LIMIT

        # Network error
        if any(term in error_str for term in ["network", "connection", "refused", "unreachable"]):
            return ErrorType.NETWORK_ERROR

        return ErrorType.UNKNOWN

    async def execute_with_retry(
        self,
        phase: SessionPhase,
        handler: PhaseHandler,
    ) -> bool:
        """Execute a phase handler with retry logic.

        Args:
            phase: The phase being executed
            handler: Async function to execute

        Returns:
            True if successful, False if failed after retries
        """
        attempt_tracker = self.state_manager.get_phase_attempt(phase)

        while attempt_tracker.can_retry:
            try:
                self.state_manager.transition_to(phase)
                await handler()
                return True

            except Exception as e:
                error_type = self.classify_error(e)
                self.state_manager.record_error(e, error_type)
                attempt_tracker.record_attempt(str(e))

                logger.warning(
                    f"Phase {phase.phase_name} failed (attempt {attempt_tracker.attempt}): {e}"
                )
                logger.debug(traceback.format_exc())

                if not attempt_tracker.can_retry:
                    # Check if we can degrade gracefully
                    if self.degradation.should_skip_service(error_type, phase):
                        msg = self.degradation.get_degradation_message(error_type, phase)
                        logger.info(f"Graceful degradation: {msg}")
                        self.state_manager.mark_degraded(phase.phase_name)
                        return True  # Continue to next phase
                    else:
                        logger.error(f"Phase {phase.phase_name} failed after max retries")
                        return False

                # Wait before retry
                delay = self.degradation.get_backoff_delay(attempt_tracker.attempt, error_type)
                logger.info(f"Retrying in {delay:.1f}s...")
                await asyncio.sleep(delay)

        return False

    async def save_git_diff_to_file(self) -> Path | None:
        """Save uncommitted changes to a diff file as fallback.

        Used when git commit fails repeatedly.
        """
        import subprocess

        try:
            result = subprocess.run(
                ["git", "diff", "HEAD"],
                cwd=str(self.state_manager.project_dir),
                capture_output=True,
                text=True,
                timeout=30,
            )

            if result.stdout.strip():
                timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
                diff_file = self.state_manager.project_dir / ".agent" / f"uncommitted_{timestamp}.diff"
                diff_file.write_text(result.stdout)
                logger.info(f"Saved uncommitted changes to {diff_file}")
                return diff_file

        except (subprocess.SubprocessError, IOError) as e:
            logger.error(f"Failed to save diff: {e}")

        return None

    async def stash_changes(self) -> bool:
        """Stash uncommitted changes as fallback."""
        import subprocess

        try:
            subprocess.run(
                ["git", "stash", "push", "-m", "auto-stash from error recovery"],
                cwd=str(self.state_manager.project_dir),
                capture_output=True,
                text=True,
                timeout=30,
                check=True,
            )
            logger.info("Changes stashed successfully")
            return True
        except subprocess.SubprocessError as e:
            logger.error(f"Failed to stash changes: {e}")
            return False


def get_session_state_manager(project_dir: Path) -> SessionStateManager:
    """Get or create a session state manager for a project."""
    return SessionStateManager(project_dir)


def get_session_recovery(project_dir: Path) -> SessionRecovery:
    """Get a session recovery handler for a project."""
    state_manager = get_session_state_manager(project_dir)
    return SessionRecovery(state_manager)


# --- Standalone convenience functions (ENG-66) ---
# These provide a simpler functional API for callers that don't need
# the full SessionStateManager class interface.

# Module-level default project directory for standalone functions
_default_project_dir: Path | None = None


def set_default_project_dir(project_dir: Path) -> None:
    """Set the default project directory for standalone functions.

    Must be called before using save_session_state, load_session_state,
    transition_phase, or clear_session_state without explicit project_dir.

    Args:
        project_dir: Path to the project root directory
    """
    global _default_project_dir
    _default_project_dir = project_dir


def _resolve_project_dir(project_dir: Path | None) -> Path:
    """Resolve project directory from argument or module default.

    Args:
        project_dir: Explicit project dir, or None to use default

    Returns:
        Resolved project directory path

    Raises:
        ValueError: If no project_dir provided and no default set
    """
    if project_dir is not None:
        return project_dir
    if _default_project_dir is not None:
        return _default_project_dir
    raise ValueError(
        "No project_dir provided and no default set. "
        "Call set_default_project_dir() first."
    )


def save_session_state(
    state: SessionState,
    project_dir: Path | None = None,
) -> None:
    """Save session state to .agent/session_state.json.

    Standalone function for persisting session state without
    managing a SessionStateManager instance (ENG-66).

    Args:
        state: The session state to persist
        project_dir: Project root directory (uses default if None)
    """
    resolved_dir = _resolve_project_dir(project_dir)
    manager = SessionStateManager(resolved_dir)
    manager._current_state = state
    manager.save_state()


def load_session_state(
    project_dir: Path | None = None,
) -> SessionState | None:
    """Load session state from .agent/session_state.json if it exists.

    Standalone function for loading session state without
    managing a SessionStateManager instance (ENG-66).

    Args:
        project_dir: Project root directory (uses default if None)

    Returns:
        SessionState if file exists and is valid, None otherwise
    """
    resolved_dir = _resolve_project_dir(project_dir)
    manager = SessionStateManager(resolved_dir)
    return manager.load_state()


def transition_phase(
    state: SessionState,
    new_phase: SessionPhase,
    project_dir: Path | None = None,
) -> SessionState:
    """Transition to a new phase, update timestamps, and save.

    Standalone function that updates the state in-place,
    marks the old phase as completed, refreshes last_updated,
    and persists to disk (ENG-66).

    Args:
        state: Current session state (modified in-place)
        new_phase: The phase to transition to
        project_dir: Project root directory (uses default if None)

    Returns:
        The updated SessionState (same object, returned for chaining)
    """
    resolved_dir = _resolve_project_dir(project_dir)
    manager = SessionStateManager(resolved_dir)
    manager._current_state = state
    manager.transition_to(new_phase)
    return state


def clear_session_state(
    project_dir: Path | None = None,
) -> None:
    """Remove the session state JSON file (called on successful completion).

    Standalone function for clearing persisted session state (ENG-66).

    Args:
        project_dir: Project root directory (uses default if None)
    """
    resolved_dir = _resolve_project_dir(project_dir)
    manager = SessionStateManager(resolved_dir)
    manager.clear_state()
