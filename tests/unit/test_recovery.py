"""
Tests for Graceful Degradation Matrix (ENG-68)
===============================================

Verifies:
1. MCP retry logic with exponential backoff (3 retries, 2s/4s/8s)
2. Playwright crash fallback (returns degraded result, doesn't block)
3. Git error recovery with stash and retry
4. Rate limit backoff (30s -> 60s -> 120s)
5. Backoff timing is correct
6. Non-rate-limit errors re-raise immediately
7. RecoveryResult dataclass fields
8. Decorator API: handle_mcp_timeout, handle_playwright_error,
   handle_git_error, handle_rate_limit, retry_with_backoff
9. FailureType enum and unified handle/protected API
"""

import tempfile
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from axon_agent.core.recovery import (
    DEFAULT_BASE_DELAY_SECONDS,
    DEFAULT_MAX_RETRIES,
    GIT_MAX_RETRIES,
    HTTP_429_TOO_MANY_REQUESTS,
    MCP_BASE_DELAY_SECONDS,
    MCP_MAX_RETRIES,
    RATE_LIMIT_BACKOFF_SECONDS,
    RATE_LIMIT_MAX_RETRIES,
    DegradedResult,
    FailureType,
    GracefulDegradation,
    RecoveryResult,
    _is_rate_limit_error,
    handle_git_error,
    handle_mcp_timeout,
    handle_playwright_error,
    handle_rate_limit,
    retry_with_backoff,
)


# --- Helpers ---

async def _always_succeeds() -> str:
    """Async function that always succeeds."""
    return "ok"


async def _always_fails() -> str:
    """Async function that always raises TimeoutError."""
    raise TimeoutError("MCP server unreachable")


def _make_flaky(fail_count: int, exc: Exception | None = None) -> AsyncMock:
    """Create a callable that fails `fail_count` times then succeeds.

    Args:
        fail_count: Number of times to raise before returning "ok"
        exc: Exception to raise (defaults to TimeoutError)

    Returns:
        AsyncMock configured to fail then succeed
    """
    error = exc or TimeoutError("transient failure")
    call_counter = {"n": 0}

    async def _func(*args: object, **kwargs: object) -> str:
        call_counter["n"] += 1
        if call_counter["n"] <= fail_count:
            raise error
        return "ok"

    mock = AsyncMock(side_effect=_func)
    mock._call_counter = call_counter  # type: ignore[attr-defined]
    return mock


# --- RecoveryResult Tests ---

class TestRecoveryResult:
    """Test RecoveryResult dataclass."""

    def test_default_values(self) -> None:
        """Default values are sensible."""
        result = RecoveryResult(success=True)
        assert result.fallback_used is False
        assert result.error_message == ""
        assert result.retry_count == 0

    def test_full_construction(self) -> None:
        """All fields can be set."""
        result = RecoveryResult(
            success=False,
            fallback_used=True,
            error_message="Service unavailable",
            retry_count=3,
        )
        assert result.success is False
        assert result.fallback_used is True
        assert result.error_message == "Service unavailable"
        assert result.retry_count == 3

    def test_success_result(self) -> None:
        """Successful result has no error and no fallback."""
        result = RecoveryResult(success=True, retry_count=0)
        assert result.success is True
        assert result.fallback_used is False
        assert result.error_message == ""

    def test_fallback_result(self) -> None:
        """Fallback result indicates degraded service."""
        result = RecoveryResult(
            success=False,
            fallback_used=True,
            error_message="Notification skipped",
            retry_count=3,
        )
        assert result.fallback_used is True
        assert result.retry_count == 3


# --- MCP Retry Tests ---

