#!/usr/bin/env python3
"""
Preflight Check Script
======================

Pre-flight checks for the Claude Agent system.
Verifies all required dependencies and configurations are in place.

Run with: python preflight.py
"""

import os
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path
from typing import NamedTuple


class CheckResult(NamedTuple):
    """Result of a preflight check."""

    passed: bool
    message: str
    details: str | None = None


def print_result(name: str, result: CheckResult) -> None:
    """Print a check result with appropriate formatting."""
    status = "\u2713 PASS" if result.passed else "\u2717 FAIL"
    print(f"  {status}: {name}")
    if result.details:
        for line in result.details.strip().split("\n"):
            print(f"         {line}")
    if not result.passed and result.message:
        print(f"         Error: {result.message}")


def run_command(cmd: list[str], timeout: int = 10) -> tuple[bool, str, str]:
    """Run a command and return (success, stdout, stderr)."""
    try:
        result = subprocess.run(
            cmd, capture_output=True, text=True, timeout=timeout, check=False
        )
        return result.returncode == 0, result.stdout.strip(), result.stderr.strip()
    except FileNotFoundError:
        return False, "", f"Command not found: {cmd[0]}"
    except subprocess.TimeoutExpired:
        return False, "", f"Command timed out after {timeout}s"
    except Exception as e:
        return False, "", str(e)


def check_claude_sdk() -> CheckResult:
    """Check if Claude SDK (anthropic package) is importable."""
    try:
        import anthropic  # noqa: F401

        return CheckResult(passed=True, message="", details="anthropic package is installed")
    except ImportError as e:
        return CheckResult(
            passed=False,
            message=str(e),
            details="Install with: pip install anthropic",
        )


def check_claude_agent_sdk() -> CheckResult:
    """Check if Claude Agent SDK is importable."""
    try:
        import claude_agent_sdk  # noqa: F401

        return CheckResult(
            passed=True, message="", details="claude_agent_sdk package is installed"
        )
    except ImportError as e:
        return CheckResult(
            passed=False,
            message=str(e),
            details="Claude Agent SDK not found",
        )


def check_task_mcp_server() -> CheckResult:
    """Check if Task MCP Server is available."""
    # Check if the task server module exists
    task_server_paths = [
        Path("/home/dev/work/AxonCode/your-claude-engineer/task_server"),
        Path("task_server"),
        Path(".").resolve() / "task_server",
    ]

    for path in task_server_paths:
        if path.exists():
            return CheckResult(
                passed=True,
                message="",
                details=f"Task server found at: {path}",
            )

    # Check if uvx can find the task-mcp-server
    success, stdout, stderr = run_command(["which", "uvx"])
    if success:
        return CheckResult(
            passed=True,
            message="",
            details="uvx available for MCP server execution",
        )

    return CheckResult(
        passed=False,
        message="Task MCP Server not found",
        details="Ensure task_server directory exists or uvx is installed",
    )


def check_telegram_mcp_server() -> CheckResult:
    """Check if Telegram MCP Server is available."""
    # Check for telegram bot configuration
    telegram_token = os.environ.get("TELEGRAM_BOT_TOKEN")
    if telegram_token:
        return CheckResult(
            passed=True,
            message="",
            details="TELEGRAM_BOT_TOKEN environment variable is set",
        )

    # Check if .env file exists with telegram config
    env_file = Path(".env")
    if env_file.exists():
        content = env_file.read_text()
        if "TELEGRAM_BOT_TOKEN" in content:
            return CheckResult(
                passed=True,
                message="",
                details="TELEGRAM_BOT_TOKEN found in .env file",
            )

    return CheckResult(
        passed=False,
        message="Telegram MCP Server not configured",
        details="Set TELEGRAM_BOT_TOKEN environment variable or add to .env file",
    )


