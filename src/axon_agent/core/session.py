"""
Логика сессии агента
=====================

Функция run_agent_session для запуска одной сессии агента.
Интегрируется с context_manager для отслеживания токенового бюджета.
Реализует управление контекстным окном с компактным режимом и плавным завершением (ENG-29).
"""

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

from axon_agent.core.context import (
    ContextManager,
    ContextMode,
    estimate_tokens,
    get_context_manager,
)


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