class TestMCPRetry:
    """Test with_mcp_retry wrapper."""

    @pytest.fixture
    def degradation(self) -> GracefulDegradation:
        """Create GracefulDegradation instance."""
        return GracefulDegradation()

    async def test_success_returns_value(self, degradation: GracefulDegradation) -> None:
        """Successful call returns DegradedResult with value."""
        result = await degradation.with_mcp_retry(_always_succeeds)

        assert result.success is True
        assert result.value == "ok"
        assert result.degraded is False

    async def test_retries_on_failure(self, degradation: GracefulDegradation) -> None:
        """Retries up to MCP_MAX_RETRIES times before degrading."""
        func = _make_flaky(MCP_MAX_RETRIES + 1)

        with patch("axon_agent.core.recovery.asyncio.sleep", new_callable=AsyncMock) as mock_sleep:
            result = await degradation.with_mcp_retry(func)

        assert result.success is False
        assert result.degraded is True
        assert "failed after" in result.message
        assert mock_sleep.call_count == MCP_MAX_RETRIES - 1

    async def test_succeeds_after_transient_failure(self, degradation: GracefulDegradation) -> None:
        """Succeeds on second attempt after one failure."""
        func = _make_flaky(1)

        with patch("axon_agent.core.recovery.asyncio.sleep", new_callable=AsyncMock):
            result = await degradation.with_mcp_retry(func)

        assert result.success is True
        assert result.value == "ok"

    async def test_exponential_backoff_timing(self, degradation: GracefulDegradation) -> None:
        """Backoff delays follow 2s, 4s pattern."""
        func = _make_flaky(MCP_MAX_RETRIES + 1)

        with patch("axon_agent.core.recovery.asyncio.sleep", new_callable=AsyncMock) as mock_sleep:
            await degradation.with_mcp_retry(func)

        # Should have slept (MCP_MAX_RETRIES - 1) times
        delays = [call.args[0] for call in mock_sleep.call_args_list]
        expected_delays = [MCP_BASE_DELAY_SECONDS * (2 ** i) for i in range(MCP_MAX_RETRIES - 1)]
        assert delays == expected_delays

    async def test_degraded_result_contains_error_details(self, degradation: GracefulDegradation) -> None:
        """Degraded result message includes individual error descriptions."""
        func = _make_flaky(MCP_MAX_RETRIES + 1, exc=TimeoutError("SSE timeout"))

        with patch("axon_agent.core.recovery.asyncio.sleep", new_callable=AsyncMock):
            result = await degradation.with_mcp_retry(func)

        assert "SSE timeout" in result.message
        assert "Skipping notifications" in result.message

    async def test_forwards_args_and_kwargs(self, degradation: GracefulDegradation) -> None:
        """Arguments and keyword arguments are forwarded to the wrapped function."""
        async def _with_args(a: int, b: str, flag: bool = False) -> str:
            return f"{a}-{b}-{flag}"

        result = await degradation.with_mcp_retry(_with_args, 42, "hello", flag=True)

        assert result.success is True
        assert result.value == "42-hello-True"


# --- Playwright Fallback Tests ---

class TestPlaywrightFallback:
    """Test with_playwright_fallback wrapper."""

    @pytest.fixture
    def degradation(self) -> GracefulDegradation:
        """Create GracefulDegradation instance."""
        return GracefulDegradation()

    async def test_success_returns_value(self, degradation: GracefulDegradation) -> None:
        """Successful call returns value."""
        result = await degradation.with_playwright_fallback(_always_succeeds)

        assert result.success is True
        assert result.value == "ok"
        assert result.degraded is False

    async def test_catches_playwright_exception(self, degradation: GracefulDegradation) -> None:
        """Playwright error returns degraded result, does not raise."""
        async def _browser_crash() -> None:
            raise RuntimeError("Browser has been closed")

        result = await degradation.with_playwright_fallback(_browser_crash)

        assert result.success is False
        assert result.degraded is True
        assert "Screenshot unavailable due to browser error" in result.message
        assert "RuntimeError" in result.message

    async def test_catches_connection_error(self, degradation: GracefulDegradation) -> None:
        """Network-level browser error is caught."""
        async def _connection_fail() -> None:
            raise ConnectionError("Playwright WebSocket connection lost")

        result = await degradation.with_playwright_fallback(_connection_fail)

        assert result.success is False
        assert result.degraded is True
        assert "browser error" in result.message

    async def test_returns_gracefully_without_blocking(self, degradation: GracefulDegradation) -> None:
        """Fallback returns immediately without retries or delays."""
        call_count = 0

        async def _explodes() -> None:
            nonlocal call_count
            call_count += 1
            raise OSError("Browser process crashed")

        result = await degradation.with_playwright_fallback(_explodes)

        assert call_count == 1  # No retries
        assert result.degraded is True


# --- Git Recovery Tests ---

