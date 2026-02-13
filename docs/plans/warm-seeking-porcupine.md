# План: Рефакторинг в переиспользуемый пакет с командной координацией

## Контекст

Проект `your-claude-engineer` — автономная оболочка AI агента на Claude Agent SDK. Сейчас в репо одновременно живут новый пакетный layout (`pyproject.toml`, `src/axon_agent/...`) и старая плоская раскладка Python‑файлов в корне; из‑за смешения путей часть модулей и тестов всё ещё тянет старые импорты. Агент пока работает последовательно: один оркестратор делегирует субагентам по очереди.

**Проблемы:**
- Не устанавливается через `pip install` — нет пакетной структуры
- Нет единой точки входа (`autonomous_agent_demo.py` — демо-скрипт, не CLI)
- Последовательное выполнение задач — нет параллелизма
- Плоская структура файлов — сложно навигировать

**Цель:** Переиспользуемый Python-пакет `axon-agent` с CLI, командным режимом (как `/build-with-agent-team` в Claude Code), встроенным dashboard и чистой структурой.

---

## Статус на 10 февраля 2026

- Уже сделано: создан пакетный каркас (`pyproject.toml`, `src/axon_agent/...`), добавлен CLI на Click (`run`, `team`, `dashboard`, `health`, `config`), перенесены основные модули и статика dashboard в `src/axon_agent/dashboard/static`, настроен `pyproject` с зависимостями (`claude-agent-sdk>=0.1.25`, в `.venv` стоит 0.1.31).
- Осталось: довести миграцию — исправить все импорты на `axon_agent.*` (в `team/worker.py` и `dashboard/api.py` тянутся старые `agent.py`, `client.py`, `context_manager.py`, `telegram_reports.py`, `heartbeat.py`, и т.д.), реализовать рабочий командный режим (в CLI вызывается несуществующий `TeamCoordinator`; воркер опирается на старые модули), обновить тесты под новый пакет (все `tests/**` ещё импортируют корневые файлы и ломаются), очистить корень от дублей (`agent.py`, `analytics_server/`, `backups/`, `screenshots/`, `mobile-analytics-dark.png`, и прочие). Также починить зависания `tests/api/test_analytics_api.py` на `/health` и падения интеграционных тестов из‑за обращений к `127.0.0.1:8003` в песочнице; добиться зелёных `make test-quick` и `make test-agent`.

---

## Шаг 1: Каркас пакета

Создать `pyproject.toml` и `src/axon_agent/` структуру:

```toml
# pyproject.toml
[build-system]
requires = ["setuptools>=68.0"]
build-backend = "setuptools.build_meta"

[project]
name = "axon-agent"
version = "0.1.0"
description = "Autonomous AI coding agent harness on Claude Agent SDK"
requires-python = ">=3.12"
dependencies = [
    "claude-agent-sdk>=0.1.25",
    "click>=8.0",
    "httpx>=0.28",
    "pydantic>=2.12",
    "pydantic-settings>=2.12",
    "python-dotenv>=1.0",
    "mcp>=1.26",
    "fastapi>=0.109",
    "uvicorn>=0.27",
]

[project.scripts]
axon-agent = "axon_agent.cli:main"

[tool.setuptools.packages.find]
where = ["src"]

[tool.setuptools.package-data]
"axon_agent" = ["prompts/*.md", "py.typed", "dashboard/static/**/*"]
```

Файлы:
- `pyproject.toml` — новый
- `src/axon_agent/__init__.py` — версия, публичный API
- `src/axon_agent/__main__.py` — `python -m axon_agent`
- `src/axon_agent/py.typed` — PEP 561 маркер

---

## Шаг 2: Миграция модулей в src layout

Порядок по графу зависимостей (от листьев к корню):

| Откуда | Куда | Зависимости |
|--------|------|-------------|
| `security.py` | `src/axon_agent/security/hooks.py` | stdlib + SDK types |
| `progress.py` | `src/axon_agent/core/progress.py` | stdlib |
| `mcp_config.py` | `src/axon_agent/mcp/config.py` | os.environ |
| `config.py` | `src/axon_agent/config.py` | pydantic |
| `recovery.py` | `src/axon_agent/core/recovery.py` | stdlib |
| `context_manager.py` | `src/axon_agent/core/context.py` | stdlib |
| `session_state.py` | `src/axon_agent/core/state.py` | stdlib |
| `prompts.py` | `src/axon_agent/core/prompts.py` | pathlib |
| `agents/definitions.py` | `src/axon_agent/agents/definitions.py` | mcp/ |
| `client.py` | `src/axon_agent/core/client.py` | mcp/, agents/, security/, core/ |
| `agent.py` → разделить | `src/axon_agent/core/session.py` + `src/axon_agent/core/runner.py` | core/client |
| `prompts/*.md` | `src/axon_agent/prompts/*.md` | data files |

