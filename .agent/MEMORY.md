# Память агента

Этот файл содержит кураторские факты, изученные между сессиями.
Агент читает это в начале сессии и обновляет в конце сессии.

---

## Структура проекта

- Основная точка входа: `agent.py` - цикл автономного агента
- Настройка клиента: `client.py` - конфигурация Claude SDK клиента
- Промпты: директория `prompts/` с markdown шаблонами
- Определения агентов: `agents/definitions.py`
- Безопасность: `security.py` - валидация bash команд
- Heartbeat: директория `heartbeat/` (Docker) и `heartbeat.py` (локальная разработка) - мониторинг застрявших задач
- Контекст: `context_manager.py` - умная загрузка контекста со сжатием промптов (уменьшение размера на 76.9%)
- Карта проекта: `.agent/PROJECT_MAP.md` - автоматически генерируемая структура проекта (ENG-33)

### Карта проекта (ENG-33)
- Автоматически генерируемый файл: `.agent/PROJECT_MAP.md`
- Скрипт генератора: `scripts/generate_project_map.py`
- Содержит: дерево директорий, ключевые файлы, зависимости, порты, последние коммиты, граф импортов
- Загружается в контекст сессии автоматически через `prompts.py:ensure_project_map()`
- Обновление после коммитов: `python scripts/generate_project_map.py`
- Проверка устаревания: регенерируется если старше 1 часа

### Dashboard (Vite + React)
- Расположение: директория `dashboard/`
- Dev сервер: http://localhost:5173
- Стилизация: Tailwind CSS
- Роутинг: React Router (`/tasks` для страницы Task Manager)
- Компоненты: `dashboard/src/components/*.jsx`
- Страницы: `dashboard/src/pages/*.jsx`
- Кастомные хуки: `dashboard/src/hooks/*.js`
  - `useKeyboardShortcuts` - обработка клавиатурных сокращений
- Kanban: drag-and-drop через `@hello-pangea/dnd`
- Шаблоны задач: Bug, Feature, Task, Epic (каждый с разными приоритетами по умолчанию)

### Analytics API
- Расположение: директория `analytics_server/`
- Dev сервер: http://localhost:8080
- Стек: Python/FastAPI
- Эндпоинты:
  - `/api/context/stats` - статистика менеджера контекста
  - `/api/context/prompts` - метрики сжатия промптов

### Тестовая инфраструктура
- Расположение: директория `tests/`
- Поддиректории: `api/`, `e2e/`, `integration/`
- Конфигурация: `pytest.ini` в корне проекта
- CI/CD: `.github/workflows/test.yml`
- Makefile таргеты: `test`, `test-api`, `test-e2e`, `test-integration`, `coverage`
- E2E фреймворк: Playwright с pytest фикстурами в `conftest.py`
- API тестирование: httpx async клиент

---

## Окружение

### Порты
- 5173: Dashboard (Vite dev сервер)
- 8003: API сервер (FastAPI)
- 8080: Analytics API (FastAPI)

### Переменные окружения
- `TASK_MCP_URL` - URL сервера управления задачами
- `TELEGRAM_MCP_URL` - URL сервера уведомлений Telegram
- `ORCHESTRATOR_MODEL` - Модель для оркестратора (haiku/sonnet/opus)
- `CODING_AGENT_MODEL` - Модель для агента кодирования
- `TASK_AGENT_MODEL` - Модель для агента задач
- `TELEGRAM_AGENT_MODEL` - Модель для агента telegram
- `HEARTBEAT_INTERVAL_MINUTES` - Контролирует частоту проверок heartbeat
- `STALE_THRESHOLD_HOURS` - Часов до того как задача считается застрявшей

---

## Зависимости

### Python
- `claude_agent_sdk` - Основной SDK для Claude агентов
- `dotenv` - Загрузка переменных окружения
- `pathlib` - Обработка путей

---

## Известные проблемы

- (пока не обнаружено)

---

## Обнаруженные паттерны

### Загрузка промптов
Используйте `prompts.py:load_prompt()` для загрузки шаблонов промптов.

### Инструменты агентов
Настройте инструменты для каждого агента в `agents/definitions.py`.

### MCP серверы
Настройка через `mcp_config.py`, URL из переменных окружения.

**Эндпоинты здоровья:**
- Task сервер: `https://mcp.axoncode.pro/task/health`
- Telegram сервер: `https://mcp.axoncode.pro/telegram/health`
- Эндпоинты здоровья исключены из аутентификации (доступны без API ключа)

