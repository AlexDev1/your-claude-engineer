# CLAUDE.md
**ВАЖНО**: вы всегда должны отвечать на русском языке!
Этот файл предоставляет руководство для Claude Code (claude.ai/code) при работе с кодом в этом репозитории.

## Обзор

Axon Agent — автономная оболочка AI-агента на [Claude Agent SDK](https://github.com/anthropics/claude-code/tree/main/agent-sdk-python). Запускает задаче-ориентированные сессии кодирования с мультиагентной оркестрацией: 9 специализированных субагентов, командный режим с параллельными воркерами и встроенный дашборд аналитики.

Агент работает в текущей директории (cwd), выбирает задачи из Task MCP Server по приоритету и выполняет их одну за другой. Поддерживает solo и team mode.

**Важно**: Это оболочка/фреймворк для запуска автономных агентов, а не традиционное приложение.

**MCP серверы**: Развёрнуты отдельно — см. [AxonCode/axon-mcp](https://github.com/AxonCode/axon-mcp).

## Команды

```bash
# Установка
pip install -e .

# Solo режим (работает в текущей директории)
axon-agent run
axon-agent run --team ENG --max-iterations 3 --model opus

# Командный режим (параллельные воркеры)
axon-agent team --team ENG --workers 3

# Утилиты
axon-agent health          # Проверка MCP серверов
axon-agent config          # Текущая конфигурация
axon-agent config --json   # Конфигурация в JSON
axon-agent dashboard       # Запуск дашборда без агента
```

## Архитектура

### Solo Mode

```
ОРКЕСТРАТОР (координирует работу, делегирует субагентам через Task tool)
    ├── TASK AGENT        → Управление задачами, приоритезация (через Task MCP Server)
    ├── CODING AGENT      → Реализация + Playwright UI тестирование + Git коммиты
    ├── REVIEWER AGENT    → Код-ревью перед коммитом (APPROVE / REQUEST_CHANGES)
    ├── TELEGRAM AGENT    → Уведомления о прогрессе (через Telegram MCP Server)
    ├── DEVOPS AGENT      → CI/CD, Docker, деплой, инфраструктура
    ├── TESTING AGENT     → Unit/integration/E2E тесты
    ├── SECURITY AGENT    → Аудит безопасности, сканирование зависимостей
    ├── RESEARCH AGENT    → Исследование перед реализацией
    └── PLANNER AGENT     → Декомпозиция задач на подзадачи
```

### Team Mode

```
COORDINATOR (axon-agent team)
    ├── WORKER 1 (axon-agent worker) → Независимая Claude SDK сессия
    ├── WORKER 2 (axon-agent worker) → Независимая Claude SDK сессия
    └── WORKER N (axon-agent worker) → Независимая Claude SDK сессия
    └── DASHBOARD (FastAPI :8003)    → Аналитика в реальном времени
```

Координатор раздаёт задачи из общей очереди, воркеры работают параллельно, каждый с собственной SDK сессией. Мониторинг здоровья воркеров + автоматический рестарт (до 3 раз).

## Ключевые файлы

Пакет находится в `src/axon_agent/`:

- `.project.json` — Контекст текущего проекта (slug, team) — используется для определения проекта и команды при работе с задачами
- `src/axon_agent/cli.py` — CLI точка входа (Click-based): `run`, `team`, `health`, `config`, `dashboard`
- `src/axon_agent/config.py` — Централизованная конфигурация (Pydantic Settings)
- `src/axon_agent/core/runner.py` — Основной цикл агента (`run_autonomous_agent()`)
- `src/axon_agent/core/session.py` — Раннер одной сессии (`run_agent_session()`)
- `src/axon_agent/core/client.py` — Настройка SDK клиента с MCP серверами
- `src/axon_agent/core/context.py` — Управление бюджетом контекстного окна
- `src/axon_agent/core/state.py` — Персистентное состояние сессии
- `src/axon_agent/core/recovery.py` — Восстановление после ошибок, graceful degradation
- `src/axon_agent/agents/definitions.py` — Определения 9 агентов с конфигурацией моделей
- `src/axon_agent/team/coordinator.py` — Координатор команды (спавнит воркеров)
- `src/axon_agent/team/worker.py` — Воркер-подпроцесс
- `src/axon_agent/team/task_queue.py` — Общая очередь задач для воркеров
- `src/axon_agent/dashboard/api.py` — FastAPI сервер аналитики
- `src/axon_agent/security/hooks.py` — Allowlist Bash команд и хуки валидации
- `src/axon_agent/mcp/config.py` — URL MCP серверов и определения инструментов
- `src/axon_agent/monitoring/` — Health checks, heartbeat, preflight, recorder
- `src/axon_agent/prompts/` — Все системные промпты агентов и шаблоны задач

**Работа с задачами**: Перед работой с задачами читай `.project.json` — он содержит `slug` (проект) и `team` (команда), которые нужно передавать в Task MCP (например, `Task_ListIssues(project=slug, team=team)`).

**Задаче-ориентированный цикл**: Каждую итерацию агент получает следующую Todo задачу по приоритету, реализует её и отмечает как Done. Когда не остаётся задач, агент выводит `ALL_TASKS_DONE:` и останавливается.

## Ключевые паттерны

1. **Паттерн оркестратора**: Основной агент делегирует 9 специализированным субагентам, передавая контекст между ними
2. **Изоляция сессии**: Свежие сессии агента на каждой итерации для избежания исчерпания контекстного окна
3. **Выполнение на основе приоритета**: Задачи выбираются по приоритету (urgent > high > medium > low)
4. **Фазы сессии**: ORIENT → RESEARCH → PLANNING → IMPLEMENTATION → TESTING → REVIEW → COMMIT
5. **Восстановление**: Checkpoint в `.agent/session_state.json`, возобновление с фазы прерывания
6. **Контекстный бюджет**: Автостоп при 85% заполнения контекстного окна (180K токенов по умолчанию)

## Модель безопасности (Глубокая защита)

- **MCP аутентификация**: OAuth 2.0 + API ключи обрабатываются MCP серверами (см. [axon-mcp](https://github.com/AxonCode/axon-mcp))
- Песочница на уровне ОС для bash команд
- Файловая система ограничена директорией проекта
- Allowlist Bash команд в `src/axon_agent/security/hooks.py` (набор `ALLOWED_COMMANDS`)
- Хук валидации до выполнения (`bash_security_hook()`)
- MCP разрешения явно настроены
- Валидация опасных команд (`rm`, `chmod`, `pkill`)

## Точки кастомизации

- **Разрешённые bash команды**: `ALLOWED_COMMANDS` в `src/axon_agent/security/hooks.py`
- **Поведение агентов**: Промпты в `src/axon_agent/prompts/`
- **Модели**: Переменные окружения (`ORCHESTRATOR_MODEL`, `CODING_AGENT_MODEL`, `TASK_AGENT_MODEL` и т.д.) или флаг `--model`
- **Команда**: Флаг `--team` (по умолчанию: ENG)
- **Конфигурация**: `src/axon_agent/config.py` (Pydantic Settings, все параметры через env vars)
- **MCP серверы**: URL в `.env` (`TASK_MCP_URL`, `TELEGRAM_MCP_URL`)

## Предварительные требования

### MCP серверы

Разверните Task и Telegram MCP серверы из [AxonCode/axon-mcp](https://github.com/AxonCode/axon-mcp), затем настройте URL в `.env`:

```
TASK_MCP_URL=https://mcp.yourdomain.com/task/sse
TELEGRAM_MCP_URL=https://mcp.yourdomain.com/telegram/sse
MCP_API_KEY=mcp_your_api_key
```

## Ограничения

- **Windows не поддерживается** (субагенты требуют Linux/macOS; WSL работает)
- Bash heredocs заблокированы (используйте Write tool вместо этого)
