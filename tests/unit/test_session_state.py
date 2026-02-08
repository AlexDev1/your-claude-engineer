"""
Tests for Session State Management (ENG-35)
============================================

Verifies:
1. Session state recorded in JSON at each phase change
2. Error in COMMIT doesn't restart IMPLEMENTATION
3. MCP timeout -> graceful degradation (skip notification, continue)
4. Crash recovery on startup restores from checkpoint
5. Exponential backoff on rate limits
"""

import asyncio
import json
import tempfile
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from session_state import (
    MAX_PHASE_RETRIES,
    ErrorType,
    GracefulDegradation,
    PhaseAttempt,
    RetryStrategy,
    SessionPhase,
    SessionRecovery,
    SessionState,
    SessionStateManager,
    clear_session_state,
    get_session_recovery,
    get_session_state_manager,
    load_session_state,
    save_session_state,
    set_default_project_dir,
    transition_phase,
)


class TestSessionPhase:
    """Test SessionPhase enum."""

    def test_phase_order(self):
        """Phases have correct order."""
        assert SessionPhase.ORIENT.order < SessionPhase.IMPLEMENTATION.order
        assert SessionPhase.IMPLEMENTATION.order < SessionPhase.COMMIT.order
        assert SessionPhase.COMMIT.order < SessionPhase.NOTIFY.order

    def test_from_string(self):
        """Can create phase from string name."""
        assert SessionPhase.from_string("orient") == SessionPhase.ORIENT
        assert SessionPhase.from_string("commit") == SessionPhase.COMMIT
        assert SessionPhase.from_string("ORIENT") == SessionPhase.ORIENT

    def test_from_string_invalid(self):
        """Invalid string raises ValueError."""
        with pytest.raises(ValueError):
            SessionPhase.from_string("invalid_phase")

    def test_is_before_or_equal(self):
        """Phase comparison works correctly."""
        assert SessionPhase.ORIENT.is_before_or_equal(SessionPhase.VERIFICATION)
        assert SessionPhase.VERIFICATION.is_before_or_equal(SessionPhase.VERIFICATION)
        assert not SessionPhase.COMMIT.is_before_or_equal(SessionPhase.VERIFICATION)

    def test_is_after(self):
        """Phase after comparison works correctly."""
        assert SessionPhase.COMMIT.is_after(SessionPhase.VERIFICATION)
        assert not SessionPhase.ORIENT.is_after(SessionPhase.VERIFICATION)


class TestSessionState:
    """Test SessionState dataclass."""

    def test_to_dict(self):
        """State serializes to dictionary including ENG-66 fields."""
        state = SessionState(
            phase=SessionPhase.COMMIT,
            issue_id="ENG-35",
            attempt=2,
        )
        data = state.to_dict()

        assert data["phase"] == "commit"
        assert data["issue_id"] == "ENG-35"
        assert data["attempt"] == 2
        assert "started_at" in data
        assert "last_updated" in data
        assert data["completed_phases"] == []
        assert data["phase_history"] == []
        assert data["error_log"] == []

    def test_from_dict(self):
        """State deserializes from dictionary."""
        data = {
            "phase": "implementation",
            "issue_id": "ENG-35",
            "attempt": 1,
            "started_at": "2025-02-07T12:00:00",
            "uncommitted_changes": True,
            "degraded_services": ["notify"],
        }
        state = SessionState.from_dict(data)

        assert state.phase == SessionPhase.IMPLEMENTATION
        assert state.issue_id == "ENG-35"
        assert state.uncommitted_changes is True
        assert "notify" in state.degraded_services

    def test_roundtrip(self):
        """State survives serialize/deserialize roundtrip including ENG-66 fields."""
        original = SessionState(
            phase=SessionPhase.MARK_DONE,
            issue_id="ENG-42",
            attempt=3,
            completed_phases=["orient", "status", "verify", "implement", "commit"],
            phase_history=[
                {"phase": "orient", "timestamp": "2026-02-07T10:00:00"},
                {"phase": "status", "timestamp": "2026-02-07T10:00:05"},
                {"phase": "verify", "timestamp": "2026-02-07T10:00:10"},
                {"phase": "implement", "timestamp": "2026-02-07T10:00:15"},
                {"phase": "commit", "timestamp": "2026-02-07T10:01:00"},
                {"phase": "mark_done", "timestamp": "2026-02-07T10:01:30"},
            ],
            error_log=["[2026-02-07T10:00:00] commit: git_error - push failed"],
            uncommitted_changes=True,
            degraded_services=["notify", "status"],
            last_error="Connection timeout",
            last_error_type=ErrorType.MCP_TIMEOUT,
        )

        data = original.to_dict()
        restored = SessionState.from_dict(data)

        assert restored.phase == original.phase
        assert restored.issue_id == original.issue_id
        assert restored.attempt == original.attempt
        assert restored.completed_phases == original.completed_phases
        assert restored.phase_history == original.phase_history
        assert restored.error_log == original.error_log
        assert restored.last_updated == original.last_updated
        assert restored.uncommitted_changes == original.uncommitted_changes
        assert restored.degraded_services == original.degraded_services
        assert restored.last_error == original.last_error
        assert restored.last_error_type == original.last_error_type


