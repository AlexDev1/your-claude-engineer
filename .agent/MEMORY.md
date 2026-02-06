# Agent Memory

This file contains curated facts learned across sessions.
The agent reads this at session start and updates it at session end.

---

## Project Structure

- Main entry: `agent.py` - autonomous agent loop
- Client setup: `client.py` - Claude SDK client configuration
- Prompts: `prompts/` directory with markdown templates
- Agent definitions: `agents/definitions.py`
- Security: `security.py` - bash command validation

---

## Environment

### Ports
- (none discovered yet)

### Environment Variables
- `TASK_MCP_URL` - Task management server URL
- `TELEGRAM_MCP_URL` - Telegram notifications server URL
- `ORCHESTRATOR_MODEL` - Model for orchestrator (haiku/sonnet/opus)
- `CODING_AGENT_MODEL` - Model for coding agent
- `TASK_AGENT_MODEL` - Model for task agent
- `TELEGRAM_AGENT_MODEL` - Model for telegram agent

---

## Dependencies

### Python
- `claude_agent_sdk` - Core SDK for Claude agents
- `dotenv` - Environment variable loading
- `pathlib` - Path handling

---

## Known Issues

- (none discovered yet)

---

## Discovered Patterns

### Loading Prompts
Use `prompts.py:load_prompt()` to load prompt templates.

### Agent Tools
Configure tools per agent in `agents/definitions.py`.

### MCP Servers
Configure via `mcp_config.py`, URLs from environment variables.

---

## Lessons Learned

- (none yet)

---

## Session History

<!-- Append-only: add new entries at the end -->

### 2024-XX-XX - Initial Setup
- Created .agent/ directory structure
- Added SOUL.md, MEMORY.md, SESSION_LOG.md templates

---

*Last updated: (auto-updated by agent)*