class TestGitRecovery:
    """Test with_git_recovery wrapper."""

    @pytest.fixture
    def temp_project(self) -> Path:
        """Create a temporary directory for git operations."""
        with tempfile.TemporaryDirectory() as tmpdir:
            yield Path(tmpdir)

    @pytest.fixture
    def degradation(self, temp_project: Path) -> GracefulDegradation:
        """Create GracefulDegradation instance with temp project dir."""
        return GracefulDegradation(project_dir=temp_project)

    async def test_success_returns_value(self, degradation: GracefulDegradation) -> None:
        """Successful git operation returns value."""
        result = await degradation.with_git_recovery(_always_succeeds)

        assert result.success is True
        assert result.value == "ok"

    async def test_retries_after_stash(self, degradation: GracefulDegradation) -> None:
        """On failure, stashes and retries the operation."""
        func = _make_flaky(1, exc=Exception("git push failed: uncommitted changes"))

        with patch.object(degradation, "_try_git_stash", return_value=True):
            result = await degradation.with_git_recovery(func)

        assert result.success is True
        assert result.value == "ok"

    async def test_returns_error_context_on_persistent_failure(
        self, degradation: GracefulDegradation
    ) -> None:
        """Returns error with context when all retries fail."""
        async def _always_git_fail() -> None:
            raise Exception("git merge conflict in file.py")

        with (
            patch.object(degradation, "_try_git_stash", return_value=False),
            patch.object(degradation, "_collect_git_context", return_value="3 modified/untracked file(s)"),
        ):
            result = await degradation.with_git_recovery(_always_git_fail)

        assert result.success is False
        assert result.degraded is False
        assert "failed after" in result.message
        assert "3 modified/untracked file(s)" in result.message

    async def test_stash_called_on_failure(self, degradation: GracefulDegradation) -> None:
        """Git stash is attempted between retries."""
        func = _make_flaky(2, exc=Exception("git error"))

        with patch.object(degradation, "_try_git_stash", return_value=True) as mock_stash:
            await degradation.with_git_recovery(func)

        # Stash should be called once (after first failure, before second attempt)
        assert mock_stash.call_count == 1

    async def test_stash_failure_does_not_block_retry(self, degradation: GracefulDegradation) -> None:
        """Even if stash fails, the retry still happens."""
        func = _make_flaky(1, exc=Exception("uncommitted changes"))

        with patch.object(degradation, "_try_git_stash", return_value=False):
            result = await degradation.with_git_recovery(func)

        assert result.success is True


# --- Rate Limit Backoff Tests ---

class TestRateLimitBackoff:
    """Test with_rate_limit_backoff wrapper."""

    @pytest.fixture
    def degradation(self) -> GracefulDegradation:
        """Create GracefulDegradation instance."""
        return GracefulDegradation()

    async def test_success_returns_value(self, degradation: GracefulDegradation) -> None:
        """Successful call returns value without backoff."""
        result = await degradation.with_rate_limit_backoff(_always_succeeds)

        assert result.success is True
        assert result.value == "ok"

    async def test_backoff_on_rate_limit(self, degradation: GracefulDegradation) -> None:
        """Rate limit triggers escalating backoff delays."""
        func = _make_flaky(RATE_LIMIT_MAX_RETRIES + 1, exc=Exception("HTTP 429: too many requests"))

        with patch("axon_agent.core.recovery.asyncio.sleep", new_callable=AsyncMock) as mock_sleep:
            with pytest.raises(RuntimeError, match="Rate limit exceeded"):
                await degradation.with_rate_limit_backoff(func)

        delays = [call.args[0] for call in mock_sleep.call_args_list]
        expected = list(RATE_LIMIT_BACKOFF_SECONDS[:-1])  # Sleep between retries, not after last
        assert delays == expected

    async def test_succeeds_after_rate_limit_clears(self, degradation: GracefulDegradation) -> None:
        """Succeeds on second attempt after rate limit clears."""
        func = _make_flaky(1, exc=Exception("Rate limit exceeded (429)"))

        with patch("axon_agent.core.recovery.asyncio.sleep", new_callable=AsyncMock):
            result = await degradation.with_rate_limit_backoff(func)

        assert result.success is True
        assert result.value == "ok"

    async def test_raises_after_max_retries(self, degradation: GracefulDegradation) -> None:
        """RuntimeError raised after all retries exhausted."""
        async def _rate_limited() -> None:
            raise Exception("429: Too Many Requests")

        with patch("axon_agent.core.recovery.asyncio.sleep", new_callable=AsyncMock):
            with pytest.raises(RuntimeError, match="Rate limit exceeded after"):
                await degradation.with_rate_limit_backoff(_rate_limited)

    async def test_non_rate_limit_error_raises_immediately(self, degradation: GracefulDegradation) -> None:
        """Non-rate-limit errors are re-raised without retry."""
        async def _auth_error() -> None:
            raise ValueError("Invalid API key")

        with pytest.raises(ValueError, match="Invalid API key"):
            await degradation.with_rate_limit_backoff(_auth_error)

    async def test_backoff_timing_30_60_120(self, degradation: GracefulDegradation) -> None:
        """Backoff schedule is exactly 30s, 60s, 120s."""
        func = _make_flaky(RATE_LIMIT_MAX_RETRIES + 1, exc=Exception("429 rate limit"))

        with patch("axon_agent.core.recovery.asyncio.sleep", new_callable=AsyncMock) as mock_sleep:
            with pytest.raises(RuntimeError):
                await degradation.with_rate_limit_backoff(func)

        delays = [call.args[0] for call in mock_sleep.call_args_list]
        # Between attempts: sleep happens between 1->2 and 2->3 (not after last)
        assert delays == [30.0, 60.0]

    async def test_error_message_includes_total_backoff(self, degradation: GracefulDegradation) -> None:
        """RuntimeError message includes total backoff time."""
        func = _make_flaky(RATE_LIMIT_MAX_RETRIES + 1, exc=Exception("429"))

        with patch("axon_agent.core.recovery.asyncio.sleep", new_callable=AsyncMock):
            with pytest.raises(RuntimeError) as exc_info:
                await degradation.with_rate_limit_backoff(func)

        assert "total backoff" in str(exc_info.value)