class TestPhaseAttempt:
    """Test PhaseAttempt tracker."""

    def test_can_retry(self):
        """Retry logic works correctly."""
        attempt = PhaseAttempt(phase=SessionPhase.COMMIT, max_attempts=2)

        assert attempt.can_retry
        attempt.record_attempt("error 1")
        assert attempt.can_retry
        attempt.record_attempt("error 2")
        assert not attempt.can_retry

    def test_record_attempt(self):
        """Records attempts correctly."""
        attempt = PhaseAttempt(phase=SessionPhase.COMMIT)
        attempt.record_attempt("first error")

        assert attempt.attempt == 1
        assert attempt.last_error == "first error"
        assert attempt.last_attempt_time is not None


class TestSessionStateManager:
    """Test SessionStateManager."""

    @pytest.fixture
    def temp_project(self):
        """Create a temporary project directory."""
        with tempfile.TemporaryDirectory() as tmpdir:
            project_dir = Path(tmpdir)
            (project_dir / ".agent").mkdir()
            yield project_dir

    def test_save_and_load_state(self, temp_project):
        """State persists to file and loads correctly."""
        manager = SessionStateManager(temp_project)

        # Start session
        state = manager.start_session("ENG-35")
        assert state.phase == SessionPhase.ORIENT

        # Transition and verify file updated
        manager.transition_to(SessionPhase.IMPLEMENTATION)

        # Load from file
        loaded = manager.load_state()
        assert loaded is not None
        assert loaded.phase == SessionPhase.IMPLEMENTATION
        assert loaded.issue_id == "ENG-35"

    def test_phase_transition_saves_state(self, temp_project):
        """Each phase transition writes to JSON file with completed_phases and phase_history (ENG-66)."""
        manager = SessionStateManager(temp_project)
        manager.start_session("ENG-35")

        # Transition through phases
        phases = [
            SessionPhase.STATUS_CHECK,
            SessionPhase.VERIFICATION,
            SessionPhase.IMPLEMENTATION,
            SessionPhase.COMMIT,
        ]

        for phase in phases:
            manager.transition_to(phase)

            # Verify state file updated
            state_file = temp_project / ".agent" / "session_state.json"
            assert state_file.exists()

            with open(state_file) as f:
                data = json.load(f)
            assert data["phase"] == phase.phase_name
            assert "last_updated" in data
            assert "completed_phases" in data
            assert "phase_history" in data

        # After all transitions, completed_phases should have earlier phases
        with open(temp_project / ".agent" / "session_state.json") as f:
            final_data = json.load(f)
        assert "orient" in final_data["completed_phases"]
        assert "status" in final_data["completed_phases"]
        assert "verify" in final_data["completed_phases"]
        assert "implement" in final_data["completed_phases"]
        # "commit" is current phase, not yet completed
        assert "commit" not in final_data["completed_phases"]

        # phase_history should have initial orient + 4 transitions = 5 entries (ENG-66)
        assert len(final_data["phase_history"]) == 5
        assert final_data["phase_history"][0]["phase"] == "orient"
        assert final_data["phase_history"][1]["phase"] == "status"
        assert final_data["phase_history"][4]["phase"] == "commit"
        # Each entry has a timestamp
        for entry in final_data["phase_history"]:
            assert "phase" in entry
            assert "timestamp" in entry

    def test_clear_state(self, temp_project):
        """Clear state removes file."""
        manager = SessionStateManager(temp_project)
        manager.start_session("ENG-35")

        state_file = temp_project / ".agent" / "session_state.json"
        assert state_file.exists()

        manager.clear_state()
        assert not state_file.exists()

    def test_get_resume_phase_early(self, temp_project):
        """Early phases restart from ORIENT."""
        manager = SessionStateManager(temp_project)

        # Test ORIENT -> restart from ORIENT
        state = SessionState(phase=SessionPhase.ORIENT, issue_id="ENG-35")
        assert manager.get_resume_phase(state) == SessionPhase.ORIENT

        # Test VERIFICATION -> restart from ORIENT
        state = SessionState(phase=SessionPhase.VERIFICATION, issue_id="ENG-35")
        assert manager.get_resume_phase(state) == SessionPhase.ORIENT

    def test_get_resume_phase_implementation(self, temp_project):
        """IMPLEMENTATION restarts from IMPLEMENTATION."""
        manager = SessionStateManager(temp_project)

        state = SessionState(phase=SessionPhase.IMPLEMENTATION, issue_id="ENG-35")
        assert manager.get_resume_phase(state) == SessionPhase.IMPLEMENTATION

    def test_get_resume_phase_late(self, temp_project):
        """Late phases (COMMIT+) restart from same phase."""
        manager = SessionStateManager(temp_project)

        # COMMIT -> resume from COMMIT
        state = SessionState(phase=SessionPhase.COMMIT, issue_id="ENG-35")
        assert manager.get_resume_phase(state) == SessionPhase.COMMIT

        # MARK_DONE -> resume from MARK_DONE
        state = SessionState(phase=SessionPhase.MARK_DONE, issue_id="ENG-35")
        assert manager.get_resume_phase(state) == SessionPhase.MARK_DONE

        # NOTIFY -> resume from NOTIFY
        state = SessionState(phase=SessionPhase.NOTIFY, issue_id="ENG-35")
        assert manager.get_resume_phase(state) == SessionPhase.NOTIFY

    def test_record_error(self, temp_project):
        """Records errors, updates attempt count, and appends to error_log (ENG-66)."""
        manager = SessionStateManager(temp_project)
        manager.start_session("ENG-35")
        manager.transition_to(SessionPhase.COMMIT)

        # Record error
        manager.record_error(
            Exception("Git push failed"),
            ErrorType.GIT_ERROR,
        )

        assert manager.current_state.last_error == "Git push failed"
        assert manager.current_state.last_error_type == ErrorType.GIT_ERROR
        assert manager.current_state.phase_attempts.get("commit") == 1

        # Verify error_log populated (ENG-66)
        assert len(manager.current_state.error_log) == 1
        assert "commit" in manager.current_state.error_log[0]
        assert "git_error" in manager.current_state.error_log[0]
        assert "Git push failed" in manager.current_state.error_log[0]

        # Record another error - log should accumulate
        manager.record_error(
            Exception("Git push failed again"),
            ErrorType.GIT_ERROR,
        )
        assert len(manager.current_state.error_log) == 2

    def test_mark_degraded(self, temp_project):
        """Marks services as degraded."""
        manager = SessionStateManager(temp_project)
        manager.start_session("ENG-35")

        manager.mark_degraded("notify")
        manager.mark_degraded("status")

        assert "notify" in manager.current_state.degraded_services
        assert "status" in manager.current_state.degraded_services

        # Duplicate should not add again
        manager.mark_degraded("notify")
        assert manager.current_state.degraded_services.count("notify") == 1


