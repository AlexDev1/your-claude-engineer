# axon_agent

Основной Python-пакет Axon Agent — автономного AI-агента на Claude Agent SDK.

## Структура пакета

```
axon_agent/
├── cli.py              # CLI (Click): run, team, health, config, dashboard
├── config.py           # AppConfig (Pydantic Settings) — все параметры через env vars
├── __init__.py         # __version__ = "0.1.0"
├── __main__.py         # python -m axon_agent
│
├── agents/             # Определения субагентов
│   └── definitions.py  # create_agent_definitions() → 9 AgentDefinition
│
├── core/               # Ядро — клиент, сессии, цикл агента
│   ├── client.py       # create_client() → ClaudeSDKClient с MCP + security
│   ├── runner.py       # run_autonomous_agent() — основной цикл с итерациями
│   ├── session.py      # run_agent_session() → SessionResult
│   ├── context.py      # ContextManager — бюджет токенов (85% порог)
│   ├── state.py        # SessionStateManager — checkpoint в .agent/session_state.json
│   ├── recovery.py     # RecoveryManager + GracefulDegradation
│   ├── progress.py     # ProgressTracker — отслеживание прогресса сессии
│   └── prompts.py      # load_prompt() + MemoryManager
│
├── team/               # Командный режим с параллельными воркерами
│   ├── coordinator.py  # run_team(TeamConfig) → TeamResult
│   ├── worker.py       # run_worker() — подпроцесс, JSON-line события
│   ├── task_queue.py   # TaskQueue — общая очередь из Task MCP
│   └── protocol.py     # TeamConfig, WorkerStatus, TaskResult
│
├── dashboard/          # Встроенный веб-дашборд
│   ├── api.py          # FastAPI: analytics, issues CRUD, session replay
│   ├── sessions.py     # GET /api/sessions — replay эндпоинты
│   └── static/         # SPA frontend
│
├── monitoring/         # Мониторинг и диагностика
│   ├── health.py       # check_mcp_health() — проверка MCP серверов
│   ├── heartbeat.py    # detect_stale_tasks() — зависшие задачи
│   ├── preflight.py    # run_preflight_checks() — проверки перед стартом
│   ├── recorder.py     # EventRecorder — запись событий для аналитики
│   └── diagnostics.py  # collect_diagnostics() — системная информация
│
├── integrations/       # Внешние интеграции
│   ├── github.py       # GitHubIntegration — PR, issues sync
│   └── telegram.py     # TelegramReporter — rich отчёты
│
├── mcp/                # MCP конфигурация
│   └── config.py       # MCP URLs, tool definitions (Playwright, Task, Telegram)
│
├── security/           # Безопасность
│   └── hooks.py        # bash_security_hook() + ALLOWED_COMMANDS (50+ команд)
│
└── prompts/            # Системные промпты (markdown)
    ├── orchestrator_prompt.md    # Главный оркестратор
    ├── task_agent_prompt.md      # Управление задачами
    ├── coding_agent_prompt.md    # Реализация кода
    ├── telegram_agent_prompt.md  # Telegram уведомления
    ├── reviewer_prompt.md        # Код-ревью
    ├── devops_agent_prompt.md    # CI/CD и деплой
    ├── testing_agent_prompt.md   # Тестирование
    ├── security_agent_prompt.md  # Аудит безопасности
    ├── research_agent_prompt.md  # Исследование
    ├── planner_agent_prompt.md   # Декомпозиция задач
    ├── execute_task.md           # Промпт первой итерации
    ├── continuation_task.md      # Промпт продолжения
    └── team_worker_prompt.md     # Промпт воркера в team mode
```

## Quick Start для разработчиков

```bash
# Установка в dev-режиме
pip install -e .

# Запуск
axon-agent run --team ENG

# Или через модуль
python -m axon_agent run --team ENG
```

## Публичный API

### CLI (`cli.py`)

Точка входа: `axon-agent` (определён в `pyproject.toml` → `project.scripts`).

| Команда | Описание |
|---------|----------|
| `run` | Solo режим — один агент, итерации с checkpoint'ами |
| `team` | Командный режим — координатор + N параллельных воркеров |
| `health` | Проверка доступности MCP серверов |
| `config` | Вывод текущей конфигурации |
| `dashboard` | Запуск дашборда аналитики без агента |

### Конфигурация (`config.py`)

```python
from axon_agent.config import get_config, AppConfig

config = get_config()  # Singleton, читает из .env и env vars
print(config.task_mcp_url)
print(config.dump())  # Человекочитаемый вывод (секреты замаскированы)
```

### Агенты (`agents/definitions.py`)

```python
from axon_agent.agents.definitions import create_agent_definitions

agents = create_agent_definitions()
# Returns: dict[str, AgentDefinition]
# Keys: task, coding, telegram, reviewer, devops, testing, security, research, planner
```

### Ядро (`core/`)

```python
from axon_agent.core.runner import run_autonomous_agent
from axon_agent.core.session import run_agent_session
from axon_agent.core.client import create_client

# Основной цикл
await run_autonomous_agent(
    project_dir="/path/to/project",
    model="haiku",
    team="ENG",
    max_iterations=10,
)

# Одна сессия
client = create_client(project_dir, model="sonnet")
result = await run_agent_session(client, message="...")
# result.status: SESSION_CONTINUE | SESSION_COMPLETE | SESSION_ERROR | SESSION_CONTEXT_LIMIT
```

### Командный режим (`team/`)

```python
from axon_agent.team.coordinator import run_team
from axon_agent.team.protocol import TeamConfig

config = TeamConfig(
    team="ENG",
    workers=3,
    model="haiku",
    project_dir="/path/to/project",
)
result = await run_team(config)
# result: TeamResult with per-worker stats
```

### Дашборд (`dashboard/`)

```python
from axon_agent.dashboard import start_dashboard

thread = start_dashboard(port=8003)  # Daemon thread with FastAPI + Uvicorn
```

## 9 специализированных агентов

| Агент | Модель по умолчанию | Env var для модели | Назначение |
|-------|---------------------|--------------------|------------|
| **task** | Haiku | `TASK_AGENT_MODEL` | Управление проектами и задачами через Task MCP |
| **coding** | Sonnet | `CODING_AGENT_MODEL` | Реализация, Playwright тесты, Git |
| **telegram** | Haiku | `TELEGRAM_AGENT_MODEL` | Уведомления через Telegram MCP |
| **reviewer** | Haiku | `REVIEWER_MODEL` | Код-ревью: APPROVE / REQUEST_CHANGES |
| **devops** | Haiku | `DEVOPS_AGENT_MODEL` | CI/CD, Docker, деплой |
| **testing** | Sonnet | `TESTING_AGENT_MODEL` | Unit/integration/E2E тесты |
| **security** | Haiku | `SECURITY_AGENT_MODEL` | Аудит безопасности, сканирование зависимостей |
| **research** | Haiku | `RESEARCH_AGENT_MODEL` | Исследование перед реализацией |
| **planner** | Sonnet | `PLANNER_AGENT_MODEL` | Декомпозиция задач на подзадачи |

Допустимые значения моделей: `haiku`, `sonnet`, `opus`, `inherit` (наследует от оркестратора).
