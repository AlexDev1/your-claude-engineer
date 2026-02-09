#!/usr/bin/env python3
"""
Health Check Module
===================

Pre-session health checks for the autonomous agent.
Verifies system health before each session iteration.

Checks:
- MCP servers are accessible (Task MCP, Telegram MCP)
- Disk space is adequate (at least 1GB free in project directory)
- No orphan agent processes running

Implements retry logic with configurable delays and Telegram escalation.

Usage:
    # Programmatic
    from health_check import run_health_check, HealthCheckResult

    result = await run_health_check(project_dir)
    if not result.passed:
        print(f"Health check failed: {result.reason}")

    # CLI
    python health_check.py
    python health_check.py --json
"""

import asyncio
import os
import shutil
import subprocess
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Final

from dotenv import load_dotenv

# Environment variable defaults
HEALTH_CHECK_RETRY_DELAY_SECONDS: Final[int] = int(
    os.environ.get("HEALTH_CHECK_RETRY_DELAY_SECONDS", "30")
)
HEALTH_CHECK_MAX_RETRIES: Final[int] = int(
    os.environ.get("HEALTH_CHECK_MAX_RETRIES", "3")
)
MINIMUM_DISK_SPACE_GB: Final[float] = 1.0


@dataclass
class HealthCheckResult:
    """Result of health check."""

    passed: bool
    reason: str = ""
    details: dict[str, str] = field(default_factory=dict)

    def __str__(self) -> str:
        """Return human-readable string representation."""
        if self.passed:
            return "Health check passed"
        return f"Health check failed: {self.reason}"


def check_disk_space(project_dir: Path, min_gb: float = MINIMUM_DISK_SPACE_GB) -> HealthCheckResult:
    """
    Check if there is adequate disk space in the project directory.

    Args:
        project_dir: Project directory to check
        min_gb: Minimum required free space in GB

    Returns:
        HealthCheckResult indicating pass/fail
    """
    try:
        stat = shutil.disk_usage(project_dir)
        free_gb = stat.free / (1024 ** 3)

        if free_gb < min_gb:
            return HealthCheckResult(
                passed=False,
                reason=f"Disk space low: {free_gb:.2f}GB free, need at least {min_gb}GB",
                details={
                    "free_gb": f"{free_gb:.2f}",
                    "required_gb": f"{min_gb}",
                    "path": str(project_dir),
                },
            )

        return HealthCheckResult(
            passed=True,
            reason="",
            details={
                "free_gb": f"{free_gb:.2f}",
                "path": str(project_dir),
            },
        )
    except OSError as e:
        return HealthCheckResult(
            passed=False,
            reason=f"Could not check disk space: {e}",
            details={"error": str(e)},
        )


def check_orphan_processes() -> HealthCheckResult:
    """
    Check for orphan agent processes that might interfere with operation.

    Uses psutil if available to find python processes running agent scripts.
    Falls back gracefully if process checking is not available.

    Returns:
        HealthCheckResult indicating pass/fail (always passes if check unavailable)
    """
    current_pid = os.getpid()
    parent_pid = os.getppid()

    # Try using psutil first (most reliable cross-platform solution)
    try:
        import psutil

        orphan_pids = []
        orphan_info = []
        agent_patterns = ["autonomous_agent_demo.py", "agent.py", "health_check.py"]

        for proc in psutil.process_iter(["pid", "ppid", "cmdline", "create_time"]):
            try:
                pid = proc.info["pid"]
                cmdline = proc.info.get("cmdline") or []
                cmdline_str = " ".join(cmdline)

                # Skip current process and parent
                if pid == current_pid or pid == parent_pid:
                    continue

                # Check if this is an agent process
                is_agent_process = any(
                    pattern in cmdline_str for pattern in agent_patterns
                )

                if is_agent_process and "python" in cmdline_str.lower():
                    orphan_pids.append(pid)
                    orphan_info.append(f"PID {pid}: {cmdline_str[:80]}")
                    if len(orphan_pids) >= 5:
                        break

            except (psutil.NoSuchProcess, psutil.AccessDenied, psutil.ZombieProcess):
                continue

        if orphan_pids:
            return HealthCheckResult(
                passed=False,
                reason=f"Found {len(orphan_pids)} orphan agent process(es)",
                details={
                    "orphan_count": str(len(orphan_pids)),
                    "orphan_pids": ",".join(map(str, orphan_pids)),
                    "orphan_info": "; ".join(orphan_info),
                },
            )

        return HealthCheckResult(
            passed=True,
            reason="",
            details={"orphan_count": "0", "method": "psutil"},
        )

    except ImportError:
        # psutil not available - skip orphan check gracefully
        return HealthCheckResult(
            passed=True,
            reason="",
            details={"warning": "psutil not available, skipping orphan check"},
        )
    except Exception as e:
        # Other errors - log but don't fail the health check
        return HealthCheckResult(
            passed=True,
            reason="",
            details={"warning": f"Could not check for orphans: {e}"},
        )


