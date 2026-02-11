"""
Security хуки для автономного агента разработки
===============================================

Pre-tool-use хуки, которые проверяют bash команды для безопасности.
Использует подход allowlist - только явно разрешённые команды могут выполняться.
"""

import os
import re
import shlex
from typing import Any, NamedTuple

from claude_agent_sdk import PreToolUseHookInput
from claude_agent_sdk.types import HookContext, SyncHookJSONOutput


class ValidationResult(NamedTuple):
    """Результат валидации команды."""

    allowed: bool
    reason: str = ""




# Разрешённые команды для задач разработки
# Минимальный набор, необходимый для автономной демонстрации разработки
ALLOWED_COMMANDS: set[str] = {
    # Инспекция файлов
    "ls",
    "cat",
    "head",
    "tail",
    "wc",
    "grep",
    "find",
    # Файловые операции (агент использует SDK инструменты для большинства файловых операций, но эти нужны иногда)
    "cp",
    "mv",
    "mkdir",
    "rm",  # Для очистки; валидируется отдельно для предотвращения опасных операций
    "touch",
    "chmod",  # Для делания скриптов исполняемыми; валидируется отдельно
    "unzip",  # Для извлечения архивов (например, бинарные файлы браузера для Playwright)
    # Навигация по директориям
    "pwd",
    "cd",
    # Текстовый вывод
    "echo",
    "printf",
    # HTTP/Сеть (для тестирования эндпоинтов)
    "curl",
    # Инспекция окружения
    "which",
    "env",
    # Python (для скриптов создания файлов)
    "python",
    "python3",
    # Node.js разработка
    "npm",
    "npx",
    "node",
    # Контроль версий
    "git",
    # Управление процессами
    "ps",
    "lsof",
    "sleep",
    "pkill",  # Для завершения dev серверов; валидируется отдельно
    # Выполнение скриптов
    "init.sh",  # Init скрипты; валидируется отдельно
    # Инструменты качества кода (ENG-19)
    "tsc",  # TypeScript type checker (npx tsc --noEmit)
    "eslint",  # JavaScript/TypeScript linter (npx eslint)
    "ruff",  # Python linter (ruff check)
    "mypy",  # Python type checker
    "black",  # Python formatter
    "prettier",  # JS/TS/CSS formatter
    "check-complexity.sh",  # Скрипт защиты от сложности; валидируется отдельно
    "lint-gate.sh",  # Post-commit linting gate; валидируется отдельно
    # Shell интерпретаторы (для запуска скриптов)
    "bash",  # Для запуска shell скриптов
    "sh",  # Для запуска shell скриптов
}

# Команды, требующие дополнительной валидации, даже когда в allowlist
COMMANDS_NEEDING_EXTRA_VALIDATION: set[str] = {
    "pkill",
    "chmod",
    "init.sh",
    "rm",
    "git",
    "check-complexity.sh",
    "lint-gate.sh",
}


def split_command_segments(command_string: str) -> list[str]:
    """
    Разбивает составную команду на отдельные сегменты команд.

    Обрабатывает операторы цепочки команд (&&, ||, ;). Pipes обрабатываются отдельно
    функцией extract_commands(), которая парсит токены внутри каждого сегмента и трактует
    "|" как указание на следующую команду.

    Примечание: Разбиение по точке с запятой использует простой regex паттерн, который может
    не обрабатывать корректно все крайние случаи с вложенными кавычками. Для валидации
    безопасности это допустимо, так как неправильные команды не будут распарсены и будут заблокированы.

    Args:
        command_string: Полная shell команда

    Returns:
        Список отдельных сегментов команд
    """
    # Split on && and || while preserving the ability to handle each segment
    # This regex splits on && or || that aren't inside quotes
    segments: list[str] = re.split(r"\s*(?:&&|\|\|)\s*", command_string)

    # Further split on semicolons
    result: list[str] = []
    for segment in segments:
        sub_segments: list[str] = re.split(r'(?<!["\'])\s*;\s*(?!["\'])', segment)
        for sub in sub_segments:
            sub = sub.strip()
            if sub:
                result.append(sub)

    return result