class TestGracefulDegradation:
    """Test GracefulDegradation strategies."""

    def test_max_retries(self):
        """Different error types have different max retries."""
        assert GracefulDegradation.get_max_retries(ErrorType.MCP_TIMEOUT) == 3
        assert GracefulDegradation.get_max_retries(ErrorType.PLAYWRIGHT_CRASH) == 2
        assert GracefulDegradation.get_max_retries(ErrorType.RATE_LIMIT) == 3

    def test_rate_limit_backoff(self):
        """Rate limit uses exponential backoff 30s/60s/120s."""
        assert GracefulDegradation.get_backoff_delay(1, ErrorType.RATE_LIMIT) == 30
        assert GracefulDegradation.get_backoff_delay(2, ErrorType.RATE_LIMIT) == 60
        assert GracefulDegradation.get_backoff_delay(3, ErrorType.RATE_LIMIT) == 120
        # Should cap at max
        assert GracefulDegradation.get_backoff_delay(4, ErrorType.RATE_LIMIT) == 120

    def test_mcp_timeout_backoff(self):
        """MCP timeout has linear backoff."""
        assert GracefulDegradation.get_backoff_delay(1, ErrorType.MCP_TIMEOUT) == 5.0
        assert GracefulDegradation.get_backoff_delay(2, ErrorType.MCP_TIMEOUT) == 10.0
        assert GracefulDegradation.get_backoff_delay(3, ErrorType.MCP_TIMEOUT) == 15.0

    def test_should_skip_service_mcp_timeout(self):
        """MCP timeout allows skipping NOTIFY and MARK_DONE."""
        assert GracefulDegradation.should_skip_service(
            ErrorType.MCP_TIMEOUT, SessionPhase.NOTIFY
        )
        assert GracefulDegradation.should_skip_service(
            ErrorType.MCP_TIMEOUT, SessionPhase.MARK_DONE
        )
        assert not GracefulDegradation.should_skip_service(
            ErrorType.MCP_TIMEOUT, SessionPhase.COMMIT
        )
        assert not GracefulDegradation.should_skip_service(
            ErrorType.MCP_TIMEOUT, SessionPhase.IMPLEMENTATION
        )

    def test_should_skip_service_playwright(self):
        """Playwright crash allows skipping VERIFICATION."""
        assert GracefulDegradation.should_skip_service(
            ErrorType.PLAYWRIGHT_CRASH, SessionPhase.VERIFICATION
        )
        assert not GracefulDegradation.should_skip_service(
            ErrorType.PLAYWRIGHT_CRASH, SessionPhase.COMMIT
        )

    def test_degradation_message(self):
        """Degradation messages are informative."""
        msg = GracefulDegradation.get_degradation_message(
            ErrorType.MCP_TIMEOUT, SessionPhase.NOTIFY
        )
        assert "Telegram" in msg
        assert "skipped" in msg

        msg = GracefulDegradation.get_degradation_message(
            ErrorType.PLAYWRIGHT_CRASH, SessionPhase.VERIFICATION
        )
        assert "Screenshot" in msg or "screenshot" in msg