# --- Rate Limit Detection Tests ---

class TestIsRateLimitError:
    """Test _is_rate_limit_error helper."""

    def test_detects_429_in_message(self) -> None:
        """Detects '429' in error message."""
        assert _is_rate_limit_error(Exception("HTTP 429 error")) is True

    def test_detects_rate_limit_phrase(self) -> None:
        """Detects 'rate limit' in error message."""
        assert _is_rate_limit_error(Exception("Rate limit exceeded")) is True

    def test_detects_too_many_requests(self) -> None:
        """Detects 'too many requests' in error message."""
        assert _is_rate_limit_error(Exception("Too Many Requests")) is True

    def test_detects_status_code_attribute(self) -> None:
        """Detects status_code=429 on exception object."""
        exc = Exception("error")
        exc.status_code = HTTP_429_TOO_MANY_REQUESTS  # type: ignore[attr-defined]
        assert _is_rate_limit_error(exc) is True

    def test_detects_response_status_code(self) -> None:
        """Detects response.status_code=429 on exception object."""
        response = MagicMock()
        response.status_code = HTTP_429_TOO_MANY_REQUESTS
        exc = Exception("error")
        exc.response = response  # type: ignore[attr-defined]
        assert _is_rate_limit_error(exc) is True

    def test_rejects_non_rate_limit(self) -> None:
        """Non-rate-limit errors return False."""
        assert _is_rate_limit_error(ValueError("Invalid input")) is False

    def test_rejects_generic_timeout(self) -> None:
        """Generic timeout is not a rate limit."""
        assert _is_rate_limit_error(TimeoutError("Connection timed out")) is False


# --- Git Helper Tests ---

