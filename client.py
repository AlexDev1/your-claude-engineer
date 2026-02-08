"""
Claude SDK Client Configuration
===============================

Functions for creating and configuring the Claude Agent SDK client.
Uses self-hosted Task MCP and Telegram MCP servers for integration.
Implements tool output truncation middleware (ENG-29).
"""

import json
import os
from pathlib import Path
from typing import Literal, TypedDict, cast

from dotenv import load_dotenv

load_dotenv()

from claude_agent_sdk import ClaudeAgentOptions, ClaudeSDKClient, McpServerConfig
from claude_agent_sdk.types import HookCallback, HookMatcher

from context_manager import (
    get_context_manager,
    truncate_tool_output,
    truncate_git_diff,
    TOOL_OUTPUT_MAX_CHARS,
)
from mcp_config import (
    ALL_MCP_TOOLS,
    TASK_TOOLS_PERMISSION,
    TELEGRAM_TOOLS_PERMISSION,
    PLAYWRIGHT_TOOLS_PERMISSION,
    get_task_mcp_config,
    get_telegram_mcp_config,
    validate_mcp_config,
)
from agents.definitions import AGENT_DEFINITIONS
from security import bash_security_hook


# Valid permission modes for the Claude SDK
PermissionMode = Literal["acceptEdits", "acceptAll", "reject", "ask"]


class SandboxConfig(TypedDict):
    """Sandbox configuration for bash command isolation."""

    enabled: bool
    autoAllowBashIfSandboxed: bool


class PermissionsConfig(TypedDict):
    """Permissions configuration for file and tool operations."""

    defaultMode: PermissionMode
    allow: list[str]


class SecuritySettings(TypedDict):
    """Complete security settings structure."""

    sandbox: SandboxConfig
    permissions: PermissionsConfig


# Playwright MCP tools for browser automation
PLAYWRIGHT_TOOLS: list[str] = [
    "mcp__playwright__browser_navigate",
    # browser_take_screenshot REMOVED — exceeds SDK 1MB buffer (base64 in response)
    "mcp__playwright__browser_click",
    "mcp__playwright__browser_type",
    "mcp__playwright__browser_select_option",
    "mcp__playwright__browser_hover",
    "mcp__playwright__browser_snapshot",
    "mcp__playwright__browser_wait_for",
]

# Built-in tools
BUILTIN_TOOLS: list[str] = [
    "Read",
    "Write",
    "Edit",
    "Glob",
    "Grep",
    "Bash",
]

# Prompts directory
PROMPTS_DIR = Path(__file__).parent / "prompts"


def load_orchestrator_prompt() -> str:
    """Load the orchestrator system prompt."""
    return (PROMPTS_DIR / "orchestrator_prompt.md").read_text()


def tool_output_truncation_hook(tool_name: str, tool_input: dict, tool_output: str) -> str:
    """
    Post-tool hook to truncate long tool outputs (ENG-29).

    This middleware runs after each tool execution and truncates
    outputs that exceed the configured limit to save context budget.

    Args:
        tool_name: Name of the tool that was executed
        tool_input: Input parameters passed to the tool
        tool_output: Raw output from the tool

    Returns:
        Possibly truncated tool output
    """
    if not tool_output or len(tool_output) <= TOOL_OUTPUT_MAX_CHARS:
        return tool_output

    # Special handling for git/bash commands
    if tool_name.lower() == "bash":
        command = tool_input.get("command", "")
        if "diff" in command.lower():
            truncated, _ = truncate_git_diff(tool_output)
            return truncated

    # General truncation
    truncated, was_truncated = truncate_tool_output(tool_output, tool_name)

    if was_truncated:
        # Track in context manager
        ctx_manager = get_context_manager()
        ctx_manager.track_tool_output(tool_name, truncated)

    return truncated


def create_security_settings() -> SecuritySettings:
    """
    Create the security settings structure.

    Returns:
        SecuritySettings with sandbox and permissions configured
    """
    return SecuritySettings(
        sandbox=SandboxConfig(enabled=True, autoAllowBashIfSandboxed=True),
        permissions=PermissionsConfig(
            defaultMode="acceptEdits",
            allow=[
                # Allow all file operations within the project directory
                "Read(./**)",
                "Write(./**)",
                "Edit(./**)",
                "Glob(./**)",
                "Grep(./**)",
                # Bash permission granted here, but actual commands are validated
                # by the bash_security_hook (see security.py for allowed commands)
                "Bash(*)",
                # Allow Playwright MCP tools for browser automation
                *PLAYWRIGHT_TOOLS,
                # Allow Task MCP tools (project/issue management)
                TASK_TOOLS_PERMISSION,
                # Allow Telegram MCP tools (notifications)
                TELEGRAM_TOOLS_PERMISSION,
            ],
        ),
    )


