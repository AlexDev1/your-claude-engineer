"""
Логика сессии агента
=====================

Основные функции взаимодействия с агентом для запуска автономных сессий разработки.
Интегрируется с context_manager для отслеживания токенового бюджета.
Интегрируется с session_state для детального восстановления после ошибок (ENG-35).
Реализует управление контекстным окном с компактным режимом и плавным завершением (ENG-29).
Реализует отслеживание фаз сессии с сохранением состояния и восстановлением после сбоев (ENG-66).
"""

import asyncio
import traceback
from pathlib import Path
from typing import Literal, NamedTuple

from claude_agent_sdk import (
    AssistantMessage,
    ClaudeSDKClient,
    TextBlock,
    ToolResultBlock,
    ToolUseBlock,
    UserMessage,
)

from client import create_client
from context_manager import (
    ContextManager,
    ContextMode,
    estimate_tokens,
    get_context_manager,
)
from progress import print_session_header
from prompts import (
    ensure_project_map,
    get_continuation_task_with_memory,
    get_execute_task_with_memory,
    get_recovery_context,
)
from session_state import (
    ErrorType,
    GracefulDegradation,
    MAX_PHASE_RETRIES,
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

# Конфигурация проверки паузы (ENG-52)
PAUSE_CHECK_INTERVAL_SECONDS: int = 60


def is_agent_paused(project_dir: Path) -> bool:
    """
    Проверяет, находится ли агент на паузе, проверяя наличие файла .agent/PAUSED (ENG-52).

    Args:
        project_dir: Путь к директории проекта

    Returns:
        True, если файл .agent/PAUSED существует, иначе False
    """
    paused_file = project_dir / ".agent" / "PAUSED"
    return paused_file.exists()


async def wait_while_paused(project_dir: Path) -> bool:
    """
    Ожидает, пока агент на паузе, проверяя каждые PAUSE_CHECK_INTERVAL_SECONDS (ENG-52).

    При возобновлении отправляет уведомление в Telegram, если настроено.

    Args:
        project_dir: Путь к директории проекта

    Returns:
        True, если агент был на паузе и теперь возобновлён, False, если не был на паузе
    """
    if not is_agent_paused(project_dir):
        return False

    print("\n" + "=" * 70)
    print("  AGENT PAUSED")
    print("=" * 70)
    print(f"\nAgent is paused. Checking every {PAUSE_CHECK_INTERVAL_SECONDS}s...")
    print("Use /resume command in Telegram to continue.\n")

    was_paused = True

    while is_agent_paused(project_dir):
        await asyncio.sleep(PAUSE_CHECK_INTERVAL_SECONDS)
        print(f"[{asyncio.get_event_loop().time():.0f}] Still paused, waiting...")

    # Агент возобновлён
    print("\n" + "=" * 70)
    print("  AGENT RESUMED")
    print("=" * 70)
    print("\nAgent has been resumed. Continuing with next task...\n")

    # Попытка отправить Telegram-уведомление
    try:
        import httpx
        import os
        from dotenv import load_dotenv
        load_dotenv(project_dir / ".env")

        telegram_bot_token = os.environ.get("TELEGRAM_BOT_TOKEN", "")
        telegram_chat_id = os.environ.get("TELEGRAM_CHAT_ID", "")

        if telegram_bot_token and telegram_chat_id:
            async with httpx.AsyncClient() as client:
                url = f"https://api.telegram.org/bot{telegram_bot_token}/sendMessage"
                payload = {
                    "chat_id": telegram_chat_id,
                    "text": "Agent resumed.",
                    "parse_mode": "HTML",
                }
                await client.post(url, json=payload, timeout=10.0)
                print("Sent resume notification to Telegram.")
    except Exception as e:
        print(f"Note: Could not send Telegram notification: {e}")

    return was_paused


# Конфигурация
AUTO_CONTINUE_DELAY_SECONDS: int = 3


# Типобезопасное объединение литералов - без накладных расходов во время выполнения
SessionStatus = Literal["continue", "error", "complete", "context_limit"]

# Константы для ясности кода
SESSION_CONTINUE: SessionStatus = "continue"
SESSION_ERROR: SessionStatus = "error"
SESSION_COMPLETE: SessionStatus = "complete"
SESSION_CONTEXT_LIMIT: SessionStatus = "context_limit"

# Сигнал завершения, который оркестратор выводит, когда все задачи выполнены
COMPLETION_SIGNAL = "ALL_TASKS_DONE:"

# Сигнал ограничения контекста, который запускает плавное завершение (ENG-29)
CONTEXT_LIMIT_SIGNAL = "CONTEXT_LIMIT_REACHED:"


class SessionResult(NamedTuple):
    """Результат выполнения сессии агента.

    Attributes:
        status: Результат сессии:
            - "continue": Нормальное завершение, агент может продолжить работу
            - "error": Возникла ошибка, будет повтор с новой сессией
            - "complete": Все задачи выполнены, оркестратор отправил сигнал ALL_TASKS_DONE
            - "context_limit": Превышен бюджет контекста, плавное завершение (ENG-29)
        response: Текст ответа от агента или сообщение об ошибке, если status == "error"
    """

    status: SessionStatus
    response: str


async def run_agent_session(
    client: ClaudeSDKClient,
    message: str,
    project_dir: Path,
    ctx_manager: ContextManager | None = None,
) -> SessionResult:
    """
    Запускает одну сессию агента с использованием Claude Agent SDK.

    Args:
        client: Claude SDK клиент
        message: Промпт для отправки
        project_dir: Путь к директории проекта
        ctx_manager: Опциональный менеджер контекста для отслеживания токенов (ENG-29)

    Returns:
        SessionResult со статусом и текстом ответа:
        - status=CONTINUE: Нормальное завершение, агент может продолжить
        - status=ERROR: Возникла ошибка, будет повтор с новой сессией
        - status=COMPLETE: Все задачи выполнены, обнаружен сигнал ALL_TASKS_DONE
        - status=CONTEXT_LIMIT: Превышен бюджет контекста, плавное завершение
    """
    print("Sending prompt to Claude Agent SDK...\n")

    # Использовать предоставленный менеджер контекста или получить глобальный
    if ctx_manager is None:
        ctx_manager = get_context_manager()

    try:
        # Отправить запрос
        await client.query(message)

        # Собрать текст ответа и показать использование инструментов
        response_text: str = ""
        tool_call_count: int = 0

        async for msg in client.receive_response():
            # Обработать AssistantMessage (текст и использование инструментов)
            if isinstance(msg, AssistantMessage):
                for block in msg.content:
                    if isinstance(block, TextBlock):
                        response_text += block.text
                        # Отследить токены ответа
                        ctx_manager.budget.add("history", estimate_tokens(block.text))
                        print(block.text, end="", flush=True)
                    elif isinstance(block, ToolUseBlock):
                        tool_call_count += 1
                        print(f"\n[Tool: {block.name}]", flush=True)
                        input_str: str = str(block.input)
                        if len(input_str) > 200:
                            print(f"   Input: {input_str[:200]}...", flush=True)
                        else:
                            print(f"   Input: {input_str}", flush=True)

            # Обработать UserMessage (результаты инструментов)
            elif isinstance(msg, UserMessage):
                for block in msg.content:
                    if isinstance(block, ToolResultBlock):
                        result_content = str(block.content)
                        is_error: bool = bool(block.is_error) if block.is_error else False

                        # Отследить и обрезать вывод инструментов (ENG-29)
                        processed_output = ctx_manager.track_tool_output(
                            tool_name="tool_result",
                            output=result_content,
                        )

                        # Проверить, была ли команда заблокирована хуком безопасности
                        if "blocked" in result_content.lower():
                            print(f"   [BLOCKED] {result_content}", flush=True)
                        elif is_error:
                            # Показать ошибки (обрезанные)
                            error_str: str = result_content[:500]
                            print(f"   [Error] {error_str}", flush=True)
                        else:
                            # Инструмент успешно выполнен - показать краткое подтверждение
                            print("   [Done]", flush=True)

            # Проверить бюджет контекста после каждого сообщения (ENG-29)
            if ctx_manager.should_trigger_shutdown():
                print("\n" + "!" * 70)
                print("  CONTEXT LIMIT WARNING: 85%+ context used")
                print("  Triggering graceful shutdown...")
                print("!" * 70 + "\n")

                # Prepare shutdown checkpoint
                memory_path = project_dir / ".agent" / "MEMORY.md"
                shutdown_info = ctx_manager.prepare_graceful_shutdown(memory_path)

                return SessionResult(
                    status=SESSION_CONTEXT_LIMIT,
                    response=f"{CONTEXT_LIMIT_SIGNAL} {shutdown_info}"
                )

        print("\n" + "-" * 70 + "\n")

        # Show context usage summary
        stats = ctx_manager.get_stats()
        mode_indicator = f" [{stats['mode'].upper()}]" if stats['mode'] != "normal" else ""
        print(f"Context: {stats['usage_percent']:.1f}% used ({stats['total_used']:,} / {stats['max_tokens']:,}){mode_indicator}")
        print(f"Tool calls: {tool_call_count}")

        # Check for completion signal from orchestrator
        if COMPLETION_SIGNAL in response_text:
            return SessionResult(status=SESSION_COMPLETE, response=response_text)

        # Check for context limit signal from orchestrator (self-reported)
        if CONTEXT_LIMIT_SIGNAL in response_text:
            return SessionResult(status=SESSION_CONTEXT_LIMIT, response=response_text)

        return SessionResult(status=SESSION_CONTINUE, response=response_text)

    except ConnectionError as e:
        print(f"\nNetwork error during agent session: {e}")
        print("Check your internet connection and try again.")
        traceback.print_exc()
        return SessionResult(status=SESSION_ERROR, response=str(e))

    except TimeoutError as e:
        print(f"\nTimeout during agent session: {e}")
        print("The API request timed out. Will retry with fresh session.")
        traceback.print_exc()
        return SessionResult(status=SESSION_ERROR, response=str(e))

    except Exception as e:
        error_type: str = type(e).__name__
        error_msg: str = str(e)

        print(f"\nError during agent session ({error_type}): {error_msg}")
        print("\nFull traceback:")
        traceback.print_exc()

        # Provide actionable guidance based on error type
        error_lower = error_msg.lower()
        if "auth" in error_lower or "token" in error_lower:
            print("\nThis appears to be an authentication error.")
            print("Check your CLAUDE_CODE_OAUTH_TOKEN environment variable.")
        elif "rate" in error_lower or "limit" in error_lower:
            print("\nThis appears to be a rate limit error.")
            print("The agent will retry after a delay.")
        elif "buffer size" in error_lower or "1048576" in error_lower:
            print("\nJSON message exceeded 1MB buffer limit.")
            print("This is usually caused by browser_take_screenshot() without filename parameter or with fullPage=True.")
            print("Fix: Always use browser_take_screenshot(filename='screenshots/ENG-XX.png') WITHOUT fullPage=True")
            print("The agent will retry with a fresh session.")
        elif "task" in error_lower:
            print("\nThis appears to be a Task MCP Server error.")
            print("Check your TASK_MCP_URL and ensure the server is running.")
        elif "telegram" in error_lower:
            print("\nThis appears to be a Telegram MCP Server error.")
            print("Check your TELEGRAM_MCP_URL and ensure the server is running.")
        elif "mcp" in error_lower:
            print("\nThis appears to be an MCP server error.")
            print("Check your MCP server URLs and ensure they are accessible.")
        else:
            # Unexpected error type - make this visible
            print(f"\nUnexpected error type: {error_type}")
            print("This may indicate a bug or an unhandled edge case.")
            print("The agent will retry, but please report this if it persists.")

        return SessionResult(status=SESSION_ERROR, response=error_msg)


async def run_autonomous_agent(
    project_dir: Path,
    model: str,
    team: str,
    max_iterations: int | None = None,
) -> None:
    """
    Запускает цикл автономного агента с отслеживанием состояния сессии и восстановлением после сбоев.

    Возможности:
    - Восстановление после сбоев из .agent/session_state.json (ENG-35, ENG-66)
    - Отслеживание фаз сессии с сохранением состояния
    - Повтор на уровне фаз с умной логикой перезапуска
    - Плавная деградация при сбоях MCP/Playwright
    - Экспоненциальная задержка при rate limits
    - Управление контекстным окном с компактным режимом (ENG-29)
    - Пауза/возобновление через Telegram (ENG-52)

    Args:
        project_dir: Рабочая директория проекта
        model: Модель Claude для использования
        team: Ключ команды для управления задачами (например, "ENG")
        max_iterations: Максимальное количество итераций (None для неограниченного)

    Raises:
        ValueError: Если max_iterations не положительное число
    """
    if max_iterations is not None and max_iterations < 1:
        raise ValueError(f"max_iterations must be positive, got {max_iterations}")

    print("\n" + "=" * 70)
    print("  AUTONOMOUS CODING AGENT")
    print("=" * 70)
    print(f"\nWorking directory: {project_dir}")
    print(f"Team: {team}")
    print(f"Model: {model}")
    if max_iterations:
        print(f"Max iterations: {max_iterations}")
    else:
        print("Max iterations: Unlimited (will run until all tasks done)")
    print()

    # Сгенерировать/обновить карту проекта при запуске (ENG-33)
    print("Generating project map...")
    project_map = ensure_project_map(project_dir)
    if project_map:
        print(f"Project map loaded ({len(project_map)} bytes)")
    else:
        print("No project map available")

    # Установить директорию проекта по умолчанию для автономных функций состояния сессии (ENG-66)
    set_default_project_dir(project_dir)

    # Инициализировать менеджер состояния сессии и проверить восстановление после сбоя
    state_manager = get_session_state_manager(project_dir)
    recovery = get_session_recovery(project_dir)

    # Проверить прерванную сессию при запуске (ENG-69)
    recovery_needed, saved_state = await recovery.check_recovery()
    resume_phase: SessionPhase | None = None
    recovery_context_text: str = ""

    if recovery_needed and saved_state:
        # Extract structured recovery info (ENG-69)
        recovery_info = recovery.get_recovery_info(saved_state)

        print("\n" + "-" * 70)
        print("  CRASH RECOVERY: Resuming from interrupted session")
        print(f"  Issue: {recovery_info['issue_id']}")
        print(f"  Last phase: {recovery_info['last_phase']}")
        print(f"  Resume phase: {recovery_info['resume_phase']}")
        if recovery_info["uncommitted_changes"]:
            print("  Status: Uncommitted changes detected")
        if recovery_info["degraded_services"]:
            print(f"  Degraded services: {', '.join(recovery_info['degraded_services'])}")
        if recovery_info["error_count"] > 0:
            print(f"  Errors in previous session: {recovery_info['error_count']}")
        print("-" * 70 + "\n")

        # Determine resume point
        resume_phase = state_manager.get_resume_phase(saved_state)
        print(f"Resuming at phase: {resume_phase.phase_name}")

        # Format recovery context for prompt injection (ENG-69)
        recovery_context_text = get_recovery_context(recovery_info)

        # Restore state
        state_manager._current_state = saved_state

    iteration: int = 0

    while True:
        iteration += 1

        # Check for pause before each iteration (ENG-52)
        await wait_while_paused(project_dir)

        # Check max iterations
        if max_iterations and iteration > max_iterations:
            print(f"\nReached max iterations ({max_iterations})")
            print("To continue, run the script again without --max-iterations")
            break

        # Print session header
        print_session_header(iteration)

        # Fresh client each iteration to avoid context window exhaustion
        client: ClaudeSDKClient = create_client(project_dir, model)

        # First iteration uses execute_task, subsequent iterations use continuation_task
        # Continuation prompt checks META issue for previous session context before proceeding
        # Both prompts now include .agent/MEMORY.md content for persistent memory
        # Track context usage via context manager
        ctx_manager = get_context_manager()
        ctx_manager.reset()  # Fresh tracking for each session

        if iteration == 1:
            prompt: str = get_execute_task_with_memory(team, project_dir)
            print("(Loading project map and memory from .agent/)")

            # If recovering, inject structured recovery context (ENG-69)
            if resume_phase and recovery_context_text:
                prompt += recovery_context_text
                resume_phase = None  # Clear after first use
                recovery_context_text = ""  # Clear after first use
        else:
            prompt = get_continuation_task_with_memory(team, project_dir)
            print("(Using continuation prompt - will check previous session context)")
            print("(Loading project map and memory from .agent/)")

        # Track prompt tokens
        ctx_manager.set_system_prompt(prompt)
        stats = ctx_manager.get_stats()
        mode_info = f" [{stats['mode'].upper()}]" if stats['mode'] != "normal" else ""
        print(f"(Context budget: {stats['total_used']:,} / {stats['max_tokens']:,} tokens{mode_info})")

        # Show compact mode instructions if active
        if ctx_manager.is_compact_mode:
            print("(COMPACT MODE: Using minimal context for issue details)")

        # Run session with error recovery
        result: SessionResult = SessionResult(status=SESSION_ERROR, response="uninitialized")
        error_type_detected: ErrorType | None = None

        try:
            async with client:
                result = await run_agent_session(client, prompt, project_dir, ctx_manager)

            # Success - clear session state
            if result.status == SESSION_COMPLETE:
                state_manager.clear_state()

            # Context limit - trigger graceful shutdown with memory flush (ENG-29)
            if result.status == SESSION_CONTEXT_LIMIT:
                print("\n" + "=" * 70)
                print("  GRACEFUL SHUTDOWN: Context limit reached (85%)")
                print("=" * 70)
                print("\nCheckpoint saved. Session will resume from this point.")

                # Prepare for continuation
                memory_path = project_dir / ".agent" / "MEMORY.md"
                ctx_manager.prepare_graceful_shutdown(memory_path)

                # Let the loop continue to next iteration with fresh context
                print(f"\nWill start fresh session in {AUTO_CONTINUE_DELAY_SECONDS}s...")
                await asyncio.sleep(AUTO_CONTINUE_DELAY_SECONDS)
                continue

        except ConnectionError as e:
            print(f"\nNetwork error during agent session: {e}")
            print("Check your internet connection and try again.")
            traceback.print_exc()
            error_type_detected = recovery.classify_error(e)
            state_manager.record_error(e, error_type_detected)
            result = SessionResult(status=SESSION_ERROR, response=str(e))

        except TimeoutError as e:
            print(f"\nTimeout during agent session: {e}")
            error_type_detected = ErrorType.MCP_TIMEOUT
            state_manager.record_error(e, error_type_detected)
            result = SessionResult(status=SESSION_ERROR, response=str(e))

        except Exception as e:
            error_type_name: str = type(e).__name__
            print(f"\nUnexpected error in session context ({error_type_name}): {e}")
            traceback.print_exc()
            error_type_detected = recovery.classify_error(e)
            state_manager.record_error(e, error_type_detected)
            result = SessionResult(status=SESSION_ERROR, response=str(e))

        # Handle status
        if result.status == SESSION_COMPLETE:
            print("\n" + "=" * 70)
            print("  ALL TASKS DONE")
            print("=" * 70)
            print("\nNo remaining tasks in Todo.")
            state_manager.clear_state()
            break

        elif result.status == SESSION_CONTINUE:
            print(f"\nAgent will auto-continue in {AUTO_CONTINUE_DELAY_SECONDS}s...")

        elif result.status == SESSION_ERROR:
            print("\nSession encountered an error")

            # Apply phase-level retry strategy (ENG-67)
            if error_type_detected:
                current_phase = (
                    state_manager.current_state.phase
                    if state_manager.current_state
                    else SessionPhase.ORIENT
                )
                attempt_tracker = state_manager.get_phase_attempt(current_phase)
                delay = GracefulDegradation.get_backoff_delay(
                    attempt_tracker.attempt, error_type_detected,
                )

                # Get retry strategy from SessionRecovery (ENG-67)
                strategy = recovery.get_retry_strategy(
                    current_phase, attempt_tracker.attempt,
                )
                print(f"Phase: {current_phase.phase_name}, "
                      f"attempt: {attempt_tracker.attempt}/{MAX_PHASE_RETRIES}, "
                      f"strategy: {strategy.value}")

                if strategy == RetryStrategy.ESCALATE:
                    # Check graceful degradation before fully escalating
                    if GracefulDegradation.should_skip_service(
                        error_type_detected, current_phase,
                    ):
                        msg = GracefulDegradation.get_degradation_message(
                            error_type_detected, current_phase,
                        )
                        print(f"Graceful degradation: {msg}")
                        state_manager.mark_degraded(current_phase.phase_name)
                        delay = AUTO_CONTINUE_DELAY_SECONDS
                    else:
                        # Save changes if git error during commit
                        if (
                            error_type_detected == ErrorType.GIT_ERROR
                            and current_phase == SessionPhase.COMMIT
                        ):
                            print("Attempting to save uncommitted changes...")
                            diff_file = await recovery.save_git_diff_to_file()
                            if diff_file:
                                print(f"Changes saved to: {diff_file}")
                            else:
                                await recovery.stash_changes()

                        # Mark issue as blocked and notify
                        print(f"ESCALATED: Phase {current_phase.phase_name} "
                              f"failed after {MAX_PHASE_RETRIES} retries")
                        if state_manager.current_state:
                            state_manager.current_state.last_error = (
                                f"Escalated: {current_phase.phase_name} "
                                f"failed after {MAX_PHASE_RETRIES} retries"
                            )
                            state_manager.save_state()

                elif strategy == RetryStrategy.RETRY_FROM_ORIENT:
                    print("Restarting from ORIENT phase (early phase failure)")
                    if state_manager.current_state:
                        state_manager._current_state.phase = SessionPhase.ORIENT

                elif strategy == RetryStrategy.RETRY_IMPLEMENTATION:
                    print("Retrying from IMPLEMENTATION phase")
                    if state_manager.current_state:
                        state_manager._current_state.phase = SessionPhase.IMPLEMENTATION

                elif strategy == RetryStrategy.RETRY_CURRENT:
                    print(f"Retrying phase {current_phase.phase_name}")

                print(f"Will retry with backoff delay of {delay:.1f}s...")
                await asyncio.sleep(delay)
                continue
            else:
                print("Will retry with a fresh session...")

        # Always wait before next iteration
        await asyncio.sleep(AUTO_CONTINUE_DELAY_SECONDS)

        # Small delay between sessions
        if max_iterations is None or iteration < max_iterations:
            print("\nPreparing next session...\n")
            await asyncio.sleep(1)

    # Final summary
    print("\n" + "=" * 70)
    print("  SESSION COMPLETE")
    print("=" * 70)
    print(f"\nWorking directory: {project_dir}")
    print("\nDone!")