def extract_commands(command_string: str) -> list[str]:
    """
    Извлекает имена команд из строки shell команды.

    Обрабатывает pipes, цепочки команд (&&, ||, ;) и subshells.
    Возвращает базовые имена команд (без путей).

    Args:
        command_string: Полная shell команда

    Returns:
        Список имён команд, найденных в строке
    """
    commands: list[str] = []

    # shlex doesn't treat ; as a separator, so we need to pre-process
    # Split on semicolons that aren't inside quotes (simple heuristic)
    # This handles common cases like "echo hello; ls"
    segments: list[str] = re.split(r'(?<!["\'])\s*;\s*(?!["\'])', command_string)

    for segment in segments:
        segment = segment.strip()
        if not segment:
            continue

        try:
            tokens: list[str] = shlex.split(segment)
        except ValueError:
            # Malformed command (unclosed quotes, etc.)
            # Return empty to trigger block (fail-safe)
            return []

        if not tokens:
            continue

        # Track when we expect a command vs arguments
        expect_command: bool = True

        for token in tokens:
            # Shell operators indicate a new command follows
            if token in ("|", "||", "&&", "&"):
                expect_command = True
                continue

            # Skip shell keywords that precede commands
            if token in (
                "if",
                "then",
                "else",
                "elif",
                "fi",
                "for",
                "while",
                "until",
                "do",
                "done",
                "case",
                "esac",
                "in",
                "!",
                "{",
                "}",
            ):
                continue

            # Skip flags/options
            if token.startswith("-"):
                continue

            # Skip variable assignments (VAR=value)
            if "=" in token and not token.startswith("="):
                continue

            if expect_command:
                # Extract the base command name (handle paths like /usr/bin/python)
                cmd: str = os.path.basename(token)
                commands.append(cmd)
                expect_command = False

    return commands


def validate_pkill_command(command_string: str) -> ValidationResult:
    """
    Validate pkill commands - only allow killing dev-related processes.

    Uses shlex to parse the command, avoiding regex bypass vulnerabilities.

    Args:
        command_string: The pkill command to validate

    Returns:
        ValidationResult with allowed status and reason if blocked
    """
    # Allowed process names for pkill
    allowed_process_names: set[str] = {
        "node",
        "npm",
        "npx",
        "vite",
        "next",
    }

    try:
        tokens: list[str] = shlex.split(command_string)
    except ValueError:
        return ValidationResult(allowed=False, reason="Could not parse pkill command")

    if not tokens:
        return ValidationResult(allowed=False, reason="Empty pkill command")

    # Separate flags from arguments
    args: list[str] = []
    for token in tokens[1:]:
        if not token.startswith("-"):
            args.append(token)

    if not args:
        return ValidationResult(allowed=False, reason="pkill requires a process name")

    # The target is typically the last non-flag argument
    target: str = args[-1]

    # For -f flag (full command line match), extract the first word as process name
    # e.g., "pkill -f 'node server.js'" -> target is "node server.js", process is "node"
    if " " in target:
        target = target.split()[0]

    if target in allowed_process_names:
        return ValidationResult(allowed=True)
    return ValidationResult(
        allowed=False,
        reason=f"pkill only allowed for dev processes: {allowed_process_names}",
    )


