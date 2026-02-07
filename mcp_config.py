"""
MCP Server Configuration
========================

Configuration for Task MCP and Telegram MCP server integration.
Replaces Arcade Gateway with self-hosted MCP servers.

Setup:
1. Deploy Task MCP Server (PostgreSQL backend) on VDS
2. Deploy Telegram MCP Server on VDS
3. Create Telegram bot via @BotFather
4. Set environment variables in .env
"""

import os
from typing import Literal, TypedDict


class McpServerConfig(TypedDict):
    """Configuration for MCP server."""

    type: Literal["sse"]
    url: str
    headers: dict[str, str]


# =============================================================================
# Environment Configuration
# =============================================================================

# Task MCP Server
TASK_MCP_URL: str = os.environ.get("TASK_MCP_URL", "http://localhost:8001/sse")

# Telegram MCP Server
TELEGRAM_MCP_URL: str = os.environ.get("TELEGRAM_MCP_URL", "http://localhost:8002/sse")

# Optional: API key for authentication (if configured on servers)
MCP_API_KEY: str = os.environ.get("MCP_API_KEY", "")


# =============================================================================
# Tool Definitions
# =============================================================================
# Tools use the format: mcp__<server>__<ToolName>

# Task MCP tools (11 tools) - replaces Linear
TASK_TOOLS: list[str] = [
    "mcp__task__Task_WhoAmI",
    "mcp__task__Task_ListTeams",
    "mcp__task__Task_CreateProject",
    "mcp__task__Task_CreateIssue",
    "mcp__task__Task_ListIssues",
    "mcp__task__Task_GetIssue",
    "mcp__task__Task_UpdateIssue",
    "mcp__task__Task_TransitionIssueState",
    "mcp__task__Task_AddComment",
    "mcp__task__Task_ListWorkflowStates",
    "mcp__task__Task_GetStaleIssues",
]

# Telegram MCP tools (3 tools) - replaces Slack
TELEGRAM_TOOLS: list[str] = [
    "mcp__telegram__Telegram_WhoAmI",
    "mcp__telegram__Telegram_SendMessage",
    "mcp__telegram__Telegram_ListChats",
]

# Playwright MCP tools for browser automation
PLAYWRIGHT_TOOLS: list[str] = [
    "mcp__playwright__browser_navigate",
    "mcp__playwright__browser_take_screenshot",
    "mcp__playwright__browser_click",
    "mcp__playwright__browser_type",
    "mcp__playwright__browser_select_option",
    "mcp__playwright__browser_hover",
    "mcp__playwright__browser_snapshot",
    "mcp__playwright__browser_wait_for",
]

# All MCP tools combined
ALL_MCP_TOOLS: list[str] = TASK_TOOLS + TELEGRAM_TOOLS + PLAYWRIGHT_TOOLS

# Permission wildcards
TASK_TOOLS_PERMISSION: str = "mcp__task__*"
TELEGRAM_TOOLS_PERMISSION: str = "mcp__telegram__*"
PLAYWRIGHT_TOOLS_PERMISSION: str = "mcp__playwright__*"


# =============================================================================
# MCP Server Configurations
# =============================================================================


def get_task_mcp_config() -> McpServerConfig:
    """
    Get the Task MCP server configuration.

    Returns:
        MCP server config dict for use in ClaudeAgentOptions.mcp_servers

    Raises:
        ValueError: If TASK_MCP_URL is not set
    """
    if not TASK_MCP_URL:
        raise ValueError(
            "TASK_MCP_URL environment variable not set.\n"
            "Deploy the Task MCP server and set TASK_MCP_URL=http://your-vds:8001/sse"
        )

    headers = {}
    if MCP_API_KEY:
        headers["Authorization"] = f"Bearer {MCP_API_KEY}"

    return McpServerConfig(
        type="sse",
        url=TASK_MCP_URL,
        headers=headers,
    )


def get_telegram_mcp_config() -> McpServerConfig:
    """
    Get the Telegram MCP server configuration.

    Returns:
        MCP server config dict for use in ClaudeAgentOptions.mcp_servers

    Raises:
        ValueError: If TELEGRAM_MCP_URL is not set
    """
    if not TELEGRAM_MCP_URL:
        raise ValueError(
            "TELEGRAM_MCP_URL environment variable not set.\n"
            "Deploy the Telegram MCP server and set TELEGRAM_MCP_URL=http://your-vds:8002/sse"
        )

    headers = {}
    if MCP_API_KEY:
        headers["Authorization"] = f"Bearer {MCP_API_KEY}"

    return McpServerConfig(
        type="sse",
        url=TELEGRAM_MCP_URL,
        headers=headers,
    )


def validate_mcp_config() -> None:
    """
    Validate the MCP configuration.

    Raises:
        ValueError: If configuration is invalid
    """
    errors = []

    if not TASK_MCP_URL:
        errors.append("TASK_MCP_URL not set")

    if not TELEGRAM_MCP_URL:
        errors.append("TELEGRAM_MCP_URL not set")

    if errors:
        raise ValueError(
            "MCP configuration errors:\n" + "\n".join(f"  - {e}" for e in errors)
        )


def print_mcp_config() -> None:
    """Print the current MCP configuration for debugging."""
    print("MCP Configuration:")
    print(f"  Task MCP URL: {TASK_MCP_URL or '(not set)'}")
    print(f"  Telegram MCP URL: {TELEGRAM_MCP_URL or '(not set)'}")
    print(f"  API Key: {'configured' if MCP_API_KEY else '(not set)'}")
    print(f"  Task tools: {len(TASK_TOOLS)} available")
    print(f"  Telegram tools: {len(TELEGRAM_TOOLS)} available")
    print(f"  Playwright tools: {len(PLAYWRIGHT_TOOLS)} available")


# =============================================================================
# Tool Getters for Multi-Agent Architecture
# =============================================================================


def get_task_tools() -> list[str]:
    """Get Task-only tools for Task agent (replaces Linear)."""
    return TASK_TOOLS


def get_telegram_tools() -> list[str]:
    """Get Telegram-only tools for Telegram agent (replaces Slack)."""
    return TELEGRAM_TOOLS


def get_coding_tools() -> list[str]:
    """Get tools for coding agent (file ops + Playwright + git)."""
    builtin_tools = ["Read", "Write", "Edit", "Glob", "Grep", "Bash"]
    return builtin_tools + PLAYWRIGHT_TOOLS


def get_reviewer_tools() -> list[str]:
    """Get tools for reviewer agent (read-only file ops + git diff)."""
    return ["Read", "Glob", "Grep", "Bash"]
