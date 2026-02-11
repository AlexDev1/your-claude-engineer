"""
Конфигурация Claude SDK клиента
================================

Функции для создания и настройки клиента Claude Agent SDK.
Использует self-hosted Task MCP и Telegram MCP серверы для интеграции.
Реализует middleware обрезки вывода инструментов (ENG-29).
Реализует обработку таймаутов MCP с экспоненциальной задержкой (ENG-70).
"""

import asyncio
import importlib.resources
import json
import logging
import os
import random
from pathlib import Path
from typing import Any, Callable, Coroutine, Final, Literal, TypedDict, TypeVar, cast

from dotenv import load_dotenv

load_dotenv()

from claude_agent_sdk import ClaudeAgentOptions, ClaudeSDKClient, McpServerConfig
from claude_agent_sdk.types import HookCallback, HookMatcher

from axon_agent.core.context import (
    get_context_manager,
    truncate_tool_output,
    truncate_git_diff,
    TOOL_OUTPUT_MAX_CHARS,
)
from axon_agent.mcp.config import (
    ALL_MCP_TOOLS,
    TASK_TOOLS_PERMISSION,
    TELEGRAM_TOOLS_PERMISSION,
    PLAYWRIGHT_TOOLS_PERMISSION,
    get_task_mcp_config,
    get_telegram_mcp_config,
    validate_mcp_config,
)
from axon_agent.agents.definitions import AGENT_DEFINITIONS
from axon_agent.core.recovery import FailureType, GracefulDegradation, _is_rate_limit_error
from axon_agent.security.hooks import bash_security_hook

logger = logging.getLogger("client")

T = TypeVar("T")

# ---------------------------------------------------------------------------
# Конфигурация таймаутов и задержек (ENG-70)
# ---------------------------------------------------------------------------
MCP_TIMEOUT_SECONDS: Final[float] = 30.0
MAX_RETRIES: Final[int] = 3
INITIAL_BACKOFF_SECONDS: Final[float] = 1.0
MAX_BACKOFF_SECONDS: Final[float] = 30.0
BACKOFF_MULTIPLIER: Final[float] = 2.0
RATE_LIMIT_INITIAL_BACKOFF_SECONDS: Final[float] = 5.0


class MCPTimeoutError(Exception):
    """Возникает, когда вызов MCP инструмента превышает таймаут после всех повторов.

    Attributes:
        tool_name: Имя MCP инструмента, у которого произошёл таймаут
        timeout: Длительность таймаута в секундах, которая была превышена
    """

    def __init__(self, tool_name: str, timeout: float) -> None:
        self.tool_name = tool_name
        self.timeout = timeout
        super().__init__(f"MCP tool '{tool_name}' timed out after {timeout}s")


def calculate_backoff(
    attempt: int,
    initial: float = INITIAL_BACKOFF_SECONDS,
    max_backoff: float = MAX_BACKOFF_SECONDS,
    multiplier: float = BACKOFF_MULTIPLIER,
) -> float:
    """Вычисляет длительность экспоненциальной задержки с jitter.

    Использует стратегию "full jitter": базовая задержка удваивается с каждой попыткой
    (ограничена ``max_backoff``), затем применяется случайный jitter +/-20% для
    предотвращения эффекта "thundering-herd".

    Args:
        attempt: Индекс попытки с нуля (0 = первый повтор)
        initial: Базовая задержка в секундах для первого повтора
        max_backoff: Максимальный предел задержки в секундах
        multiplier: Множитель, применяемый к каждой попытке (экспоненциальная база)

    Returns:
        Длительность задержки в секундах, всегда >= 0
    """
    backoff = min(initial * (multiplier ** attempt), max_backoff)
    jitter = backoff * 0.2 * (random.random() * 2 - 1)
    return max(0.0, backoff + jitter)


async def subagent_start_hook(input: dict[str, Any], tool_use_id: str | None, context: dict[str, Any]) -> dict[str, Any]:
    """
    Логирует запуск субагента для аудита.

    Args:
        input: Данные хука (ожидает SubagentStartHookInput)
        tool_use_id: Не используется для этого события
        context: Контекст хука (резерв)
    """
    agent_id = input.get("agent_id", "unknown")
    agent_type = input.get("agent_type", "unknown")
    logger.info("Subagent started: id=%s type=%s", agent_id, agent_type)
    return {}  # Продолжить выполнение без изменений