def validate_chmod_command(command_string: str) -> ValidationResult:
    """
    Validate chmod commands - only allow making files executable with +x.

    Args:
        command_string: The chmod command to validate

    Returns:
        ValidationResult with allowed status and reason if blocked
    """
    try:
        tokens: list[str] = shlex.split(command_string)
    except ValueError:
        return ValidationResult(allowed=False, reason="Could not parse chmod command")

    if not tokens or tokens[0] != "chmod":
        return ValidationResult(allowed=False, reason="Not a chmod command")

    # Look for the mode argument
    # Valid modes: +x, u+x, a+x, etc. (anything ending with +x for execute permission)
    mode: str | None = None
    files: list[str] = []

    for token in tokens[1:]:
        if token.startswith("-"):
            # Skip flags like -R (we don't allow recursive chmod anyway)
            return ValidationResult(allowed=False, reason="chmod flags are not allowed")
        elif mode is None:
            mode = token
        else:
            files.append(token)

    if mode is None:
        return ValidationResult(allowed=False, reason="chmod requires a mode")

    if not files:
        return ValidationResult(
            allowed=False, reason="chmod requires at least one file"
        )

    # Only allow +x variants (making files executable)
    # This matches: +x, u+x, g+x, o+x, a+x, ug+x, etc.
    if not re.match(r"^[ugoa]*\+x$", mode):
        return ValidationResult(
            allowed=False, reason=f"chmod only allowed with +x mode, got: {mode}"
        )

    return ValidationResult(allowed=True)


def validate_init_script(command_string: str) -> ValidationResult:
    """
    Validate init.sh script execution - only allow ./init.sh.

    Args:
        command_string: The init script command to validate

    Returns:
        ValidationResult with allowed status and reason if blocked
    """
    try:
        tokens: list[str] = shlex.split(command_string)
    except ValueError:
        return ValidationResult(
            allowed=False, reason="Could not parse init script command"
        )

    if not tokens:
        return ValidationResult(allowed=False, reason="Empty command")

    # The command should be exactly ./init.sh (possibly with arguments)
    script: str = tokens[0]

    # Allow ./init.sh or paths ending in /init.sh
    if script == "./init.sh" or script.endswith("/init.sh"):
        return ValidationResult(allowed=True)

    return ValidationResult(
        allowed=False, reason=f"Only ./init.sh is allowed, got: {script}"
    )


def validate_git_command(command_string: str) -> ValidationResult:
    """
    Validate git commands - allow safe operations, block dangerous ones.

    Blocked:
    - git push --force to main/master (dangerous)
    - git reset --hard (can destroy work)
    - git clean -f (can destroy work)
    - git checkout . (discards all changes)
    - git restore . (discards all changes)

    Allowed:
    - All other git commands including push (for GitHub integration)

    Args:
        command_string: The git command to validate

    Returns:
        ValidationResult with allowed status and reason if blocked
    """
    try:
        tokens: list[str] = shlex.split(command_string)
    except ValueError:
        return ValidationResult(allowed=False, reason="Could not parse git command")

    if not tokens or tokens[0] != "git":
        return ValidationResult(allowed=False, reason="Not a git command")

    # Get the git subcommand
    if len(tokens) < 2:
        return ValidationResult(allowed=True)  # Just "git" is harmless

    subcommand: str = tokens[1]

    # Block dangerous operations
    if subcommand == "push":
        # Check for force push to main/master
        has_force = "--force" in tokens or "-f" in tokens
        targets_main = "main" in tokens or "master" in tokens

        if has_force and targets_main:
            return ValidationResult(
                allowed=False,
                reason="Force push to main/master is not allowed",
            )

    elif subcommand == "reset":
        if "--hard" in tokens:
            return ValidationResult(
                allowed=False,
                reason="git reset --hard is not allowed (can destroy work)",
            )

    elif subcommand == "clean":
        if "-f" in tokens or "--force" in tokens:
            return ValidationResult(
                allowed=False,
                reason="git clean -f is not allowed (can destroy untracked files)",
            )

    elif subcommand == "checkout":
        # Block "git checkout ." which discards all changes
        if "." in tokens:
            # Check if it's just "git checkout ." without a branch/file
            non_flag_args = [t for t in tokens[2:] if not t.startswith("-")]
            if non_flag_args == ["."]:
                return ValidationResult(
                    allowed=False,
                    reason="git checkout . is not allowed (discards all changes)",
                )

    elif subcommand == "restore":
        # Block "git restore ." which discards all changes
        if "." in tokens:
            non_flag_args = [t for t in tokens[2:] if not t.startswith("-")]
            if non_flag_args == ["."]:
                return ValidationResult(
                    allowed=False,
                    reason="git restore . is not allowed (discards all changes)",
                )

    elif subcommand == "branch":
        # Block git branch -D (force delete)
        if "-D" in tokens:
            # Allow if it's an agent branch
            agent_branch = False
            for token in tokens:
                if token.startswith("agent/"):
                    agent_branch = True
                    break
            if not agent_branch:
                return ValidationResult(
                    allowed=False,
                    reason="git branch -D is only allowed for agent/* branches",
                )

    # All other git commands are allowed
    return ValidationResult(allowed=True)


