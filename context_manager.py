"""
Context Manager
================

Smart context selection, lazy loading, and budget tracking for agent sessions.
Reduces token usage while maintaining quality through:
- AST-based function extraction
- Incremental context loading
- Token budget monitoring
- Auto-summarization when approaching limits
"""

import ast
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable


# Token estimation: ~4 chars per token for English/code
CHARS_PER_TOKEN = 4

# Default context budget (Claude's context window)
DEFAULT_MAX_TOKENS = 200_000

# Warning threshold as percentage of max
WARNING_THRESHOLD = 0.8

# Categories for context breakdown
CONTEXT_CATEGORIES = ["system_prompt", "files", "history", "memory", "issue"]


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
    def is_warning(self) -> bool:
        """True if usage exceeds warning threshold."""
        return self.total_used >= (self.max_tokens * WARNING_THRESHOLD)

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
            "is_warning": self.is_warning,
            "breakdown": self.breakdown.copy(),
        }

    def format_display(self) -> str:
        """Format for CLI display."""
        bar_width = 30
        filled = int((self.usage_percent / 100) * bar_width)
        bar = "[" + "=" * filled + " " * (bar_width - filled) + "]"

        status = " WARNING" if self.is_warning else ""
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


class ContextManager:
    """Manages context loading and budget tracking."""

    def __init__(self, max_tokens: int = DEFAULT_MAX_TOKENS):
        self.budget = ContextBudget(max_tokens=max_tokens)
        self.cache = FileCache()
        self._loaded_files: set[str] = set()
        self._history: list[dict] = []

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
        return {
            **self.budget.to_dict(),
            "files_loaded": len(self._loaded_files),
            "history_messages": len(self._history),
        }

    def reset(self) -> None:
        """Reset manager state for new session."""
        self.budget = ContextBudget(max_tokens=self.budget.max_tokens)
        self._loaded_files.clear()
        self._history.clear()
        # Keep cache for efficiency across sessions


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
