"""
Prompt Loading Utilities
========================

Functions for loading prompt templates from the prompts directory.
Supports loading persistent agent memory from .agent/MEMORY.md.
Supports loading project map from .agent/PROJECT_MAP.md (ENG-33).
Integrates with context_manager for token budget tracking.
"""

from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from context_manager import ContextManager


PROMPTS_DIR: Path = Path(__file__).parent / "prompts"
AGENT_DIR: Path = Path(__file__).parent / ".agent"


def load_prompt(name: str) -> str:
    """
    Load a prompt template from the prompts directory.

    Args:
        name: Prompt name (without .md extension)

    Returns:
        Prompt text content

    Raises:
        FileNotFoundError: If prompt file doesn't exist
        IOError: If prompt file cannot be read
    """
    prompt_path: Path = PROMPTS_DIR / f"{name}.md"

    if not prompt_path.exists():
        raise FileNotFoundError(
            f"Prompt file not found: {prompt_path}\n"
            f"Expected prompts directory: {PROMPTS_DIR}\n"
            f"This may indicate an incomplete installation."
        )

    try:
        return prompt_path.read_text()
    except IOError as e:
        raise IOError(
            f"Failed to read prompt file {prompt_path}: {e}\n"
            f"Check file permissions."
        ) from e


def get_execute_task(team: str) -> str:
    """
    Get the task message for executing the next task.

    Args:
        team: Team key (e.g., "ENG")

    Returns:
        Task message with team and cwd substituted
    """
    template = load_prompt("execute_task")
    return template.format(team=team, cwd=Path.cwd())


def get_continuation_task(team: str) -> str:
    """
    Get the continuation task message for resuming work.

    This prompt instructs the orchestrator to check previous session context
    from the META issue before picking up work.

    Args:
        team: Team key (e.g., "ENG")

    Returns:
        Continuation task message with team and cwd substituted
    """
    template = load_prompt("continuation_task")
    return template.format(team=team, cwd=Path.cwd())


def load_agent_memory(project_dir: Path | None = None) -> str:
    """
    Load the agent memory file (.agent/MEMORY.md) if it exists.

    The memory file contains curated facts learned across sessions,
    including discovered patterns, known issues, and project-specific context.

    Args:
        project_dir: Project directory to look for .agent/MEMORY.md.
                     If None, uses the module's parent directory.

    Returns:
        Contents of MEMORY.md, or empty string if file doesn't exist.
    """
    if project_dir is None:
        agent_dir = AGENT_DIR
    else:
        agent_dir = project_dir / ".agent"

    memory_path = agent_dir / "MEMORY.md"

    if not memory_path.exists():
        return ""

    try:
        return memory_path.read_text()
    except IOError:
        # Fail silently - memory is optional
        return ""


def load_agent_soul(project_dir: Path | None = None) -> str:
    """
    Load the agent soul file (.agent/SOUL.md) if it exists.

    The soul file defines immutable identity, preferences, and principles
    for the coding agent. It is included in the system prompt.

    Args:
        project_dir: Project directory to look for .agent/SOUL.md.
                     If None, uses the module's parent directory.

    Returns:
        Contents of SOUL.md, or empty string if file doesn't exist.
    """
    if project_dir is None:
        agent_dir = AGENT_DIR
    else:
        agent_dir = project_dir / ".agent"

    soul_path = agent_dir / "SOUL.md"

    if not soul_path.exists():
        return ""

    try:
        return soul_path.read_text()
    except IOError:
        # Fail silently - soul is optional
        return ""


def load_project_map(project_dir: Path | None = None) -> str:
    """
    Load the project map file (.agent/PROJECT_MAP.md) if it exists.

    The project map contains auto-generated project structure, dependencies,
    ports, recent commits, and import graph (ENG-33).

    Args:
        project_dir: Project directory to look for .agent/PROJECT_MAP.md.
                     If None, uses the module's parent directory.

    Returns:
        Contents of PROJECT_MAP.md, or empty string if file doesn't exist.
    """
    if project_dir is None:
        agent_dir = AGENT_DIR
    else:
        agent_dir = project_dir / ".agent"

    map_path = agent_dir / "PROJECT_MAP.md"

    if not map_path.exists():
        return ""

    try:
        return map_path.read_text()
    except IOError:
        # Fail silently - project map is optional
        return ""


