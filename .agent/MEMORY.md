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
- Context: `context_manager.py` - smart context loading with prompt compression (76.9% size reduction)
- Project Map: `.agent/PROJECT_MAP.md` - auto-generated project structure (ENG-33)

### Project Map (ENG-33)
- Auto-generated file: `.agent/PROJECT_MAP.md`
- Generator script: `scripts/generate_project_map.py`
- Contains: directory tree, key files, dependencies, ports, recent commits, import graph
- Loaded into session context automatically via `prompts.py:ensure_project_map()`
- Update after commits: `python scripts/generate_project_map.py`
- Staleness check: regenerated if older than 1 hour

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
- Endpoints:
  - `/api/context/stats` - context manager statistics
  - `/api/context/prompts` - prompt compression metrics

### Test Infrastructure
- Location: `tests/` directory
- Subdirectories: `api/`, `e2e/`, `integration/`
- Config: `pytest.ini` at project root
- CI/CD: `.github/workflows/test.yml`
- Makefile targets: `test`, `test-api`, `test-e2e`, `test-integration`, `coverage`
- E2E framework: Playwright with pytest fixtures in `conftest.py`
- API testing: httpx async client

---

## Environment

### Ports
- 5173: Dashboard (Vite dev server)
- 8003: API server (FastAPI)
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

## Dashboard

### Theming System
- Theme context: `dashboard/src/context/ThemeContext.jsx`
- Three themes available: Light, Dark, Midnight
- Theme toggle component: `dashboard/src/components/ThemeToggle.jsx`
- Settings page: `dashboard/src/pages/Settings.jsx` with accent color picker
- All components use CSS variables from `dashboard/src/styles/themes.css`

### Theme Storage (localStorage)
- Theme preference: `theme-preference` key
- Accent color: `accent-color` key

---

## Lessons Learned

- Screenshots directory (`/screenshots`) is in .gitignore - evidence files kept locally but not committed
- Screenshots path for testing: `/home/dev/work/AxonCode/your-claude-engineer/screenshots/`
- Prompt compression achieved 76.9% reduction while maintaining quality - aggressive compression is viable

---

## Session History

<!-- Append-only: add new entries at the end -->

### 2024-XX-XX - Initial Setup
- Created .agent/ directory structure
- Added SOUL.md, MEMORY.md, SESSION_LOG.md templates

### 2026-02-07 - ENG-49 Comprehensive Test Suite
- Created test infrastructure with pytest and Playwright
- Test directories: `tests/api/`, `tests/e2e/`, `tests/integration/`
- CI/CD pipeline: `.github/workflows/test.yml`
- Makefile with test targets (`make test`, `make test-e2e`, etc.)
- E2E tests use Playwright with conftest for fixtures
- API tests use httpx async client
- Coverage requirement: >80%

**Key test files:**
- Tests: `tests/`
- CI workflow: `.github/workflows/test.yml`
- Test config: `pytest.ini`
- Makefile at project root

### 2026-02-07 - ENG-48 Data Import/Export
- Commit: 186ab40
- Implemented comprehensive data import/export system for dashboard

**New files created:**
- `dashboard/src/pages/Import.jsx` - Import UI with tabs for JSON/CSV, Linear, GitHub
- `dashboard/src/pages/Export.jsx` - Export UI with JSON/CSV/Markdown export and backup management
- `scripts/backup.py` - Scheduled backup script with 30-day retention and Telegram notification

**Architecture notes:**
- Export/Import endpoints added to `analytics_server/server.py` (720+ lines)
- Import supports dry-run mode and conflict resolution (skip/update/create duplicates)
- Linear importer maps: Linear state -> workflow state, Linear priority -> priority
- GitHub importer can filter by labels and import comments
- Backups stored in `backups/` directory with 30-day retention

### 2026-02-07 - ENG-33 Codebase Map
- Implemented auto-generated project map for agent context

**New files created:**
- `scripts/generate_project_map.py` - Generates `.agent/PROJECT_MAP.md`
- `.agent/PROJECT_MAP.md` - Auto-generated project structure

**Modified files:**
- `prompts.py` - Added `load_project_map()`, `ensure_project_map()` functions
- `agent.py` - Added project map generation on startup
- `prompts/coding_agent_prompt.md` - Added instruction to update map after commits

**Features:**
- Directory structure with file counts
- Key files by category (entry points, configs, docs)
- Dependencies from requirements.txt and package.json
- Port configurations
- Recent 5 git commits
- Import dependency graph with hub file detection

---

*Last updated: 2026-02-07 (added ENG-33 Codebase Map documentation)*
