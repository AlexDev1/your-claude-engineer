"""
Prompt Loading Utilities
========================

Functions for loading prompt templates from the prompts directory.
"""

from pathlib import Path


PROMPTS_DIR: Path = Path(__file__).parent / "prompts"


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