class TestSessionRecovery:
    """Test SessionRecovery."""

    @pytest.fixture
    def temp_project(self):
        """Create a temporary project directory."""
        with tempfile.TemporaryDirectory() as tmpdir:
            project_dir = Path(tmpdir)
            (project_dir / ".agent").mkdir()
            yield project_dir

    def test_classify_error_mcp_timeout(self, temp_project):
        """Classifies MCP timeout errors."""
        recovery = get_session_recovery(temp_project)

        error = TimeoutError("MCP server SSE connection timeout")
        assert recovery.classify_error(error) == ErrorType.MCP_TIMEOUT

    def test_classify_error_playwright(self, temp_project):
        """Classifies Playwright errors."""
        recovery = get_session_recovery(temp_project)

        error = Exception("Playwright browser crashed")
        assert recovery.classify_error(error) == ErrorType.PLAYWRIGHT_CRASH

    def test_classify_error_git(self, temp_project):
        """Classifies git errors."""
        recovery = get_session_recovery(temp_project)

        error = Exception("git push failed: remote rejected")
        assert recovery.classify_error(error) == ErrorType.GIT_ERROR

    def test_classify_error_rate_limit(self, temp_project):
        """Classifies rate limit errors."""
        recovery = get_session_recovery(temp_project)

        error = Exception("Rate limit exceeded (429)")
        assert recovery.classify_error(error) == ErrorType.RATE_LIMIT

    def test_classify_error_network(self, temp_project):
        """Classifies network errors."""
        recovery = get_session_recovery(temp_project)

        error = ConnectionError("Connection refused")
        assert recovery.classify_error(error) == ErrorType.NETWORK_ERROR

    @pytest.mark.asyncio
    async def test_check_recovery_no_state(self, temp_project):
        """No recovery needed when no saved state."""
        recovery = get_session_recovery(temp_project)

        needed, state = await recovery.check_recovery()
        assert not needed
        assert state is None

    @pytest.mark.asyncio
    async def test_check_recovery_incomplete_session(self, temp_project):
        """Recovery needed for incomplete session."""
        # Create saved state
        state_file = temp_project / ".agent" / "session_state.json"
        state_data = {
            "phase": "commit",
            "issue_id": "ENG-35",
            "attempt": 1,
            "started_at": "2025-02-07T12:00:00",
        }
        with open(state_file, "w") as f:
            json.dump(state_data, f)

        recovery = get_session_recovery(temp_project)
        needed, state = await recovery.check_recovery()

        assert needed
        assert state is not None
        assert state.phase == SessionPhase.COMMIT
        assert state.issue_id == "ENG-35"

    @pytest.mark.asyncio
    async def test_check_recovery_completed_session(self, temp_project):
        """No recovery for completed session (MEMORY_FLUSH)."""
        # Create saved state at final phase
        state_file = temp_project / ".agent" / "session_state.json"
        state_data = {
            "phase": "flush",
            "issue_id": "ENG-35",
            "attempt": 1,
            "started_at": "2025-02-07T12:00:00",
        }
        with open(state_file, "w") as f:
            json.dump(state_data, f)

        recovery = get_session_recovery(temp_project)
        needed, state = await recovery.check_recovery()

        assert not needed
        # State file should be cleared
        assert not state_file.exists()

    @pytest.mark.asyncio
    async def test_execute_with_retry_success(self, temp_project):
        """Successful execution clears attempts."""
        recovery = get_session_recovery(temp_project)
        recovery.state_manager.start_session("ENG-35")

        handler_called = False

        async def success_handler():
            nonlocal handler_called
            handler_called = True

        result = await recovery.execute_with_retry(
            SessionPhase.COMMIT, success_handler
        )

        assert result is True
        assert handler_called

    @pytest.mark.asyncio
    async def test_execute_with_retry_failure_then_success(self, temp_project):
        """Retries on failure until success.

        Note: max_attempts=2 means it can try twice. If first fails, second succeeds.
        We need the handler to succeed before exhausting retries.
        """
        recovery = get_session_recovery(temp_project)
        recovery.state_manager.start_session("ENG-35")

        # Increase max attempts for this test
        recovery.state_manager._phase_attempts[SessionPhase.COMMIT] = PhaseAttempt(
            phase=SessionPhase.COMMIT,
            max_attempts=3,  # Allow 3 attempts
        )

        call_count = 0

        async def flaky_handler():
            nonlocal call_count
            call_count += 1
            if call_count < 2:
                raise Exception("Temporary failure")

        result = await recovery.execute_with_retry(
            SessionPhase.COMMIT, flaky_handler
        )

        assert result is True
        assert call_count == 2

    @pytest.mark.asyncio
    async def test_execute_with_retry_graceful_degradation(self, temp_project):
        """Graceful degradation after max retries for skippable phase."""
        recovery = get_session_recovery(temp_project)
        recovery.state_manager.start_session("ENG-35")

        async def failing_handler():
            raise TimeoutError("MCP SSE timeout")

        # NOTIFY phase can be skipped on MCP timeout
        result = await recovery.execute_with_retry(
            SessionPhase.NOTIFY, failing_handler
        )

        # Should succeed due to graceful degradation
        assert result is True
        assert "notify" in recovery.state_manager.current_state.degraded_services