class TestGitHelpers:
    """Test git helper methods."""

    @pytest.fixture
    def temp_project(self) -> Path:
        """Create a temporary directory."""
        with tempfile.TemporaryDirectory() as tmpdir:
            yield Path(tmpdir)

    def test_try_git_stash_success(self, temp_project: Path) -> None:
        """Git stash returns True on success."""
        degradation = GracefulDegradation(project_dir=temp_project)

        with patch("axon_agent.core.recovery.subprocess.run") as mock_run:
            mock_run.return_value = MagicMock(returncode=0, stderr="")
            result = degradation._try_git_stash()

        assert result is True

    def test_try_git_stash_failure(self, temp_project: Path) -> None:
        """Git stash returns False on failure."""
        degradation = GracefulDegradation(project_dir=temp_project)

        with patch("axon_agent.core.recovery.subprocess.run") as mock_run:
            mock_run.return_value = MagicMock(returncode=1, stderr="No local changes to save")
            result = degradation._try_git_stash()

        assert result is False

    def test_try_git_stash_exception(self, temp_project: Path) -> None:
        """Git stash returns False on subprocess error."""
        degradation = GracefulDegradation(project_dir=temp_project)

        with patch("axon_agent.core.recovery.subprocess.run", side_effect=FileNotFoundError("git not found")):
            result = degradation._try_git_stash()

        assert result is False

    def test_collect_git_context_clean(self, temp_project: Path) -> None:
        """Returns 'clean working tree' when no changes."""
        degradation = GracefulDegradation(project_dir=temp_project)

        with patch("axon_agent.core.recovery.subprocess.run") as mock_run:
            mock_run.return_value = MagicMock(returncode=0, stdout="")
            context = degradation._collect_git_context()

        assert context == "clean working tree"

    def test_collect_git_context_with_changes(self, temp_project: Path) -> None:
        """Returns file count when there are changes."""
        degradation = GracefulDegradation(project_dir=temp_project)

        with patch("axon_agent.core.recovery.subprocess.run") as mock_run:
            mock_run.return_value = MagicMock(returncode=0, stdout="M file1.py\nM file2.py\n?? new.txt")
            context = degradation._collect_git_context()

        assert "3 modified/untracked file(s)" in context

    def test_collect_git_context_error(self, temp_project: Path) -> None:
        """Returns fallback message on error."""
        degradation = GracefulDegradation(project_dir=temp_project)

        with patch("axon_agent.core.recovery.subprocess.run", side_effect=FileNotFoundError("git not found")):
            context = degradation._collect_git_context()

        assert "unable to read git status" in context


# --- DegradedResult Tests ---

class TestDegradedResult:
    """Test DegradedResult dataclass."""

    def test_default_values(self) -> None:
        """Default values are sensible."""
        result = DegradedResult(success=True)
        assert result.value is None
        assert result.degraded is False
        assert result.message == ""

    def test_full_construction(self) -> None:
        """All fields can be set."""
        result = DegradedResult(
            success=False,
            value=42,
            degraded=True,
            message="Service unavailable",
        )
        assert result.success is False
        assert result.value == 42
        assert result.degraded is True
        assert result.message == "Service unavailable"


# --- Decorator API Tests (ENG-68) ---

class TestRetryWithBackoffDecorator:
    """Test the @retry_with_backoff decorator."""

    async def test_success_on_first_attempt(self) -> None:
        """Returns success with retry_count=0 on first attempt."""
        @retry_with_backoff(max_retries=3, base_delay=0.01)
        async def _succeeds() -> str:
            return "done"

        result = await _succeeds()
        assert result.success is True
        assert result.retry_count == 0
        assert result.fallback_used is False

    async def test_retries_then_succeeds(self) -> None:
        """Succeeds after transient failure with correct retry_count."""
        counter = {"n": 0}

        @retry_with_backoff(max_retries=3, base_delay=0.01)
        async def _flaky() -> str:
            counter["n"] += 1
            if counter["n"] < 2:
                raise TimeoutError("transient")
            return "recovered"

        with patch("axon_agent.core.recovery.asyncio.sleep", new_callable=AsyncMock):
            result = await _flaky()

        assert result.success is True
        assert result.retry_count == 1

    async def test_exhausts_retries(self) -> None:
        """Returns failure after all retries exhausted."""
        @retry_with_backoff(max_retries=2, base_delay=0.01)
        async def _fails() -> None:
            raise RuntimeError("permanent failure")

        with patch("axon_agent.core.recovery.asyncio.sleep", new_callable=AsyncMock):
            result = await _fails()

        assert result.success is False
        assert result.retry_count == 2
        assert "permanent failure" in result.error_message

    async def test_backoff_delays(self) -> None:
        """Delays follow exponential pattern: base, base*factor, ..."""
        @retry_with_backoff(max_retries=3, base_delay=1.0, backoff_factor=2.0)
        async def _fails() -> None:
            raise RuntimeError("fail")

        with patch("axon_agent.core.recovery.asyncio.sleep", new_callable=AsyncMock) as mock_sleep:
            await _fails()

        delays = [call.args[0] for call in mock_sleep.call_args_list]
        assert delays == [1.0, 2.0]  # 1*2^0, 1*2^1 (no sleep after last)