def write_security_settings(project_dir: Path, settings: SecuritySettings) -> Path:
    """
    Write security settings to project directory.

    Args:
        project_dir: Directory to write settings to
        settings: Security settings to write

    Returns:
        Path to the settings file

    Raises:
        IOError: If settings file cannot be written
    """
    project_dir.mkdir(parents=True, exist_ok=True)
    settings_file: Path = project_dir / ".claude_settings.json"

    try:
        with open(settings_file, "w") as f:
            json.dump(settings, f, indent=2)
    except IOError as e:
        raise IOError(
            f"Failed to write security settings to {settings_file}: {e}\n"
            f"Check disk space and file permissions.\n"
            f"Agent cannot start without security settings."
        ) from e

    return settings_file


def create_client(project_dir: Path, model: str) -> ClaudeSDKClient:
    """
    Create a Claude Agent SDK client with multi-layered security.

    Args:
        project_dir: Directory for the project
        model: Claude model to use

    Returns:
        Configured ClaudeSDKClient

    Raises:
        ValueError: If required environment variables are not set

    Security layers (defense in depth):
    1. Sandbox - OS-level bash command isolation prevents filesystem escape
       (bwrap/docker-style isolation)
    2. Permissions - File operations restricted to project_dir only
       (enforced by SDK before tool execution)
    3. Security hooks - Bash commands validated against an allowlist
       (runs pre-execution via PreToolUse hook, see security.py for ALLOWED_COMMANDS)

    Execution: Permissions checked first, then hooks run, finally sandbox executes.
    """
    # Validate MCP configuration
    validate_mcp_config()

    # Get MCP server configurations
    task_config = get_task_mcp_config()
    telegram_config = get_telegram_mcp_config()

    # Create and write security settings
    security_settings: SecuritySettings = create_security_settings()
    settings_file: Path = write_security_settings(project_dir, security_settings)

    # Get context budget info (ENG-29)
    ctx_manager = get_context_manager()
    max_tokens = ctx_manager.budget.max_tokens

    print(f"Created security settings at {settings_file}")
    print("   - Sandbox enabled (OS-level bash isolation)")
    print(f"   - Filesystem restricted to: {project_dir.resolve()}")
    print("   - Bash commands restricted to allowlist (see security.py)")
    print(f"   - Context budget: {max_tokens:,} tokens (MAX_CONTEXT_TOKENS)")
    print(f"   - Compact mode: 70% ({int(max_tokens * 0.7):,} tokens)")
    print(f"   - Graceful shutdown: 85% ({int(max_tokens * 0.85):,} tokens)")
    print(f"   - Tool output limit: {TOOL_OUTPUT_MAX_CHARS:,} chars")
    print(f"   - MCP servers:")
    print(f"       - playwright (browser automation)")
    print(f"       - task ({task_config['url']})")
    print(f"       - telegram ({telegram_config['url']})")
    print()

    # Load orchestrator prompt as system prompt
    orchestrator_prompt = load_orchestrator_prompt()

    return ClaudeSDKClient(
        options=ClaudeAgentOptions(
            model=model,
            system_prompt=orchestrator_prompt,
            allowed_tools=[
                *BUILTIN_TOOLS,
                *ALL_MCP_TOOLS,
            ],
            mcp_servers=cast(
                dict[str, McpServerConfig],
                {
                    "playwright": {"command": "npx", "args": ["-y", "@playwright/mcp@latest"]},
                    "task": task_config,
                    "telegram": telegram_config,
                },
            ),
            hooks={
                "PreToolUse": [
                    HookMatcher(
                        matcher="Bash",
                        hooks=[cast(HookCallback, bash_security_hook)],
                    ),
                ],
            },
            agents=AGENT_DEFINITIONS,
            max_turns=1000,
            cwd=str(project_dir.resolve()),
            settings=str(settings_file.resolve()),
        )
    )