class TestIntegration:
    """Integration tests for the full error recovery flow."""

    @pytest.fixture
    def temp_project(self):
        """Create a temporary project directory with git."""
        with tempfile.TemporaryDirectory() as tmpdir:
            project_dir = Path(tmpdir)
            (project_dir / ".agent").mkdir()

            # Initialize git repo
            import subprocess
            subprocess.run(["git", "init"], cwd=tmpdir, capture_output=True)
            subprocess.run(
                ["git", "config", "user.email", "test@test.com"],
                cwd=tmpdir, capture_output=True
            )
            subprocess.run(
                ["git", "config", "user.name", "Test"],
                cwd=tmpdir, capture_output=True
            )

            yield project_dir

    def test_commit_error_preserves_implementation(self, temp_project):
        """Error in COMMIT phase doesn't require re-running IMPLEMENTATION."""
        manager = get_session_state_manager(temp_project)

        # Simulate session that reached COMMIT
        manager.start_session("ENG-35")
        manager.transition_to(SessionPhase.STATUS_CHECK)
        manager.transition_to(SessionPhase.VERIFICATION)
        manager.transition_to(SessionPhase.IMPLEMENTATION)
        manager.transition_to(SessionPhase.COMMIT)

        # Simulate error during commit
        manager.record_error(
            Exception("Git push failed"),
            ErrorType.GIT_ERROR,
        )

        # Save state (simulating crash)
        manager.save_state()

        # New manager loads state
        new_manager = get_session_state_manager(temp_project)
        saved_state = new_manager.load_state()

        assert saved_state is not None
        assert saved_state.phase == SessionPhase.COMMIT

        # Get resume phase - should NOT go back to IMPLEMENTATION
        resume_phase = new_manager.get_resume_phase(saved_state)
        assert resume_phase == SessionPhase.COMMIT
        assert resume_phase != SessionPhase.IMPLEMENTATION

    def test_mcp_timeout_degrades_gracefully(self, temp_project):
        """MCP timeout skips notification and continues."""
        manager = get_session_state_manager(temp_project)
        manager.start_session("ENG-35")
        manager.transition_to(SessionPhase.NOTIFY)

        # Max out retries
        for _ in range(3):
            manager.record_error(
                TimeoutError("MCP timeout"),
                ErrorType.MCP_TIMEOUT,
            )

        # Should be able to skip this phase
        assert GracefulDegradation.should_skip_service(
            ErrorType.MCP_TIMEOUT,
            SessionPhase.NOTIFY,
        )

        manager.mark_degraded("notify")
        assert "notify" in manager.current_state.degraded_services

    def test_full_session_lifecycle(self, temp_project):
        """Full session goes through all phases and clears state on completion."""
        manager = get_session_state_manager(temp_project)

        # Start and progress through all phases
        manager.start_session("ENG-35")

        all_phases = [
            SessionPhase.STATUS_CHECK,
            SessionPhase.VERIFICATION,
            SessionPhase.IMPLEMENTATION,
            SessionPhase.COMMIT,
            SessionPhase.MARK_DONE,
            SessionPhase.NOTIFY,
            SessionPhase.MEMORY_FLUSH,
        ]

        for phase in all_phases:
            manager.transition_to(phase)

        # Before clearing, verify completed_phases (ENG-66)
        assert len(manager.current_state.completed_phases) == 7
        assert "orient" in manager.current_state.completed_phases
        assert "notify" in manager.current_state.completed_phases

        # Verify phase_history has initial orient + 7 transitions = 8 entries (ENG-66)
        assert len(manager.current_state.phase_history) == 8
        assert manager.current_state.phase_history[0]["phase"] == "orient"
        assert manager.current_state.phase_history[-1]["phase"] == "flush"

        # Clear on completion
        manager.clear_state()

        # Verify state cleared
        state_file = temp_project / ".agent" / "session_state.json"
        assert not state_file.exists()
        assert manager.current_state is None