async def subagent_stop_hook(input: dict[str, Any], tool_use_id: str | None, context: dict[str, Any]) -> dict[str, Any]:
    """
    Логирует завершение субагента и путь к транскрипту.

    Args:
        input: Данные хука (ожидает SubagentStopHookInput)
        tool_use_id: Не используется для этого события
        context: Контекст хука (резерв)
    """
    agent_id = input.get("agent_id", "unknown")
    agent_type = input.get("agent_type", "unknown")
    transcript = input.get("agent_transcript_path", "n/a")
    logger.info("Subagent stopped: id=%s type=%s transcript=%s", agent_id, agent_type, transcript)
    return {}  # Продолжить выполнение без изменений


async def call_mcp_tool_with_retry(
    tool_name: str,
    call_fn: Callable[..., Coroutine[Any, Any, T]],
    *args: Any,
    timeout: float = MCP_TIMEOUT_SECONDS,
    max_retries: int = MAX_RETRIES,
    **kwargs: Any,
) -> T:
    """Вызывает MCP инструмент с таймаутом и повторами с экспоненциальной задержкой.

    Оборачивает ``call_fn`` в ``asyncio.wait_for`` для применения таймаута на каждый вызов.
    При ``asyncio.TimeoutError`` повторяет с экспоненциальной задержкой. При ошибках
    rate limit (HTTP 429 / "rate limit" в сообщении) использует большую начальную задержку.

    Когда все повторы исчерпаны, запускает плавную деградацию, помечая MCP сервис
    как деградированный через ``GracefulDegradation.protected()``.

    Args:
        tool_name: Идентификатор MCP инструмента (для сообщений об ошибках и отслеживания деградации)
        call_fn: Асинхронная функция, выполняющая фактический вызов MCP инструмента
        *args: Позиционные аргументы, переданные в ``call_fn``
        timeout: Таймаут на один вызов в секундах
        max_retries: Максимальное количество попыток (включая первый вызов)
        **kwargs: Ключевые аргументы, переданные в ``call_fn``

    Returns:
        Результат от ``call_fn`` при успехе

    Raises:
        MCPTimeoutError: Если все повторы исчерпаны из-за таймаутов
        Exception: Повторно вызывается rate-limit или другие ошибки после исчерпания повторов
    """
    last_exception: Exception | None = None

    for attempt in range(max_retries):
        try:
            result = await asyncio.wait_for(
                call_fn(*args, **kwargs),
                timeout=timeout,
            )
            if attempt > 0:
                logger.info(
                    "MCP tool '%s' succeeded on attempt %d/%d",
                    tool_name, attempt + 1, max_retries,
                )
            return result

        except asyncio.TimeoutError:
            last_exception = asyncio.TimeoutError(
                f"MCP tool '{tool_name}' timed out after {timeout}s"
            )
            logger.warning(
                "MCP tool '%s' timed out (attempt %d/%d)",
                tool_name, attempt + 1, max_retries,
            )
            if attempt < max_retries - 1:
                backoff = calculate_backoff(attempt)
                logger.info("Retrying '%s' in %.2fs...", tool_name, backoff)
                await asyncio.sleep(backoff)

        except Exception as exc:
            last_exception = exc
            if _is_rate_limit_error(exc):
                logger.warning(
                    "MCP tool '%s' rate limited (attempt %d/%d): %s",
                    tool_name, attempt + 1, max_retries, exc,
                )
                if attempt < max_retries - 1:
                    backoff = calculate_backoff(
                        attempt, initial=RATE_LIMIT_INITIAL_BACKOFF_SECONDS,
                    )
                    logger.info(
                        "Rate limit backoff for '%s': %.2fs", tool_name, backoff,
                    )
                    await asyncio.sleep(backoff)
            else:
                # Non-retryable error -- propagate immediately
                raise

    # All retries exhausted -- trigger graceful degradation
    recovery = GracefulDegradation()
    async with recovery.protected(FailureType.MCP_TIMEOUT):
        if isinstance(last_exception, asyncio.TimeoutError):
            raise MCPTimeoutError(tool_name, timeout)
        if last_exception is not None:
            raise last_exception

    # If we reach here, the protected block caught the exception.
    # Re-raise MCPTimeoutError so callers can handle it explicitly.
    raise MCPTimeoutError(tool_name, timeout)


