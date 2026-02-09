"""
Менеджер контекста
==================

Умный выбор контекста, ленивая загрузка и отслеживание бюджета для сессий агента.
Снижает использование токенов при сохранении качества через:
- Извлечение функций на основе AST
- Инкрементальную загрузку контекста
- Мониторинг токенового бюджета
- Автоматическое резюмирование при приближении к лимитам
- Компактный режим при нехватке контекста (ENG-29)
- Плавное завершение при критическом пороге (ENG-29)
- Обрезка вывода инструментов (ENG-29)
"""

import ast
import os
import re
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Callable


# Token estimation: ~4 chars per token for English/code
CHARS_PER_TOKEN = 4

# Default context budget - configurable via MAX_CONTEXT_TOKENS env var
# Default: 180000 for claude-3-5-sonnet (leaves headroom from 200k limit)
DEFAULT_MAX_TOKENS = int(os.environ.get("MAX_CONTEXT_TOKENS", "180000"))

# Warning threshold: 70% - triggers compact mode (ENG-29)
WARNING_THRESHOLD = 0.70

# Critical threshold: 85% - triggers graceful shutdown (ENG-29)
CRITICAL_THRESHOLD = 0.85

# Tool output truncation limits (ENG-29)
TOOL_OUTPUT_MAX_CHARS = 5000
TOOL_OUTPUT_TRUNCATE_FIRST = 2000
TOOL_OUTPUT_TRUNCATE_LAST = 2000
GIT_DIFF_MAX_CHARS = 3000

# Categories for context breakdown
CONTEXT_CATEGORIES = ["system_prompt", "files", "history", "memory", "issue", "tool_outputs"]


class ContextMode:
    """Context mode flags for orchestrator behavior (ENG-29)."""

    NORMAL = "normal"
    COMPACT = "compact"  # 70%+ usage - minimal context
    CRITICAL = "critical"  # 85%+ usage - trigger graceful shutdown


@dataclass
class ContextBudget:
    """Track context usage by category."""

    max_tokens: int = DEFAULT_MAX_TOKENS
    breakdown: dict = field(default_factory=lambda: {
        "system_prompt": 0,
        "files": 0,
        "history": 0,
        "memory": 0,
        "issue": 0,
        "tool_outputs": 0,
    })

    @property
    def total_used(self) -> int:
        """Total tokens used across all categories."""
        return sum(self.breakdown.values())

    @property
    def remaining(self) -> int:
        """Tokens remaining in budget."""
        return max(0, self.max_tokens - self.total_used)

    @property
    def usage_percent(self) -> float:
        """Usage as percentage of max."""
        return (self.total_used / self.max_tokens) * 100

    @property
    def usage_ratio(self) -> float:
        """Usage as decimal ratio (0.0 to 1.0)."""
        return self.total_used / self.max_tokens

    @property
    def is_warning(self) -> bool:
        """True if usage exceeds warning threshold (70%)."""
        return self.usage_ratio >= WARNING_THRESHOLD

    @property
    def is_critical(self) -> bool:
        """True if usage exceeds critical threshold (85%)."""
        return self.usage_ratio >= CRITICAL_THRESHOLD

    @property
    def mode(self) -> str:
        """Get current context mode based on usage (ENG-29)."""
        if self.is_critical:
            return ContextMode.CRITICAL
        elif self.is_warning:
            return ContextMode.COMPACT
        return ContextMode.NORMAL

    def add(self, category: str, tokens: int) -> None:
        """Add tokens to a category."""
        if category in self.breakdown:
            self.breakdown[category] += tokens

    def set(self, category: str, tokens: int) -> None:
        """Set tokens for a category (replaces existing)."""
        if category in self.breakdown:
            self.breakdown[category] = tokens

    def to_dict(self) -> dict:
        """Export as dictionary for API/UI."""
        return {
            "max_tokens": self.max_tokens,
            "total_used": self.total_used,
            "remaining": self.remaining,
            "usage_percent": round(self.usage_percent, 1),
            "usage_ratio": round(self.usage_ratio, 3),
            "is_warning": self.is_warning,
            "is_critical": self.is_critical,
            "mode": self.mode,
            "breakdown": self.breakdown.copy(),
        }

    def format_display(self) -> str:
        """Format for CLI display."""
        bar_width = 30
        filled = int((self.usage_percent / 100) * bar_width)
        bar = "[" + "=" * filled + " " * (bar_width - filled) + "]"

        if self.is_critical:
            status = " CRITICAL"
        elif self.is_warning:
            status = " COMPACT MODE"
        else:
            status = ""

        lines = [
            f"Context Budget: {self.total_used:,} / {self.max_tokens:,} tokens ({self.usage_percent:.1f}%){status}",
            bar,
            "Breakdown:",
        ]
        for cat, tokens in self.breakdown.items():
            if tokens > 0:
                lines.append(f"  {cat}: {tokens:,}")
        return "\n".join(lines)


