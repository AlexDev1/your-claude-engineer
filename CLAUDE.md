# CLAUDE.md
**IMPORTANT**: you must always answer in Russian!
This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Overview

This is an autonomous AI agent harness built on the Claude Agent SDK. It runs task-driven coding sessions using multi-agent orchestration with specialized sub-agents for Task management, Coding (implementation with Playwright testing and Git), and Telegram (notifications).

The agent works in the current directory (cwd), picks tasks from the Task MCP Server by priority, and executes them one at a time until no tasks remain.

**Important**: This is a harness/framework for running autonomous agents, not a traditional application.

**MCP Servers**: Deployed separately — see [AxonCode/axon-mcp](https://github.com/AxonCode/axon-mcp) for Task and Telegram MCP server deployment.

## Commands

```bash
# Setup
pip install -r requirements.txt

# Run the agent (works in current directory)
uv run python autonomous_agent_demo.py
uv run python autonomous_agent_demo.py --team ENG
uv run python autonomous_agent_demo.py --team ENG --max-iterations 3 --model opus

# Test security hooks
uv run python test_security.py
```

## Architecture

```
ORCHESTRATOR (coordinates work, delegates to sub-agents via Task tool)
    ├── TASK AGENT        → Issue management, prioritization (via Task MCP Server)
    ├── CODING AGENT      → Implementation + Playwright UI testing + Git commits
    └── TELEGRAM AGENT    → Progress notifications (via Telegram MCP Server)
```

**Key files**:
- `autonomous_agent_demo.py` - Main entry point, CLI argument parsing
- `agent.py` - Session runner (`run_agent_session()`, `run_autonomous_agent()`)
- `client.py` - SDK client setup with MCP servers and security settings
- `mcp_config.py` - MCP server URLs and tool definitions
- `security.py` - Bash command allowlist and validation hooks
- `prompts/` - All agent system prompts and task templates
- `prompts/execute_task.md` - Per-iteration task prompt (get next task, implement, mark done)

**Task-driven loop**: Each iteration the agent gets the next Todo task by priority, implements it, and marks it Done. When no tasks remain, the agent outputs `ALL_TASKS_DONE:` and stops.

## Key Patterns

1. **Orchestrator pattern**: Main agent delegates to specialized sub-agents, passing context between them
2. **Session isolation**: Fresh agent sessions each iteration to avoid context window exhaustion
3. **Priority-based execution**: Tasks are picked by priority (urgent > high > medium > low)
4. **Screenshot evidence**: All features require screenshot proof before marking Done

## Security Model (Defense-in-Depth)

- **MCP Authentication**: OAuth 2.0 + API Keys handled by MCP servers (see [axon-mcp](https://github.com/AxonCode/axon-mcp))
- OS-level sandbox for bash commands
- Filesystem restricted to project directory
- Bash command allowlist in `security.py` (`ALLOWED_COMMANDS` set)
- Pre-execution validation hook (`bash_security_hook()`)
- MCP permissions explicitly configured

## Customization Points

- **Allowed bash commands**: Add to `ALLOWED_COMMANDS` in `security.py`
- **Agent behavior**: Edit corresponding prompt in `prompts/`
- **Models**: Set env vars (`ORCHESTRATOR_MODEL`, `CODING_AGENT_MODEL`, etc.) or use `--model` flag
- **Team**: Use `--team` flag (default: ENG)

## Prerequisites

### MCP Servers

Deploy Task and Telegram MCP servers from [AxonCode/axon-mcp](https://github.com/AxonCode/axon-mcp), then configure URLs in `.env`:

```
TASK_MCP_URL=https://mcp.yourdomain.com/task/sse
TELEGRAM_MCP_URL=https://mcp.yourdomain.com/telegram/sse
MCP_API_KEY=mcp_your_api_key
```

## Constraints

- **Windows not supported** (subagents require Linux/macOS; WSL works)
- Bash heredocs are blocked (use Write tool instead)
