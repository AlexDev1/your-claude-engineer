"""
Graceful Degradation Matrix
============================

Provides async wrappers and decorators that handle various failure scenarios:
- MCP timeout: 3 retries with exponential backoff, degrade to skip notifications
- Playwright crash: catch errors, return fallback message instead of blocking
- Git errors: stash changes, retry, return context on persistent failure
- Rate limits: exponential backoff (30s -> 60s -> 120s), clear error on exhaust

ENG-68: Graceful Degradation Matrix

Three APIs are available:

1. Method-based::

       recovery = GracefulDegradation()
       result = await recovery.with_mcp_retry(func, *args)

2. Standalone decorator-based::

       @handle_mcp_timeout
       async def call_mcp_tool(...): ...

3. Unified instance-based decorator and context manager::

       recovery = GracefulDegradation()

       @recovery.handle(FailureType.MCP_TIMEOUT)
       async def call_mcp_tool(...): ...

       async with recovery.protected(FailureType.PLAYWRIGHT_CRASH):
           await take_screenshot()

APIs 1 and 2 return ``DegradedResult`` and ``RecoveryResult`` respectively.
API 3 returns ``RecoveryResult`` (decorator) or yields inside the context manager,
storing the outcome in ``RecoveryResult`` accessible via the context variable.
"""

import asyncio
import functools
import logging
import subprocess
from contextlib import asynccontextmanager
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Any, AsyncIterator, Callable, Coroutine, Final, ParamSpec, TypeVar

logger = logging.getLogger("recovery")

T = TypeVar("T")
P = ParamSpec("P")

# ---------------------------------------------------------------------------
# Retry configuration constants
# ---------------------------------------------------------------------------
MCP_MAX_RETRIES: Final[int] = 3
MCP_BASE_DELAY_SECONDS: Final[float] = 2.0

PLAYWRIGHT_MAX_RETRIES: Final[int] = 1

GIT_MAX_RETRIES: Final[int] = 2

RATE_LIMIT_BACKOFF_SECONDS: Final[list[float]] = [30.0, 60.0, 120.0]
RATE_LIMIT_MAX_RETRIES: Final[int] = len(RATE_LIMIT_BACKOFF_SECONDS)

# HTTP status code for rate limiting
HTTP_429_TOO_MANY_REQUESTS: Final[int] = 429

# Default generic retry settings
DEFAULT_MAX_RETRIES: Final[int] = 3
DEFAULT_BASE_DELAY_SECONDS: Final[float] = 1.0


# ---------------------------------------------------------------------------
# Failure type enum (ENG-68)
# ---------------------------------------------------------------------------

class FailureType(Enum):
    """Categories of failures for the unified handle/protected API.

    Each value maps to a specific recovery strategy:
    - MCP_TIMEOUT: 3 retries with 2s exponential backoff, then skip notifications
    - PLAYWRIGHT_CRASH: No retry, return fallback immediately
    - GIT_ERROR: Stash changes, retry once
    - RATE_LIMIT: Exponential backoff at 30s, 60s, 120s
    """

    MCP_TIMEOUT = "mcp_timeout"
    PLAYWRIGHT_CRASH = "playwright_crash"
    GIT_ERROR = "git_error"
    RATE_LIMIT = "rate_limit"


# ---------------------------------------------------------------------------
# Result dataclasses
# ---------------------------------------------------------------------------

@dataclass
class RecoveryResult:
    """Result from a decorator-wrapped recovery call.

    Attributes:
        success: Whether the operation completed successfully
        fallback_used: True if a fallback/degraded path was taken
        error_message: Human-readable error description, empty on success
        retry_count: Number of retry attempts made (0 means first attempt succeeded)
    """

    success: bool
    fallback_used: bool = False
    error_message: str = ""
    retry_count: int = 0


@dataclass
class DegradedResult:
    """Result returned when a service degrades gracefully (method API).

    Attributes:
        success: Whether the operation completed (possibly in degraded mode)
        value: Return value from the wrapped function, or None on degradation
        degraded: True if the result is from a fallback path
        message: Human-readable description of what happened
    """

    success: bool
    value: Any = None
    degraded: bool = False
    message: str = ""