**Доступные MCP инструменты:**
- `Task_GetStaleIssues` - Программное определение застрявших задач (требует развёртывания)

**Эндпоинты Task сервера:**
- `/stale-issues` - Проверка застрявших/застопорившихся задач (требует развёртывания)

**Инфраструктура аутентификации:**
- OAuth 2.0 + API key аутентификация в `task_mcp_server` и `telegram_mcp_server`
- Middleware IP whitelist: `ip_whitelist.py` в каждом сервере
- Admin CLI: `admin_cli.py` для создания/управления API ключами

**Развёртывание:**
- nginx конфигурация reverse proxy: `deploy/nginx/mcp-servers.conf`
- Включает HTTPS, rate limiting и security заголовки

---

## Dashboard

### Система тем
- Контекст темы: `dashboard/src/context/ThemeContext.jsx`
- Три доступные темы: Light, Dark, Midnight
- Компонент переключения темы: `dashboard/src/components/ThemeToggle.jsx`
- Страница настроек: `dashboard/src/pages/Settings.jsx` с выбором accent цвета
- Все компоненты используют CSS переменные из `dashboard/src/styles/themes.css`

### Хранение темы (localStorage)
- Предпочтение темы: ключ `theme-preference`
- Accent цвет: ключ `accent-color`

---

## Извлечённые уроки

- Директория скриншотов (`/screenshots`) в .gitignore - файлы-доказательства хранятся локально но не коммитятся
- Путь скриншотов для тестирования: `/home/dev/work/AxonCode/your-claude-engineer/screenshots/`
- Сжатие промптов достигло уменьшения на 76.9% при сохранении качества - агрессивное сжатие жизнеспособно

---

## История сессий

<!-- Только добавление: добавляйте новые записи в конец -->

### 2024-XX-XX - Начальная настройка
- Создана структура директории .agent/
- Добавлены шаблоны SOUL.md, MEMORY.md, SESSION_LOG.md

### 2026-02-07 - ENG-49 Comprehensive Test Suite
- Создана тестовая инфраструктура с pytest и Playwright
- Директории тестов: `tests/api/`, `tests/e2e/`, `tests/integration/`
- CI/CD пайплайн: `.github/workflows/test.yml`
- Makefile с таргетами тестов (`make test`, `make test-e2e` и т.д.)
- E2E тесты используют Playwright с conftest для фикстур
- API тесты используют httpx async клиент
- Требование покрытия: >80%

**Ключевые тестовые файлы:**
- Тесты: `tests/`
- CI workflow: `.github/workflows/test.yml`
- Конфигурация тестов: `pytest.ini`
- Makefile в корне проекта

### 2026-02-07 - ENG-48 Data Import/Export
- Коммит: 186ab40
- Реализована комплексная система импорта/экспорта данных для dashboard

**Созданные новые файлы:**
- `dashboard/src/pages/Import.jsx` - UI импорта с вкладками для JSON/CSV, Linear, GitHub
- `dashboard/src/pages/Export.jsx` - UI экспорта с экспортом JSON/CSV/Markdown и управлением бэкапами
- `scripts/backup.py` - Скрипт планируемого бэкапа с 30-дневным хранением и уведомлением в Telegram

**Архитектурные заметки:**
- Эндпоинты Export/Import добавлены в `analytics_server/server.py` (720+ строк)
- Импорт поддерживает dry-run режим и разрешение конфликтов (пропуск/обновление/создание дубликатов)
- Linear импортер маппит: Linear state -> workflow state, Linear priority -> priority
- GitHub импортер может фильтровать по лейблам и импортировать комментарии
- Бэкапы хранятся в директории `backups/` с 30-дневным хранением

### 2026-02-07 - ENG-33 Codebase Map
- Реализована автоматически генерируемая карта проекта для контекста агента

**Созданные новые файлы:**
- `scripts/generate_project_map.py` - Генерирует `.agent/PROJECT_MAP.md`
- `.agent/PROJECT_MAP.md` - Автоматически генерируемая структура проекта

**Изменённые файлы:**
- `prompts.py` - Добавлены функции `load_project_map()`, `ensure_project_map()`
- `agent.py` - Добавлена генерация карты проекта при запуске
- `prompts/coding_agent_prompt.md` - Добавлена инструкция обновлять карту после коммитов

