# Возможности Claude Agent SDK для мультиагентной координации

> Итоговый отчёт на основе детального изучения репозитория `your-claude-engineer`

---

## 1. Версия SDK и установленные пакеты

**Файл**: `requirements.txt`

**Ключевой пакет**:
- `claude-agent-sdk==0.1.25` (пин в requirements)
- Фактически установлена `claude-agent-sdk 0.1.31` в `.venv` (проверено 10 февраля 2026) — план следует актуальной версии

**Дополнительные зависимости**:

- `mcp==1.26.0` — Model Context Protocol
- `sse-starlette==3.2.0` — Server-Sent Events
- `httpx==0.28.1` — Async HTTP

---

## 2. Встроенная поддержка агентов в SDK

**Основной класс**: `ClaudeAgentOptions`
**Файл**: `.venv/lib/python3.12/site-packages/claude_agent_sdk/types.py`

Ключевое поле для агентов:

```python
agents: dict[str, AgentDefinition] | None = None
```

Это поле позволяет регистрировать несколько специализированных агентов при инициализации SDK.

---

## 3. Структура AgentDefinition

**Файл**: `agents/definitions.py`

```python
@dataclass
class AgentDefinition:
    description: str          # Описание роли агента
    prompt: str               # Системный промпт агента
    tools: list[str] | None   # Список доступных инструментов
    model: Literal["sonnet", "opus", "haiku", "inherit"] | None
```

**Четыре встроенных агента в проекте**:

| # | Агент | Модель | Назначение |
|---|-------|--------|-----------|
| 1 | Task Agent | haiku | Управление задачами через Task MCP |
| 2 | Coding Agent | sonnet | Реализация и тестирование |
| 3 | Reviewer Agent | haiku | Ревью кода |
| 4 | Telegram Agent | haiku | Отправка уведомлений |

---

## 4. Механизмы делегирования между агентами

### А) Текстовый паттерн делегирования (текущий подход)

**Файл**: `prompts/orchestrator_prompt.md`

Оркестратор делегирует работу через текстовые инструкции в системном промпте:

#### Схема принятия решений

| Ситуация | Агент | Что передать |
|----------|-------|--------------|
| Нужен список задач | task | Ключ команды |
| Нужна реализация | coding | Полный контекст от task agent |
| Нужно ревью | reviewer | Вывод git diff |
| Нужно уведомить | telegram | Детали вехи |

**Ключевой паттерн**: Оркестратор получает результаты от одного агента и передает их другому через контекст промпта.

#### Поток контекста

```
task agent -> детали задачи -> ОРКЕСТРАТОР -> coding agent
coding agent -> файлы/снимки -> ОРКЕСТРАТОР -> task agent (отметить Done)
```

### Б) Hook-система для отслеживания агентов

**Файлы**:
- `client.py` (строка 418-423)
- `.venv/lib/python3.12/site-packages/claude_agent_sdk/types.py`

#### Доступные hook-события

```python
HookEvent = (
    "PreToolUse"
    | "PostToolUse"
    | "PostToolUseFailure"
    | "UserPromptSubmit"
    | "Stop"
    | "SubagentStop"          # ← Событие завершения субагента
    | "PreCompact"
    | "Notification"
    | "SubagentStart"         # ← Событие начала субагента
    | "PermissionRequest"
)
```

#### Hook Input структуры для агентов

```python
class SubagentStartHookInput(BaseHookInput):
    """Событие начала субагента"""
    hook_event_name: Literal["SubagentStart"]
    agent_id: str
    agent_type: str

class SubagentStopHookInput(BaseHookInput):
    """Событие завершения субагента"""
    hook_event_name: Literal["SubagentStop"]
    stop_hook_active: bool
    agent_id: str
    agent_transcript_path: str
    agent_type: str
```

---

## 5. Регистрация агентов в SDK

**Файл**: `client.py` (строки 402-431)