class TestStandaloneFunctions:
    """Test standalone convenience functions (ENG-66)."""

    @pytest.fixture
    def temp_project(self):
        """Create a temporary project directory."""
        with tempfile.TemporaryDirectory() as tmpdir:
            project_dir = Path(tmpdir)
            (project_dir / ".agent").mkdir()
            yield project_dir

    def test_save_and_load_session_state(self, temp_project):
        """save_session_state and load_session_state round-trip correctly."""
        state = SessionState(
            phase=SessionPhase.IMPLEMENTATION,
            issue_id="ENG-66",
        )

        save_session_state(state, project_dir=temp_project)

        loaded = load_session_state(project_dir=temp_project)
        assert loaded is not None
        assert loaded.phase == SessionPhase.IMPLEMENTATION
        assert loaded.issue_id == "ENG-66"

    def test_transition_phase(self, temp_project):
        """transition_phase updates phase and tracks completed_phases."""
        state = SessionState(
            phase=SessionPhase.ORIENT,
            issue_id="ENG-66",
        )
        save_session_state(state, project_dir=temp_project)

        result = transition_phase(state, SessionPhase.STATUS_CHECK, project_dir=temp_project)

        assert result is state  # Same object returned
        assert result.phase == SessionPhase.STATUS_CHECK
        assert "orient" in result.completed_phases
        assert result.last_updated != result.started_at  # Timestamp updated

        # Verify persisted
        loaded = load_session_state(project_dir=temp_project)
        assert loaded is not None
        assert loaded.phase == SessionPhase.STATUS_CHECK
        assert "orient" in loaded.completed_phases

    def test_clear_session_state(self, temp_project):
        """clear_session_state removes the JSON file."""
        state = SessionState(
            phase=SessionPhase.COMMIT,
            issue_id="ENG-66",
        )
        save_session_state(state, project_dir=temp_project)

        state_file = temp_project / ".agent" / "session_state.json"
        assert state_file.exists()

        clear_session_state(project_dir=temp_project)
        assert not state_file.exists()

    def test_load_session_state_no_file(self, temp_project):
        """load_session_state returns None when no file exists."""
        loaded = load_session_state(project_dir=temp_project)
        assert loaded is None

    def test_set_default_project_dir(self, temp_project):
        """set_default_project_dir allows functions without explicit dir."""
        set_default_project_dir(temp_project)

        state = SessionState(
            phase=SessionPhase.ORIENT,
            issue_id="ENG-66",
        )
        save_session_state(state)  # No explicit project_dir

        loaded = load_session_state()  # No explicit project_dir
        assert loaded is not None
        assert loaded.issue_id == "ENG-66"

        clear_session_state()  # No explicit project_dir
        assert not (temp_project / ".agent" / "session_state.json").exists()

    def test_no_default_raises_error(self):
        """Functions raise ValueError without default or explicit dir."""
        import session_state as ss
        old_default = ss._default_project_dir
        ss._default_project_dir = None

        try:
            with pytest.raises(ValueError, match="No project_dir provided"):
                load_session_state()
        finally:
            ss._default_project_dir = old_default

    def test_error_log_persists_through_roundtrip(self, temp_project):
        """error_log entries survive save/load cycle."""
        state = SessionState(
            phase=SessionPhase.COMMIT,
            issue_id="ENG-66",
            error_log=[
                "[2026-02-07T10:00:00] commit: git_error - push failed",
                "[2026-02-07T10:01:00] commit: git_error - push failed again",
            ],
        )
        save_session_state(state, project_dir=temp_project)

        loaded = load_session_state(project_dir=temp_project)
        assert loaded is not None
        assert len(loaded.error_log) == 2
        assert "push failed" in loaded.error_log[0]

    def test_completed_phases_persist_through_roundtrip(self, temp_project):
        """completed_phases survive save/load cycle."""
        state = SessionState(
            phase=SessionPhase.COMMIT,
            issue_id="ENG-66",
            completed_phases=["orient", "status", "verify", "implement"],
        )
        save_session_state(state, project_dir=temp_project)

        loaded = load_session_state(project_dir=temp_project)
        assert loaded is not None
        assert loaded.completed_phases == ["orient", "status", "verify", "implement"]

    def test_phase_history_persists_through_roundtrip(self, temp_project):
        """phase_history entries survive save/load cycle (ENG-66)."""
        history = [
            {"phase": "orient", "timestamp": "2026-02-07T12:00:00"},
            {"phase": "status", "timestamp": "2026-02-07T12:00:05"},
            {"phase": "implement", "timestamp": "2026-02-07T12:00:10"},
        ]
        state = SessionState(
            phase=SessionPhase.IMPLEMENTATION,
            issue_id="ENG-66",
            phase_history=history,
        )
        save_session_state(state, project_dir=temp_project)

        loaded = load_session_state(project_dir=temp_project)
        assert loaded is not None
        assert len(loaded.phase_history) == 3
        assert loaded.phase_history[0]["phase"] == "orient"
        assert loaded.phase_history[0]["timestamp"] == "2026-02-07T12:00:00"
        assert loaded.phase_history[2]["phase"] == "implement"

    def test_transition_phase_appends_to_phase_history(self, temp_project):
        """transition_phase adds entry to phase_history (ENG-66)."""
        state = SessionState(
            phase=SessionPhase.ORIENT,
            issue_id="ENG-66",
            phase_history=[{"phase": "orient", "timestamp": "2026-02-07T12:00:00"}],
        )
        save_session_state(state, project_dir=temp_project)

        result = transition_phase(state, SessionPhase.STATUS_CHECK, project_dir=temp_project)

        assert len(result.phase_history) == 2
        assert result.phase_history[1]["phase"] == "status"
        assert "timestamp" in result.phase_history[1]

        # Verify persisted
        loaded = load_session_state(project_dir=temp_project)
        assert loaded is not None
        assert len(loaded.phase_history) == 2

    def test_atomic_write_no_temp_files_left(self, temp_project):
        """Atomic write leaves no temp files after successful save."""
        state = SessionState(
            phase=SessionPhase.ORIENT,
            issue_id="ENG-66",
        )
        save_session_state(state, project_dir=temp_project)

        agent_dir = temp_project / ".agent"
        files = list(agent_dir.iterdir())
        tmp_files = [f for f in files if f.suffix == ".tmp"]
        assert len(tmp_files) == 0, f"Temp files left behind: {tmp_files}"
        assert (agent_dir / "session_state.json").exists()