def estimate_tokens(text: str) -> int:
    """Estimate token count from text."""
    if not text:
        return 0
    return len(text) // CHARS_PER_TOKEN


def truncate_tool_output(output: str, tool_name: str = "") -> tuple[str, bool]:
    """
    Truncate tool output if it exceeds limits (ENG-29).

    Args:
        output: Raw tool output string
        tool_name: Optional tool name for specialized truncation

    Returns:
        Tuple of (truncated_output, was_truncated)
    """
    if not output:
        return output, False

    # Special handling for git diff - show stat + first files
    if tool_name.lower() in ("git", "bash") and "diff" in output.lower():
        return truncate_git_diff(output)

    # Special handling for screenshots - only keep path, not base64
    if "base64" in output.lower() or "data:image" in output.lower():
        return truncate_screenshot_output(output)

    # General truncation for long outputs
    if len(output) <= TOOL_OUTPUT_MAX_CHARS:
        return output, False

    first_part = output[:TOOL_OUTPUT_TRUNCATE_FIRST]
    last_part = output[-TOOL_OUTPUT_TRUNCATE_LAST:]
    truncated_chars = len(output) - TOOL_OUTPUT_TRUNCATE_FIRST - TOOL_OUTPUT_TRUNCATE_LAST

    truncated = (
        f"{first_part}\n\n"
        f"[...truncated {truncated_chars:,} chars, showing first {TOOL_OUTPUT_TRUNCATE_FIRST} and last {TOOL_OUTPUT_TRUNCATE_LAST} chars]\n\n"
        f"{last_part}"
    )

    return truncated, True


def truncate_git_diff(diff_output: str) -> tuple[str, bool]:
    """
    Truncate git diff to show stat + first changed files (ENG-29).

    Args:
        diff_output: Raw git diff output

    Returns:
        Tuple of (truncated_output, was_truncated)
    """
    if len(diff_output) <= GIT_DIFF_MAX_CHARS:
        return diff_output, False

    lines = diff_output.split("\n")
    result_lines = []
    char_count = 0
    file_count = 0
    in_diff = False

    for line in lines:
        # Track diff file headers
        if line.startswith("diff --git"):
            file_count += 1
            in_diff = True

        # Stop if we exceed limit
        if char_count + len(line) > GIT_DIFF_MAX_CHARS - 200:  # Leave room for summary
            break

        result_lines.append(line)
        char_count += len(line) + 1

    total_files = diff_output.count("diff --git")
    remaining = total_files - file_count

    if remaining > 0:
        result_lines.append("")
        result_lines.append(f"[...truncated, showing {file_count}/{total_files} files, {len(diff_output) - char_count:,} more chars]")

    return "\n".join(result_lines), True


def truncate_screenshot_output(output: str) -> tuple[str, bool]:
    """
    Remove base64 image data from screenshot outputs (ENG-29).

    Keeps only the file path, not the embedded image data.

    Args:
        output: Raw output that may contain base64 image data

    Returns:
        Tuple of (cleaned_output, was_truncated)
    """
    import re

    # Pattern to match base64 data URLs
    base64_pattern = r'data:image/[^;]+;base64,[A-Za-z0-9+/=]+'

    # Check if there's base64 data
    if not re.search(base64_pattern, output):
        return output, False

    # Replace base64 data with placeholder
    cleaned = re.sub(
        base64_pattern,
        "[base64 image data removed - see screenshot path]",
        output
    )

    return cleaned, True