def check_mcp_servers(project_dir: Path) -> HealthCheckResult:
    """
    Check if MCP servers are configured and accessible.

    Uses environment variables TASK_MCP_URL and TELEGRAM_MCP_URL
    to verify server configuration.

    Args:
        project_dir: Project directory (to load .env if needed)

    Returns:
        HealthCheckResult indicating pass/fail
    """
    # Load .env file to get MCP URLs
    env_file = project_dir / ".env"
    if env_file.exists():
        load_dotenv(env_file)

    task_mcp_url = os.environ.get("TASK_MCP_URL", "")
    telegram_mcp_url = os.environ.get("TELEGRAM_MCP_URL", "")
    mcp_api_key = os.environ.get("MCP_API_KEY", "")

    issues = []
    details = {}

    # Check Task MCP Server URL
    if not task_mcp_url:
        issues.append("TASK_MCP_URL not configured")
    else:
        details["task_mcp_url"] = task_mcp_url[:50] + "..." if len(task_mcp_url) > 50 else task_mcp_url

    # Check Telegram MCP Server URL
    if not telegram_mcp_url:
        issues.append("TELEGRAM_MCP_URL not configured")
    else:
        details["telegram_mcp_url"] = telegram_mcp_url[:50] + "..." if len(telegram_mcp_url) > 50 else telegram_mcp_url

    # Check API key
    if not mcp_api_key:
        issues.append("MCP_API_KEY not configured")
    else:
        details["mcp_api_key"] = "***" + mcp_api_key[-4:] if len(mcp_api_key) > 4 else "***"

    if issues:
        return HealthCheckResult(
            passed=False,
            reason="; ".join(issues),
            details=details,
        )

    return HealthCheckResult(
        passed=True,
        reason="",
        details=details,
    )


async def send_telegram_escalation(project_dir: Path, reason: str) -> bool:
    """
    Send escalation message to Telegram when health checks fail.

    Args:
        project_dir: Project directory (to load .env)
        reason: Reason for the health check failure

    Returns:
        True if message was sent successfully, False otherwise
    """
    try:
        import httpx

        # Load .env file
        env_file = project_dir / ".env"
        if env_file.exists():
            load_dotenv(env_file)

        telegram_bot_token = os.environ.get("TELEGRAM_BOT_TOKEN", "")
        telegram_chat_id = os.environ.get("TELEGRAM_CHAT_ID", "")

        if not telegram_bot_token or not telegram_chat_id:
            print("Предупреждение: Учётные данные Telegram не настроены, невозможно отправить эскалацию")
            return False

        # Format the escalation message
        # Using Unicode cross mark since emoji might not display correctly
        message = f"\u274c Health Check Failed: {reason}. Agent stopped after {HEALTH_CHECK_MAX_RETRIES} retries."

        async with httpx.AsyncClient() as client:
            url = f"https://api.telegram.org/bot{telegram_bot_token}/sendMessage"
            payload = {
                "chat_id": telegram_chat_id,
                "text": message,
                "parse_mode": "HTML",
            }
            response = await client.post(url, json=payload, timeout=10.0)
            response.raise_for_status()
            print(f"Отправлена эскалация в Telegram: {reason}")
            return True

    except ImportError:
        print("Предупреждение: httpx не установлен, невозможно отправить эскалацию в Telegram")
        return False
    except Exception as e:
        print(f"Предупреждение: Не удалось отправить эскалацию в Telegram: {e}")
        return False