class TestRetryStrategy:
    """Test RetryStrategy enum and get_retry_strategy logic (ENG-67)."""

    @pytest.fixture
    def temp_project(self):
        """Create a temporary project directory."""
        with tempfile.TemporaryDirectory() as tmpdir:
            project_dir = Path(tmpdir)
            (project_dir / ".agent").mkdir()
            yield project_dir

    def test_retry_strategy_enum_values(self):
        """RetryStrategy enum has all expected values."""
        assert RetryStrategy.RETRY_CURRENT.value == "retry_current"
        assert RetryStrategy.RETRY_FROM_ORIENT.value == "retry_from_orient"
        assert RetryStrategy.RETRY_IMPLEMENTATION.value == "retry_implementation"
        assert RetryStrategy.ESCALATE.value == "escalate"

    def test_max_phase_retries_constant(self):
        """MAX_PHASE_RETRIES is set to 2."""
        assert MAX_PHASE_RETRIES == 2

    def test_orient_retries_from_orient(self, temp_project):
        """ORIENT phase failure retries from ORIENT."""
        recovery = get_session_recovery(temp_project)
        strategy = recovery.get_retry_strategy(SessionPhase.ORIENT, attempts=0)
        assert strategy == RetryStrategy.RETRY_FROM_ORIENT

    def test_status_check_retries_from_orient(self, temp_project):
        """STATUS_CHECK phase failure retries from ORIENT."""
        recovery = get_session_recovery(temp_project)
        strategy = recovery.get_retry_strategy(SessionPhase.STATUS_CHECK, attempts=0)
        assert strategy == RetryStrategy.RETRY_FROM_ORIENT

    def test_verification_retries_from_orient(self, temp_project):
        """VERIFICATION phase failure retries from ORIENT."""
        recovery = get_session_recovery(temp_project)
        strategy = recovery.get_retry_strategy(SessionPhase.VERIFICATION, attempts=1)
        assert strategy == RetryStrategy.RETRY_FROM_ORIENT

    def test_implementation_retries_implementation(self, temp_project):
        """IMPLEMENTATION phase failure retries from IMPLEMENTATION."""
        recovery = get_session_recovery(temp_project)
        strategy = recovery.get_retry_strategy(SessionPhase.IMPLEMENTATION, attempts=0)
        assert strategy == RetryStrategy.RETRY_IMPLEMENTATION

    def test_implementation_retries_implementation_attempt_1(self, temp_project):
        """IMPLEMENTATION with 1 attempt still retries IMPLEMENTATION."""
        recovery = get_session_recovery(temp_project)
        strategy = recovery.get_retry_strategy(SessionPhase.IMPLEMENTATION, attempts=1)
        assert strategy == RetryStrategy.RETRY_IMPLEMENTATION

    def test_commit_retries_current(self, temp_project):
        """COMMIT phase failure retries just COMMIT."""
        recovery = get_session_recovery(temp_project)
        strategy = recovery.get_retry_strategy(SessionPhase.COMMIT, attempts=0)
        assert strategy == RetryStrategy.RETRY_CURRENT

    def test_mark_done_retries_current(self, temp_project):
        """MARK_DONE phase failure retries just MARK_DONE."""
        recovery = get_session_recovery(temp_project)
        strategy = recovery.get_retry_strategy(SessionPhase.MARK_DONE, attempts=1)
        assert strategy == RetryStrategy.RETRY_CURRENT

    def test_notify_retries_current(self, temp_project):
        """NOTIFY phase failure retries just NOTIFY."""
        recovery = get_session_recovery(temp_project)
        strategy = recovery.get_retry_strategy(SessionPhase.NOTIFY, attempts=0)
        assert strategy == RetryStrategy.RETRY_CURRENT

    def test_memory_flush_retries_current(self, temp_project):
        """MEMORY_FLUSH phase failure retries just MEMORY_FLUSH."""
        recovery = get_session_recovery(temp_project)
        strategy = recovery.get_retry_strategy(SessionPhase.MEMORY_FLUSH, attempts=0)
        assert strategy == RetryStrategy.RETRY_CURRENT

    def test_escalate_on_max_retries_orient(self, temp_project):
        """ORIENT escalates after MAX_PHASE_RETRIES attempts."""
        recovery = get_session_recovery(temp_project)
        strategy = recovery.get_retry_strategy(
            SessionPhase.ORIENT, attempts=MAX_PHASE_RETRIES,
        )
        assert strategy == RetryStrategy.ESCALATE

    def test_escalate_on_max_retries_implementation(self, temp_project):
        """IMPLEMENTATION escalates after MAX_PHASE_RETRIES attempts."""
        recovery = get_session_recovery(temp_project)
        strategy = recovery.get_retry_strategy(
            SessionPhase.IMPLEMENTATION, attempts=MAX_PHASE_RETRIES,
        )
        assert strategy == RetryStrategy.ESCALATE

    def test_escalate_on_max_retries_commit(self, temp_project):
        """COMMIT escalates after MAX_PHASE_RETRIES attempts."""
        recovery = get_session_recovery(temp_project)
        strategy = recovery.get_retry_strategy(
            SessionPhase.COMMIT, attempts=MAX_PHASE_RETRIES,
        )
        assert strategy == RetryStrategy.ESCALATE

    def test_escalate_on_max_retries_notify(self, temp_project):
        """NOTIFY escalates after MAX_PHASE_RETRIES attempts."""
        recovery = get_session_recovery(temp_project)
        strategy = recovery.get_retry_strategy(
            SessionPhase.NOTIFY, attempts=MAX_PHASE_RETRIES,
        )
        assert strategy == RetryStrategy.ESCALATE

    def test_escalate_on_excess_retries(self, temp_project):
        """Escalates when attempts exceed MAX_PHASE_RETRIES."""
        recovery = get_session_recovery(temp_project)
        strategy = recovery.get_retry_strategy(
            SessionPhase.ORIENT, attempts=MAX_PHASE_RETRIES + 5,
        )
        assert strategy == RetryStrategy.ESCALATE

    def test_all_early_phases_retry_from_orient(self, temp_project):
        """All early phases (ORIENT, STATUS_CHECK, VERIFICATION) -> RETRY_FROM_ORIENT."""
        recovery = get_session_recovery(temp_project)
        early_phases = [
            SessionPhase.ORIENT,
            SessionPhase.STATUS_CHECK,
            SessionPhase.VERIFICATION,
        ]
        for phase in early_phases:
            strategy = recovery.get_retry_strategy(phase, attempts=0)
            assert strategy == RetryStrategy.RETRY_FROM_ORIENT, (
                f"Expected RETRY_FROM_ORIENT for {phase.phase_name}, got {strategy}"
            )

    def test_all_late_phases_retry_current(self, temp_project):
        """All late phases (COMMIT, MARK_DONE, NOTIFY, MEMORY_FLUSH) -> RETRY_CURRENT."""
        recovery = get_session_recovery(temp_project)
        late_phases = [
            SessionPhase.COMMIT,
            SessionPhase.MARK_DONE,
            SessionPhase.NOTIFY,
            SessionPhase.MEMORY_FLUSH,
        ]
        for phase in late_phases:
            strategy = recovery.get_retry_strategy(phase, attempts=0)
            assert strategy == RetryStrategy.RETRY_CURRENT, (
                f"Expected RETRY_CURRENT for {phase.phase_name}, got {strategy}"
            )


