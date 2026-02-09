#!/usr/bin/env python3
"""
Autonomous Coding Agent Demo
============================

A minimal harness demonstrating long-running autonomous coding with Claude.
This script implements an orchestrator pattern where a main agent delegates to
specialized sub-agents (task, coding, telegram) for different domains.

The agent works in the current directory, picks tasks from the Task MCP Server
by priority, and executes them one at a time.

Example Usage:
    uv run python autonomous_agent_demo.py
    uv run python autonomous_agent_demo.py --team ENG --max-iterations 5
    uv run python autonomous_agent_demo.py --model opus
"""

import argparse
import asyncio
import os
import sys
from pathlib import Path

from dotenv import load_dotenv

from agent import run_autonomous_agent
from preflight import run_preflight_checks

# Load environment variables from .env file
load_dotenv()


# Available Claude 4.5 models
AVAILABLE_MODELS: dict[str, str] = {
    "haiku": "claude-haiku-4-5-20251001",
    "sonnet": "claude-sonnet-4-5-20250929",
    "opus": "claude-opus-4-5-20251101",
}

# Default orchestrator model (can be overridden by ORCHESTRATOR_MODEL env var or --model flag)
# Orchestrator just delegates, so haiku is sufficient and cost-effective
DEFAULT_MODEL: str = os.environ.get("ORCHESTRATOR_MODEL", "haiku").lower()
if DEFAULT_MODEL not in AVAILABLE_MODELS:
    DEFAULT_MODEL = "haiku"


def parse_args() -> argparse.Namespace:
    """Parse command line arguments."""
    parser = argparse.ArgumentParser(
        description="Автономный агент-кодер — агентная система на основе задач",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Примеры:
  # Запуск в текущей директории, команда по умолчанию ENG
  uv run python autonomous_agent_demo.py

  # Указать команду
  uv run python autonomous_agent_demo.py --team ENG

  # Использовать opus для оркестратора (более способный, но дороже)
  uv run python autonomous_agent_demo.py --model opus

  # Ограничить итерации для тестирования
  uv run python autonomous_agent_demo.py --max-iterations 5

  # Пропустить preflight проверки для быстрой разработки
  uv run python autonomous_agent_demo.py --skip-preflight

  # Остановиться на первой ошибке preflight
  uv run python autonomous_agent_demo.py --fail-fast

Переменные окружения:
  ORCHESTRATOR_MODEL         Модель оркестратора (по умолчанию: haiku)
  TASK_MCP_URL               URL Task MCP сервера
  TELEGRAM_MCP_URL           URL Telegram MCP сервера
  MCP_API_KEY                API ключ для MCP серверов
        """,
    )

    parser.add_argument(
        "--team",
        type=str,
        default="ENG",
        help="Ключ команды для управления задачами (по умолчанию: ENG)",
    )

    parser.add_argument(
        "--max-iterations",
        type=int,
        default=None,
        help="Максимальное количество итераций агента (по умолчанию: без ограничений)",
    )

    parser.add_argument(
        "--model",
        type=str,
        choices=list(AVAILABLE_MODELS.keys()),
        default=DEFAULT_MODEL,
        help=f"Модель для оркестратора (суб-агенты имеют фиксированные модели: coding=sonnet, остальные=haiku) (по умолчанию: {DEFAULT_MODEL})",
    )

    parser.add_argument(
        "--skip-preflight",
        action="store_true",
        help="Пропустить preflight проверки (для быстрой разработки)",
    )

    parser.add_argument(
        "--fail-fast",
        action="store_true",
        help="Выйти при первой ошибке preflight (по умолчанию: выполнить все проверки)",
    )

    return parser.parse_args()


def main() -> int:
    """
    Main entry point.

    Returns:
        Exit code (0 for success, 1 for error, 2 for preflight failure, 130 for keyboard interrupt)
    """
    args: argparse.Namespace = parse_args()

    # Run preflight checks unless skipped
    if not args.skip_preflight:
        preflight_passed: bool = run_preflight_checks(fail_fast=args.fail_fast)
        if not preflight_passed:
            print("\nПроверки preflight не пройдены. Используйте --skip-preflight для пропуска.")
            return 2  # Distinct exit code for preflight failure
        print()  # Blank line before starting agent

    # Working directory is always cwd
    project_dir: Path = Path.cwd()

    # Resolve model short name to full model ID
    model_id: str = AVAILABLE_MODELS[args.model]

    print("Запуск автономного агента...")
    print()

    # Run the agent
    try:
        asyncio.run(
            run_autonomous_agent(
                project_dir=project_dir,
                model=model_id,
                team=args.team,
                max_iterations=args.max_iterations,
            )
        )
        return 0
    except KeyboardInterrupt:
        print("\n\nПрервано пользователем")
        print("Для возобновления запустите ту же команду снова")
        return 130  # Standard Unix exit code for SIGINT
    except Exception as e:
        error_type: str = type(e).__name__
        print(f"\nКритическая ошибка ({error_type}): {e}")
        print("\nРаспространённые причины:")
        print("  1. Отсутствует аутентификация Claude (выполните: claude login)")
        print("  2. Проблемы с подключением к MCP серверам (проверьте TASK_MCP_URL, TELEGRAM_MCP_URL в .env)")
        print("\nПолные детали ошибки:")
        raise


if __name__ == "__main__":
    sys.exit(main())