@dataclass
class RetryStats:
    """Statistics collected during retry attempts.

    Attributes:
        attempts: Number of attempts made (including the initial call)
        total_delay_seconds: Cumulative backoff time spent waiting
        errors: List of error messages from each failed attempt
    """

    attempts: int = 0
    total_delay_seconds: float = 0.0
    errors: list[str] = field(default_factory=list)


# ---------------------------------------------------------------------------
# Helper predicates
# ---------------------------------------------------------------------------

def _is_rate_limit_error(error: Exception) -> bool:
    """Check whether an exception represents a rate limit response.

    Detects HTTP 429 status codes and common rate-limit error message patterns.

    Args:
        error: The exception to inspect

    Returns:
        True if the error looks like a rate limit, False otherwise
    """
    error_str = str(error).lower()
    if "429" in error_str:
        return True
    if "rate limit" in error_str or "rate_limit" in error_str:
        return True
    if "too many requests" in error_str:
        return True

    # Check for httpx Response attribute (status_code)
    status_code = getattr(error, "status_code", None)
    if status_code == HTTP_429_TOO_MANY_REQUESTS:
        return True

    # Check for wrapped response objects
    response = getattr(error, "response", None)
    if response is not None:
        resp_status = getattr(response, "status_code", None)
        if resp_status == HTTP_429_TOO_MANY_REQUESTS:
            return True

    return False


def _degradation_message_for(failure_type: FailureType, error_detail: str) -> str:
    """Build a human-readable degradation message for a failure type.

    Args:
        failure_type: The category of failure
        error_detail: Detailed error string (typically "ExcType: message")

    Returns:
        Descriptive message suitable for logging or issue comments
    """
    prefix_map: dict[FailureType, str] = {
        FailureType.MCP_TIMEOUT: "MCP call failed, skipping notifications",
        FailureType.PLAYWRIGHT_CRASH: "Screenshot unavailable due to browser error",
        FailureType.GIT_ERROR: "Git operation failed",
        FailureType.RATE_LIMIT: "Rate limit exceeded",
    }
    prefix = prefix_map.get(failure_type, f"Operation failed ({failure_type.value})")
    return f"{prefix}: {error_detail}"


def _is_git_merge_conflict(stderr: str) -> bool:
    """Check if git stderr output indicates a merge conflict.

    Args:
        stderr: Standard error output from a git command

    Returns:
        True if the output contains merge conflict indicators
    """
    conflict_markers = [
        "merge conflict",
        "conflict",
        "unmerged",
        "both modified",
        "both added",
    ]
    lower_stderr = stderr.lower()
    return any(marker in lower_stderr for marker in conflict_markers)


# ---------------------------------------------------------------------------
# Decorator API (ENG-68)
# ---------------------------------------------------------------------------

def retry_with_backoff(
    max_retries: int = DEFAULT_MAX_RETRIES,
    base_delay: float = DEFAULT_BASE_DELAY_SECONDS,
    backoff_factor: float = 2.0,
) -> Callable[
    [Callable[P, Coroutine[Any, Any, T]]],
    Callable[P, Coroutine[Any, Any, RecoveryResult]],
]:
    """Generic retry decorator with exponential backoff.

    Wraps an async function so that transient failures are retried up to
    ``max_retries`` times with exponential backoff (delay * backoff_factor
    after each failure). Returns a ``RecoveryResult`` instead of raising.

    Args:
        max_retries: Maximum number of attempts (including the first call)
        base_delay: Initial delay in seconds before the first retry
        backoff_factor: Multiplier applied to the delay after each retry

    Returns:
        Decorator that transforms an async function into one returning
        ``RecoveryResult``

    Example::

        @retry_with_backoff(max_retries=3, base_delay=1.0)
        async def fetch_data():
            ...
    """

    def decorator(
        func: Callable[P, Coroutine[Any, Any, T]],
    ) -> Callable[P, Coroutine[Any, Any, RecoveryResult]]:
        @functools.wraps(func)
        async def wrapper(*args: P.args, **kwargs: P.kwargs) -> RecoveryResult:
            last_error = ""
            for attempt in range(1, max_retries + 1):
                try:
                    await func(*args, **kwargs)
                    return RecoveryResult(
                        success=True,
                        retry_count=attempt - 1,
                    )
                except Exception as exc:
                    last_error = f"{type(exc).__name__}: {exc}"
                    logger.info(
                        "retry_with_backoff attempt %d/%d failed: %s",
                        attempt, max_retries, last_error,
                    )
                    if attempt < max_retries:
                        delay = base_delay * (backoff_factor ** (attempt - 1))
                        await asyncio.sleep(delay)

            logger.warning(
                "retry_with_backoff exhausted after %d attempts: %s",
                max_retries, last_error,
            )
            return RecoveryResult(
                success=False,
                fallback_used=False,
                error_message=last_error,
                retry_count=max_retries,
            )

        return wrapper

    return decorator