class TestHandleMCPTimeoutDecorator:
    """Test the @handle_mcp_timeout decorator."""

    async def test_success(self) -> None:
        """Decorated function succeeds on first call."""
        @handle_mcp_timeout
        async def _mcp_call() -> str:
            return "ok"

        result = await _mcp_call()
        assert result.success is True
        assert result.retry_count == 0

    async def test_retries_and_degrades(self) -> None:
        """Returns fallback_used=True after MCP_MAX_RETRIES failures."""
        counter = {"n": 0}

        @handle_mcp_timeout
        async def _mcp_timeout() -> None:
            counter["n"] += 1
            raise TimeoutError("MCP SSE timeout")

        with patch("axon_agent.core.recovery.asyncio.sleep", new_callable=AsyncMock):
            result = await _mcp_timeout()

        assert result.success is False
        assert result.fallback_used is True
        assert result.retry_count == MCP_MAX_RETRIES
        assert "skipping notifications" in result.error_message
        assert counter["n"] == MCP_MAX_RETRIES

    async def test_backoff_timing(self) -> None:
        """MCP timeout uses 2s, 4s exponential backoff."""
        @handle_mcp_timeout
        async def _mcp_timeout() -> None:
            raise TimeoutError("timeout")

        with patch("axon_agent.core.recovery.asyncio.sleep", new_callable=AsyncMock) as mock_sleep:
            await _mcp_timeout()

        delays = [call.args[0] for call in mock_sleep.call_args_list]
        expected = [MCP_BASE_DELAY_SECONDS * (2 ** i) for i in range(MCP_MAX_RETRIES - 1)]
        assert delays == expected

    async def test_succeeds_after_one_failure(self) -> None:
        """Returns success after transient MCP failure."""
        counter = {"n": 0}

        @handle_mcp_timeout
        async def _flaky_mcp() -> str:
            counter["n"] += 1
            if counter["n"] < 2:
                raise TimeoutError("transient MCP failure")
            return "ok"

        with patch("axon_agent.core.recovery.asyncio.sleep", new_callable=AsyncMock):
            result = await _flaky_mcp()

        assert result.success is True
        assert result.retry_count == 1


class TestHandlePlaywrightErrorDecorator:
    """Test the @handle_playwright_error decorator."""

    async def test_success(self) -> None:
        """Returns success when browser operation works."""
        @handle_playwright_error
        async def _take_screenshot() -> str:
            return "screenshot.png"

        result = await _take_screenshot()
        assert result.success is True
        assert result.retry_count == 0

    async def test_catches_browser_crash(self) -> None:
        """Returns fallback result on browser crash, no retry."""
        @handle_playwright_error
        async def _browser_crash() -> None:
            raise RuntimeError("Browser has been closed")

        result = await _browser_crash()

        assert result.success is False
        assert result.fallback_used is True
        assert result.retry_count == 0
        assert "Screenshot unavailable" in result.error_message
        assert "RuntimeError" in result.error_message

    async def test_catches_connection_error(self) -> None:
        """WebSocket disconnect is caught gracefully."""
        @handle_playwright_error
        async def _ws_fail() -> None:
            raise ConnectionError("WebSocket disconnected")

        result = await _ws_fail()

        assert result.success is False
        assert result.fallback_used is True
        assert "browser error" in result.error_message


class TestHandleGitErrorDecorator:
    """Test the @handle_git_error decorator."""

    async def test_success(self) -> None:
        """Returns success for clean git operation."""
        @handle_git_error
        async def _git_commit() -> str:
            return "committed"

        result = await _git_commit()
        assert result.success is True
        assert result.retry_count == 0

    async def test_retries_with_stash(self) -> None:
        """Attempts git stash between retries."""
        counter = {"n": 0}

        @handle_git_error
        async def _git_conflict() -> str:
            counter["n"] += 1
            if counter["n"] < 2:
                raise Exception("git merge conflict")
            return "resolved"

        with patch("axon_agent.core.recovery._try_git_stash_cwd", return_value=True) as mock_stash:
            result = await _git_conflict()

        assert result.success is True
        assert result.retry_count == 1
        mock_stash.assert_called_once()

    async def test_fails_after_max_retries(self) -> None:
        """Returns failure after GIT_MAX_RETRIES attempts."""
        @handle_git_error
        async def _always_conflict() -> None:
            raise Exception("persistent merge conflict")

        with patch("axon_agent.core.recovery._try_git_stash_cwd", return_value=False):
            result = await _always_conflict()

        assert result.success is False
        assert result.retry_count == GIT_MAX_RETRIES
        assert "failed after" in result.error_message