def ensure_project_map(project_dir: Path | None = None) -> str:
    """
    Ensure project map exists, generating it if needed.

    This function checks if PROJECT_MAP.md exists and generates it
    if missing or stale (older than 1 hour).

    Args:
        project_dir: Project directory

    Returns:
        Contents of PROJECT_MAP.md
    """
    import subprocess
    import time

    if project_dir is None:
        project_dir = Path(__file__).parent

    agent_dir = project_dir / ".agent"
    map_path = agent_dir / "PROJECT_MAP.md"

    # Check if map needs regeneration
    should_generate = False

    if not map_path.exists():
        should_generate = True
    else:
        # Check if stale (older than 1 hour)
        mtime = map_path.stat().st_mtime
        age_hours = (time.time() - mtime) / 3600
        if age_hours > 1:
            should_generate = True

    if should_generate:
        # Try to generate the map
        script_path = project_dir / "scripts" / "generate_project_map.py"
        if script_path.exists():
            try:
                subprocess.run(
                    ["python", str(script_path), str(project_dir)],
                    capture_output=True,
                    timeout=30,
                )
            except (subprocess.TimeoutExpired, FileNotFoundError):
                pass

    return load_project_map(project_dir)


def get_execute_task_with_memory(team: str, project_dir: Path | None = None) -> str:
    """
    Get the task message with memory and project map context loaded.

    Args:
        team: Team key (e.g., "ENG")
        project_dir: Project directory for .agent/MEMORY.md and .agent/PROJECT_MAP.md

    Returns:
        Task message with team, cwd, memory, and project map context
    """
    template = load_prompt("execute_task")
    base_prompt = template.format(team=team, cwd=Path.cwd())

    sections = []

    # Load project map first (ENG-33)
    project_map = ensure_project_map(project_dir)
    if project_map:
        sections.append(f"## Project Map (from .agent/PROJECT_MAP.md)\n\n{project_map}")

    # Then load memory
    memory = load_agent_memory(project_dir)
    if memory:
        sections.append(f"## Agent Memory (from .agent/MEMORY.md)\n\n{memory}")

    if sections:
        return base_prompt + "\n\n---\n\n" + "\n\n---\n\n".join(sections)

    return base_prompt


def get_continuation_task_with_memory(team: str, project_dir: Path | None = None) -> str:
    """
    Get the continuation task message with memory and project map context loaded.

    Args:
        team: Team key (e.g., "ENG")
        project_dir: Project directory for .agent/MEMORY.md and .agent/PROJECT_MAP.md

    Returns:
        Continuation task message with team, cwd, memory, and project map context
    """
    template = load_prompt("continuation_task")
    base_prompt = template.format(team=team, cwd=Path.cwd())

    sections = []

    # Load project map first (ENG-33)
    project_map = ensure_project_map(project_dir)
    if project_map:
        sections.append(f"## Project Map (from .agent/PROJECT_MAP.md)\n\n{project_map}")

    # Then load memory
    memory = load_agent_memory(project_dir)
    if memory:
        sections.append(f"## Agent Memory (from .agent/MEMORY.md)\n\n{memory}")

    if sections:
        return base_prompt + "\n\n---\n\n" + "\n\n---\n\n".join(sections)

    return base_prompt


def get_prompt_with_context_tracking(
    prompt_name: str,
    context_manager: "ContextManager | None" = None,
    **format_kwargs,
) -> str:
    """
    Load prompt and track tokens in context manager.

    Args:
        prompt_name: Name of prompt template
        context_manager: Optional context manager for tracking
        **format_kwargs: Format arguments for template

    Returns:
        Formatted prompt text
    """
    template = load_prompt(prompt_name)
    prompt = template.format(**format_kwargs) if format_kwargs else template

    if context_manager:
        from context_manager import estimate_tokens
        context_manager.budget.add("system_prompt", estimate_tokens(prompt))

    return prompt


def get_all_prompt_stats() -> dict:
    """
    Get token statistics for all prompts.

    Returns:
        Dictionary with prompt names and their token counts
    """
    from context_manager import estimate_tokens

    stats = {}
    total = 0

    for prompt_file in PROMPTS_DIR.glob("*.md"):
        content = prompt_file.read_text()
        tokens = estimate_tokens(content)
        stats[prompt_file.stem] = {
            "chars": len(content),
            "tokens": tokens,
        }
        total += tokens

    stats["_total"] = {"tokens": total}
    return stats
