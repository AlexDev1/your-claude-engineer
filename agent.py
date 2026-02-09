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
    print("  АГЕНТ НА ПАУЗЕ")
    print("=" * 70)
    print(f"\nАгент на паузе. Проверка каждые {PAUSE_CHECK_INTERVAL_SECONDS}с...")
    print("Используйте команду /resume в Telegram для продолжения.\n")

    was_paused = True

    while is_agent_paused(project_dir):
        await asyncio.sleep(PAUSE_CHECK_INTERVAL_SECONDS)
        print(f"[{asyncio.get_event_loop().time():.0f}] Всё ещё на паузе, ожидание...")

    # Агент возобновлён
    print("\n" + "=" * 70)
    print("  АГЕНТ ВОЗОБНОВЛЁН")
    print("=" * 70)
    print("\nАгент был возобновлён. Продолжаю выполнение следующей задачи...\n")

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
                print("Отправлено уведомление в Telegram о возобновлении.")
    except Exception as e:
        print(f"Примечание: Не удалось отправить уведомление в Telegram: {e}")

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
    print("Отправка промпта в Claude Agent SDK...\n")

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
                print("  ПРЕДУПРЕЖДЕНИЕ О ЛИМИТЕ КОНТЕКСТА: использовано 85%+ контекста")
                print("  Запуск плавного завершения...")
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
        print(f"\nСетевая ошибка во время сессии агента: {e}")
        print("Проверьте подключение к Интернету и повторите попытку.")
        traceback.print_exc()
        return SessionResult(status=SESSION_ERROR, response=str(e))

    except TimeoutError as e:
        print(f"\nТаймаут во время сессии агента: {e}")
        print("Истекло время ожидания ответа API. Будет повтор с новой сессией.")
        traceback.print_exc()
        return SessionResult(status=SESSION_ERROR, response=str(e))

    except Exception as e:
        error_type: str = type(e).__name__
        error_msg: str = str(e)

        print(f"\nОшибка во время сессии агента ({error_type}): {error_msg}")
        print("\nПолная трассировка:")
        traceback.print_exc()

        # Provide actionable guidance based on error type
        error_lower = error_msg.lower()
        if "auth" in error_lower or "token" in error_lower:
            print("\nПохоже на ошибку аутентификации.")
            print("Проверьте переменную окружения CLAUDE_CODE_OAUTH_TOKEN.")
        elif "rate" in error_lower or "limit" in error_lower:
            print("\nПохоже на ошибку превышения лимита запросов.")
            print("Агент повторит попытку после задержки.")
        elif "buffer size" in error_lower or "1048576" in error_lower:
            print("\nJSON-сообщение превысило лимит буфера 1МБ.")
            print("Обычно это вызвано browser_take_screenshot() без параметра filename или с fullPage=True.")
            print("Исправление: Всегда используйте browser_take_screenshot(filename='screenshots/ENG-XX.png') БЕЗ fullPage=True")
            print("Агент повторит попытку с новой сессией.")
        elif "task" in error_lower:
            print("\nПохоже на ошибку Task MCP Server.")
            print("Проверьте TASK_MCP_URL и убедитесь, что сервер запущен.")
        elif "telegram" in error_lower:
            print("\nПохоже на ошибку Telegram MCP Server.")
            print("Проверьте TELEGRAM_MCP_URL и убедитесь, что сервер запущен.")
        elif "mcp" in error_lower:
            print("\nПохоже на ошибку MCP-сервера.")
            print("Проверьте URL MCP-серверов и убедитесь, что они доступны.")
        else:
            # Unexpected error type - make this visible
            print(f"\nНеожиданный тип ошибки: {error_type}")
            print("Это может указывать на баг или необработанный крайний случай.")
            print("Агент повторит попытку, но пожалуйста сообщите об этом, если ошибка повторяется.")

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
    print("  АВТОНОМНЫЙ АГЕНТ-КОДЕР")
    print("=" * 70)
    print(f"\nРабочая директория: {project_dir}")
    print(f"Команда: {team}")
    print(f"Модель: {model}")
    if max_iterations:
        print(f"Макс. итераций: {max_iterations}")
    else:
        print("Макс. итераций: без ограничений (будет работать до завершения всех задач)")
    print()

    # Сгенерировать/обновить карту проекта при запуске (ENG-33)
    print("Генерация карты проекта...")
    project_map = ensure_project_map(project_dir)
    if project_map:
        print(f"Карта проекта загружена ({len(project_map)} байт)")
    else:
        print("Карта проекта недоступна")

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
        print("  ВОССТАНОВЛЕНИЕ ПОСЛЕ СБОЯ: Возобновление прерванной сессии")
        print(f"  Задача: {recovery_info['issue_id']}")
        print(f"  Последняя фаза: {recovery_info['last_phase']}")
        print(f"  Фаза возобновления: {recovery_info['resume_phase']}")
        if recovery_info["uncommitted_changes"]:
            print("  Статус: Обнаружены незакоммиченные изменения")
        if recovery_info["degraded_services"]:
            print(f"  Деградированные сервисы: {', '.join(recovery_info['degraded_services'])}")
        if recovery_info["error_count"] > 0:
            print(f"  Ошибок в предыдущей сессии: {recovery_info['error_count']}")
        print("-" * 70 + "\n")

        # Determine resume point
        resume_phase = state_manager.get_resume_phase(saved_state)
        print(f"Возобновление на фазе: {resume_phase.phase_name}")

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
            print(f"\nДостигнут максимум итераций ({max_iterations})")
            print("Для продолжения запустите скрипт снова без --max-iterations")
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
            print("(Загрузка карты проекта и памяти из .agent/)")

            # If recovering, inject structured recovery context (ENG-69)
            if resume_phase and recovery_context_text:
                prompt += recovery_context_text
                resume_phase = None  # Clear after first use
                recovery_context_text = ""  # Clear after first use
        else:
            prompt = get_continuation_task_with_memory(team, project_dir)
            print("(Использование промпта продолжения - будет проверен контекст предыдущей сессии)")
            print("(Загрузка карты проекта и памяти из .agent/)")

        # Track prompt tokens
        ctx_manager.set_system_prompt(prompt)
        stats = ctx_manager.get_stats()
        mode_info = f" [{stats['mode'].upper()}]" if stats['mode'] != "normal" else ""
        print(f"(Бюджет контекста: {stats['total_used']:,} / {stats['max_tokens']:,} токенов{mode_info})")

        # Show compact mode instructions if active
        if ctx_manager.is_compact_mode:
            print("(КОМПАКТНЫЙ РЕЖИМ: Использование минимального контекста для деталей задачи)")

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
                print("  ПЛАВНОЕ ЗАВЕРШЕНИЕ: Достигнут лимит контекста (85%)")
                print("=" * 70)
                print("\nКонтрольная точка сохранена. Сессия возобновится с этого места.")

                # Prepare for continuation
                memory_path = project_dir / ".agent" / "MEMORY.md"
                ctx_manager.prepare_graceful_shutdown(memory_path)

                # Let the loop continue to next iteration with fresh context
                print(f"\nЗапуск новой сессии через {AUTO_CONTINUE_DELAY_SECONDS}с...")
                await asyncio.sleep(AUTO_CONTINUE_DELAY_SECONDS)
                continue

        except ConnectionError as e:
            print(f"\nСетевая ошибка во время сессии агента: {e}")
            print("Проверьте подключение к Интернету и повторите попытку.")
            traceback.print_exc()
            error_type_detected = recovery.classify_error(e)
            state_manager.record_error(e, error_type_detected)
            result = SessionResult(status=SESSION_ERROR, response=str(e))

        except TimeoutError as e:
            print(f"\nТаймаут во время сессии агента: {e}")
            error_type_detected = ErrorType.MCP_TIMEOUT
            state_manager.record_error(e, error_type_detected)
            result = SessionResult(status=SESSION_ERROR, response=str(e))

        except Exception as e:
            error_type_name: str = type(e).__name__
            print(f"\nНеожиданная ошибка в контексте сессии ({error_type_name}): {e}")
            traceback.print_exc()
            error_type_detected = recovery.classify_error(e)
            state_manager.record_error(e, error_type_detected)
            result = SessionResult(status=SESSION_ERROR, response=str(e))

        # Handle status
        if result.status == SESSION_COMPLETE:
            print("\n" + "=" * 70)
            print("  ВСЕ ЗАДАЧИ ВЫПОЛНЕНЫ")
            print("=" * 70)
            print("\nНет оставшихся задач в Todo.")
            state_manager.clear_state()
            break

        elif result.status == SESSION_CONTINUE:
            print(f"\nАгент автоматически продолжит работу через {AUTO_CONTINUE_DELAY_SECONDS}с...")

        elif result.status == SESSION_ERROR:
            print("\nВ сессии произошла ошибка")

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
                print(f"Фаза: {current_phase.phase_name}, "
                      f"попытка: {attempt_tracker.attempt}/{MAX_PHASE_RETRIES}, "
                      f"стратегия: {strategy.value}")

                if strategy == RetryStrategy.ESCALATE:
                    # Check graceful degradation before fully escalating
                    if GracefulDegradation.should_skip_service(
                        error_type_detected, current_phase,
                    ):
                        msg = GracefulDegradation.get_degradation_message(
                            error_type_detected, current_phase,
                        )
                        print(f"Плавная деградация: {msg}")
                        state_manager.mark_degraded(current_phase.phase_name)
                        delay = AUTO_CONTINUE_DELAY_SECONDS
                    else:
                        # Save changes if git error during commit
                        if (
                            error_type_detected == ErrorType.GIT_ERROR
                            and current_phase == SessionPhase.COMMIT
                        ):
                            print("Попытка сохранить незакоммиченные изменения...")
                            diff_file = await recovery.save_git_diff_to_file()
                            if diff_file:
                                print(f"Изменения сохранены в: {diff_file}")
                            else:
                                await recovery.stash_changes()

                        # Mark issue as blocked and notify
                        print(f"ЭСКАЛАЦИЯ: Фаза {current_phase.phase_name} "
                              f"не удалась после {MAX_PHASE_RETRIES} попыток")
                        if state_manager.current_state:
                            state_manager.current_state.last_error = (
                                f"Эскалация: {current_phase.phase_name} "
                                f"не удалась после {MAX_PHASE_RETRIES} попыток"
                            )
                            state_manager.save_state()

                elif strategy == RetryStrategy.RETRY_FROM_ORIENT:
                    print("Перезапуск с фазы ORIENT (сбой на ранней фазе)")
                    if state_manager.current_state:
                        state_manager._current_state.phase = SessionPhase.ORIENT

                elif strategy == RetryStrategy.RETRY_IMPLEMENTATION:
                    print("Повтор с фазы IMPLEMENTATION")
                    if state_manager.current_state:
                        state_manager._current_state.phase = SessionPhase.IMPLEMENTATION

                elif strategy == RetryStrategy.RETRY_CURRENT:
                    print(f"Повтор фазы {current_phase.phase_name}")

                print(f"Повтор с задержкой {delay:.1f}с...")
                await asyncio.sleep(delay)
                continue
            else:
                print("Повтор с новой сессией...")

        # Always wait before next iteration
        await asyncio.sleep(AUTO_CONTINUE_DELAY_SECONDS)

        # Small delay between sessions
        if max_iterations is None or iteration < max_iterations:
            print("\nПодготовка следующей сессии...\n")
            await asyncio.sleep(1)

    # Final summary
    print("\n" + "=" * 70)
    print("  СЕССИЯ ЗАВЕРШЕНА")
    print("=" * 70)
    print(f"\nРабочая директория: {project_dir}")
    print("\nГотово!")