def validate_rm_command(command_string: str) -> ValidationResult:
    """
    Validate rm commands - prevent dangerous deletions.

    Blocks:
    - rm on system directories (/, /etc, /usr, /var, /home, /Users, etc.)
    - rm -rf with wildcards on sensitive paths

    Allows:
    - rm on project files, temp directories, node_modules, etc.

    Args:
        command_string: The rm command to validate

    Returns:
        ValidationResult with allowed status and reason if blocked
    """
    # Dangerous root paths that should never be deleted
    dangerous_paths: set[str] = {
        "/",
        "/etc",
        "/usr",
        "/var",
        "/bin",
        "/sbin",
        "/lib",
        "/opt",
        "/boot",
        "/root",
        "/home",
        "/Users",
        "/System",
        "/Library",
        "/Applications",
        "/private",
        "~",
    }

    try:
        tokens: list[str] = shlex.split(command_string)
    except ValueError:
        return ValidationResult(allowed=False, reason="Could not parse rm command")

    if not tokens or tokens[0] != "rm":
        return ValidationResult(allowed=False, reason="Not an rm command")

    # Collect flags and paths
    flags: list[str] = []
    paths: list[str] = []

    for token in tokens[1:]:
        if token.startswith("-"):
            flags.append(token)
        else:
            paths.append(token)

    if not paths:
        return ValidationResult(allowed=False, reason="rm requires at least one path")

    # Check each path for dangerous patterns
    for path in paths:
        # Normalize the path for comparison
        # Special case: "/" should remain "/" after normalization (rstrip("/") on "/" returns "")
        normalized = path.rstrip("/") or "/"

        # Block exact matches to dangerous paths
        if normalized in dangerous_paths:
            return ValidationResult(
                allowed=False,
                reason=f"rm on system directory '{path}' is not allowed",
            )

        # Block paths that start with dangerous roots (but allow subdirs of project paths)
        for dangerous in dangerous_paths:
            if dangerous == "/":
                continue  # Skip root, check separately
            # Block if path IS the dangerous path or is directly under it without much depth
            # e.g., block /Users but allow /Users/rasmus/projects/my-project/node_modules
            if normalized == dangerous or (
                normalized.startswith(dangerous + "/")
                and normalized.count("/") <= dangerous.count("/") + 1
            ):
                return ValidationResult(
                    allowed=False,
                    reason=f"rm too close to system directory '{dangerous}' is not allowed",
                )

        # Block rm /* patterns (removing everything in root)
        if path == "/*" or path.startswith("/*"):
            return ValidationResult(
                allowed=False, reason="rm on root wildcard is not allowed"
            )

    return ValidationResult(allowed=True)


