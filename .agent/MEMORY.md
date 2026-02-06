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
- Heartbeat: `heartbeat/` directory (Docker) and `heartbeat.py` (local dev) - monitors for stale tasks

### Dashboard (Vite + React)
- Location: `dashboard/` directory
- Dev server: http://localhost:5173
- Styling: Tailwind CSS
- Routing: React Router (`/tasks` for Task Manager page)
- Components: `dashboard/src/components/*.jsx`
- Pages: `dashboard/src/pages/*.jsx`
- Custom hooks: `dashboard/src/hooks/*.js`
  - `useKeyboardShortcuts` - keyboard shortcut handling
- Kanban: drag-and-drop via `@hello-pangea/dnd`
- Issue templates: Bug, Feature, Task, Epic (each with different default priorities)

### Analytics API
- Location: `analytics_server/` directory
- Dev server: http://localhost:8080
- Stack: Python/FastAPI

---

## Environment

### Ports
- 5173: Dashboard (Vite dev server)
- 8080: Analytics API (FastAPI)

### Environment Variables
- `TASK_MCP_URL` - Task management server URL
- `TELEGRAM_MCP_URL` - Telegram notifications server URL
- `ORCHESTRATOR_MODEL` - Model for orchestrator (haiku/sonnet/opus)
- `CODING_AGENT_MODEL` - Model for coding agent
- `TASK_AGENT_MODEL` - Model for task agent
- `TELEGRAM_AGENT_MODEL` - Model for telegram agent
- `HEARTBEAT_INTERVAL_MINUTES` - Controls heartbeat check frequency
- `STALE_THRESHOLD_HOURS` - Hours before a task is considered stale

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

**Health Endpoints:**
- Task server: `https://mcp.axoncode.pro/task/health`
- Telegram server: `https://mcp.axoncode.pro/telegram/health`
- Health endpoints excluded from auth (accessible without API key)

**Available MCP Tools:**
- `Task_GetStaleIssues` - Programmatic stale task detection (requires deployment)

**Task Server Endpoints:**
- `/stale-issues` - Check for stuck/stale tasks (needs deployment)

**Authentication Infrastructure:**
- OAuth 2.0 + API key authentication in both `task_mcp_server` and `telegram_mcp_server`
- IP whitelist middleware: `ip_whitelist.py` in each server
- Admin CLI: `admin_cli.py` for creating/managing API keys

**Deployment:**
- nginx reverse proxy config: `deploy/nginx/mcp-servers.conf`
- Includes HTTPS, rate limiting, and security headers

---

## Lessons Learned

- Screenshots directory (`/screenshots`) is in .gitignore - evidence files kept locally but not committed
- Screenshots path for testing: `/home/dev/work/AxonCode/your-claude-engineer/screenshots/`

---

## Session History

<!-- Append-only: add new entries at the end -->

### 2024-XX-XX - Initial Setup
- Created .agent/ directory structure
- Added SOUL.md, MEMORY.md, SESSION_LOG.md templates

---

*Last updated: 2026-02-07 (added ports, routes, dashboard libraries, issue templates)*