```python
return ClaudeSDKClient(
    options=ClaudeAgentOptions(
        model=model,
        system_prompt=orchestrator_prompt,
        allowed_tools=[...],
        agents=AGENT_DEFINITIONS,  # ← Регистрация всех агентов
        hooks={                     # ← Регистрация hook обработчиков
            "PreToolUse": [...],
            "SubagentStart": [...],
            "SubagentStop": [...],
        },
    )
)
```

---

## 6. Как агенты используются на практике

**Текущая архитектура (оркестраторная)**:

1. **Инициализация** — Оркестратор создается с регистрированными агентами в `ClaudeAgentOptions.agents`
2. **Делегирование** — Оркестратор указывает в промпте, какому агенту что делать:
   - `task agent`: "Список Todo-задач для {team}"
   - `coding agent`: "Реализовать следующую функцию с полным контекстом..."
3. **Контекстный трансфер** — Оркестратор получает результаты и передает их следующему агенту
4. **Мониторинг** — Hook-система отслеживает события `SubagentStart` и `SubagentStop`

---

## 7. Инструменты SDK для координации

| Класс | Назначение |
|-------|-----------|
| `ClaudeSDKClient` | Основной клиент для взаимодействия |
| `ClaudeAgentOptions` | Конфигурация агентов и инструментов |
| `AgentDefinition` | Определение специализированного агента |
| `HookMatcher` | Регистрация handler'ов для event'ов |
| `HookCallback` | Callback-функция для hook events |

---

## 8. Ограничения текущей реализации

Из документации проекта (`CLAUDE.md`):

1. **Нет встроенного механизма прямого вызова** — Агенты не могут напрямую друг друга вызывать; координация идет через оркестратор
2. **Нет общей памяти между агентами** — "Агенты не имеют общей памяти. ТЫ должен передавать информацию между ними"
3. **Нет встроенной очереди задач** — Оркестратор должен вручную управлять потоком работы
4. **Текстовая синхронизация** — Результаты передаются через текстовые блоки в контексте

---

## 9. Рекомендуемые паттерны использования

### Паттерн 1: Sequential Execution (последовательное выполнение)

```
Task Agent (получить задачу)
  → Coding Agent (реализовать)
    → Reviewer Agent (ревью)
      → Coding Agent (исправить)
        → Task Agent (отметить Done)
```

### Паттерн 2: Context Passing (передача контекста)

```python
# Оркестратор получает результат от одного агента
result_from_task_agent = "ENG-42: Implement feature X..."

# И передает его другому агенту в новом промпте
prompt_for_coding = f"""
Issue details from task agent:
{result_from_task_agent}

Please implement this feature...
"""
```

### Паттерн 3: Hook Monitoring (мониторинг через hooks)

```python
hooks={
    "SubagentStart": [
        HookMatcher(
            matcher="coding",
            hooks=[my_callback_when_coding_starts]
        )
    ]
}
```

---

## 10. Файлы для дальнейшего изучения

### Ключевые файлы архитектуры

| Файл | Описание |
|------|---------|
| `agent.py` | Основной цикл выполнения (строки 171-625) |
| `client.py` | Конфигурация SDK (строки 346-431) |
| `agents/definitions.py` | Определение агентов (строки 143-185) |
| `prompts/orchestrator_prompt.md` | Логика делегирования (строки 17-159) |

### SDK типы (в `.venv`)

- `claude_agent_sdk/types.py` — Полная типизация (700+ строк)
- `claude_agent_sdk/client.py` — API клиента

---

## Выводы

Claude Agent SDK 0.1.25 поддерживает мультиагентную координацию через:

1. **Регистрацию агентов** — параметр `agents` в `ClaudeAgentOptions`
2. **Hook-систему** — отслеживание `SubagentStart` и `SubagentStop` событий
3. **Специализированные определения** — `AgentDefinition` с custom prompts и tools
4. **Оркестраторный паттерн** — один главный агент координирует работу других
5. **MCP-интеграция** — специализированные инструменты через Task и Telegram MCP серверы

**Ограничение**: SDK предоставляет инфраструктуру, но координация логики остается ответственностью оркестратора через текстовые промпты. Это by design — SDK обеспечивает гибкость, но требует явного управления потоком работы в промпте оркестратора.
