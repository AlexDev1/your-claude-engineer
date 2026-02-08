"""
Tests for MCP timeout handling and exponential backoff (ENG-70)
================================================================

Verifies:
1. Exponential backoff calculation with correct bounds
2. Jitter stays within +/-20% of base backoff
3. Retry on timeout with exponential backoff
4. Max retries exceeded raises MCPTimeoutError
5. Rate limit backoff uses longer initial delay
6. Graceful degradation triggered on exhaustion
7. MCPTimeoutError attributes
8. Non-retryable errors propagate immediately
9. Success on first attempt (no retry overhead)
10. Success after transient timeout
"""

import asyncio
from typing import Any
from unittest.mock import AsyncMock, patch

import pytest

from client import (
    BACKOFF_MULTIPLIER,
    INITIAL_BACKOFF_SECONDS,
    MAX_BACKOFF_SECONDS,
    MAX_RETRIES,
    MCP_TIMEOUT_SECONDS,
    RATE_LIMIT_INITIAL_BACKOFF_SECONDS,
    MCPTimeoutError,
    calculate_backoff,
    call_mcp_tool_with_retry,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_timeout_fn(fail_count: int) -> AsyncMock:
    """Create a callable that raises TimeoutError ``fail_count`` times then succeeds.

    Args:
        fail_count: Number of times to raise asyncio.TimeoutError before returning

    Returns:
        AsyncMock that simulates transient timeouts
    """
    counter = {"n": 0}

    async def _fn(*args: Any, **kwargs: Any) -> str:
        counter["n"] += 1
        if counter["n"] <= fail_count:
            raise asyncio.TimeoutError("simulated timeout")
        return "ok"

    mock = AsyncMock(side_effect=_fn)
    mock._counter = counter  # type: ignore[attr-defined]
    return mock


# ---------------------------------------------------------------------------
# MCPTimeoutError Tests
# ---------------------------------------------------------------------------

class TestMCPTimeoutError:
    """Test MCPTimeoutError exception class."""

    def test_attributes(self) -> None:
        """Error stores tool_name and timeout as attributes."""
        err = MCPTimeoutError("mcp__task__GetIssue", 30.0)
        assert err.tool_name == "mcp__task__GetIssue"
        assert err.timeout == 30.0

    def test_message_format(self) -> None:
        """Error message includes tool name and timeout value."""
        err = MCPTimeoutError("mcp__telegram__SendMessage", 15.5)
        assert "mcp__telegram__SendMessage" in str(err)
        assert "15.5s" in str(err)

    def test_inherits_exception(self) -> None:
        """MCPTimeoutError is an Exception subclass."""
        err = MCPTimeoutError("tool", 1.0)
        assert isinstance(err, Exception)


# ---------------------------------------------------------------------------
# calculate_backoff Tests
# ---------------------------------------------------------------------------

class TestCalculateBackoff:
    """Test exponential backoff calculation."""

    def test_first_attempt_near_initial(self) -> None:
        """Attempt 0 produces a backoff near the initial value."""
        for _ in range(50):
            backoff = calculate_backoff(0, initial=1.0, max_backoff=30.0, multiplier=2.0)
            # 1.0 +/- 20% => [0.8, 1.2]
            assert 0.8 <= backoff <= 1.2

    def test_exponential_growth(self) -> None:
        """Backoff grows exponentially with attempt number."""
        with patch("client.random.random", return_value=0.5):
            # Jitter factor = 0.2 * (0.5*2 - 1) = 0.0, so no jitter
            b0 = calculate_backoff(0, initial=1.0, max_backoff=100.0, multiplier=2.0)
            b1 = calculate_backoff(1, initial=1.0, max_backoff=100.0, multiplier=2.0)
            b2 = calculate_backoff(2, initial=1.0, max_backoff=100.0, multiplier=2.0)

        assert b0 == pytest.approx(1.0)
        assert b1 == pytest.approx(2.0)
        assert b2 == pytest.approx(4.0)

    def test_capped_at_max_backoff(self) -> None:
        """Backoff never exceeds max_backoff (plus jitter ceiling)."""
        for _ in range(50):
            backoff = calculate_backoff(
                100, initial=1.0, max_backoff=30.0, multiplier=2.0,
            )
            # max is 30.0 + 20% jitter = 36.0
            assert backoff <= 36.0

    def test_jitter_within_bounds(self) -> None:
        """Jitter stays within +/-20% of the base backoff."""
        base = 10.0
        low = base * 0.8
        high = base * 1.2

        for _ in range(100):
            backoff = calculate_backoff(0, initial=10.0, max_backoff=100.0, multiplier=2.0)
            assert low <= backoff <= high, f"Backoff {backoff} outside [{low}, {high}]"

    def test_never_negative(self) -> None:
        """Backoff is always non-negative, even with max negative jitter."""
        with patch("client.random.random", return_value=0.0):
            # Jitter factor = 0.2 * (0.0*2 - 1) = -0.2
            backoff = calculate_backoff(0, initial=0.1, max_backoff=30.0, multiplier=2.0)
        assert backoff >= 0.0

    def test_custom_multiplier(self) -> None:
        """Custom multiplier is applied correctly."""
        with patch("client.random.random", return_value=0.5):
            backoff = calculate_backoff(
                2, initial=1.0, max_backoff=100.0, multiplier=3.0,
            )
        # 1.0 * 3^2 = 9.0, no jitter when random=0.5
        assert backoff == pytest.approx(9.0)

    def test_default_parameters_match_constants(self) -> None:
        """Default parameters use the module-level constants."""
        with patch("client.random.random", return_value=0.5):
            backoff = calculate_backoff(0)
        assert backoff == pytest.approx(INITIAL_BACKOFF_SECONDS)


# ---------------------------------------------------------------------------
# call_mcp_tool_with_retry Tests
# ---------------------------------------------------------------------------

class TestCallMCPToolWithRetry:
    """Test MCP tool call wrapper with timeout and retry."""

    async def test_success_on_first_attempt(self) -> None:
        """Returns result immediately when call succeeds."""
        mock_fn = AsyncMock(return_value={"status": "ok"})

        with patch("client.asyncio.wait_for", new_callable=AsyncMock) as mock_wf:
            mock_wf.return_value = {"status": "ok"}
            result = await call_mcp_tool_with_retry(
                "mcp__task__GetIssue", mock_fn, timeout=5.0,
            )

        assert result == {"status": "ok"}

    async def test_retries_on_timeout(self) -> None:
        """Retries the call when asyncio.TimeoutError occurs."""
        call_count = 0

        async def _mock_wait_for(coro: Any, timeout: float) -> str:
            nonlocal call_count
            call_count += 1
            # Close the coroutine to avoid warnings
            coro.close()
            if call_count < 2:
                raise asyncio.TimeoutError()
            return "recovered"

        with (
            patch("client.asyncio.wait_for", side_effect=_mock_wait_for),
            patch("client.asyncio.sleep", new_callable=AsyncMock),
        ):
            result = await call_mcp_tool_with_retry(
                "mcp__task__GetIssue", AsyncMock(), timeout=5.0, max_retries=3,
            )

        assert result == "recovered"
        assert call_count == 2

    async def test_raises_mcp_timeout_after_max_retries(self) -> None:
        """Raises MCPTimeoutError after all retries are exhausted."""
        async def _mock_wait_for(coro: Any, timeout: float) -> None:
            coro.close()
            raise asyncio.TimeoutError()

        with (
            patch("client.asyncio.wait_for", side_effect=_mock_wait_for),
            patch("client.asyncio.sleep", new_callable=AsyncMock),
        ):
            with pytest.raises(MCPTimeoutError) as exc_info:
                await call_mcp_tool_with_retry(
                    "mcp__task__ListIssues", AsyncMock(),
                    timeout=30.0, max_retries=2,
                )

        assert exc_info.value.tool_name == "mcp__task__ListIssues"
        assert exc_info.value.timeout == 30.0

    async def test_backoff_called_between_retries(self) -> None:
        """asyncio.sleep is called with calculated backoff between retries."""
        async def _mock_wait_for(coro: Any, timeout: float) -> None:
            coro.close()
            raise asyncio.TimeoutError()

        with (
            patch("client.asyncio.wait_for", side_effect=_mock_wait_for),
            patch("client.asyncio.sleep", new_callable=AsyncMock) as mock_sleep,
            patch("client.calculate_backoff", side_effect=[1.5, 3.0]) as mock_backoff,
        ):
            with pytest.raises(MCPTimeoutError):
                await call_mcp_tool_with_retry(
                    "mcp__task__GetIssue", AsyncMock(),
                    timeout=5.0, max_retries=3,
                )

        # calculate_backoff called for attempt 0 and 1 (not after last)
        assert mock_backoff.call_count == 2
        mock_backoff.assert_any_call(0)
        mock_backoff.assert_any_call(1)

        # asyncio.sleep called with the backoff values
        sleep_values = [call.args[0] for call in mock_sleep.call_args_list]
        assert sleep_values == [1.5, 3.0]

    async def test_rate_limit_uses_longer_backoff(self) -> None:
        """Rate limit errors use RATE_LIMIT_INITIAL_BACKOFF_SECONDS as base."""
        call_count = 0

        async def _mock_wait_for(coro: Any, timeout: float) -> str:
            nonlocal call_count
            coro.close()
            call_count += 1
            if call_count < 3:
                raise Exception("HTTP 429: Too Many Requests")
            return "ok"

        with (
            patch("client.asyncio.wait_for", side_effect=_mock_wait_for),
            patch("client.asyncio.sleep", new_callable=AsyncMock),
            patch("client.calculate_backoff", return_value=5.0) as mock_backoff,
        ):
            result = await call_mcp_tool_with_retry(
                "mcp__task__GetIssue", AsyncMock(),
                timeout=5.0, max_retries=3,
            )

        assert result == "ok"
        # Both calls should use initial=RATE_LIMIT_INITIAL_BACKOFF_SECONDS
        for call in mock_backoff.call_args_list:
            assert call.kwargs.get("initial") == RATE_LIMIT_INITIAL_BACKOFF_SECONDS

    async def test_non_retryable_error_propagates_immediately(self) -> None:
        """Non-timeout, non-rate-limit errors are raised without retry."""
        call_count = 0

        async def _mock_wait_for(coro: Any, timeout: float) -> None:
            nonlocal call_count
            coro.close()
            call_count += 1
            raise ValueError("Invalid API key")

        with patch("client.asyncio.wait_for", side_effect=_mock_wait_for):
            with pytest.raises(ValueError, match="Invalid API key"):
                await call_mcp_tool_with_retry(
                    "mcp__task__GetIssue", AsyncMock(),
                    timeout=5.0, max_retries=3,
                )

        # Only called once -- no retry for non-retryable errors
        assert call_count == 1

    async def test_forwards_args_and_kwargs(self) -> None:
        """Positional and keyword arguments are forwarded to call_fn."""
        captured_args: tuple[Any, ...] = ()
        captured_kwargs: dict[str, Any] = {}

        async def _tool_fn(*args: Any, **kwargs: Any) -> dict[str, str]:
            return {"id": args[0], "state": kwargs.get("state", "Todo")}

        async def _mock_wait_for(coro: Any, timeout: float) -> Any:
            return await coro

        with patch("client.asyncio.wait_for", side_effect=_mock_wait_for):
            result = await call_mcp_tool_with_retry(
                "mcp__task__UpdateIssue",
                _tool_fn,
                "ENG-70",
                state="In Progress",
                timeout=5.0,
            )

        assert result == {"id": "ENG-70", "state": "In Progress"}

    async def test_default_timeout_matches_constant(self) -> None:
        """Default timeout parameter uses MCP_TIMEOUT_SECONDS."""
        captured_timeout: list[float] = []

        async def _mock_wait_for(coro: Any, timeout: float) -> str:
            captured_timeout.append(timeout)
            coro.close()
            return "ok"

        with patch("client.asyncio.wait_for", side_effect=_mock_wait_for):
            await call_mcp_tool_with_retry("mcp__task__WhoAmI", AsyncMock())

        assert captured_timeout[0] == MCP_TIMEOUT_SECONDS

    async def test_default_max_retries_matches_constant(self) -> None:
        """Default max_retries parameter uses MAX_RETRIES."""
        call_count = 0

        async def _mock_wait_for(coro: Any, timeout: float) -> None:
            nonlocal call_count
            coro.close()
            call_count += 1
            raise asyncio.TimeoutError()

        with (
            patch("client.asyncio.wait_for", side_effect=_mock_wait_for),
            patch("client.asyncio.sleep", new_callable=AsyncMock),
        ):
            with pytest.raises(MCPTimeoutError):
                await call_mcp_tool_with_retry(
                    "mcp__task__GetIssue", AsyncMock(),
                )

        assert call_count == MAX_RETRIES

    async def test_graceful_degradation_triggered_on_exhaustion(self) -> None:
        """GracefulDegradation is instantiated when retries are exhausted."""
        async def _mock_wait_for(coro: Any, timeout: float) -> None:
            coro.close()
            raise asyncio.TimeoutError()

        with (
            patch("client.asyncio.wait_for", side_effect=_mock_wait_for),
            patch("client.asyncio.sleep", new_callable=AsyncMock),
            patch("client.GracefulDegradation") as mock_gd_cls,
        ):
            from contextlib import asynccontextmanager

            @asynccontextmanager
            async def _mock_protected(failure_type: Any) -> Any:
                """Mock protected context that re-raises exceptions."""
                try:
                    yield
                except Exception:
                    raise

            mock_recovery = mock_gd_cls.return_value
            mock_recovery.protected = _mock_protected

            with pytest.raises(MCPTimeoutError):
                await call_mcp_tool_with_retry(
                    "mcp__task__GetIssue", AsyncMock(),
                    timeout=5.0, max_retries=2,
                )

            mock_gd_cls.assert_called_once()

    async def test_rate_limit_exhaustion_raises_timeout_error(self) -> None:
        """When rate-limit retries are exhausted, MCPTimeoutError is raised."""
        async def _mock_wait_for(coro: Any, timeout: float) -> None:
            coro.close()
            raise Exception("429 Too Many Requests")

        with (
            patch("client.asyncio.wait_for", side_effect=_mock_wait_for),
            patch("client.asyncio.sleep", new_callable=AsyncMock),
        ):
            with pytest.raises(MCPTimeoutError):
                await call_mcp_tool_with_retry(
                    "mcp__task__GetIssue", AsyncMock(),
                    timeout=5.0, max_retries=2,
                )

    async def test_success_after_transient_timeout(self) -> None:
        """Succeeds on third attempt after two timeouts."""
        call_count = 0

        async def _mock_wait_for(coro: Any, timeout: float) -> str:
            nonlocal call_count
            coro.close()
            call_count += 1
            if call_count <= 2:
                raise asyncio.TimeoutError()
            return "finally"

        with (
            patch("client.asyncio.wait_for", side_effect=_mock_wait_for),
            patch("client.asyncio.sleep", new_callable=AsyncMock),
        ):
            result = await call_mcp_tool_with_retry(
                "mcp__task__GetIssue", AsyncMock(),
                timeout=5.0, max_retries=3,
            )

        assert result == "finally"
        assert call_count == 3


# ---------------------------------------------------------------------------
# Constants Tests
# ---------------------------------------------------------------------------

class TestTimeoutConstants:
    """Verify timeout configuration constants have expected values."""

    def test_mcp_timeout_seconds(self) -> None:
        """Default MCP timeout is 30 seconds."""
        assert MCP_TIMEOUT_SECONDS == 30.0

    def test_max_retries(self) -> None:
        """Default max retries is 3."""
        assert MAX_RETRIES == 3

    def test_initial_backoff(self) -> None:
        """Initial backoff is 1 second."""
        assert INITIAL_BACKOFF_SECONDS == 1.0

    def test_max_backoff(self) -> None:
        """Maximum backoff is 30 seconds."""
        assert MAX_BACKOFF_SECONDS == 30.0

    def test_backoff_multiplier(self) -> None:
        """Backoff multiplier is 2x."""
        assert BACKOFF_MULTIPLIER == 2.0

    def test_rate_limit_initial_backoff(self) -> None:
        """Rate limit initial backoff is 5 seconds."""
        assert RATE_LIMIT_INITIAL_BACKOFF_SECONDS == 5.0