def get_compact_issue_context(issue: dict) -> dict:
    """
    Get minimal issue context for compact mode (ENG-29).

    When at 70%+ context usage, orchestrator uses this instead of full issue details.

    Args:
        issue: Full issue dictionary

    Returns:
        Minimal issue dict with only essential fields
    """
    # Only keep: id, title, first line of description
    description = issue.get("description", "")
    first_line = description.split("\n")[0][:100] if description else ""

    return {
        "id": issue.get("id", ""),
        "title": issue.get("title", ""),
        "description": first_line + ("..." if len(description) > 100 else ""),
        "_compact_mode": True,
    }


class FileCache:
    """Cache for parsed file contents and AST."""

    def __init__(self):
        self._content_cache: dict[str, str] = {}
        self._ast_cache: dict[str, ast.Module] = {}
        self._structure_cache: dict[str, dict] = {}

    def get_content(self, file_path: str | Path) -> str | None:
        """Get cached file content."""
        key = str(file_path)
        if key not in self._content_cache:
            path = Path(file_path)
            if path.exists():
                try:
                    self._content_cache[key] = path.read_text()
                except Exception:
                    return None
            else:
                return None
        return self._content_cache[key]

    def get_ast(self, file_path: str | Path) -> ast.Module | None:
        """Get cached AST for Python file."""
        key = str(file_path)
        if key not in self._ast_cache:
            content = self.get_content(file_path)
            if content and str(file_path).endswith(".py"):
                try:
                    self._ast_cache[key] = ast.parse(content)
                except SyntaxError:
                    return None
            else:
                return None
        return self._ast_cache[key]

    def get_structure(self, file_path: str | Path) -> dict | None:
        """Get file structure (classes, functions, etc.)."""
        key = str(file_path)
        if key not in self._structure_cache:
            tree = self.get_ast(file_path)
            if tree:
                self._structure_cache[key] = extract_structure(tree)
            else:
                return None
        return self._structure_cache[key]

    def invalidate(self, file_path: str | Path) -> None:
        """Remove file from all caches."""
        key = str(file_path)
        self._content_cache.pop(key, None)
        self._ast_cache.pop(key, None)
        self._structure_cache.pop(key, None)

    def clear(self) -> None:
        """Clear all caches."""
        self._content_cache.clear()
        self._ast_cache.clear()
        self._structure_cache.clear()


