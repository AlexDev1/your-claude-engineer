# Your Claude Engineer

**Ваш собственный AI-инженер, который управляет проектами, пишет код и сообщает о прогрессе — автономно.**

Когда-нибудь хотели передать задачу на разработку и получить её полностью реализованной, протестированной и задокументированной? Your Claude Engineer — это фреймворк для длительных задач на базе [Claude Agent SDK](https://github.com/anthropics/claude-code/tree/main/agent-sdk-python), который превращает Claude в долго работающего инженера, способного решать сложные многоэтапные задачи.

Полный рабочий процесс разработки с использованием субагентов:

- **Управление проектом**: Создаёт и отслеживает работу через самохостируемый Task MCP Server (бэкенд на PostgreSQL), разбивает фичи на задачи и обновляет статусы
- **Реализация кода**: Пишет, тестирует и итерирует код с UI-верификацией через Playwright
- **Контроль версий**: Коммитит изменения в локальный git-репозиторий
- **Коммуникация**: Информирует о прогрессе через Telegram

Мультиагентная архитектура использует специализированных агентов (Task, Coding, Telegram), координируемых оркестратором, что позволяет проводить длительные автономные сессии без исчерпания контекстного окна. Все интеграции используют самохостируемые MCP серверы на вашем VDS.

## Ключевые возможности

- **Длительная автономность**: Архитектура позволяет проводить расширенные сессии кодинга
- **Мультиагентная оркестрация**: Специализированные агенты отвечают за отдельные задачи
- **Самохостируемое управление задачами**: PostgreSQL-бэкенд с полным контролем над данными
- **Локальный Git**: Автоматические коммиты с описательными сообщениями
- **Уведомления в Telegram**: Обновления прогресса в личный чат
- **Браузерное тестирование**: Playwright MCP для автоматической UI-верификации
- **Конфигурация моделей**: Выбор модели для каждого агента (Haiku, Sonnet или Opus)
- **API Key аутентификация**: Защита MCP серверов API-ключами через nginx `auth_request`

## Требования

> Не работает на Windows из-за ограничений Claude Agent SDK и субагентов. Используйте WSL или Linux VM!

### 0. Создание виртуального окружения Python (рекомендуется)

```bash
# Создание виртуального окружения
python3 -m venv venv

# Активация
source venv/bin/activate  # На macOS/Linux
```

### 1. Установка Claude Code CLI и Python SDK

```bash
# Установка Claude Code CLI (требуется последняя версия)
npm install -g @anthropic-ai/claude-code

# Установка Python-зависимостей
pip install -r requirements.txt
```

### 2. Развёртывание MCP серверов

Разверните Task MCP Server и Telegram MCP Server на вашем VDS:

```bash
# На вашем VDS
# Создайте директорию secrets и файлы с секретами
mkdir -p secrets
echo "ваш_безопасный_пароль_бд" > secrets/db_password.txt
echo "ваш_токен_бота" > secrets/telegram_bot_token.txt
echo "ваш_chat_id" > secrets/telegram_chat_id.txt

# Установите права доступа
chmod 600 secrets/*

# Запуск сервисов (используется pgvector/pgvector:pg16)
docker-compose up -d

# Проверка статуса
docker-compose ps
curl http://localhost:8001/health
curl http://localhost:8002/health
```

> **Примечание:** Используется образ `pgvector/pgvector:pg16` вместо стандартного PostgreSQL для поддержки векторных операций и RAG.

### 3. Настройка локального окружения

```bash
# Скопируйте пример файла окружения
cp .env.example .env

# Отредактируйте .env с URL ваших MCP серверов:
# - TASK_MCP_URL: http://your-vds:8001/sse
# - TELEGRAM_MCP_URL: http://your-vds:8002/sse
```

<details>
<summary><strong>Справочник переменных окружения</strong></summary>

| Переменная | Описание | Обязательна |
|------------|----------|-------------|
| `TASK_MCP_URL` | URL вашего Task MCP Server | Да |
| `TELEGRAM_MCP_URL` | URL вашего Telegram MCP Server | Да |
| `MCP_API_KEY` | API ключ для аутентификации MCP серверов (см. [Настройка аутентификации](#5-настройка-api-key-аутентификации)) | Да |
| `GENERATIONS_BASE_PATH` | Базовая директория для генерируемых проектов (по умолчанию: ./generations) | Нет |
| `ORCHESTRATOR_MODEL` | Модель для оркестратора: haiku, sonnet, opus (по умолчанию: haiku) | Нет |
| `TASK_AGENT_MODEL` | Модель для Task агента (по умолчанию: haiku) | Нет |
| `CODING_AGENT_MODEL` | Модель для Coding агента (по умолчанию: sonnet) | Нет |
| `TELEGRAM_AGENT_MODEL` | Модель для Telegram агента (по умолчанию: haiku) | Нет |

</details>

### 4. Создание Telegram бота

1. Напишите [@BotFather](https://t.me/BotFather) в Telegram
2. Отправьте `/newbot` и следуйте инструкциям
3. Скопируйте токен бота в `TELEGRAM_BOT_TOKEN`
4. Напишите [@userinfobot](https://t.me/userinfobot) чтобы получить ваш chat ID
5. Установите `TELEGRAM_CHAT_ID` в `.env` файле на VDS

### 5. Настройка API Key аутентификации

MCP серверы защищены API-ключами через nginx `auth_request`. Аутентификация централизована через Task MCP Server (PostgreSQL), Telegram MCP Server не требует изменений.

```
Client --[Authorization: Bearer <key>]--> nginx
    nginx --[auth_request]--> Task MCP /auth/validate
        Task MCP --> PostgreSQL (проверка хеша ключа)
    nginx --> 200 OK → proxy_pass к Task/Telegram MCP
         --> 401/403 → отказ
```

**Создание пользователя и API ключа:**

```bash
# Применить миграцию (если БД уже работает)
docker exec -i mcp-postgres psql -U agent -d tasks < task_mcp_server/migrations/001_auth_tables.sql

# Создать пользователя
docker exec -it mcp-task python admin_cli.py create-user agent --email agent@example.com

# Создать API ключ (показывается ОДИН раз!)
docker exec -it mcp-task python admin_cli.py create-key agent --name "Production Key"

# Скопируйте полученный ключ (mcp_...) в .env:
# MCP_API_KEY=mcp_...
```

**Управление ключами:**

```bash
# Список пользователей и ключей
docker exec -it mcp-task python admin_cli.py list-users
docker exec -it mcp-task python admin_cli.py list-keys --username agent

# Отозвать ключ по префиксу
docker exec -it mcp-task python admin_cli.py revoke-key mcp_abcd

# Проверить ключ (для отладки)
docker exec -it mcp-task python admin_cli.py verify-key mcp_...

# Создать ключ с ограниченным сроком действия
docker exec -it mcp-task python admin_cli.py create-key agent --name "Temp Key" --expires-days 30
```

**Обновить nginx конфиг и перезагрузить:**

```bash
cp deploy/nginx/mcp-servers.conf /etc/nginx/sites-available/mcp-servers.conf
nginx -t && systemctl reload nginx
```

**Проверка аутентификации:**

```bash
# Без ключа — 401:
curl https://mcp.axoncode.pro/task/sse

# С ключом — SSE поток:
curl -N -H "Authorization: Bearer mcp_..." https://mcp.axoncode.pro/task/sse

# Health — без auth:
curl https://mcp.axoncode.pro/task/health
```

### 6. Проверка установки

```bash
claude --version  # Должна быть последняя версия
pip show claude-agent-sdk  # Проверка установки SDK

# Тест подключения к MCP серверам (health не требует auth)
curl https://your-vds/task/health
curl https://your-vds/telegram/health

# Тест с API ключом
curl -H "Authorization: Bearer $MCP_API_KEY" https://your-vds/task/sse

# Запуск интеграционных тестов
uv run python test_mcp_servers.py
```

## Быстрый старт

```bash
# Базовое использование — создаёт проект в ./generations/my-app/
uv run python autonomous_agent_demo.py --project-dir my-app

# Указать другую директорию вывода
uv run python autonomous_agent_demo.py --generations-base ~/projects/ai --project-dir my-app

# Ограничить итерации для тестирования
uv run python autonomous_agent_demo.py --project-dir my-app --max-iterations 3

# Использовать Opus для оркестратора (более мощный, но дороже)
uv run python autonomous_agent_demo.py --project-dir my-app --model opus
```

## Как это работает

### Мультиагентная оркестрация

```
┌───────────────────────────────────────────────────────────────┐
│                  МУЛЬТИАГЕНТНАЯ АРХИТЕКТУРА                   │
├───────────────────────────────────────────────────────────────┤
│                                                               │
│                    ┌─────────────────┐                        │
│                    │   ОРКЕСТРАТОР   │  (Haiku по умолчанию)  │
│                    │   Координирует  │                        │
│                    └────────┬────────┘                        │
│                             │                                 │
│           ┌─────────────────┼─────────────────┐               │
│           │                 │                 │               │
│      ┌────▼─────┐    ┌─────▼──────┐   ┌─────▼──────┐          │
│      │   TASK   │    │   CODING   │   │ TELEGRAM   │          │
│      │  (Haiku) │    │  (Sonnet)  │   │  (Haiku)   │          │
│      └────┬─────┘    └─────┬──────┘   └─────┬──────┘          │
│           │                │                │                 │
│      Task MCP         Playwright       Telegram MCP           │
│      Server           + Local Git         Server              │
│     (PostgreSQL)                        (Bot API)             │
│                                                               │
│     ┌──────────────────────────────────────────────┐          │
│     │          ПРОЕКТ (Изолированный Git)          │          │
│     │      GENERATIONS_BASE_PATH/project-name/     │          │
│     └──────────────────────────────────────────────┘          │
└───────────────────────────────────────────────────────────────┘
```

### Ответственность агентов

1. **Оркестратор:**
   - Читает состояние проекта из `.task_project.json`
   - Запрашивает текущий статус у Task MCP Server
   - Решает, что делать дальше
   - Делегирует специализированным агентам через Task tool
   - Координирует передачу между агентами

2. **Task Agent:**
   - Создаёт и обновляет проекты и задачи
   - Управляет переходами статусов (Todo → In Progress → Done)
   - Добавляет комментарии с деталями реализации
   - Поддерживает META issue для отслеживания сессий

3. **Coding Agent:**
   - Реализует фичи на основе задач
   - Пишет и тестирует код приложения
   - Использует Playwright для браузерного UI-тестирования
   - Валидирует ранее завершённые фичи
   - Управляет локальными git-коммитами

4. **Telegram Agent:**
   - Публикует обновления прогресса в ваш Telegram-чат
   - Уведомляет о завершении фич
   - Отправляет сводки статуса проекта

## Опции командной строки

| Опция | Описание | По умолчанию |
|-------|----------|--------------|
| `--project-dir` | Имя проекта или путь | `./autonomous_demo_project` |
| `--generations-base` | Базовая директория для всех проектов | `./generations` или `GENERATIONS_BASE_PATH` |
| `--max-iterations` | Максимум итераций агента | Без ограничений |
| `--model` | Модель оркестратора: haiku, sonnet, или opus | `haiku` или `ORCHESTRATOR_MODEL` |

## Кастомизация

### Изменение приложения

Отредактируйте `prompts/app_spec.txt` чтобы указать другое приложение для сборки.

### Изменение количества задач

Отредактируйте `prompts/initializer_task.md` чтобы изменить количество создаваемых задач.

### Изменение разрешённых команд

Отредактируйте `security.py` чтобы добавить или удалить команды из `ALLOWED_COMMANDS`.

## Структура проекта

```
your-claude-engineer/
├── autonomous_agent_demo.py  # Точка входа
├── agent.py                  # Логика сессий агента
├── client.py                 # Конфигурация Claude SDK + MCP
├── mcp_config.py             # URL MCP серверов и определения инструментов
├── security.py               # Allowlist bash-команд и валидация
├── progress.py               # Утилиты отслеживания прогресса
├── prompts.py                # Утилиты загрузки промптов
├── test_mcp_servers.py       # Интеграционные тесты MCP серверов
├── docker-compose.yml        # Конфигурация развёртывания MCP серверов
├── Makefile                  # Команды сборки и развёртывания
├── agents/
│   ├── definitions.py        # Определения агентов с конфигурацией моделей
│   └── orchestrator.py       # Запуск сессии оркестратора
├── prompts/
│   ├── app_spec.txt              # Спецификация приложения
│   ├── orchestrator_prompt.md    # Системный промпт оркестратора
│   ├── initializer_task.md       # Сообщение задачи для первой сессии
│   ├── continuation_task.md      # Сообщение задачи для продолжения
│   ├── task_agent_prompt.md      # Промпт Task субагента
│   ├── coding_agent_prompt.md    # Промпт Coding субагента
│   └── telegram_agent_prompt.md  # Промпт Telegram субагента
├── task_mcp_server/          # Task MCP Server (PostgreSQL + pgvector)
│   ├── server.py             # FastMCP сервер с 10 инструментами + auth endpoint
│   ├── database.py           # Async PostgreSQL с retry, connection pool и auth
│   ├── models.py             # Pydantic модели
│   ├── admin_cli.py          # CLI управления пользователями и API ключами
│   ├── init_db.sql           # Схема БД с pgvector, RAG и auth таблицами
│   ├── migrations/
│   │   └── 001_auth_tables.sql  # Миграция auth таблиц для работающей БД
│   ├── requirements.txt
│   ├── Dockerfile
│   └── .dockerignore
├── telegram_mcp_server/      # Telegram MCP Server
│   ├── server.py             # FastMCP сервер с 3 инструментами
│   ├── requirements.txt
│   ├── Dockerfile
│   └── .dockerignore
├── deploy/
│   └── nginx/
│       └── mcp-servers.conf  # Nginx конфиг с auth_request и SSE
├── secrets/                  # Docker secrets (не в git)
│   ├── db_password.txt
│   ├── telegram_bot_token.txt
│   └── telegram_chat_id.txt
└── requirements.txt          # Python зависимости
```

## Структура генерируемого проекта

Проекты создаются в изолированных директориях со своими git-репозиториями:

```
generations/my-app/           # Или GENERATIONS_BASE_PATH/my-app/
├── .task_project.json        # Состояние проекта (маркер-файл)
├── app_spec.txt              # Скопированная спецификация
├── init.sh                   # Скрипт настройки окружения
├── .claude_settings.json     # Настройки безопасности
├── .git/                     # Отдельный git-репозиторий
└── [файлы приложения]        # Сгенерированный код приложения
```

## MCP серверы

| Сервер | Транспорт | Назначение |
|--------|-----------|------------|
| **Task MCP Server** | HTTP (SSE) | Управление проектами/задачами с PostgreSQL + pgvector бэкендом |
| **Telegram MCP Server** | HTTP (SSE) | Уведомления через Telegram Bot API |
| **Playwright** | stdio | Браузерная автоматизация для UI-тестирования |

### База данных (PostgreSQL + pgvector)

Task MCP Server использует PostgreSQL 16 с расширением pgvector для поддержки семантического поиска:

- **pgvector 0.8.1** — векторные операции и HNSW индексы для RAG
- **Enterprise индексы** — composite, functional, covering индексы для высокой производительности
- **RAG инфраструктура** — таблицы `rag_documents`, `rag_chunks`, `rag_embeddings` с автоматической синхронизацией через триггеры
- **Docker secrets** — безопасное хранение паролей БД и токенов

### Инструменты Task MCP Server (10 инструментов)

| Инструмент | Описание |
|------------|----------|
| `Task_WhoAmI` | Получить профиль и членство в командах |
| `Task_ListTeams` | Список всех команд |
| `Task_CreateProject` | Создать новый проект |
| `Task_CreateIssue` | Создать новую задачу |
| `Task_ListIssues` | Список задач с фильтрами |
| `Task_GetIssue` | Получить детали задачи |
| `Task_UpdateIssue` | Обновить поля задачи |
| `Task_TransitionIssueState` | Изменить статус задачи |
| `Task_AddComment` | Добавить комментарий к задаче |
| `Task_ListWorkflowStates` | Список доступных статусов |

<details>
<summary><strong>RAG инфраструктура (pgvector)</strong></summary>

База данных включает таблицы для Retrieval-Augmented Generation:

| Таблица | Назначение |
|---------|------------|
| `rag_documents` | Исходные документы (issues, comments) |
| `rag_chunks` | Разбитые куски текста для embedding |
| `rag_embeddings` | Векторы с HNSW индексом для быстрого поиска |
| `embedding_models` | Конфигурация моделей (OpenAI, etc) |

**Триггеры автоматической синхронизации:**
- При создании issue → создаётся rag_document
- При обновлении issue → обновляется rag_document (status='pending')
- При создании comment → создаётся rag_document

**SQL функции:**
- `search_similar_documents(query_embedding, team_id, limit, threshold)` — семантический поиск
- `chunk_document(document_id, chunk_size, overlap)` — разбиение документа
- `get_chunk_context(chunk_id, context_radius)` — контекст вокруг chunk

</details>

### Инструменты Telegram MCP Server (3 инструмента)

| Инструмент | Описание |
|------------|----------|
| `Telegram_WhoAmI` | Получить информацию о боте и статус конфигурации |
| `Telegram_SendMessage` | Отправить сообщение (авто-конвертация Slack emoji) |
| `Telegram_ListChats` | Список недавних чатов |

## Модель безопасности

Демо использует многоуровневую безопасность (см. `security.py` и `client.py`):

1. **API Key аутентификация:** MCP серверы защищены API-ключами через nginx `auth_request` — без валидного ключа доступ запрещён (401/403)
2. **Песочница на уровне ОС:** Bash-команды выполняются в изолированном окружении
3. **Ограничения файловой системы:** Файловые операции ограничены директорией проекта
4. **Allowlist Bash:** Разрешены только определённые команды (npm, node, git, curl, rm с валидацией и т.д.)
5. **MCP-разрешения:** Инструменты явно разрешены в настройках безопасности
6. **Валидация опасных команд:** Команды типа `rm` валидируются для предотвращения удаления системных директорий

## Интеграционные тесты

Для проверки работоспособности MCP серверов используйте интеграционные тесты:

```bash
# Убедитесь, что серверы запущены
docker-compose up -d

# Запуск тестов
uv run python test_mcp_servers.py
```

**Тесты Task MCP Server (9 тестов):**
- Health endpoint
- SSE подключение
- Список инструментов
- WhoAmI, ListTeams
- CreateIssue, GetIssue
- TransitionIssueState
- AddComment

**Тесты Telegram MCP Server (5 тестов):**
- Health endpoint
- SSE подключение
- Список инструментов
- WhoAmI
- SendMessage

## Устранение неполадок

**"TASK_MCP_URL not set"**
Установите `TASK_MCP_URL=http://your-vds:8001/sse` в вашем `.env` файле

**"TELEGRAM_MCP_URL not set"**
Установите `TELEGRAM_MCP_URL=http://your-vds:8002/sse` в вашем `.env` файле

**"Connection refused" к MCP серверам**
Проверьте, что MCP серверы запущены: `docker-compose ps` на вашем VDS

**"Command blocked by security hook"**
Агент попытался выполнить запрещённую команду. Добавьте её в `ALLOWED_COMMANDS` в `security.py` при необходимости.

**"Telegram message failed"**
Убедитесь, что вы сначала написали боту (отправьте `/start`) и что `TELEGRAM_CHAT_ID` корректен.

**"Database connection failed"**
Проверьте, что PostgreSQL запущен и `DATABASE_URL` правильно настроен в docker-compose.

**"Integration tests fail on SSE connection"**
Убедитесь, что MCP серверы полностью запустились. Проверьте логи: `docker-compose logs -f`

**"pgvector extension not found"**
Убедитесь, что используется образ `pgvector/pgvector:pg16`, а не стандартный PostgreSQL.

**"Permission denied" при запуске PostgreSQL**
Образ pgvector использует UID 999 (Debian), а не 70 (Alpine). Удалите volume и пересоздайте:
```bash
docker-compose down -v
docker-compose up -d
```

**401 "unauthorized" при подключении к MCP серверам**
Убедитесь, что `MCP_API_KEY` установлен в `.env` файле. Создайте ключ через `admin_cli.py` (см. [Настройка аутентификации](#5-настройка-api-key-аутентификации)).

**403 "forbidden" при подключении к MCP серверам**
API ключ невалиден, истёк или отозван. Проверьте ключ: `docker exec -it mcp-task python admin_cli.py verify-key mcp_...`

## Просмотр прогресса

**Task MCP Server:**
- Просмотр задач через прямые запросы к БД
- Наблюдение за изменениями статусов в реальном времени (Todo → In Progress → Done)
- Чтение комментариев с деталями реализации
- Проверка сводок сессий в META issue

**Telegram:**
- Получение обновлений прогресса в настроенный чат
- Уведомления о завершении фич

**Локальный Git:**
- Просмотр коммитов в директории сгенерированного проекта
- Проверка истории реализации через git log

## Лицензия

MIT License — см. [LICENSE](LICENSE) для деталей.