**agent.py (30KB) разделяется на два модуля:**
- `core/session.py` (~200 строк) — `run_agent_session()`, `SessionResult`, сигнальные константы
- `core/runner.py` (~400 строк) — `run_autonomous_agent()`, цикл итераций, пауза/восстановление

При миграции:
- Обновить все импорты: `from module import X` → `from axon_agent.module import X`
- Промпты загружать через `importlib.resources` для совместимости с pip install
- Не удалять старые файлы до полной миграции

---

## Шаг 3: CLI на Click

Файл: `src/axon_agent/cli.py`

```
axon-agent run     — solo-режим (текущее поведение)
  --team ENG       — ключ команды
  --model haiku    — модель оркестратора
  --max-iterations — лимит итераций
  --skip-preflight — пропустить проверки

axon-agent team    — командный режим (НОВОЕ)
  --team ENG       — ключ команды
  --workers 3      — количество параллельных воркеров
  --model haiku    — модель
  --max-tasks      — макс. задач

axon-agent health  — проверка здоровья MCP серверов
axon-agent config  — дамп конфигурации (--json, --show-secrets)

# Внутренняя (hidden) команда, вызывается координатором:
axon-agent worker  — запуск одного воркера в subprocess
  --worker-id      — ID воркера
  --team           — ключ команды
  --project-dir    — рабочая директория
  --model          — модель
```

---

## Шаг 4: Командный модуль (team/)

### Архитектура

```
axon-agent team --team ENG --workers 3
        │
        ▼
  TeamCoordinator (основной процесс)
    1. Подключается к Task MCP → получает Todo задачи
    2. Спавнит N воркеров как subprocess
    3. Мониторит прогресс через Task MCP
    4. Когда все Done → Telegram итог → завершение
        │
   asyncio.create_subprocess_exec
   ┌────┼────┐
   ▼    ▼    ▼
Worker Worker Worker  (каждый — отдельный subprocess)
  │      │      │
  ▼      ▼      ▼
Task MCP Server (общая очередь задач)
```

### Почему subprocess

- Каждый воркер = отдельный `ClaudeSDKClient` с изолированным контекстным окном
- Crash одного не валит остальных
- Точно как в Claude Code: каждый teammate = отдельный CLI процесс

### Новые файлы

**`src/axon_agent/team/protocol.py`** — типы данных:
- `TeamConfig(team, project_dir, model, num_workers, poll_interval)`
- `WorkerStatus(worker_id, status, current_task, message)`
- `TeamResult(completed, failed, duration_seconds)`

**`src/axon_agent/team/task_queue.py`** — абстракция над Task MCP:
- Прямой SSE-доступ к Task MCP через `mcp` Python клиент
- `get_next_task()` — получить Todo задачу по приоритету
- `claim_task(issue_id)` — атомарный захват (transition → In Progress + comment-маркер)
- `complete_task(issue_id)` — отметить Done
- `add_comment(issue_id, body)` — коммуникация

**`src/axon_agent/team/worker.py`** — автономный рабочий:
- Цикл: claim задачу → создать ClaudeSDKClient → выполнить → Done → repeat
- Выходит когда нет задач (exit code 0) или ошибка (exit code 1)
- Пишет статус в stdout (JSON-lines для координатора)

**`src/axon_agent/team/coordinator.py`** — лидер:
- Спавнит N subprocess через `asyncio.create_subprocess_exec`
- Мониторит stdout воркеров + состояние задач в Task MCP
- При crash воркера: перезапуск с backoff
- При завершении всех задач: Telegram-итог, shutdown

**`src/axon_agent/prompts/team_worker_prompt.md`** — промпт воркера:
- Фокус на одну задачу (не оркестрирует, не выбирает)
- Получает полный контекст задачи в промпте
- Использует coding subagent для реализации

### Атомарный захват задач