def handle_mcp_timeout(
    func: Callable[P, Coroutine[Any, Any, T]],
) -> Callable[P, Coroutine[Any, Any, RecoveryResult]]:
    """Decorator for MCP calls with timeout retry logic.

    Retries up to ``MCP_MAX_RETRIES`` times with exponential backoff
    (2s, 4s, 8s). On final failure the decorated function returns a
    ``RecoveryResult`` with ``fallback_used=True`` and a message indicating
    notifications were skipped -- the caller should continue without MCP.

    Args:
        func: Async function making an MCP call

    Returns:
        Wrapped async function returning ``RecoveryResult``
    """

    @functools.wraps(func)
    async def wrapper(*args: P.args, **kwargs: P.kwargs) -> RecoveryResult:
        last_error = ""
        for attempt in range(1, MCP_MAX_RETRIES + 1):
            try:
                await func(*args, **kwargs)
                return RecoveryResult(
                    success=True,
                    retry_count=attempt - 1,
                )
            except Exception as exc:
                last_error = f"{type(exc).__name__}: {exc}"
                logger.warning(
                    "MCP timeout handler attempt %d/%d: %s",
                    attempt, MCP_MAX_RETRIES, last_error,
                )
                if attempt < MCP_MAX_RETRIES:
                    delay = MCP_BASE_DELAY_SECONDS * (2 ** (attempt - 1))
                    logger.info("Retrying MCP call in %.1fs...", delay)
                    await asyncio.sleep(delay)

        logger.warning(
            "MCP call failed after %d attempts. Skipping notifications.",
            MCP_MAX_RETRIES,
        )
        return RecoveryResult(
            success=False,
            fallback_used=True,
            error_message=(
                f"MCP call failed after {MCP_MAX_RETRIES} retries, "
                f"skipping notifications. Last error: {last_error}"
            ),
            retry_count=MCP_MAX_RETRIES,
        )

    return wrapper


def handle_playwright_error(
    func: Callable[P, Coroutine[Any, Any, T]],
) -> Callable[P, Coroutine[Any, Any, RecoveryResult]]:
    """Decorator for Playwright/browser operations with graceful fallback.

    Catches any exception from the wrapped function and returns a degraded
    ``RecoveryResult`` instead of raising. The caller should skip the
    screenshot requirement and add a comment to the task instead.

    No retries are performed -- browser crashes are unlikely to resolve
    immediately.

    Args:
        func: Async function performing a Playwright/browser operation

    Returns:
        Wrapped async function returning ``RecoveryResult``
    """

    @functools.wraps(func)
    async def wrapper(*args: P.args, **kwargs: P.kwargs) -> RecoveryResult:
        try:
            await func(*args, **kwargs)
            return RecoveryResult(success=True, retry_count=0)
        except Exception as exc:
            error_name = type(exc).__name__
            msg = f"Screenshot unavailable due to browser error: {error_name}: {exc}"
            logger.warning("Playwright error handler: %s", msg)
            return RecoveryResult(
                success=False,
                fallback_used=True,
                error_message=msg,
                retry_count=0,
            )

    return wrapper