class TestHandleRateLimitDecorator:
    """Test the @handle_rate_limit decorator."""

    async def test_success(self) -> None:
        """Returns success on first call without backoff."""
        @handle_rate_limit
        async def _api_call() -> str:
            return "response"

        result = await _api_call()
        assert result.success is True
        assert result.retry_count == 0

    async def test_rate_limit_backoff_30_60_120(self) -> None:
        """Uses 30s, 60s backoff between retries."""
        @handle_rate_limit
        async def _rate_limited() -> None:
            raise Exception("429 Too Many Requests")

        with patch("axon_agent.core.recovery.asyncio.sleep", new_callable=AsyncMock) as mock_sleep:
            result = await _rate_limited()

        assert result.success is False
        assert result.retry_count == RATE_LIMIT_MAX_RETRIES
        delays = [call.args[0] for call in mock_sleep.call_args_list]
        assert delays == [30.0, 60.0]  # No sleep after last attempt

    async def test_non_rate_limit_returns_immediately(self) -> None:
        """Non-rate-limit errors return failed result without retrying."""
        @handle_rate_limit
        async def _auth_fail() -> None:
            raise ValueError("Invalid API key")

        result = await _auth_fail()

        assert result.success is False
        assert result.retry_count == 0
        assert "Non-rate-limit error" in result.error_message

    async def test_succeeds_after_rate_limit_clears(self) -> None:
        """Recovers when rate limit clears on second attempt."""
        counter = {"n": 0}

        @handle_rate_limit
        async def _transient_limit() -> str:
            counter["n"] += 1
            if counter["n"] < 2:
                raise Exception("HTTP 429: rate limit")
            return "ok"

        with patch("axon_agent.core.recovery.asyncio.sleep", new_callable=AsyncMock):
            result = await _transient_limit()

        assert result.success is True
        assert result.retry_count == 1

    async def test_error_message_on_exhaustion(self) -> None:
        """Error message describes rate limit exhaustion."""
        @handle_rate_limit
        async def _always_limited() -> None:
            raise Exception("429 rate limit exceeded")

        with patch("axon_agent.core.recovery.asyncio.sleep", new_callable=AsyncMock):
            result = await _always_limited()

        assert "Rate limit exceeded" in result.error_message
        assert result.retry_count == RATE_LIMIT_MAX_RETRIES


# --- FailureType Enum Tests (ENG-68) ---

class TestFailureType:
    """Test FailureType enum values."""

    def test_all_members(self) -> None:
        """All four failure types are defined."""
        assert FailureType.MCP_TIMEOUT.value == "mcp_timeout"
        assert FailureType.PLAYWRIGHT_CRASH.value == "playwright_crash"
        assert FailureType.GIT_ERROR.value == "git_error"
        assert FailureType.RATE_LIMIT.value == "rate_limit"

    def test_member_count(self) -> None:
        """Exactly four failure types exist."""
        assert len(FailureType) == 4


# --- Unified handle() Decorator Tests (ENG-68) ---