class TestResetPhaseAttempts:
    """Test phase attempt counter reset on success (ENG-67)."""

    @pytest.fixture
    def temp_project(self):
        """Create a temporary project directory."""
        with tempfile.TemporaryDirectory() as tmpdir:
            project_dir = Path(tmpdir)
            (project_dir / ".agent").mkdir()
            yield project_dir

    def test_reset_clears_attempt_counter(self, temp_project):
        """reset_phase_attempts resets the attempt count to zero."""
        manager = SessionStateManager(temp_project)
        manager.start_session("ENG-67")
        manager.transition_to(SessionPhase.COMMIT)

        # Record some errors to increment attempt counter
        manager.record_error(Exception("fail 1"), ErrorType.GIT_ERROR)
        manager.record_error(Exception("fail 2"), ErrorType.GIT_ERROR)

        assert manager.get_phase_attempt(SessionPhase.COMMIT).attempt == 2
        assert manager.current_state.phase_attempts.get("commit") == 2

        # Reset and verify
        manager.reset_phase_attempts(SessionPhase.COMMIT)

        assert manager.get_phase_attempt(SessionPhase.COMMIT).attempt == 0
        assert manager.current_state.phase_attempts.get("commit") == 0

    def test_reset_allows_retry_again(self, temp_project):
        """After reset, can_retry returns True again."""
        manager = SessionStateManager(temp_project)
        manager.start_session("ENG-67")
        manager.transition_to(SessionPhase.COMMIT)

        # Exhaust retries
        for _ in range(2):
            manager.record_error(Exception("fail"), ErrorType.GIT_ERROR)

        assert not manager.get_phase_attempt(SessionPhase.COMMIT).can_retry

        # Reset
        manager.reset_phase_attempts(SessionPhase.COMMIT)

        assert manager.get_phase_attempt(SessionPhase.COMMIT).can_retry

    def test_reset_untracked_phase_is_noop(self, temp_project):
        """Resetting a phase with no recorded attempts is a no-op."""
        manager = SessionStateManager(temp_project)
        manager.start_session("ENG-67")

        # Should not raise
        manager.reset_phase_attempts(SessionPhase.NOTIFY)

        # Attempt tracker should still be at 0
        assert manager.get_phase_attempt(SessionPhase.NOTIFY).attempt == 0

    def test_reset_persists_to_state(self, temp_project):
        """Phase attempt reset persists when state is saved and loaded."""
        manager = SessionStateManager(temp_project)
        manager.start_session("ENG-67")
        manager.transition_to(SessionPhase.IMPLEMENTATION)

        manager.record_error(Exception("fail"), ErrorType.UNKNOWN)
        assert manager.current_state.phase_attempts.get("implement") == 1

        manager.reset_phase_attempts(SessionPhase.IMPLEMENTATION)

        # Reload from disk
        loaded = manager.load_state()
        assert loaded is not None
        assert loaded.phase_attempts.get("implement") == 0