```
1. Task_ListIssues(state="Todo") → отсортировать по приоритету
2. Task_GetIssue(id) → проверить что ещё Todo
3. Task_AddComment(id, "__CLAIM__{worker_id}__") → маркер
4. Task_TransitionIssueState(id, "In Progress")
5. Если race condition (уже In Progress) → пропустить, взять следующую
```

---

## Шаг 5: Dashboard — встроенный в пакет, запускается с агентом

### Концепция

Dashboard и analytics API включаются в пакет и автоматически стартуют при `axon-agent run` или `axon-agent team`. Агент работает — dashboard показывает прогресс в реальном времени.

### Архитектура

```
axon-agent run --team ENG
    │
    ├── Основной процесс: агент (ClaudeSDKClient)
    │
    └── Фоновый поток: FastAPI (uvicorn)
        ├── /api/analytics/* — KPI эндпоинты
        ├── /api/issues/*    — CRUD задач
        ├── /api/sessions/*  — Session replay
        └── /*               — React SPA (static files)
```

При старте: `uvicorn` запускается в `threading.Thread(daemon=True)` на порту 8003 (настраиваемо). Открывается в браузере автоматически (или `--no-dashboard` чтобы пропустить).

### Миграция файлов

| Откуда | Куда |
|--------|------|
| `analytics_server/server.py` | `src/axon_agent/dashboard/api.py` |
| `analytics_server/sessions_router.py` | `src/axon_agent/dashboard/sessions.py` |
| `dashboard/dist/` (pre-built) | `src/axon_agent/dashboard/static/` |

### Новые файлы

**`src/axon_agent/dashboard/__init__.py`** — запуск dashboard сервера:
```python
def start_dashboard(port: int = 8003) -> threading.Thread:
    """Запускает FastAPI + static dashboard в фоновом потоке."""
    thread = threading.Thread(
        target=uvicorn.run,
        args=(app,),
        kwargs={"host": "0.0.0.0", "port": port, "log_level": "warning"},
        daemon=True,
    )
    thread.start()
    return thread
```

**`src/axon_agent/dashboard/api.py`** — FastAPI приложение (из `analytics_server/server.py`):
- Добавить `StaticFiles` mount для React SPA
- Обновить импорты на `axon_agent.dashboard.sessions`
- Убрать `analytics_server/requirements.txt` (зависимости в pyproject.toml)

**React dashboard** (`dashboard/` в корне):
- Исходники остаются в `dashboard/src/` для разработки (`npm run dev`)
- `npm run build` генерирует `dashboard/dist/`
- При `pip install -e .` — скрипт копирует `dashboard/dist/` → `src/axon_agent/dashboard/static/`
- При продакшн-сборке статика включается в wheel

### CLI интеграция

```
axon-agent run     — запускает агент + dashboard (по умолчанию)
  --no-dashboard   — без dashboard
  --dashboard-port — порт (по умолчанию 8003)

axon-agent team    — запускает координатор + dashboard
  --no-dashboard   — без dashboard

axon-agent dashboard  — только dashboard (без агента)
  --port 8003      — порт
```

---

## Шаг 6: Миграция интеграций и мониторинга

| Откуда | Куда |
|--------|------|
| `github_integration.py` | `src/axon_agent/integrations/github.py` |
| `telegram_reports.py` | `src/axon_agent/integrations/telegram.py` |
| `health_check.py` | `src/axon_agent/monitoring/health.py` |
| `heartbeat.py` | `src/axon_agent/monitoring/heartbeat.py` |
| `self_diagnostics.py` | `src/axon_agent/monitoring/diagnostics.py` |
| `session_recorder.py` | `src/axon_agent/monitoring/recorder.py` |
| `preflight.py` | `src/axon_agent/monitoring/preflight.py` |

---

## Шаг 7: Обновление тестов

- Обновить все импорты в `tests/` на `from axon_agent.xxx import yyy`
- Перенести `test_security.py` (корень) → `tests/unit/test_security.py`
- Добавить: `tests/unit/test_coordinator.py`, `tests/unit/test_worker.py`
- Добавить: `tests/integration/test_team_workflow.py`
- Обновить `pytest.ini` и `Makefile`

---

## Шаг 8: Очистка

**Удалить:**
- `autonomous_agent_demo.py` — заменён CLI
- `analytics_server/` — перенесён в `src/axon_agent/dashboard/`
- `backups/` — устаревшие данные (3 файла, 54KB)
- `screenshots/` — артефакты тестирования (92 файла, 19MB)
- `mobile-analytics-dark.png` — скриншот в корне
- `AgentHarnessDiagram.png` → `docs/` (если нужен)
- Старые .py файлы из корня (после полной миграции в src/)