def handle_git_error(
    func: Callable[P, Coroutine[Any, Any, T]],
) -> Callable[P, Coroutine[Any, Any, RecoveryResult]]:
    """Decorator for git operations with stash/retry recovery.

    On failure, attempts ``git stash`` in the current working directory
    and retries once. If the retry also fails, returns an error
    ``RecoveryResult`` with diagnostic context.

    Args:
        func: Async function performing a git operation

    Returns:
        Wrapped async function returning ``RecoveryResult``
    """

    @functools.wraps(func)
    async def wrapper(*args: P.args, **kwargs: P.kwargs) -> RecoveryResult:
        last_error = ""
        for attempt in range(1, GIT_MAX_RETRIES + 1):
            try:
                await func(*args, **kwargs)
                return RecoveryResult(
                    success=True,
                    retry_count=attempt - 1,
                )
            except Exception as exc:
                last_error = f"{type(exc).__name__}: {exc}"
                logger.warning(
                    "Git error handler attempt %d/%d: %s",
                    attempt, GIT_MAX_RETRIES, last_error,
                )
                if attempt < GIT_MAX_RETRIES:
                    # Try git stash in cwd
                    stash_ok = _try_git_stash_cwd()
                    if stash_ok:
                        logger.info("Stashed changes, retrying git operation...")
                    else:
                        logger.warning("Git stash failed; retrying without stash")

        return RecoveryResult(
            success=False,
            fallback_used=False,
            error_message=(
                f"Git operation failed after {GIT_MAX_RETRIES} attempts. "
                f"Last error: {last_error}"
            ),
            retry_count=GIT_MAX_RETRIES,
        )

    return wrapper


def handle_rate_limit(
    func: Callable[P, Coroutine[Any, Any, T]],
) -> Callable[P, Coroutine[Any, Any, RecoveryResult]]:
    """Decorator for API calls with rate-limit-aware exponential backoff.

    Detects rate limit errors (HTTP 429, "rate limit" in message) and
    applies escalating backoff: 30s, 60s, 120s. Non-rate-limit errors
    are returned immediately as failed ``RecoveryResult``.

    Args:
        func: Async function making an API call

    Returns:
        Wrapped async function returning ``RecoveryResult``
    """

    @functools.wraps(func)
    async def wrapper(*args: P.args, **kwargs: P.kwargs) -> RecoveryResult:
        last_error = ""
        for attempt in range(1, RATE_LIMIT_MAX_RETRIES + 1):
            try:
                await func(*args, **kwargs)
                return RecoveryResult(
                    success=True,
                    retry_count=attempt - 1,
                )
            except Exception as exc:
                if not _is_rate_limit_error(exc):
                    return RecoveryResult(
                        success=False,
                        fallback_used=False,
                        error_message=f"Non-rate-limit error: {type(exc).__name__}: {exc}",
                        retry_count=attempt - 1,
                    )

                last_error = f"{type(exc).__name__}: {exc}"
                delay_index = min(attempt - 1, len(RATE_LIMIT_BACKOFF_SECONDS) - 1)
                delay = RATE_LIMIT_BACKOFF_SECONDS[delay_index]

                logger.warning(
                    "Rate limit hit (attempt %d/%d). Backing off %.0fs...",
                    attempt, RATE_LIMIT_MAX_RETRIES, delay,
                )

                if attempt < RATE_LIMIT_MAX_RETRIES:
                    await asyncio.sleep(delay)

        return RecoveryResult(
            success=False,
            fallback_used=False,
            error_message=(
                f"Rate limit exceeded after {RATE_LIMIT_MAX_RETRIES} retries. "
                f"Last error: {last_error}"
            ),
            retry_count=RATE_LIMIT_MAX_RETRIES,
        )

    return wrapper


# ---------------------------------------------------------------------------
# Standalone git helper for decorator API
# ---------------------------------------------------------------------------