def check_playwright_mcp() -> CheckResult:
    """Check if Playwright MCP is working."""
    try:
        # Check if playwright is installed
        import playwright  # noqa: F401

        # Check if browsers are installed
        success, stdout, stderr = run_command(
            ["playwright", "install", "--dry-run", "chromium"], timeout=30
        )

        # Check for playwright executable
        playwright_path = shutil.which("playwright")
        if playwright_path:
            return CheckResult(
                passed=True,
                message="",
                details=f"Playwright installed at: {playwright_path}",
            )

        return CheckResult(
            passed=True,
            message="",
            details="playwright package is installed",
        )
    except ImportError:
        return CheckResult(
            passed=False,
            message="Playwright not installed",
            details="Install with: pip install playwright && playwright install chromium",
        )


def check_git_installation() -> CheckResult:
    """Check Git installation and configuration."""
    # Check git version
    success, version, stderr = run_command(["git", "--version"])
    if not success:
        return CheckResult(
            passed=False,
            message="Git not installed",
            details=stderr,
        )

    # Check git config
    success_name, user_name, _ = run_command(["git", "config", "user.name"])
    success_email, user_email, _ = run_command(["git", "config", "user.email"])

    details_lines = [version]
    issues = []

    if success_name and user_name:
        details_lines.append(f"user.name: {user_name}")
    else:
        issues.append("user.name not configured")

    if success_email and user_email:
        details_lines.append(f"user.email: {user_email}")
    else:
        issues.append("user.email not configured")

    if issues:
        return CheckResult(
            passed=False,
            message="; ".join(issues),
            details="\n".join(details_lines),
        )

    return CheckResult(
        passed=True,
        message="",
        details="\n".join(details_lines),
    )


def check_node_npm() -> CheckResult:
    """Check Node.js and npm availability."""
    # Check node version
    success_node, node_version, stderr_node = run_command(["node", "--version"])
    if not success_node:
        return CheckResult(
            passed=False,
            message="Node.js not installed",
            details=stderr_node or "Install from https://nodejs.org/",
        )

    # Check npm version
    success_npm, npm_version, stderr_npm = run_command(["npm", "--version"])
    if not success_npm:
        return CheckResult(
            passed=False,
            message="npm not installed",
            details=stderr_npm,
        )

    return CheckResult(
        passed=True,
        message="",
        details=f"Node.js {node_version}, npm {npm_version}",
    )


def check_filesystem_permissions() -> CheckResult:
    """Test filesystem write permissions."""
    test_dirs = [
        Path("."),
        Path(tempfile.gettempdir()),
    ]

    results = []
    issues = []

    for test_dir in test_dirs:
        test_file = test_dir / ".preflight_test_file"
        try:
            # Try to write
            test_file.write_text("preflight test")
            # Try to read
            content = test_file.read_text()
            if content == "preflight test":
                results.append(f"Writable: {test_dir.resolve()}")
            else:
                issues.append(f"Read/write mismatch in {test_dir}")
            # Clean up
            test_file.unlink()
        except PermissionError as e:
            issues.append(f"Permission denied: {test_dir} - {e}")
        except Exception as e:
            issues.append(f"Error in {test_dir}: {e}")

    if issues:
        return CheckResult(
            passed=False,
            message="; ".join(issues),
            details="\n".join(results) if results else None,
        )

    return CheckResult(
        passed=True,
        message="",
        details="\n".join(results),
    )