def validate_lint_script(command_string: str) -> ValidationResult:
    """
    Validate lint-gate.sh and check-complexity.sh script execution.

    Only allow execution from scripts/ directory with safe arguments.

    Args:
        command_string: The script command to validate

    Returns:
        ValidationResult with allowed status and reason if blocked
    """
    try:
        tokens: list[str] = shlex.split(command_string)
    except ValueError:
        return ValidationResult(
            allowed=False, reason="Could not parse lint script command"
        )

    if not tokens:
        return ValidationResult(allowed=False, reason="Empty command")

    script: str = tokens[0]

    # Allow ./scripts/lint-gate.sh, scripts/lint-gate.sh, or absolute paths ending in scripts/lint-gate.sh
    # Same for check-complexity.sh
    allowed_scripts = ("lint-gate.sh", "check-complexity.sh")

    script_name = os.path.basename(script)
    if script_name not in allowed_scripts:
        return ValidationResult(
            allowed=False,
            reason=f"Only lint-gate.sh and check-complexity.sh are allowed, got: {script}",
        )

    # Ensure it's from scripts directory or current directory
    if script.startswith("./scripts/") or script.startswith("scripts/"):
        return ValidationResult(allowed=True)
    if "/scripts/" in script and script.endswith(script_name):
        return ValidationResult(allowed=True)
    if script == f"./{script_name}" or script == script_name:
        return ValidationResult(allowed=True)

    return ValidationResult(
        allowed=False,
        reason=f"Script must be run from scripts/ directory: {script}",
    )


def get_command_for_validation(cmd: str, segments: list[str]) -> str:
    """
    Find the specific command segment that contains the given command.

    Args:
        cmd: The command name to find
        segments: List of command segments

    Returns:
        The segment containing the command, or empty string if not found
    """
    for segment in segments:
        segment_commands: list[str] = extract_commands(segment)
        if cmd in segment_commands:
            return segment
    return ""


async def bash_security_hook(
    input_data: PreToolUseHookInput,
    tool_use_id: str | None = None,
    context: HookContext | None = None,
) -> SyncHookJSONOutput:
    """
    Pre-tool-use хук, который валидирует bash команды с использованием allowlist.

    Только команды из ALLOWED_COMMANDS разрешены.

    Args:
        input_data: Словарь, содержащий tool_name и tool_input
        tool_use_id: Опциональный ID использования инструмента
        context: Опциональный контекст

    Returns:
        Пустой словарь для разрешения или словарь с decision='block' для блокировки
    """
    if input_data.get("tool_name") != "Bash":
        return {}

    command: str = input_data.get("tool_input", {}).get("command", "")
    if not command:
        return {}

    # Extract all commands from the command string
    commands: list[str] = extract_commands(command)

    if not commands:
        # Could not parse - fail safe by blocking
        return SyncHookJSONOutput(
            decision="block",
            reason=f"Could not parse command for security validation: {command}",
        )

    # Split into segments for per-command validation
    segments: list[str] = split_command_segments(command)

    # Check each command against the allowlist
    for cmd in commands:
        if cmd not in ALLOWED_COMMANDS:
            return SyncHookJSONOutput(
                decision="block",
                reason=f"Command '{cmd}' is not in the allowed commands list",
            )

        # Additional validation for sensitive commands
        if cmd in COMMANDS_NEEDING_EXTRA_VALIDATION:
            # Find the specific segment containing this command
            cmd_segment: str = get_command_for_validation(cmd, segments)
            if not cmd_segment:
                cmd_segment = command  # Fallback to full command

            if cmd == "pkill":
                result: ValidationResult = validate_pkill_command(cmd_segment)
                if not result.allowed:
                    return SyncHookJSONOutput(decision="block", reason=result.reason)
            elif cmd == "chmod":
                result = validate_chmod_command(cmd_segment)
                if not result.allowed:
                    return SyncHookJSONOutput(decision="block", reason=result.reason)
            elif cmd == "init.sh":
                result = validate_init_script(cmd_segment)
                if not result.allowed:
                    return SyncHookJSONOutput(decision="block", reason=result.reason)
            elif cmd == "rm":
                result = validate_rm_command(cmd_segment)
                if not result.allowed:
                    return SyncHookJSONOutput(decision="block", reason=result.reason)
            elif cmd == "git":
                result = validate_git_command(cmd_segment)
                if not result.allowed:
                    return SyncHookJSONOutput(decision="block", reason=result.reason)
            elif cmd in ("check-complexity.sh", "lint-gate.sh"):
                result = validate_lint_script(cmd_segment)
                if not result.allowed:
                    return SyncHookJSONOutput(decision="block", reason=result.reason)

    return {}