async def run_health_check(
    project_dir: Path,
    max_retries: int = HEALTH_CHECK_MAX_RETRIES,
    retry_delay_seconds: int = HEALTH_CHECK_RETRY_DELAY_SECONDS,
    send_telegram_on_failure: bool = True,
) -> HealthCheckResult:
    """
    Run all health checks with retry logic.

    Performs the following checks:
    1. MCP servers are configured
    2. Disk space is adequate (1GB free)
    3. No orphan agent processes

    Retries up to max_retries times with retry_delay_seconds between attempts.
    Sends Telegram escalation after all retries fail.

    Args:
        project_dir: Project directory to check
        max_retries: Maximum number of retry attempts (default: 3)
        retry_delay_seconds: Delay between retries in seconds (default: 30)
        send_telegram_on_failure: Whether to send Telegram message on final failure

    Returns:
        HealthCheckResult with overall pass/fail status
    """
    print("=" * 70)
    print("  ПРОВЕРКА ЗДОРОВЬЯ СИСТЕМЫ")
    print("=" * 70)
    print()

    last_failure_reason = ""

    for attempt in range(1, max_retries + 1):
        print(f"Попытка проверки {attempt}/{max_retries}...")

        all_passed = True
        failure_reasons = []

        # Check 1: MCP Servers
        mcp_result = check_mcp_servers(project_dir)
        if mcp_result.passed:
            print("  [OK] MCP серверы настроены")
        else:
            print(f"  [ОШИБКА] MCP серверы: {mcp_result.reason}")
            all_passed = False
            failure_reasons.append(f"MCP: {mcp_result.reason}")

        # Check 2: Disk Space
        disk_result = check_disk_space(project_dir)
        if disk_result.passed:
            print(f"  [OK] Дисковое пространство: {disk_result.details.get('free_gb', '?')}ГБ свободно")
        else:
            print(f"  [ОШИБКА] Дисковое пространство: {disk_result.reason}")
            all_passed = False
            failure_reasons.append(f"Диск: {disk_result.reason}")

        # Check 3: Orphan Processes
        orphan_result = check_orphan_processes()
        if orphan_result.passed:
            orphan_count = orphan_result.details.get("orphan_count", "0")
            warning = orphan_result.details.get("warning", "")
            if warning:
                print(f"  [OK] Потерянные процессы: {warning}")
            else:
                print(f"  [OK] Нет потерянных процессов ({orphan_count} найдено)")
        else:
            print(f"  [ОШИБКА] Потерянные процессы: {orphan_result.reason}")
            all_passed = False
            failure_reasons.append(f"Процессы: {orphan_result.reason}")

        if all_passed:
            print()
            print("  Проверка здоровья ПРОЙДЕНА")
            print("-" * 70)
            return HealthCheckResult(
                passed=True,
                reason="",
                details={
                    "attempt": str(attempt),
                    "mcp": "ok",
                    "disk": "ok",
                    "orphans": "ok",
                },
            )

        # Collect failure reason
        last_failure_reason = "; ".join(failure_reasons)

        if attempt < max_retries:
            print(f"\n  Повтор через {retry_delay_seconds}с...")
            await asyncio.sleep(retry_delay_seconds)
            print()
        else:
            print(f"\n  Все {max_retries} попыток не удались")

    # All retries exhausted - send escalation
    print()
    print("!" * 70)
    print(f"  ПРОВЕРКА НЕ ПРОЙДЕНА после {max_retries} попыток")
    print(f"  Причина: {last_failure_reason}")
    print("!" * 70)

    if send_telegram_on_failure:
        await send_telegram_escalation(project_dir, last_failure_reason)

    return HealthCheckResult(
        passed=False,
        reason=last_failure_reason,
        details={
            "attempts": str(max_retries),
            "final_reason": last_failure_reason,
        },
    )


async def run_health_check_cli(project_dir: Path, output_json: bool = False) -> int:
    """
    CLI entry point for health check.

    Args:
        project_dir: Project directory to check
        output_json: Whether to output JSON format

    Returns:
        Exit code (0 for success, 1 for failure)
    """
    result = await run_health_check(
        project_dir,
        send_telegram_on_failure=False,  # Don't send Telegram in CLI mode
    )

    if output_json:
        import json
        print(json.dumps({
            "passed": result.passed,
            "reason": result.reason,
            "details": result.details,
        }, indent=2))
    else:
        if not result.passed:
            print(f"\nПроверка здоровья не пройдена: {result.reason}")

    return 0 if result.passed else 1


def main() -> int:
    """CLI entry point."""
    import argparse

    parser = argparse.ArgumentParser(
        description="Проверка здоровья для автономного агента"
    )
    parser.add_argument(
        "--json",
        action="store_true",
        help="Вывести результаты в JSON формате",
    )
    parser.add_argument(
        "--project-dir",
        type=str,
        default=".",
        help="Директория проекта для проверки (по умолчанию: текущая директория)",
    )

    args = parser.parse_args()

    project_dir = Path(args.project_dir).resolve()

    return asyncio.run(run_health_check_cli(project_dir, args.json))


if __name__ == "__main__":
    sys.exit(main())