# Допустимые режимы разрешений для Claude SDK
PermissionMode = Literal["acceptEdits", "acceptAll", "reject", "ask"]


class SandboxConfig(TypedDict):
    """Конфигурация sandbox для изоляции bash команд."""

    enabled: bool
    autoAllowBashIfSandboxed: bool


class PermissionsConfig(TypedDict):
    """Конфигурация разрешений для файловых операций и инструментов."""

    defaultMode: PermissionMode
    allow: list[str]


class SecuritySettings(TypedDict):
    """Полная структура настроек безопасности."""

    sandbox: SandboxConfig
    permissions: PermissionsConfig


# Playwright MCP инструменты для автоматизации браузера
PLAYWRIGHT_TOOLS: list[str] = [
    "mcp__playwright__browser_navigate",
    # browser_take_screenshot УДАЛЁН — превышает буфер SDK 1MB (base64 в ответе)
    "mcp__playwright__browser_click",
    "mcp__playwright__browser_type",
    "mcp__playwright__browser_select_option",
    "mcp__playwright__browser_hover",
    "mcp__playwright__browser_snapshot",
    "mcp__playwright__browser_wait_for",
]

# Встроенные инструменты
BUILTIN_TOOLS: list[str] = [
    "Read",
    "Write",
    "Edit",
    "Glob",
    "Grep",
    "Bash",
]

# Директория промптов
PROMPTS_DIR = Path(str(importlib.resources.files("axon_agent") / "prompts"))


def load_orchestrator_prompt() -> str:
    """Загружает системный промпт оркестратора."""
    return (PROMPTS_DIR / "orchestrator_prompt.md").read_text()


def tool_output_truncation_hook(tool_name: str, tool_input: dict, tool_output: str) -> str:
    """
    Post-tool хук для обрезки длинных выводов инструментов (ENG-29).

    Этот middleware запускается после каждого выполнения инструмента и обрезает
    выводы, превышающие настроенный лимит, чтобы сохранить контекстный бюджет.

    Args:
        tool_name: Имя выполненного инструмента
        tool_input: Входные параметры, переданные инструменту
        tool_output: Необработанный вывод от инструмента

    Returns:
        Возможно обрезанный вывод инструмента
    """
    if not tool_output or len(tool_output) <= TOOL_OUTPUT_MAX_CHARS:
        return tool_output

    # Special handling for git/bash commands
    if tool_name.lower() == "bash":
        command = tool_input.get("command", "")
        if "diff" in command.lower():
            truncated, _ = truncate_git_diff(tool_output)
            return truncated

    # General truncation
    truncated, was_truncated = truncate_tool_output(tool_output, tool_name)

    if was_truncated:
        # Track in context manager
        ctx_manager = get_context_manager()
        ctx_manager.track_tool_output(tool_name, truncated)

    return truncated


def create_security_settings() -> SecuritySettings:
    """
    Создаёт структуру настроек безопасности.

    Returns:
        SecuritySettings с настроенными sandbox и разрешениями
    """
    return SecuritySettings(
        sandbox=SandboxConfig(enabled=True, autoAllowBashIfSandboxed=True),
        permissions=PermissionsConfig(
            defaultMode="acceptEdits",
            allow=[
                # Allow all file operations within the project directory
                "Read(./**)",
                "Write(./**)",
                "Edit(./**)",
                "Glob(./**)",
                "Grep(./**)",
                # Bash permission granted here, but actual commands are validated
                # by the bash_security_hook (see security.py for allowed commands)
                "Bash(*)",
                # Allow Playwright MCP tools for browser automation
                *PLAYWRIGHT_TOOLS,
                # Allow Task MCP tools (project/issue management)
                TASK_TOOLS_PERMISSION,
                # Allow Telegram MCP tools (notifications)
                TELEGRAM_TOOLS_PERMISSION,
            ],
        ),
    )