class TestHandleDecorator:
    """Test GracefulDegradation.handle() unified decorator API."""

    @pytest.fixture
    def recovery(self) -> GracefulDegradation:
        """Create GracefulDegradation instance."""
        return GracefulDegradation()

    async def test_mcp_timeout_decorator(self, recovery: GracefulDegradation) -> None:
        """handle(MCP_TIMEOUT) wraps with MCP retry logic."""
        @recovery.handle(FailureType.MCP_TIMEOUT)
        async def _mcp_call() -> str:
            return "ok"

        result = await _mcp_call()
        assert result.success is True
        assert result.retry_count == 0

    async def test_playwright_crash_decorator(self, recovery: GracefulDegradation) -> None:
        """handle(PLAYWRIGHT_CRASH) catches browser errors."""
        @recovery.handle(FailureType.PLAYWRIGHT_CRASH)
        async def _screenshot() -> None:
            raise RuntimeError("Browser closed")

        result = await _screenshot()
        assert result.success is False
        assert result.fallback_used is True
        assert "Screenshot unavailable" in result.error_message

    async def test_git_error_decorator(self, recovery: GracefulDegradation) -> None:
        """handle(GIT_ERROR) wraps with git stash/retry logic."""
        @recovery.handle(FailureType.GIT_ERROR)
        async def _git_push() -> str:
            return "pushed"

        result = await _git_push()
        assert result.success is True
        assert result.retry_count == 0

    async def test_rate_limit_decorator(self, recovery: GracefulDegradation) -> None:
        """handle(RATE_LIMIT) wraps with rate limit backoff."""
        @recovery.handle(FailureType.RATE_LIMIT)
        async def _api_call() -> str:
            return "response"

        result = await _api_call()
        assert result.success is True
        assert result.retry_count == 0

    async def test_mcp_timeout_retries_and_degrades(
        self, recovery: GracefulDegradation
    ) -> None:
        """handle(MCP_TIMEOUT) retries then reports fallback."""
        counter = {"n": 0}

        @recovery.handle(FailureType.MCP_TIMEOUT)
        async def _mcp_fail() -> None:
            counter["n"] += 1
            raise TimeoutError("MCP unreachable")

        with patch("axon_agent.core.recovery.asyncio.sleep", new_callable=AsyncMock):
            result = await _mcp_fail()

        assert result.success is False
        assert result.fallback_used is True
        assert counter["n"] == MCP_MAX_RETRIES


# --- Unified protected() Context Manager Tests (ENG-68) ---

class TestProtectedContextManager:
    """Test GracefulDegradation.protected() async context manager."""

    @pytest.fixture
    def recovery(self) -> GracefulDegradation:
        """Create GracefulDegradation instance."""
        return GracefulDegradation()

    async def test_success_marks_result(self, recovery: GracefulDegradation) -> None:
        """On success, result.success is True and fallback_used is False."""
        async with recovery.protected(FailureType.PLAYWRIGHT_CRASH) as result:
            pass  # No error

        assert result.success is True
        assert result.fallback_used is False
        assert result.error_message == ""

    async def test_playwright_crash_caught(self, recovery: GracefulDegradation) -> None:
        """Browser crash inside protected block is caught gracefully."""
        async with recovery.protected(FailureType.PLAYWRIGHT_CRASH) as result:
            raise RuntimeError("Browser has been closed")

        assert result.success is False
        assert result.fallback_used is True
        assert "Screenshot unavailable due to browser error" in result.error_message
        assert "RuntimeError" in result.error_message

    async def test_mcp_timeout_caught(self, recovery: GracefulDegradation) -> None:
        """MCP timeout inside protected block is caught gracefully."""
        async with recovery.protected(FailureType.MCP_TIMEOUT) as result:
            raise TimeoutError("SSE connection timed out")

        assert result.success is False
        assert result.fallback_used is True
        assert "MCP call failed" in result.error_message

    async def test_git_error_caught(self, recovery: GracefulDegradation) -> None:
        """Git error inside protected block is caught gracefully."""
        async with recovery.protected(FailureType.GIT_ERROR) as result:
            raise Exception("git merge conflict in main.py")

        assert result.success is False
        assert result.fallback_used is True
        assert "Git operation failed" in result.error_message

    async def test_rate_limit_caught(self, recovery: GracefulDegradation) -> None:
        """Rate limit inside protected block is caught gracefully."""
        async with recovery.protected(FailureType.RATE_LIMIT) as result:
            raise Exception("HTTP 429: Too Many Requests")

        assert result.success is False
        assert result.fallback_used is True
        assert "Rate limit exceeded" in result.error_message

    async def test_no_retry_in_context_manager(
        self, recovery: GracefulDegradation
    ) -> None:
        """Context manager does not retry -- single attempt only."""
        call_count = 0

        async with recovery.protected(FailureType.MCP_TIMEOUT) as result:
            call_count += 1
            raise TimeoutError("timeout")

        assert call_count == 1
        assert result.retry_count == 0

    async def test_does_not_propagate_exception(
        self, recovery: GracefulDegradation
    ) -> None:
        """Exception from body does not escape the async with block."""
        caught_outside = False
        try:
            async with recovery.protected(FailureType.PLAYWRIGHT_CRASH) as result:
                raise OSError("Process crashed")
        except OSError:
            caught_outside = True

        assert caught_outside is False
        assert result.fallback_used is True