**Оставить вне пакета:**
- `dashboard/` (React исходники) — для `npm run dev` / `npm run build`
- `scripts/` — утилиты (backup, lint-gate, complexity)
- `.agent/` — runtime данные
- `tests/` — тесты

---

## Целевая структура

```
your-claude-engineer/
├── pyproject.toml
├── README.md
├── CLAUDE.md
├── LICENSE
├── .env.example
├── .mcp.json
├── Makefile
│
├── src/
│   └── axon_agent/
│       ├── __init__.py
│       ├── __main__.py
│       ├── cli.py
│       ├── config.py
│       ├── py.typed
│       │
│       ├── core/
│       │   ├── __init__.py
│       │   ├── session.py      ← agent.py (run_agent_session)
│       │   ├── runner.py       ← agent.py (run_autonomous_agent)
│       │   ├── client.py       ← client.py
│       │   ├── context.py      ← context_manager.py
│       │   ├── state.py        ← session_state.py
│       │   ├── recovery.py     ← recovery.py
│       │   ├── prompts.py      ← prompts.py
│       │   └── progress.py     ← progress.py
│       │
│       ├── agents/
│       │   ├── __init__.py
│       │   └── definitions.py  ← agents/definitions.py
│       │
│       ├── mcp/
│       │   ├── __init__.py
│       │   └── config.py       ← mcp_config.py
│       │
│       ├── security/
│       │   ├── __init__.py
│       │   └── hooks.py        ← security.py
│       │
│       ├── team/               ← НОВЫЙ
│       │   ├── __init__.py
│       │   ├── coordinator.py
│       │   ├── worker.py
│       │   ├── protocol.py
│       │   └── task_queue.py
│       │
│       ├── dashboard/          ← analytics_server/ + React static
│       │   ├── __init__.py     (start_dashboard(), FastAPI mount)
│       │   ├── api.py          ← analytics_server/server.py
│       │   ├── sessions.py     ← analytics_server/sessions_router.py
│       │   └── static/         ← dashboard/dist/ (pre-built React SPA)
│       │
│       ├── integrations/
│       │   ├── __init__.py
│       │   ├── github.py       ← github_integration.py
│       │   └── telegram.py     ← telegram_reports.py
│       │
│       ├── monitoring/
│       │   ├── __init__.py
│       │   ├── health.py       ← health_check.py
│       │   ├── heartbeat.py    ← heartbeat.py
│       │   ├── diagnostics.py  ← self_diagnostics.py
│       │   ├── recorder.py     ← session_recorder.py
│       │   └── preflight.py    ← preflight.py
│       │
│       └── prompts/
│           ├── orchestrator_prompt.md
│           ├── coding_agent_prompt.md
│           ├── task_agent_prompt.md
│           ├── telegram_agent_prompt.md
│           ├── reviewer_prompt.md
│           ├── devops_agent_prompt.md
│           ├── testing_agent_prompt.md
│           ├── security_agent_prompt.md
│           ├── research_agent_prompt.md
│           ├── planner_agent_prompt.md
│           ├── execute_task.md
│           ├── continuation_task.md
│           └── team_worker_prompt.md  ← НОВЫЙ
│
├── tests/                      ← обновить импорты
├── dashboard/                  ← React исходники (npm run build → static/)
└── scripts/                    ← без изменений
```

---

## Верификация

1. **Установка:** `pip install -e .` → `axon-agent --version` работает
2. **Solo mode:** `axon-agent run --team ENG --max-iterations 1` → агент + dashboard стартуют, задача выполняется
3. **Team mode:** `axon-agent team --team ENG --workers 2 --max-tasks 2` → координатор + dashboard + 2 воркера
4. **Dashboard:** `axon-agent dashboard` → открывается http://localhost:8003, показывает задачи и аналитику
5. **Solo без dashboard:** `axon-agent run --no-dashboard` → только агент
6. **Health:** `axon-agent health` → проверяет MCP серверы
7. **Config:** `axon-agent config --json` → дамп конфигурации
8. **Тесты:** `pytest tests/` → все тесты проходят с новыми импортами
9. **Очистка:** `git status` → нет старых .py в корне, нет analytics_server/, нет backups/