def write_security_settings(project_dir: Path, settings: SecuritySettings) -> Path:
    """
    Write security settings to project directory.

    Args:
        project_dir: Directory to write settings to
        settings: Security settings to write

    Returns:
        Path to the settings file

    Raises:
        IOError: If settings file cannot be written
    """
    project_dir.mkdir(parents=True, exist_ok=True)
    settings_file: Path = project_dir / ".claude_settings.json"

    try:
        with open(settings_file, "w") as f:
            json.dump(settings, f, indent=2)
    except IOError as e:
        raise IOError(
            f"Failed to write security settings to {settings_file}: {e}\n"
            f"Check disk space and file permissions.\n"
            f"Agent cannot start without security settings."
        ) from e

    return settings_file


def create_client(project_dir: Path, model: str) -> ClaudeSDKClient:
    """
    Создаёт Claude Agent SDK клиент с многоуровневой безопасностью.

    Args:
        project_dir: Директория проекта
        model: Модель Claude для использования

    Returns:
        Настроенный ClaudeSDKClient

    Raises:
        ValueError: Если не установлены необходимые переменные окружения

    Уровни безопасности (глубокая защита):
    1. Sandbox - изоляция bash команд на уровне ОС предотвращает побег из файловой системы
       (изоляция в стиле bwrap/docker)
    2. Разрешения - файловые операции ограничены только project_dir
       (применяется SDK перед выполнением инструмента)
    3. Security hooks - bash команды проверяются по allowlist
       (выполняется перед запуском через PreToolUse hook, см. security.py для ALLOWED_COMMANDS)

    Порядок выполнения: сначала проверяются разрешения, затем выполняются хуки, наконец sandbox выполняет.
    """
    # Validate MCP configuration
    validate_mcp_config()

    # Get MCP server configurations
    task_config = get_task_mcp_config()
    telegram_config = get_telegram_mcp_config()

    # Create and write security settings
    security_settings: SecuritySettings = create_security_settings()
    settings_file: Path = write_security_settings(project_dir, security_settings)

    # Get context budget info (ENG-29)
    ctx_manager = get_context_manager()
    max_tokens = ctx_manager.budget.max_tokens

    print(f"Created security settings at {settings_file}")
    print("   - Sandbox enabled (OS-level bash isolation)")
    print(f"   - Filesystem restricted to: {project_dir.resolve()}")
    print("   - Bash commands restricted to allowlist (see security.py)")
    print(f"   - Context budget: {max_tokens:,} tokens (MAX_CONTEXT_TOKENS)")
    print(f"   - Compact mode: 70% ({int(max_tokens * 0.7):,} tokens)")
    print(f"   - Graceful shutdown: 85% ({int(max_tokens * 0.85):,} tokens)")
    print(f"   - Tool output limit: {TOOL_OUTPUT_MAX_CHARS:,} chars")
    print(f"   - MCP servers:")
    print(f"       - playwright (browser automation)")
    print(f"       - task ({task_config['url']})")
    print(f"       - telegram ({telegram_config['url']})")
    print()

    # Load orchestrator prompt as system prompt
    orchestrator_prompt = load_orchestrator_prompt()

    return ClaudeSDKClient(
        options=ClaudeAgentOptions(
            model=model,
            system_prompt=orchestrator_prompt,
            allowed_tools=[
                *BUILTIN_TOOLS,
                *ALL_MCP_TOOLS,
            ],
            mcp_servers=cast(
                dict[str, McpServerConfig],
                {
                    "playwright": {"command": "npx", "args": ["-y", "@playwright/mcp@latest"]},
                    "task": task_config,
                    "telegram": telegram_config,
                },
            ),
            hooks={
                "PreToolUse": [
                    HookMatcher(
                        matcher="Bash",
                        hooks=[cast(HookCallback, bash_security_hook)],
                    ),
                ],
                "SubagentStart": [
                    HookMatcher(
                        hooks=[cast(HookCallback, subagent_start_hook)],
                    ),
                ],
                "SubagentStop": [
                    HookMatcher(
                        hooks=[cast(HookCallback, subagent_stop_hook)],
                    ),
                ],
            },
            agents=AGENT_DEFINITIONS,
            max_turns=1000,
            cwd=str(project_dir.resolve()),
            settings=str(settings_file.resolve()),
        )
    )