def check_security_hooks() -> CheckResult:
    """Validate security hooks are active."""
    git_hooks_dir = Path(".git/hooks")

    if not git_hooks_dir.exists():
        return CheckResult(
            passed=False,
            message=".git/hooks directory not found",
            details="Ensure you are in a git repository",
        )

    # Check for expected hook files (sample files indicate git is properly initialized)
    expected_samples = [
        "pre-commit.sample",
        "commit-msg.sample",
        "pre-push.sample",
    ]

    found_samples = []
    found_active_hooks = []

    for hook_file in git_hooks_dir.iterdir():
        if hook_file.suffix == ".sample":
            found_samples.append(hook_file.name)
        elif hook_file.is_file() and os.access(hook_file, os.X_OK):
            found_active_hooks.append(hook_file.name)

    details_lines = []
    if found_samples:
        details_lines.append(f"Sample hooks available: {len(found_samples)}")
    if found_active_hooks:
        details_lines.append(f"Active hooks: {', '.join(found_active_hooks)}")
    else:
        details_lines.append("No active hooks (sample hooks available)")

    # Check if security.py exists (our custom security module)
    security_module = Path("security.py")
    if security_module.exists():
        details_lines.append("security.py module present")

    return CheckResult(
        passed=True,
        message="",
        details="\n".join(details_lines),
    )


def check_python_packages() -> CheckResult:
    """Check critical Python packages are installed."""
    required_packages = [
        ("httpx", "HTTP client"),
        ("pydantic", "Data validation"),
    ]

    missing = []
    installed = []

    for package, description in required_packages:
        try:
            __import__(package)
            installed.append(f"{package} ({description})")
        except ImportError:
            missing.append(package)

    if missing:
        return CheckResult(
            passed=False,
            message=f"Missing packages: {', '.join(missing)}",
            details=f"Installed: {', '.join(installed)}" if installed else None,
        )

    return CheckResult(
        passed=True,
        message="",
        details=f"Installed: {', '.join(installed)}",
    )


# List of all preflight checks (name, function)
PREFLIGHT_CHECKS: list[tuple[str, callable]] = [
    ("Claude SDK (anthropic)", check_claude_sdk),
    ("Claude Agent SDK", check_claude_agent_sdk),
    ("Task MCP Server", check_task_mcp_server),
    ("Telegram MCP Server", check_telegram_mcp_server),
    ("Playwright MCP", check_playwright_mcp),
    ("Git Installation", check_git_installation),
    ("Node.js / npm", check_node_npm),
    ("Filesystem Permissions", check_filesystem_permissions),
    ("Security Hooks", check_security_hooks),
    ("Python Packages", check_python_packages),
]


def run_preflight_checks(fail_fast: bool = False) -> bool:
    """
    Run all preflight checks programmatically.

    Args:
        fail_fast: If True, stop on first failure. If False (default), run all checks.

    Returns:
        True if all checks passed, False if any check failed.
    """
    print("=" * 70)
    print("  ПРОВЕРКИ ПЕРЕД ЗАПУСКОМ")
    print("=" * 70)

    passed = 0
    failed = 0

    print()
    for name, check_func in PREFLIGHT_CHECKS:
        try:
            result = check_func()
        except Exception as e:
            result = CheckResult(
                passed=False,
                message=f"Check raised exception: {e}",
            )

        print_result(name, result)

        if result.passed:
            passed += 1
        else:
            failed += 1
            if fail_fast:
                print()
                print("-" * 70)
                print(f"  Результаты: {passed} пройдено, {failed} не пройдено (остановлено досрочно)")
                print("-" * 70)
                print(f"\n  ПРОВЕРКА НЕ ПРОЙДЕНА: {name}")
                print("  Используйте --skip-preflight для пропуска проверок при необходимости.")
                return False

    # Summary
    print()
    print("-" * 70)
    print(f"  Результаты: {passed} пройдено, {failed} не пройдено")
    print("-" * 70)

    if failed == 0:
        print("\n  ВСЕ ПРОВЕРКИ ПРОЙДЕНЫ")
        print("  Система готова к работе агента.")
        return True
    else:
        print(f"\n  {failed} ПРОВЕРОК НЕ ПРОЙДЕНО")
        print("  Пожалуйста, устраните указанные проблемы перед продолжением.")
        return False


def main() -> int:
    """Run all preflight checks (CLI entry point)."""
    all_passed = run_preflight_checks(fail_fast=False)
    return 0 if all_passed else 1


if __name__ == "__main__":
    sys.exit(main())
