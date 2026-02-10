"""
Agent Definitions
=================

Specialized agent configurations using Claude Agent SDK's AgentDefinition.
Model selection is configurable via environment variables.

Agents:
- task: Manages tasks, projects, and session tracking (replaces Linear)
- coding: Writes code, tests with Playwright, handles git operations
- telegram: Sends notifications via Telegram (replaces Slack)
- reviewer: Reviews code diffs before commit (automated code review gate)
"""

import os
from pathlib import Path
from typing import Final, Literal, TypeGuard

from claude_agent_sdk.types import AgentDefinition

from mcp_config import (
    get_task_tools,
    get_telegram_tools,
    get_coding_tools,
    get_reviewer_tools,
    get_devops_tools,
    get_testing_tools,
    get_security_tools,
    get_research_tools,
    get_planner_tools,
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
    "reviewer": "haiku",
    "devops": "haiku",
    "testing": "sonnet",
    "security": "haiku",
    "research": "haiku",
    "planner": "sonnet",
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


def _load_soul() -> str:
    """
    Load the agent soul file (.agent/SOUL.md) if it exists.

    The soul file defines immutable identity, preferences, and principles
    for the coding agent. It is included in the system prompt.

    Returns:
        Contents of SOUL.md, or empty string if file doesn't exist.
    """
    soul_path = PROMPTS_DIR.parent / ".agent" / "SOUL.md"

    if not soul_path.exists():
        return ""

    try:
        return soul_path.read_text()
    except IOError:
        return ""


def _get_coding_prompt() -> str:
    """
    Get the coding agent prompt with SOUL.md content appended.

    Returns:
        Combined prompt with base coding prompt and soul identity.
    """
    base_prompt = _load_prompt("coding_agent_prompt")
    soul = _load_soul()

    if soul:
        return f"{base_prompt}\n\n---\n\n## Your Identity (from .agent/SOUL.md)\n\n{soul}"

    return base_prompt


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
    - reviewer: Automated code review before commit (ENG-42)
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
            prompt=_get_coding_prompt(),
            tools=get_coding_tools(),
            model=_get_model("coding"),
        ),
        "reviewer": AgentDefinition(
            description="Reviews code diffs before commit. Checks for security issues, code quality, and best practices. Returns APPROVE or REQUEST_CHANGES verdict.",
            prompt=_load_prompt("reviewer_prompt"),
            tools=get_reviewer_tools(),
            model=_get_model("reviewer"),
        ),
        "devops": AgentDefinition(
            description="Manages CI/CD pipelines, Docker, deployment, and infrastructure. Use for DevOps operations.",
            prompt=_load_prompt("devops_agent_prompt"),
            tools=get_devops_tools(),
            model=_get_model("devops"),
        ),
        "testing": AgentDefinition(
            description="Writes and runs tests (unit, integration, E2E). Dedicated testing agent. Use for test creation and execution.",
            prompt=_load_prompt("testing_agent_prompt"),
            tools=get_testing_tools(),
            model=_get_model("testing"),
        ),
        "security": AgentDefinition(
            description="Performs security auditing, dependency scanning, and vulnerability detection. Use for security reviews.",
            prompt=_load_prompt("security_agent_prompt"),
            tools=get_security_tools(),
            model=_get_model("security"),
        ),
        "research": AgentDefinition(
            description="Investigates codebase, documentation, and libraries before implementation. Use for pre-coding research.",
            prompt=_load_prompt("research_agent_prompt"),
            tools=get_research_tools(),
            model=_get_model("research"),
        ),
        "planner": AgentDefinition(
            description="Analyzes tasks, creates implementation plans, and decomposes complex tasks into subtasks. Use for task planning.",
            prompt=_load_prompt("planner_agent_prompt"),
            tools=get_planner_tools(),
            model=_get_model("planner"),
        ),
    }


# Create definitions at import time (reads env vars)
AGENT_DEFINITIONS: dict[str, AgentDefinition] = create_agent_definitions()

# Export individual agents for convenience
TASK_AGENT = AGENT_DEFINITIONS["task"]
TELEGRAM_AGENT = AGENT_DEFINITIONS["telegram"]
CODING_AGENT = AGENT_DEFINITIONS["coding"]
REVIEWER_AGENT = AGENT_DEFINITIONS["reviewer"]
DEVOPS_AGENT = AGENT_DEFINITIONS["devops"]
TESTING_AGENT = AGENT_DEFINITIONS["testing"]
SECURITY_AGENT = AGENT_DEFINITIONS["security"]
RESEARCH_AGENT = AGENT_DEFINITIONS["research"]
PLANNER_AGENT = AGENT_DEFINITIONS["planner"]