def _try_git_stash_cwd() -> bool:
    """Attempt to stash uncommitted changes in the current working directory.

    Returns:
        True if stash succeeded, False otherwise
    """
    try:
        result = subprocess.run(
            ["git", "stash", "push", "-m", "auto-stash from recovery"],
            capture_output=True,
            text=True,
            timeout=30,
        )
        if result.returncode == 0:
            logger.info("Git stash succeeded (cwd)")
            return True
        logger.warning("Git stash returned non-zero: %s", result.stderr.strip())
        return False
    except (subprocess.SubprocessError, FileNotFoundError) as exc:
        logger.warning("Git stash failed: %s", exc)
        return False


# ---------------------------------------------------------------------------
# Class-based method API (original)
# ---------------------------------------------------------------------------

class GracefulDegradation:
    """Handles graceful degradation for various failure scenarios.

    Wraps async callables with retry logic, backoff, and fallback strategies
    tailored to each failure category (MCP, Playwright, Git, rate limits).

    Args:
        project_dir: Working directory for git operations. When None,
                     git recovery will use the current working directory.
    """

    def __init__(self, project_dir: Path | None = None) -> None:
        self.project_dir = project_dir or Path.cwd()

    # --- Unified decorator / context manager API (ENG-68) ---

    def handle(
        self,
        failure_type: FailureType,
    ) -> Callable[
        [Callable[P, Coroutine[Any, Any, T]]],
        Callable[P, Coroutine[Any, Any, RecoveryResult]],
    ]:
        """Return a decorator that wraps an async function with recovery logic.

        The specific retry/backoff strategy is selected by ``failure_type``.

        Args:
            failure_type: The category of failure to guard against

        Returns:
            Decorator that transforms an async function into one returning
            ``RecoveryResult``

        Example::

            recovery = GracefulDegradation()

            @recovery.handle(FailureType.MCP_TIMEOUT)
            async def call_mcp_tool():
                ...
        """
        strategy_map: dict[
            FailureType,
            Callable[
                [Callable[P, Coroutine[Any, Any, T]]],
                Callable[P, Coroutine[Any, Any, RecoveryResult]],
            ],
        ] = {
            FailureType.MCP_TIMEOUT: handle_mcp_timeout,
            FailureType.PLAYWRIGHT_CRASH: handle_playwright_error,
            FailureType.GIT_ERROR: handle_git_error,
            FailureType.RATE_LIMIT: handle_rate_limit,
        }

        decorator = strategy_map.get(failure_type)
        if decorator is None:
            raise ValueError(f"Unsupported failure type: {failure_type}")

        return decorator

    @asynccontextmanager
    async def protected(
        self,
        failure_type: FailureType,
    ) -> AsyncIterator[RecoveryResult]:
        """Async context manager that catches failures and applies recovery.

        The yielded ``RecoveryResult`` is updated in-place after the body
        executes: on success its ``success`` field is True, on failure it
        reflects the degradation outcome. The caller can inspect the result
        after the ``async with`` block to decide next steps.

        No retries are performed inside the context manager -- this API is
        best for one-shot operations where you want to catch and degrade
        gracefully. For retry logic, use the ``handle()`` decorator instead.

        Args:
            failure_type: The category of failure to guard against

        Yields:
            A mutable ``RecoveryResult`` that is populated after the body runs

        Example::

            recovery = GracefulDegradation()

            async with recovery.protected(FailureType.PLAYWRIGHT_CRASH) as result:
                await take_screenshot()

            if result.fallback_used:
                logger.info("Screenshot skipped: %s", result.error_message)
        """
        result = RecoveryResult(success=False)

        try:
            yield result
            # Body completed without exception
            result.success = True
        except Exception as exc:
            error_msg = f"{type(exc).__name__}: {exc}"
            logger.warning(
                "Protected block caught %s error: %s",
                failure_type.value, error_msg,
            )
            result.success = False
            result.error_message = _degradation_message_for(failure_type, error_msg)
            result.fallback_used = True
            result.retry_count = 0

    async def with_mcp_retry(
        self,
        func: Callable[..., Coroutine[Any, Any, T]],
        *args: Any,
        **kwargs: Any,
    ) -> DegradedResult:
        """Execute an MCP call with retry logic.

        Retries up to MCP_MAX_RETRIES times with exponential backoff
        (2s, 4s, 8s). On final failure, returns a degraded result so
        the caller can continue without the MCP service.

        Args:
            func: Async callable to execute
            *args: Positional arguments forwarded to func
            **kwargs: Keyword arguments forwarded to func

        Returns:
            DegradedResult with the function's return value on success,
            or a degraded result with diagnostic message on exhaustion
        """
        stats = RetryStats()

        for attempt in range(1, MCP_MAX_RETRIES + 1):
            stats.attempts = attempt
            try:
                result = await func(*args, **kwargs)
                return DegradedResult(success=True, value=result)
            except Exception as exc:
                error_msg = f"Attempt {attempt}/{MCP_MAX_RETRIES}: {type(exc).__name__}: {exc}"
                stats.errors.append(error_msg)
                logger.warning("MCP retry %d/%d failed: %s", attempt, MCP_MAX_RETRIES, exc)

                if attempt < MCP_MAX_RETRIES:
                    delay = MCP_BASE_DELAY_SECONDS * (2 ** (attempt - 1))
                    stats.total_delay_seconds += delay
                    logger.info("Retrying MCP call in %.1fs...", delay)
                    await asyncio.sleep(delay)

        # All retries exhausted -- degrade gracefully
        logger.warning(
            "MCP call failed after %d attempts. Continuing in degraded mode.",
            MCP_MAX_RETRIES,
        )
        return DegradedResult(
            success=False,
            degraded=True,
            message=(
                f"MCP call failed after {MCP_MAX_RETRIES} retries. "
                f"Skipping notifications. Errors: {'; '.join(stats.errors)}"
            ),
        )

    async def with_playwright_fallback(
        self,
        func: Callable[..., Coroutine[Any, Any, T]],
        *args: Any,
        **kwargs: Any,
    ) -> DegradedResult:
        """Execute a Playwright action with fallback on failure.

        Catches Playwright exceptions and returns a degraded result with
        the message "Screenshot unavailable due to browser error" so the
        workflow can continue without blocking.

        Args:
            func: Async callable (typically a Playwright operation)
            *args: Positional arguments forwarded to func
            **kwargs: Keyword arguments forwarded to func

        Returns:
            DegradedResult with the value on success, or a degraded
            result noting the screenshot is unavailable
        """
        try:
            result = await func(*args, **kwargs)
            return DegradedResult(success=True, value=result)
        except Exception as exc:
            error_name = type(exc).__name__
            logger.warning("Playwright action failed (%s): %s", error_name, exc)
            return DegradedResult(
                success=False,
                degraded=True,
                message=f"Screenshot unavailable due to browser error: {error_name}: {exc}",
            )

    async def with_git_recovery(
        self,
        func: Callable[..., Coroutine[Any, Any, T]],
        *args: Any,
        **kwargs: Any,
    ) -> DegradedResult:
        """Execute a git command with stash/recovery.

        On failure, attempts to stash uncommitted changes and retry the
        operation. Handles common scenarios like uncommitted changes and
        merge conflicts.

        Args:
            func: Async callable performing a git operation
            *args: Positional arguments forwarded to func
            **kwargs: Keyword arguments forwarded to func

        Returns:
            DegradedResult with the value on success, or an error result
            with diagnostic context on persistent failure
        """
        stats = RetryStats()

        for attempt in range(1, GIT_MAX_RETRIES + 1):
            stats.attempts = attempt
            try:
                result = await func(*args, **kwargs)
                return DegradedResult(success=True, value=result)
            except Exception as exc:
                error_msg = f"Attempt {attempt}/{GIT_MAX_RETRIES}: {type(exc).__name__}: {exc}"
                stats.errors.append(error_msg)
                logger.warning("Git operation failed (attempt %d/%d): %s", attempt, GIT_MAX_RETRIES, exc)

                if attempt < GIT_MAX_RETRIES:
                    # Try to recover by stashing uncommitted changes
                    stash_ok = self._try_git_stash()
                    if stash_ok:
                        logger.info("Stashed uncommitted changes, retrying git operation...")
                    else:
                        logger.warning("Git stash failed; retrying without stash")

        # All retries exhausted
        context = self._collect_git_context()
        return DegradedResult(
            success=False,
            degraded=False,
            message=(
                f"Git operation failed after {GIT_MAX_RETRIES} attempts. "
                f"Context: {context}. Errors: {'; '.join(stats.errors)}"
            ),
        )

    async def with_rate_limit_backoff(
        self,
        func: Callable[..., Coroutine[Any, Any, T]],
        *args: Any,
        **kwargs: Any,
    ) -> DegradedResult:
        """Execute with rate-limit-aware backoff.

        Uses escalating delays of 30s, 60s, 120s when rate limit errors
        are detected (HTTP 429 or rate-limit keywords in the error message).
        Non-rate-limit errors are raised immediately.

        Args:
            func: Async callable to execute
            *args: Positional arguments forwarded to func
            **kwargs: Keyword arguments forwarded to func

        Returns:
            DegradedResult with the value on success

        Raises:
            RuntimeError: After all retries are exhausted with a descriptive message
            Exception: Re-raised immediately if the error is not a rate limit
        """
        stats = RetryStats()

        for attempt in range(1, RATE_LIMIT_MAX_RETRIES + 1):
            stats.attempts = attempt
            try:
                result = await func(*args, **kwargs)
                return DegradedResult(success=True, value=result)
            except Exception as exc:
                if not _is_rate_limit_error(exc):
                    raise

                error_msg = f"Attempt {attempt}/{RATE_LIMIT_MAX_RETRIES}: {type(exc).__name__}: {exc}"
                stats.errors.append(error_msg)

                delay_index = min(attempt - 1, len(RATE_LIMIT_BACKOFF_SECONDS) - 1)
                delay = RATE_LIMIT_BACKOFF_SECONDS[delay_index]
                stats.total_delay_seconds += delay

                logger.warning(
                    "Rate limit hit (attempt %d/%d). Backing off %.0fs...",
                    attempt,
                    RATE_LIMIT_MAX_RETRIES,
                    delay,
                )

                if attempt < RATE_LIMIT_MAX_RETRIES:
                    await asyncio.sleep(delay)

        raise RuntimeError(
            f"Rate limit exceeded after {RATE_LIMIT_MAX_RETRIES} retries "
            f"(total backoff: {stats.total_delay_seconds:.0f}s). "
            f"Errors: {'; '.join(stats.errors)}"
        )

    # --- Git helper methods ---

    def _try_git_stash(self) -> bool:
        """Attempt to stash uncommitted changes.

        Returns:
            True if stash succeeded, False otherwise
        """
        try:
            result = subprocess.run(
                ["git", "stash", "push", "-m", "auto-stash from recovery"],
                cwd=str(self.project_dir),
                capture_output=True,
                text=True,
                timeout=30,
            )
            if result.returncode == 0:
                logger.info("Git stash succeeded")
                return True
            logger.warning("Git stash returned non-zero: %s", result.stderr.strip())
            return False
        except (subprocess.SubprocessError, FileNotFoundError) as exc:
            logger.warning("Git stash failed: %s", exc)
            return False

    def _collect_git_context(self) -> str:
        """Collect current git status for error reporting.

        Returns:
            String summary of git status, or a fallback message on failure
        """
        try:
            status_result = subprocess.run(
                ["git", "status", "--porcelain"],
                cwd=str(self.project_dir),
                capture_output=True,
                text=True,
                timeout=10,
            )
            status_lines = status_result.stdout.strip().split("\n") if status_result.stdout.strip() else []
            file_count = len(status_lines)

            if file_count == 0:
                return "clean working tree"

            return f"{file_count} modified/untracked file(s)"
        except (subprocess.SubprocessError, FileNotFoundError) as exc:
            return f"unable to read git status: {exc}"