def extract_structure(tree: ast.Module) -> dict:
    """Extract structure from AST (classes, functions, docstrings)."""
    structure = {
        "imports": [],
        "classes": [],
        "functions": [],
        "constants": [],
    }

    for node in ast.iter_child_nodes(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                structure["imports"].append(alias.name)
        elif isinstance(node, ast.ImportFrom):
            module = node.module or ""
            for alias in node.names:
                structure["imports"].append(f"{module}.{alias.name}")
        elif isinstance(node, ast.ClassDef):
            methods = []
            for item in node.body:
                if isinstance(item, ast.FunctionDef | ast.AsyncFunctionDef):
                    methods.append({
                        "name": item.name,
                        "lineno": item.lineno,
                        "end_lineno": item.end_lineno,
                        "docstring": ast.get_docstring(item),
                    })
            structure["classes"].append({
                "name": node.name,
                "lineno": node.lineno,
                "end_lineno": node.end_lineno,
                "docstring": ast.get_docstring(node),
                "methods": methods,
            })
        elif isinstance(node, ast.FunctionDef | ast.AsyncFunctionDef):
            structure["functions"].append({
                "name": node.name,
                "lineno": node.lineno,
                "end_lineno": node.end_lineno,
                "docstring": ast.get_docstring(node),
            })
        elif isinstance(node, ast.Assign):
            for target in node.targets:
                if isinstance(target, ast.Name) and target.id.isupper():
                    structure["constants"].append(target.id)

    return structure


def extract_function(file_path: str | Path, func_name: str, cache: FileCache | None = None) -> str | None:
    """Extract a specific function from a Python file.

    Args:
        file_path: Path to Python file
        func_name: Name of function to extract
        cache: Optional file cache

    Returns:
        Function source code with signature and docstring, or None if not found
    """
    if cache is None:
        cache = FileCache()

    content = cache.get_content(file_path)
    if not content:
        return None

    tree = cache.get_ast(file_path)
    if not tree:
        return None

    lines = content.splitlines()

    for node in ast.walk(tree):
        if isinstance(node, ast.FunctionDef | ast.AsyncFunctionDef):
            if node.name == func_name:
                start = node.lineno - 1
                end = node.end_lineno
                return "\n".join(lines[start:end])
        elif isinstance(node, ast.ClassDef):
            for item in node.body:
                if isinstance(item, ast.FunctionDef | ast.AsyncFunctionDef):
                    if item.name == func_name:
                        start = item.lineno - 1
                        end = item.end_lineno
                        # Include class context
                        class_header = f"class {node.name}:"
                        func_lines = lines[start:end]
                        return f"{class_header}\n    ...\n" + "\n".join(func_lines)

    return None


def extract_class(file_path: str | Path, class_name: str, cache: FileCache | None = None) -> str | None:
    """Extract a specific class from a Python file.

    Args:
        file_path: Path to Python file
        class_name: Name of class to extract
        cache: Optional file cache

    Returns:
        Class source code, or None if not found
    """
    if cache is None:
        cache = FileCache()

    content = cache.get_content(file_path)
    if not content:
        return None

    tree = cache.get_ast(file_path)
    if not tree:
        return None

    lines = content.splitlines()

    for node in ast.walk(tree):
        if isinstance(node, ast.ClassDef) and node.name == class_name:
            start = node.lineno - 1
            end = node.end_lineno
            return "\n".join(lines[start:end])

    return None


def get_file_summary(file_path: str | Path, cache: FileCache | None = None) -> str:
    """Get a summary of file structure without full content.

    Returns compact overview: imports, class/function signatures, constants.
    Much smaller than full file content.
    """
    if cache is None:
        cache = FileCache()

    path = Path(file_path)

    if not path.exists():
        return f"# {path.name} - File not found"

    # For non-Python files, just show first few lines
    if not str(file_path).endswith(".py"):
        content = cache.get_content(file_path)
        if content:
            lines = content.splitlines()[:10]
            summary = "\n".join(lines)
            if len(content.splitlines()) > 10:
                summary += f"\n... ({len(content.splitlines()) - 10} more lines)"
            return f"# {path.name}\n{summary}"
        return f"# {path.name} - Unable to read"

    structure = cache.get_structure(file_path)
    if not structure:
        return f"# {path.name} - Unable to parse"

    lines = [f"# {path.name}"]

    if structure["imports"]:
        lines.append(f"# Imports: {', '.join(structure['imports'][:5])}")
        if len(structure["imports"]) > 5:
            lines.append(f"#   ... and {len(structure['imports']) - 5} more")

    if structure["constants"]:
        lines.append(f"# Constants: {', '.join(structure['constants'])}")

    for cls in structure["classes"]:
        doc = f'  """{cls["docstring"][:50]}..."""' if cls.get("docstring") else ""
        lines.append(f"class {cls['name']}:{doc}")
        for method in cls["methods"]:
            lines.append(f"    def {method['name']}(...)")

    for func in structure["functions"]:
        doc = f'  """{func["docstring"][:50]}..."""' if func.get("docstring") else ""
        lines.append(f"def {func['name']}(...){doc}")

    return "\n".join(lines)


@dataclass
class InterruptedSession:
    """Checkpoint for interrupted session recovery (ENG-29)."""

    interrupted_at: str
    issue_id: str
    step: str
    context_usage_percent: float
    timestamp: str = field(default_factory=lambda: datetime.now().isoformat())

    def to_dict(self) -> dict:
        """Serialize for storage."""
        return {
            "interrupted_at": self.interrupted_at,
            "issue_id": self.issue_id,
            "step": self.step,
            "context_usage_percent": self.context_usage_percent,
            "timestamp": self.timestamp,
        }

    @classmethod
    def from_dict(cls, data: dict) -> "InterruptedSession":
        """Deserialize from storage."""
        return cls(
            interrupted_at=data.get("interrupted_at", "unknown"),
            issue_id=data.get("issue_id", ""),
            step=data.get("step", "unknown"),
            context_usage_percent=data.get("context_usage_percent", 0.0),
            timestamp=data.get("timestamp", datetime.now().isoformat()),
        )


class ContextManager:
    """Manages context loading and budget tracking.

    Enhanced with ENG-29 features:
    - Compact mode at 70% usage
    - Graceful shutdown at 85% usage
    - Tool output truncation
    - Interrupted session checkpointing
    """

    def __init__(self, max_tokens: int = DEFAULT_MAX_TOKENS):
        self.budget = ContextBudget(max_tokens=max_tokens)
        self.cache = FileCache()
        self._loaded_files: set[str] = set()
        self._history: list[dict] = []
        self._current_issue_id: str = ""
        self._current_step: str = ""
        self._interrupted_session: InterruptedSession | None = None

    @property
    def is_compact_mode(self) -> bool:
        """Check if compact mode is active (70%+ usage)."""
        return self.budget.is_warning

    @property
    def is_critical(self) -> bool:
        """Check if critical threshold reached (85%+ usage)."""
        return self.budget.is_critical

    @property
    def mode(self) -> str:
        """Get current context mode."""
        return self.budget.mode

    def set_current_issue(self, issue_id: str) -> None:
        """Set the current issue being worked on."""
        self._current_issue_id = issue_id

    def set_current_step(self, step: str) -> None:
        """Set the current step in the workflow."""
        self._current_step = step

    def track_tool_output(self, tool_name: str, output: str) -> str:
        """
        Track and optionally truncate tool output (ENG-29).

        Args:
            tool_name: Name of the tool
            output: Raw tool output

        Returns:
            Processed (possibly truncated) output
        """
        processed, was_truncated = truncate_tool_output(output, tool_name)
        tokens = estimate_tokens(processed)
        self.budget.add("tool_outputs", tokens)

        if was_truncated:
            print(f"   [Truncated: {len(output):,} -> {len(processed):,} chars]", flush=True)

        return processed

    def create_checkpoint(self) -> InterruptedSession:
        """
        Create a checkpoint for session continuation (ENG-29).

        Called before graceful shutdown at 85% context usage.
        """
        checkpoint = InterruptedSession(
            interrupted_at=f"step_{self._current_step}",
            issue_id=self._current_issue_id,
            step=self._current_step,
            context_usage_percent=round(self.budget.usage_percent, 1),
        )
        self._interrupted_session = checkpoint
        return checkpoint

    def should_trigger_shutdown(self) -> bool:
        """
        Check if graceful shutdown should be triggered (ENG-29).

        Returns True at 85%+ context usage.
        """
        return self.budget.is_critical

    def should_use_compact_mode(self) -> bool:
        """
        Check if compact mode should be used (ENG-29).

        Returns True at 70%+ context usage.
        """
        return self.budget.is_warning

    def get_compact_context_instructions(self) -> str:
        """
        Get instructions for compact mode operation (ENG-29).

        Returns instructions string for orchestrator when in compact mode.
        """
        if not self.is_compact_mode:
            return ""

        return """
## COMPACT MODE ACTIVE (70%+ context usage)

To preserve context budget:
- Use ONLY: issue_id + title + 1-line description
- Do NOT request full issue descriptions
- Do NOT request META issue history
- Pass minimal context to Coding Agent
- Skip verbose logging and explanations
"""

    def load_file(self, file_path: str | Path, full: bool = False) -> str:
        """Load file content with smart selection.

        Args:
            file_path: Path to file
            full: If True, load entire file. If False, load summary for large files.

        Returns:
            File content or summary
        """
        path = Path(file_path)
        key = str(path)

        content = self.cache.get_content(path)
        if not content:
            return f"# {path.name} - Unable to read"

        tokens = estimate_tokens(content)

        # For large files, use summary unless explicitly requested full
        if tokens > 500 and not full:
            summary = get_file_summary(path, self.cache)
            self.budget.add("files", estimate_tokens(summary))
            self._loaded_files.add(key)
            return summary

        self.budget.add("files", tokens)
        self._loaded_files.add(key)
        return content

    def load_function(self, file_path: str | Path, func_name: str) -> str:
        """Load a specific function from a file.

        More efficient than loading entire file when only one function needed.
        """
        result = extract_function(file_path, func_name, self.cache)
        if result:
            self.budget.add("files", estimate_tokens(result))
            return result
        return f"# Function {func_name} not found in {file_path}"

    def load_class(self, file_path: str | Path, class_name: str) -> str:
        """Load a specific class from a file."""
        result = extract_class(file_path, class_name, self.cache)
        if result:
            self.budget.add("files", estimate_tokens(result))
            return result
        return f"# Class {class_name} not found in {file_path}"

    def set_system_prompt(self, prompt: str) -> None:
        """Register system prompt tokens."""
        self.budget.set("system_prompt", estimate_tokens(prompt))

    def set_issue_context(self, issue: dict | str) -> None:
        """Register issue context tokens."""
        if isinstance(issue, dict):
            text = str(issue)
        else:
            text = issue
        self.budget.set("issue", estimate_tokens(text))

    def add_to_history(self, role: str, content: str) -> None:
        """Add message to history and update budget."""
        self._history.append({"role": role, "content": content})
        self.budget.add("history", estimate_tokens(content))

    def summarize_history(self, keep_recent: int = 5) -> list[dict]:
        """Summarize older history to save tokens.

        Keeps recent messages intact, summarizes older ones.
        """
        if len(self._history) <= keep_recent:
            return self._history

        old = self._history[:-keep_recent]
        recent = self._history[-keep_recent:]

        # Simple summary: count messages and key actions
        summary = f"[Previous {len(old)} messages summarized: "
        actions = []
        for msg in old:
            content = msg.get("content", "")
            if "commit" in content.lower():
                actions.append("commit")
            elif "test" in content.lower():
                actions.append("test")
            elif "implement" in content.lower():
                actions.append("implement")
        if actions:
            summary += ", ".join(set(actions))
        else:
            summary += "general discussion"
        summary += "]"

        # Recalculate history budget
        new_history = [{"role": "system", "content": summary}] + recent
        history_tokens = sum(estimate_tokens(m.get("content", "")) for m in new_history)
        self.budget.set("history", history_tokens)

        self._history = new_history
        return new_history

    def should_summarize(self) -> bool:
        """Check if we should summarize to save context."""
        return self.budget.is_warning

    def get_stats(self) -> dict:
        """Get current context statistics."""
        stats = {
            **self.budget.to_dict(),
            "files_loaded": len(self._loaded_files),
            "history_messages": len(self._history),
            "current_issue_id": self._current_issue_id,
            "current_step": self._current_step,
        }

        if self._interrupted_session:
            stats["interrupted_session"] = self._interrupted_session.to_dict()

        return stats

    def prepare_graceful_shutdown(self, memory_path: Path | None = None) -> dict:
        """
        Prepare for graceful shutdown at 85% context (ENG-29).

        Steps:
        1. Create checkpoint
        2. Write interrupted session info to memory
        3. Return shutdown info for session state

        Args:
            memory_path: Path to memory file for flushing context

        Returns:
            Dict with shutdown info for session continuation
        """
        checkpoint = self.create_checkpoint()

        shutdown_info = {
            "reason": "context_limit_85_percent",
            "checkpoint": checkpoint.to_dict(),
            "context_stats": self.get_stats(),
            "recommendation": "Continue in next session with this checkpoint",
        }

        # Append to memory file if provided
        if memory_path and memory_path.exists():
            try:
                memory_content = memory_path.read_text()
                checkpoint_note = f"""

---

### Context Limit Shutdown ({checkpoint.timestamp})
- Issue: {checkpoint.issue_id}
- Interrupted at: {checkpoint.interrupted_at}
- Context usage: {checkpoint.context_usage_percent}%
- **Resume from step: {checkpoint.step}**
"""
                memory_path.write_text(memory_content + checkpoint_note)
            except IOError:
                pass  # Non-critical, continue with shutdown

        return shutdown_info

    def load_interrupted_session(self, session_data: dict) -> InterruptedSession | None:
        """
        Load interrupted session checkpoint for continuation (ENG-29).

        Args:
            session_data: Data from session_state.json

        Returns:
            InterruptedSession if found, None otherwise
        """
        if "checkpoint" in session_data:
            self._interrupted_session = InterruptedSession.from_dict(session_data["checkpoint"])
            return self._interrupted_session
        return None

    def reset(self) -> None:
        """Reset manager state for new session."""
        self.budget = ContextBudget(max_tokens=self.budget.max_tokens)
        self._loaded_files.clear()
        self._history.clear()
        self._current_issue_id = ""
        self._current_step = ""
        # Keep cache for efficiency across sessions
        # Keep interrupted_session for continuation


# Global instance for convenience
_global_manager: ContextManager | None = None


def get_context_manager() -> ContextManager:
    """Get or create global context manager."""
    global _global_manager
    if _global_manager is None:
        _global_manager = ContextManager()
    return _global_manager


def reset_context_manager() -> None:
    """Reset global context manager."""
    global _global_manager
    if _global_manager:
        _global_manager.reset()
