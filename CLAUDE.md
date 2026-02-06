# CLAUDE.md
**IMPORTANT**: you must always answer in Russian!
This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Overview

This is an autonomous AI agent harness built on the Claude Agent SDK. It runs long-duration coding sessions using multi-agent orchestration with specialized sub-agents for Task management (PostgreSQL-backed), Coding (implementation with Playwright testing and Git), and Telegram (notifications).

**Important**: This is a harness/framework for running autonomous agents, not a traditional application.

## Commands

```bash
# Setup
pip install -r requirements.txt

# Deploy MCP servers to VDS
docker-compose up -d  # On your VDS

# Run the agent
uv run python autonomous_agent_demo.py --project-dir my-app
uv run python autonomous_agent_demo.py --project-dir my-app --max-iterations 3 --model opus

# Test security hooks
uv run python test_security.py
```

## Architecture

```
ORCHESTRATOR (coordinates work, delegates to sub-agents via Task tool)
    ├── TASK AGENT        → Project/issue management (PostgreSQL via Task MCP Server)
    ├── CODING AGENT      → Implementation + Playwright UI testing + Git commits
    └── TELEGRAM AGENT    → Progress notifications (Telegram Bot API)
```

**MCP Servers (self-hosted on VDS)**:
- `task_mcp_server/` - Task management with PostgreSQL backend, OAuth 2.0 Authorization Server (replaces Linear)
- `telegram_mcp_server/` - Notifications via Telegram Bot API, OAuth 2.0 Resource Server (replaces Slack)

**Key files**:
- `autonomous_agent_demo.py` - Main entry point, CLI argument parsing
- `agent.py` - Session runner (`run_agent_session()`, `run_autonomous_agent()`)
- `client.py` - SDK client setup with MCP servers and security settings
- `mcp_config.py` - MCP server URLs and tool definitions
- `security.py` - Bash command allowlist and validation hooks
- `prompts/` - All agent system prompts and task templates
- `prompts/app_spec.txt` - Application specification (edit this to build different apps)
- `docker-compose.yml` - Deployment configuration for MCP servers

**OAuth 2.0 files** (for Claude.ai web connector compatibility):
- `task_mcp_server/oauth_provider.py` - PostgresOAuthProvider (Authorization Server)
- `task_mcp_server/oauth_login.py` - Login page for API key → OAuth code exchange
- `telegram_mcp_server/token_verifier.py` - HttpTokenVerifier (validates tokens via Task MCP)

**State tracking**: `.task_project.json` marker file tracks initialization; Task MCP Server is the source of truth for work status.

## Key Patterns

1. **Orchestrator pattern**: Main agent delegates to specialized sub-agents, passing context between them
2. **Session isolation**: Fresh agent sessions each iteration to avoid context window exhaustion
3. **Verification gates**: Orchestrator asks coding agent to verify existing features via Playwright before new work
4. **Screenshot evidence**: All features require screenshot proof before marking Done

## Security Model (Defense-in-Depth)

- **OAuth 2.0 + API Keys**: FastMCP handles auth natively (no nginx auth_request)
  - Task MCP = Authorization Server + Resource Server (`auth_server_provider`)
  - Telegram MCP = Resource Server (`token_verifier` → HTTP to Task MCP)
  - `load_access_token()` checks OAuth tokens first, then SHA-256 hashed API keys
- OS-level sandbox for bash commands
- Filesystem restricted to project directory
- Bash command allowlist in `security.py` (`ALLOWED_COMMANDS` set)
- Pre-execution validation hook (`bash_security_hook()`)
- MCP permissions explicitly configured

## Customization Points

- **App to build**: Edit `prompts/app_spec.txt`
- **Issue count**: Edit `prompts/initializer_task.md`
- **Allowed bash commands**: Add to `ALLOWED_COMMANDS` in `security.py`
- **Agent behavior**: Edit corresponding prompt in `prompts/`
- **Models**: Set env vars (`ORCHESTRATOR_MODEL`, `CODING_AGENT_MODEL`, etc.) or use `--model` flag

## Deployment

### MCP Servers on VDS

1. Create `.env` file with:
   ```
   DB_PASSWORD=your_secure_password
   TELEGRAM_BOT_TOKEN=your_bot_token
   TELEGRAM_CHAT_ID=your_chat_id
   ```

2. Deploy:
   ```bash
   docker-compose up -d
   ```

3. Configure client:
   ```
   TASK_MCP_URL=http://your-vds:8001/sse
   TELEGRAM_MCP_URL=http://your-vds:8002/sse
   ```

### Creating Telegram Bot

1. Message @BotFather on Telegram
2. Send `/newbot` and follow instructions
3. Copy the bot token to `TELEGRAM_BOT_TOKEN`
4. Message @userinfobot to get your chat ID
5. Set `TELEGRAM_CHAT_ID` in your `.env`

## Constraints

- **Windows not supported** (subagents require Linux/macOS; WSL works)
- Bash heredocs are blocked (use Write tool instead)
- First session creates all tasks and sets up the project