**Функции:**
- Структура директорий с подсчётом файлов
- Ключевые файлы по категориям (точки входа, конфиги, документация)
- Зависимости из requirements.txt и package.json
- Конфигурации портов
- Последние 5 git коммитов
- Граф зависимостей импортов с определением hub файлов

---

*Последнее обновление: 2026-02-07 (добавлена документация ENG-33 Codebase Map)*


---

### Context Limit Shutdown (2026-02-08T20:07:18.299875)
- Issue:
- Interrupted at: step_
- Context usage: 85.6%
- **Resume from step: **


---

### Context Limit Shutdown (2026-02-08T20:07:18.353086)
- Issue:
- Interrupted at: step_
- Context usage: 85.6%
- **Resume from step: **


---

### Context Limit Shutdown (2026-02-08T20:12:58.739381)
- Issue:
- Interrupted at: step_
- Context usage: 122.3%
- **Resume from step: **


---

### Context Limit Shutdown (2026-02-08T20:12:58.802170)
- Issue:
- Interrupted at: step_
- Context usage: 122.3%
- **Resume from step: **

### 2026-02-09 - ENG-68 Graceful Degradation Matrix (Завершено)
- Добавлен унифицированный API: FailureType enum, handle() декоратор, protected() контекстный менеджер
- Коммит: 0c24626
- Файлы: recovery.py, tests/unit/test_recovery.py
- Все 74 теста пройдены

### 2026-02-09 - ENG-35 Crash Recovery Epic (Завершено)
- **ENG-66**: Машина состояний сессии и отслеживание фаз (коммит 8c866b6)
  - SessionPhase enum с 8 фазами
  - SessionStateManager с save/load в .agent/session_state.json
  - 49 тестов
- **ENG-67**: Логика повторов на уровне фаз (коммит 8b0d1d9)
  - RetryStrategy enum (RETRY_CURRENT, RETRY_FROM_ORIENT, RETRY_IMPLEMENTATION, ESCALATE)
  - get_retry_strategy() в SessionRecovery
  - 22 новых теста (71 всего)
- **ENG-69**: Восстановление после сбоя при запуске (коммит fddc098)
  - Определение устаревшего восстановления (порог 24ч)
  - get_recovery_info() и get_recovery_context()
  - Секция Recovery Mode в execute_task.md
  - 20 новых тестов (90 всего)
- **ENG-70**: Обработка таймаутов и backoff (коммит 3925cb9)
  - MCPTimeoutError исключение
  - calculate_backoff() с jitter
  - call_mcp_tool_with_retry() async обёртка
  - 28 новых тестов

**Ключевые файлы:**
- session_state.py - машина состояний, восстановление, логика повторов
- client.py - обработка таймаутов, backoff
- agent.py - интеграция
- prompts/execute_task.md - инструкции режима восстановления

### 2026-02-09 - ENG-62 Auto-push to GitHub (Завершено)
- Коммит: 55a9636
- Файлы: github_integration.py, test_github_integration.py, prompts/*.md, mcp_config.py
- Добавлено: LintGateResult dataclass, run_lint_gate(), auto_push_with_gate()
- Workflow: Теперь использует ветки agent/{issue-id} вместо коммитов в main
- Тесты: 11 новых тестов, все 230 пройдены
- Code review: ОДОБРЕН

**Ключевая реализация:**
- `run_lint_gate()` - запускает scripts/lint-gate.sh с таймаутом 120с
- `auto_push_with_gate()` - контролирует push через прохождение lint-gate
- Пропуск push грациозно если GITHUB_TOKEN не установлен

### 2026-02-09 - ENG-79 Russian Localization of Prompts (Завершено)
- Переведены все 7 файлов промптов на русский язык
- Файлы: prompts/orchestrator_prompt.md, coding_agent_prompt.md, task_agent_prompt.md, telegram_agent_prompt.md, reviewer_prompt.md, execute_task.md, continuation_task.md
- Часть Epic ENG-73 (Полная русификация)
- Коммит запушен в ветку agent/ENG-79
- Примечание: initializer_task.md из описания задачи не существует, вместо этого был переведён reviewer_prompt.md

### 2026-02-09 - ENG-81 Russian Dashboard UI (Завершено)
- Переведены все 28 файлов dashboard на русский язык
- Файлы: App.jsx, 8 страниц, 19 компонентов
- Переводы: навигация, статусы, приоритеты, кнопки, лейблы, плейсхолдеры, сообщения об ошибках
- Часть Epic ENG-73 (Полная русификация)
- Коммит запушен в ветку agent/ENG-81
- Code review: ОДОБРЕН
