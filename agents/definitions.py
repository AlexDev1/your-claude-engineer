"""
Agent Definitions
=================

Specialized agent configurations using Claude Agent SDK's AgentDefinition.
Model selection is configurable via environment variables.

Agents:
- task: Manages tasks, projects, and session tracking (replaces Linear)
- coding: Writes code, tests with Playwright, handles git operations
- telegram: Sends notifications via Telegram (replaces Slack)
"""

import os
from pathlib import Path
from typing import Final, Literal, TypeGuard

from claude_agent_sdk.types import AgentDefinition

from mcp_config import (
    get_task_tools,
    get_telegram_tools,
    get_coding_tools,
)

# File tools needed by multiple agents
FILE_TOOLS: list[str] = ["Read", "Write", "Edit", "Glob"]

PROMPTS_DIR = Path(__file__).parent.parent / "prompts"

# Valid model options for AgentDefinition
ModelOption = Literal["haiku", "sonnet", "opus", "inherit"]

# Valid model values as a tuple for runtime validation
_VALID_MODELS: Final[tuple[str, ...]] = ("haiku", "sonnet", "opus", "inherit")

# Default models for each agent (immutable)
DEFAULT_MODELS: Final[dict[str, ModelOption]] = {
    "task": "haiku",
    "coding": "sonnet",
    "telegram": "haiku",
}


def _is_valid_model(value: str) -> TypeGuard[ModelOption]:
    """Type guard to validate model option values."""
    return value in _VALID_MODELS


def _get_model(agent_name: str) -> ModelOption:
    """
    Get the model for an agent from environment variable or default.

    Environment variables:
        TASK_AGENT_MODEL, CODING_AGENT_MODEL, TELEGRAM_AGENT_MODEL

    Valid values: haiku, sonnet, opus, inherit
    """
    env_var = f"{agent_name.upper()}_AGENT_MODEL"
    value = os.environ.get(env_var, "").lower().strip()

    if _is_valid_model(value):
        return value  # Type checker knows this is ModelOption via TypeGuard

    default = DEFAULT_MODELS.get(agent_name)
    if default is not None:
        return default  # DEFAULT_MODELS is typed as dict[str, ModelOption]

    # Fallback for unknown agent names
    return "haiku"


def _load_prompt(name: str) -> str:
    """Load a prompt file."""
    return (PROMPTS_DIR / f"{name}.md").read_text()


OrchestratorModelOption = Literal["haiku", "sonnet", "opus"]

# Valid orchestrator model values (no "inherit" option since orchestrator is root)
_VALID_ORCHESTRATOR_MODELS: Final[tuple[str, ...]] = ("haiku", "sonnet", "opus")


def _is_valid_orchestrator_model(value: str) -> TypeGuard[OrchestratorModelOption]:
    """Type guard to validate orchestrator model option values."""
    return value in _VALID_ORCHESTRATOR_MODELS


def get_orchestrator_model() -> OrchestratorModelOption:
    """
    Get the orchestrator model from environment variable or default.

    Environment variable: ORCHESTRATOR_MODEL
    Valid values: haiku, sonnet, opus (no "inherit" since orchestrator is root)
    Default: haiku
    """
    value = os.environ.get("ORCHESTRATOR_MODEL", "").lower().strip()
    if _is_valid_orchestrator_model(value):
        return value  # Type checker knows this is OrchestratorModelOption via TypeGuard
    return "haiku"


def create_agent_definitions() -> dict[str, AgentDefinition]:
    """
    Create agent definitions with models from environment configuration.

    This is called at import time but reads env vars, so changes to
    environment require reimporting or restarting.

    Agents:
    - task: Project/issue management via Task MCP Server (replaces Linear)
    - coding: Code implementation + Playwright testing + local git
    - telegram: Notifications via Telegram Bot API (replaces Slack)
    """
    return {
        "task": AgentDefinition(
            description="Manages tasks, projects, and session tracking. Use for any task management operations.",
            prompt=_load_prompt("task_agent_prompt"),
            tools=get_task_tools() + ["Read", "Glob"],
            model=_get_model("task"),
        ),
        "telegram": AgentDefinition(
            description="Sends Telegram notifications to keep users informed. Use for progress updates.",
            prompt=_load_prompt("telegram_agent_prompt"),
            tools=get_telegram_tools() + FILE_TOOLS,
            model=_get_model("telegram"),
        ),
        "coding": AgentDefinition(
            description="Writes code, tests with Playwright, and manages local git. Use for implementation and version control.",
            prompt=_load_prompt("coding_agent_prompt"),
            tools=get_coding_tools(),
            model=_get_model("coding"),
        ),
    }


# Create definitions at import time (reads env vars)
AGENT_DEFINITIONS: dict[str, AgentDefinition] = create_agent_definitions()

# Export individual agents for convenience
TASK_AGENT = AGENT_DEFINITIONS["task"]
TELEGRAM_AGENT = AGENT_DEFINITIONS["telegram"]
CODING_AGENT = AGENT_DEFINITIONS["coding"]
