# Repository Guidelines
**ВАЖНО**: вы всегда должны отвечать на русском языке!
## Project Structure & Module Organization
- Core runtime: `agent.py` plus `agents/definitions.py` and `agents/orchestrator.py`; CLI demo `autonomous_agent_demo.py`.
- Services: `analytics_server/` (API + telemetry) and `dashboard/` (React/Vite UI); prompts live in `prompts/`; config/allowlist in `client.py`, `mcp_config.py`, `security.py`.
- Tests in `tests/api/`, `tests/integration/`, `tests/e2e/` with extra guards in `test_security.py` and `test_github_integration.py`; generated outputs belong in `generations/` (git-ignored).

## Build, Test, and Development Commands
- `make install` installs Python deps, dashboard packages, and Playwright.
- `make dev` prints steps: start API `python -m analytics_server.server` (8003) and dashboard `cd dashboard && npm run dev` (5173).
- `make test` aggregates suites; targeted runs: `make test-api`, `make test-agent`, `make test-security`, `make test-e2e` (`HEADLESS=true` or `make test-e2e-headed`).
- `make coverage` enforces 80%+ coverage and writes `htmlcov/`; hygiene: `make lint` (ruff/mypy), `make format` (ruff fmt + isort); health checks: `make preflight`, `make diagnose`.

## Coding Style & Naming Conventions
- Python: 4-space indent, snake_case for modules/functions, PascalCase classes, UPPER_SNAKE constants; keep side effects under `if __name__ == "__main__":`.
- Tooling: `ruff check .`, `ruff format .`, `isort .`; optional `mypy analytics_server/ agents/ --ignore-missing-imports`.
- Dashboard: functional React components in PascalCase, hooks `useX`; prefer Tailwind utilities, keep module state in camelCase.

## Testing Guidelines
- Add `test_*.py` beside the feature area under `tests/`; use markers `api`, `integration`, `e2e`, `slow` from `pytest.ini`.
- E2E needs API+dashboard running; set `HEADLESS=true` in CI. Quick smoke: `make test-quick`.
- Update `test_security.py` when changing the shell allowlist; target ≥80% coverage via `make coverage`.

## Commit & Pull Request Guidelines
- Use conventional prefixes (`feat:`, `fix:`, `chore:`, `docs:`) and include ticket IDs when relevant (e.g., `ENG-123`); branches often follow `agent/ENG-123-short-desc`.
- PRs should list what changed, linked issue, commands run (`make test`, `make lint`), and coverage notes; attach UI screenshots/GIFs for dashboard tweaks and mention env or security changes.

## Security & Configuration Tips
- Copy `.env.example` to `.env`; key vars: `TASK_MCP_URL`, `TELEGRAM_MCP_URL`, `MCP_API_KEY`, optional `GENERATIONS_BASE_PATH`. Never commit secrets.
- Shell commands executed by agents are allowlisted in `security.py`; expand cautiously and mirror changes with tests. Generated projects live in isolated git repos under `generations/`.
