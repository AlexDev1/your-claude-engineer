# Axon Agent

**Автономный AI-инженер, который управляет проектами, пишет код и сообщает о прогрессе.**

Axon Agent — фреймворк для длительных задач на базе [Claude Agent SDK](https://github.com/anthropics/claude-code/tree/main/agent-sdk-python), который превращает Claude в долго работающего инженера, способного решать сложные многоэтапные задачи.

Полный рабочий процесс разработки с 9 специализированными субагентами:

- **Управление проектом**: Отслеживает работу через самохостируемый Task MCP Server (PostgreSQL), разбивает фичи на задачи и обновляет статусы
- **Реализация кода**: Пишет, тестирует и итерирует код с UI-верификацией через Playwright
- **Код-ревью**: Автоматическое ревью перед коммитом (APPROVE / REQUEST_CHANGES)
- **Контроль версий**: Коммитит изменения в локальный git
- **Тестирование**: Unit, integration и E2E тесты
- **Безопасность**: Аудит кода и сканирование зависимостей
- **DevOps**: CI/CD, Docker, деплой
- **Коммуникация**: Уведомления о прогрессе через Telegram
- **Командный режим**: Параллельная работа нескольких воркеров с общей очередью задач

## Ключевые возможности

- **Длительная автономность**: Свежая сессия каждую итерацию — без исчерпания контекстного окна
- **9 специализированных агентов**: Task, Coding, Reviewer, Telegram, DevOps, Testing, Security, Research, Planner
- **Командный режим**: Параллельные воркеры с координатором, общей очередью и автоматическим рестартом
- **Встроенный дашборд**: FastAPI аналитика (velocity, efficiency, bottlenecks) на порту 8003
- **Самохостируемое управление задачами**: PostgreSQL-бэкенд с полным контролем над данными
- **Восстановление после сбоев**: Checkpoint сессии, возобновление с фазы прерывания
- **Контекстный бюджет**: Автостоп при 85% заполнения окна (180K токенов)
- **Фазы сессии**: ORIENT → RESEARCH → PLANNING → IMPLEMENTATION → TESTING → REVIEW → COMMIT
- **Браузерное тестирование**: Playwright MCP для автоматической UI-верификации
- **Конфигурация моделей**: Выбор модели для каждого агента (Haiku, Sonnet, Opus)
- **OAuth 2.0 + API Key**: Двойная аутентификация для MCP серверов

## Требования

> Не работает на Windows из-за ограничений Claude Agent SDK. Используйте WSL или Linux VM!

### 1. Установка Claude Code CLI и пакета

```bash
# Установка Claude Code CLI (требуется последняя версия)
npm install -g @anthropic-ai/claude-code

# Установка Axon Agent
pip install -e .
```

### 2. Развёртывание MCP серверов

MCP серверы (Task + Telegram) развёрнуты в отдельном репозитории: **[AxonCode/axon-mcp](https://github.com/AxonCode/axon-mcp)**

Следуйте инструкциям в axon-mcp для деплоя серверов, затем вернитесь сюда для настройки агента.

### 3. Настройка окружения

```bash
cp .env.example .env

# Отредактируйте .env:
# TASK_MCP_URL=https://mcp.yourdomain.com/task/sse
# TELEGRAM_MCP_URL=https://mcp.yourdomain.com/telegram/sse
# MCP_API_KEY=mcp_your_api_key
```

### 4. Проверка установки

```bash
claude --version
axon-agent health   # Проверка подключения к MCP серверам
axon-agent config   # Просмотр текущей конфигурации
```

## Быстрый старт

```bash
# Solo режим — агент работает в текущей директории
axon-agent run

# Указать команду и ограничить итерации
axon-agent run --team ENG --max-iterations 5

# Использовать Opus для оркестратора
axon-agent run --model opus

# Командный режим — 3 параллельных воркера
axon-agent team --team ENG --workers 3

# Запустить дашборд аналитики отдельно
axon-agent dashboard --port 8003
```

## Как это работает

### Мультиагентная архитектура

```
┌─────────────────────────────────────────────────────────────────────┐
│                    МУЛЬТИАГЕНТНАЯ АРХИТЕКТУРА                        │
├─────────────────────────────────────────────────────────────────────┤
│                                                                     │
│                      ┌─────────────────┐                            │
│                      │   ОРКЕСТРАТОР   │  (Haiku по умолчанию)      │
│                      │   Координирует  │                            │
│                      └────────┬────────┘                            │
│                               │                                     │
│     ┌──────────┬──────────┬───┴───┬──────────┬──────────┐           │
│     │          │          │       │          │          │           │
│ ┌───▼────┐ ┌──▼───┐ ┌────▼──┐ ┌──▼───┐ ┌───▼────┐ ┌──▼───┐       │
│ │  TASK  │ │CODING│ │REVIEW │ │ TELE │ │ DEVOPS │ │ TEST │       │
│ │(Haiku) │ │(Son.)│ │(Haiku)│ │(Hai.)│ │(Haiku) │ │(Son.)│       │
│ └───┬────┘ └──┬───┘ └───────┘ └──┬───┘ └────────┘ └──────┘       │
│     │         │                   │                                │
│ Task MCP   Playwright        Telegram MCP                          │
│ (Postgres) + Local Git        (Bot API)                            │
│                                                                     │
│ ┌──────────┐ ┌──────────┐ ┌──────────┐                              │
│ │ SECURITY │ │ RESEARCH │ │ PLANNER  │                              │
│ │ (Haiku)  │ │ (Haiku)  │ │ (Sonnet) │                              │
│ └──────────┘ └──────────┘ └──────────┘                              │
│                                                                     │
│     ┌──────────────────────────────────────────────┐                │
│     │         ПРОЕКТ (Рабочая директория)           │                │
│     │              cwd с Git                        │                │
│     └──────────────────────────────────────────────┘                │
└─────────────────────────────────────────────────────────────────────┘
```

### Командный режим

```
┌─────────────────────────────────────────────────────────┐
│                     TEAM MODE                            │
├─────────────────────────────────────────────────────────┤
│                                                         │
│  ┌─────────────┐     ┌──────────────────────────┐       │
│  │ COORDINATOR │────▶│   Общая очередь задач    │       │
│  │  (главный)  │     │  (Task MCP → TaskQueue)  │       │
│  └──────┬──────┘     └──────────────────────────┘       │
│         │                                               │
│   ┌─────┼──────────────┐                                │
│   │     │              │                                │
│ ┌─▼──┐ ┌▼───┐ ┌─────┐ ┌──────────┐                     │
│ │ W1 │ │ W2 │ │ W3  │ │DASHBOARD │                     │
│ │SDK │ │SDK │ │SDK  │ │ :8003    │                     │
│ └────┘ └────┘ └─────┘ └──────────┘                     │
│                                                         │
│  Каждый воркер = независимый axon-agent worker          │
│  Мониторинг здоровья + авторестарт (до 3 раз)           │
└─────────────────────────────────────────────────────────┘
```

### Агенты

| Агент | Модель | Назначение |
|-------|--------|------------|
| **Task** | Haiku | Управление задачами, приоритезация, отслеживание через Task MCP |
| **Coding** | Sonnet | Реализация фич, Playwright тесты, Git коммиты |
| **Reviewer** | Haiku | Код-ревью перед коммитом: APPROVE или REQUEST_CHANGES |
| **Telegram** | Haiku | Уведомления о прогрессе через Telegram Bot API |
| **DevOps** | Haiku | CI/CD, Docker, деплой, инфраструктура |
| **Testing** | Sonnet | Unit, integration и E2E тестирование |
| **Security** | Haiku | Аудит безопасности, сканирование зависимостей |
| **Research** | Haiku | Исследование перед реализацией |
| **Planner** | Sonnet | Декомпозиция задач на подзадачи |

Модели настраиваются через переменные окружения: `TASK_AGENT_MODEL`, `CODING_AGENT_MODEL` и т.д. Допустимые значения: `haiku`, `sonnet`, `opus`, `inherit`.

### Фазы сессии

Каждая итерация агента проходит через фазы с checkpoint'ами для восстановления:

1. **ORIENT** — Понимание текущей задачи
2. **RESEARCH** — Исследование кодовой базы
3. **PLANNING** — Декомпозиция задачи
4. **IMPLEMENTATION** — Написание кода
5. **TESTING** — Запуск тестов
6. **REVIEW** — Код-ревью
7. **COMMIT** — Git коммит

## CLI справочник

| Команда | Опции | Описание |
|---------|-------|----------|
| `axon-agent run` | `--team`, `--model`, `--max-iterations`, `--skip-preflight`, `--no-dashboard`, `--dashboard-port` | Solo режим |
| `axon-agent team` | `--team`, `--workers`, `--model`, `--max-tasks`, `--no-dashboard`, `--dashboard-port` | Командный режим |
| `axon-agent health` | — | Проверка MCP серверов |
| `axon-agent config` | `--json`, `--show-secrets` | Просмотр конфигурации |
| `axon-agent dashboard` | `--port` | Запуск дашборда отдельно |

<details>
<summary><strong>Справочник переменных окружения</strong></summary>

| Переменная | Описание | По умолчанию |
|------------|----------|--------------|
| `TASK_MCP_URL` | URL Task MCP Server | `http://localhost:8001/sse` |
| `TELEGRAM_MCP_URL` | URL Telegram MCP Server | `http://localhost:8002/sse` |
| `MCP_API_KEY` | API ключ для MCP аутентификации | — |
| `ORCHESTRATOR_MODEL` | Модель оркестратора | `haiku` |
| `TASK_AGENT_MODEL` | Модель Task агента | `haiku` |
| `CODING_AGENT_MODEL` | Модель Coding агента | `sonnet` |
| `TELEGRAM_AGENT_MODEL` | Модель Telegram агента | `haiku` |
| `MAX_CONTEXT_TOKENS` | Бюджет контекстного окна | `180000` |
| `HEARTBEAT_INTERVAL_MINUTES` | Интервал проверки зависших задач | `5` |
| `STALE_THRESHOLD_HOURS` | Часов без обновления = задача зависла | `2.0` |
| `GITHUB_TOKEN` | GitHub PAT для интеграции | — |
| `GITHUB_REPO` | Репозиторий (owner/repo) | — |

</details>

## Структура проекта

```
your-claude-engineer/
├── src/axon_agent/              # Основной пакет
│   ├── cli.py                   # CLI точка входа (Click)
│   ├── config.py                # Конфигурация (Pydantic Settings)
│   ├── __init__.py              # Версия и экспорты
│   ├── __main__.py              # python -m axon_agent
│   │
│   ├── agents/                  # Определения агентов
│   │   └── definitions.py       # 9 агентов с конфигурацией моделей
│   │
│   ├── core/                    # Ядро агента
│   │   ├── client.py            # Claude SDK клиент + MCP серверы
│   │   ├── runner.py            # Основной цикл (run_autonomous_agent)
│   │   ├── session.py           # Раннер одной сессии
│   │   ├── context.py           # Бюджет контекстного окна
│   │   ├── state.py             # Персистентное состояние
│   │   ├── recovery.py          # Восстановление после ошибок
│   │   ├── progress.py          # Отслеживание прогресса
│   │   └── prompts.py           # Загрузка промптов
│   │
│   ├── team/                    # Командный режим
│   │   ├── coordinator.py       # Координатор (спавнит воркеров)
│   │   ├── worker.py            # Воркер-подпроцесс
│   │   ├── task_queue.py        # Общая очередь задач
│   │   └── protocol.py          # Типы данных (TeamConfig, WorkerStatus)
│   │
│   ├── dashboard/               # Веб-дашборд аналитики
│   │   ├── api.py               # FastAPI сервер
│   │   ├── sessions.py          # Session replay (ENG-75)
│   │   └── static/              # Frontend (HTML/CSS/JS)
│   │
│   ├── monitoring/              # Мониторинг и диагностика
│   │   ├── health.py            # Health checks MCP серверов
│   │   ├── heartbeat.py         # Детекция зависших задач
│   │   ├── preflight.py         # Pre-flight проверки
│   │   ├── recorder.py          # Запись событий
│   │   └── diagnostics.py       # Диагностическая информация
│   │
│   ├── integrations/            # Внешние интеграции
│   │   ├── github.py            # GitHub PR и issues
│   │   └── telegram.py          # Telegram rich reports
│   │
│   ├── mcp/                     # MCP конфигурация
│   │   └── config.py            # URL серверов и определения инструментов
│   │
│   ├── security/                # Безопасность
│   │   └── hooks.py             # Allowlist Bash команд
│   │
│   └── prompts/                 # Системные промпты агентов
│       ├── orchestrator_prompt.md
│       ├── task_agent_prompt.md
│       ├── coding_agent_prompt.md
│       ├── telegram_agent_prompt.md
│       ├── reviewer_prompt.md
│       ├── devops_agent_prompt.md
│       ├── testing_agent_prompt.md
│       ├── security_agent_prompt.md
│       ├── research_agent_prompt.md
│       ├── planner_agent_prompt.md
│       ├── execute_task.md
│       ├── continuation_task.md
│       └── team_worker_prompt.md
│
├── pyproject.toml               # Метаданные пакета и зависимости
├── .env.example                 # Пример переменных окружения
├── .project.json                # Контекст текущего проекта (slug, team)
├── CLAUDE.md                    # Инструкции для Claude Code
└── README.md                    # Этот файл
```

## Кастомизация

### Изменение поведения агентов

Отредактируйте соответствующий промпт в `src/axon_agent/prompts/`. Каждый агент имеет свой `.md` файл с системным промптом.

### Изменение разрешённых команд

Отредактируйте `ALLOWED_COMMANDS` в `src/axon_agent/security/hooks.py`.

### Конфигурация моделей

Через переменные окружения или флаг `--model`:

```bash
# Через env vars (в .env)
ORCHESTRATOR_MODEL=opus
CODING_AGENT_MODEL=sonnet
TASK_AGENT_MODEL=haiku

# Через CLI (устанавливает модель оркестратора)
axon-agent run --model opus
```

### Добавление нового агента

1. Добавьте промпт в `src/axon_agent/prompts/new_agent_prompt.md`
2. Добавьте определение в `src/axon_agent/agents/definitions.py`
3. Добавьте env var для модели в `src/axon_agent/config.py`

## MCP серверы

MCP серверы развёрнуты отдельно — см. [AxonCode/axon-mcp](https://github.com/AxonCode/axon-mcp).

| Сервер | Транспорт | Назначение |
|--------|-----------|------------|
| **Task MCP** | SSE | Управление проектами/задачами (PostgreSQL) |
| **Telegram MCP** | SSE | Уведомления через Telegram Bot API |
| **Playwright** | stdio | Браузерная автоматизация для UI-тестирования |

## Модель безопасности

Многоуровневая защита (см. `src/axon_agent/security/hooks.py` и `src/axon_agent/core/client.py`):

1. **OAuth 2.0 + API Key**: Обрабатывается MCP серверами ([axon-mcp](https://github.com/AxonCode/axon-mcp))
2. **Песочница на уровне ОС**: Bash-команды в изолированном окружении
3. **Ограничения файловой системы**: Операции ограничены директорией проекта
4. **Allowlist Bash**: Разрешены только определённые команды (50+)
5. **Валидация опасных команд**: `rm`, `chmod`, `pkill` проходят дополнительные проверки
6. **MCP-разрешения**: Инструменты явно разрешены в настройках безопасности
7. **Truncation hook**: Обрезка больших выводов инструментов (>5000 символов)

## Дашборд

Встроенный веб-дашборд запускается автоматически (порт 8003) или отдельно:

```bash
axon-agent dashboard --port 8003
```

**Эндпоинты:**
- `/api/analytics/velocity` — Скорость выполнения задач
- `/api/analytics/efficiency` — Success rate, среднее время
- `/api/analytics/bottlenecks` — Зависшие задачи
- `/api/issues` — CRUD операции с задачами
- `/api/sessions` — Session replay

## Устранение неполадок

**`axon-agent: command not found`**
Убедитесь, что пакет установлен: `pip install -e .`

**`axon-agent health` показывает ошибки**
Проверьте URL MCP серверов в `.env` и что серверы запущены.

**"Command blocked by security hook"**
Агент попытался выполнить запрещённую команду. Добавьте в `ALLOWED_COMMANDS` в `src/axon_agent/security/hooks.py`.

**Воркер не стартует в team mode**
Проверьте, что `axon-agent worker` доступен (пакет установлен через `pip install -e .`).

**Контекстное окно исчерпано**
Агент автоматически останавливается при 85% заполнения и продолжает в новой сессии. Увеличьте `MAX_CONTEXT_TOKENS` если нужно.

**401 Unauthorized к MCP серверам**
Проверьте `MCP_API_KEY` в `.env`. Создайте ключ через `admin_cli.py` в axon-mcp.

## Лицензия

MIT License — см. [LICENSE](LICENSE) для деталей.
