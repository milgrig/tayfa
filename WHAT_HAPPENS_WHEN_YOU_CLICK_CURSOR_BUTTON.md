# Что происходит, когда ты нажимаешь "Cursor" и пишешь агенту в Tayfa

## Краткий ответ

Когда ты нажимаешь кнопку **"Cursor"** в интерфейсе Tayfa и отправляешь сообщение агенту:

1. **Tayfa orchestrator** вместо отправки запроса в Claude API
2. **Запускает Cursor CLI** через WSL (Windows Subsystem for Linux)
3. **Cursor CLI** обрабатывает твой prompt как Cursor Agent
4. **Результат** возвращается обратно в Tayfa и показывается в интерфейсе

Это позволяет использовать **Cursor's proprietary Composer model** вместо Claude для обработки задач агента.

---

## Подробный процесс

### 1️⃣ Нажимаешь кнопку "Send" в Tayfa UI

```javascript
// В kok/static/index.html, функция sendPrompt()

if (runtime === 'cursor') {
    const result = await api('POST', '/api/send-prompt-cursor', {
        name: agentForRequest,      // Имя агента, например "developer"
        prompt: text                // Твой текст сообщения
    });
    if (result.success) {
        addChatMessage(agentForRequest, 'agent', result.result, 'Cursor CLI');
    }
} else {
    // Claude API
    const result = await api('POST', '/api/send-prompt', { ... });
}
```

**Что видишь в интерфейсе:**
- Кнопка "Send" становится неактивной
- Появляется индикатор "Developer thinking..."
- Runtime меняется на "Via Cursor CLI" (вместо "Via Claude API")

---

### 2️⃣ Tayfa отправляет POST запрос

**URL**: `http://localhost:8008/api/send-prompt-cursor`

**Payload**:
```json
{
    "name": "developer",
    "prompt": "Add a new feature to authenticate users",
    "task_id": "T001",
    "use_chat": true
}
```

---

### 3️⃣ Tayfa обработчик на бэкенде

**Файл**: `kok/app.py`, функция `send_prompt_cursor()`

```python
@app.post("/api/send-prompt-cursor")
async def send_prompt_cursor(data: dict):
    """
    Send a prompt to Cursor CLI via WSL. Saves history to chat_history.json.
    Agent chat: from .cursor_chats.json or created via create-chat on first send.
    Command in WSL: agent -p --force [--resume <chat_id>] --output-format json "<prompt>".
    """
    name = data.get("name")                  # "developer"
    prompt_text = data.get("prompt")         # Твой текст
    task_id = data.get("task_id")            # "T001"
    use_chat = data.get("use_chat", True)    # Использовать сохранённый чат

    # Запустить Cursor CLI
    result = await run_cursor_cli(name, prompt_text, use_chat=use_chat)

    # Сохранить историю в chat_history.json
    save_chat_message(
        agent_name=name,
        prompt=prompt_text,
        result=result.get("result", ""),
        runtime="cursor",              # ← Это отмечает, что использовалась Cursor
        duration_sec=duration_sec,
        task_id=task_id,
        success=result.get("success", False),
    )

    return result
```

---

### 4️⃣ Запуск Cursor CLI через WSL

**Функция**: `run_cursor_cli()` в `kok/app.py`

```python
async def run_cursor_cli(agent_name: str, user_prompt: str, use_chat: bool = True) -> dict:
    """
    Runs Cursor CLI in WSL in headless mode.
    If use_chat=True, ensures a chat exists for the agent (create-chat if needed)
    and sends a message with --resume <chat_id>. Otherwise — a one-time call.
    Returns { "success": bool, "result": str, "stderr": str }.
    """

    # 1. Построить полный prompt с контекстом агента
    full_prompt = _build_cursor_cli_prompt(agent_name, user_prompt)
    # Результат: "Role: developer. Working directory: Personal (project/ — code, common/Rules/ — rules).
    //            Consider context from developer/prompt.md and common/Rules/. Task: Add a new feature..."

    # 2. Если нужно использовать сохранённый чат — получить его ID
    if use_chat:
        chat_id, chat_error = await ensure_cursor_chat(agent_name)
        # Если чата нет — создать новый через `agent create-chat`

    # 3. Написать prompt в временный файл
    CURSOR_CLI_PROMPT_FILE.write_text(full_prompt, encoding="utf-8")
    # Файл: .cursor_cli_prompt.txt

    # 4. Построить WSL команду
    wsl_script = (
        f"{_cursor_cli_base_script()} && "  # Установить PATH, cd в проект
        "content=$(cat .cursor_cli_prompt.txt | sed 's/\"/\\\\\"/g') && "  # Прочитать промпт
        f"agent -p --force --resume '{chat_id}' --output-format json \"$content\""
        # Запустить Cursor Agent в headless mode с сохранённым чатом
    )

    # 5. Выполнить команду в WSL
    proc = await asyncio.create_subprocess_exec(
        "wsl", "bash",
        stdin=asyncio.subprocess.PIPE,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
        cwd=str(TAYFA_ROOT_WIN),
    )

    stdout, stderr = await asyncio.wait_for(
        proc.communicate(input=wsl_script.encode("utf-8")),
        timeout=CURSOR_CLI_TIMEOUT,  # 30 сек или больше
    )

    # 6. Вернуть результат
    return {
        "success": proc.returncode == 0,
        "result": stdout.decode("utf-8"),  # Ответ от Cursor
        "stderr": stderr.decode("utf-8"),
    }
```

---

### 5️⃣ Что происходит в WSL/Cursor CLI

**Выполняется команда**:
```bash
agent -p --force --resume '<chat_id>' --output-format json "Role: developer. Working directory: Personal (...). Task: Add a new feature to authenticate users"
```

**Флаги**:
- `-p` — plan mode (думает перед ответом)
- `--force` — игнорирует кэш
- `--resume <chat_id>` — продолжить сохранённый чат (контекст сохраняется)
- `--output-format json` — результат в JSON

**Cursor делает**:
1. Загружает контекст из сохранённого чата (если существует)
2. Смотрит на роль агента ("developer")
3. Читает рабочую папку и правила (.tayfa/common/Rules/)
4. Запускает Cursor Agent (Composer model) с твоим промптом
5. Возвращает результат в JSON формате

---

### 6️⃣ Результат возвращается в Tayfa

**Response** из WSL/Cursor:
```json
{
    "success": true,
    "result": "I'll implement authentication using JWT tokens. Here's my plan:\n1. Create auth module\n2. Add password hashing\n3. Create login endpoint\n...",
    "stderr": ""
}
```

**Tayfa**:
1. Получает результат
2. Сохраняет в `.tayfa/developer/chat_history.json`:
   ```json
   {
       "role": "developer",
       "prompt": "Add a new feature to authenticate users",
       "result": "I'll implement authentication...",
       "runtime": "cursor",
       "task_id": "T001",
       "timestamp": "2026-02-18T10:30:00",
       "duration_sec": 4.2,
       "success": true
   }
   ```
3. Возвращает в UI

**В интерфейсе видишь**:
- Сообщение от агента: "I'll implement authentication..."
- Бэйдж: "Cursor CLI" (вместо "$0.0045 · 2 turns")
- Статус: Done

---

## 🔄 Сохранение Cursor чатов

### Первый запрос к агенту через Cursor

1. **Запрос поступает** в `send_prompt_cursor()`
2. **Проверяется** наличие чата в `.cursor_chats.json`
3. **Если чата нет:**
   ```python
   async def ensure_cursor_chat(agent_name: str):
       chats = _load_cursor_chats()  # Загрузить .cursor_chats.json
       if agent_name in chats and chats[agent_name]:
           return chats[agent_name], ""  # Чат уже есть

       # Создать новый чат
       create_result = await run_cursor_cli_create_chat()
       # Выполнить: agent --print --output-format json create-chat

       chat_id = create_result["chat_id"]  # Получить ID нового чата
       chats[agent_name] = chat_id         # Сохранить
       _save_cursor_chats(chats)           # Записать в .cursor_chats.json

       return chat_id, ""
   ```

4. **Команда запускается с `--resume <chat_id>`**
   - Cursor запомнит контекст
   - Следующие запросы будут в том же чате
   - История сохранится в Cursor

### Файл `.cursor_chats.json`

**Расположение**: корень проекта (`.tayfa/common/` или рядом с `tasks.json`)

**Содержимое**:
```json
{
    "developer": "550e8400-e29b-41d4-a716-446655440000",
    "tester": "6ba7b810-9dad-11d1-80b4-00c04fd430c8",
    "analyst": "6ba7b811-9dad-11d1-80b4-00c04fd430c8"
}
```

---

## 📊 Сравнение Claude vs Cursor

### Когда нажимаешь "Claude"

```
prompt → /api/send-prompt → call_claude_api() → Claude API (cloud) → result + cost
```

- ✅ Полная интеграция с API
- ✅ Метрики: стоимость, токены, turns
- ❌ Зависит от интернета и API ключа
- ❌ Дороже (Opus — $15 за миллион токенов)

### Когда нажимаешь "Cursor"

```
prompt → /api/send-prompt-cursor → run_cursor_cli() → WSL → Cursor CLI (agent command) → result
```

- ✅ Локальная обработка (через Cursor, установленный на машине)
- ✅ Proprietary Composer model (оптимизирован для кода)
- ✅ Бесплатно (если у тебя есть Cursor с подпиской)
- ❌ Зависит от WSL и установленного Cursor
- ❌ Нет метрик стоимости

---

## 🔧 Как это работает на практике

### Сценарий 1: Быстрая помощь в коде

```
Ты в Tayfa → видишь задачу T001
↓
Нажимаешь "Send message to developer"
↓
Выбираешь "Cursor" (быстрее, бесплатнее)
↓
Пишешь: "Add error handling to auth module"
↓
Tayfa → запускает `agent --resume <chat_id> "Add error handling..."`
↓
Cursor в WSL → анализирует код → предлагает решение
↓
Результат в интерфейсе → developer может работать
```

### Сценарий 2: Сложная архитектурная задача

```
Ты в Tayfa → видишь задачу T002
↓
Нужно глубокое размышление → выбираешь "Claude"
↓
Tayfa → вызывает Claude API (Opus)
↓
Claude → детально продумывает архитектуру
↓
Результат + стоимость ($0.0045) в интерфейсе
```

---

## 🚀 Преимущества использования Cursor в Tayfa

| Аспект | Claude | Cursor |
|--------|--------|--------|
| **Скорость** | Медленнее (API) | Быстрее (локально) |
| **Стоимость** | Платно | Бесплатно (с подпиской) |
| **Модель** | Claude Opus/Sonnet | Proprietary Composer |
| **Оптимизация** | Общего назначения | Специально для кода |
| **Метрики** | Да (cost, tokens) | Нет |
| **Зависимость** | Интернет + API ключ | WSL + Cursor |
| **Лучше для** | Анализ, дизайн | Реальный код |

---

## 🐛 Возможные проблемы

### "Cursor CLI не найден"

```
Error: Failed to get Cursor chat for 'developer':
Timeout 30 sec. Cursor CLI did not finish in time.
```

**Решение:**
1. Убедись, что Cursor установлен в WSL
2. Проверь, что `agent` команда доступна
3. Проверь WSL подключение

### "Чат не сохраняется"

```
.cursor_chats.json не обновляется
```

**Решение:**
1. Убедись, что папка `.tayfa/` доступна для записи
2. Проверь, что `agent create-chat` работает вручную
3. Проверь логи в `tayfa_server.log`

### "Результат пустой"

```
Result: "(Empty response)"
```

**Решение:**
1. Убедись, что prompt не пустой
2. Проверь доступ к рабочей папке
3. Запустив `agent -p "test"` вручную для отладки

---

## 📝 Архитектура в коде

### kok/app.py — основные функции

```python
@app.post("/api/send-prompt")
async def send_prompt(data: dict):
    """Отправить в Claude API"""

@app.post("/api/send-prompt-cursor")
async def send_prompt_cursor(data: dict):
    """Отправить в Cursor CLI через WSL"""

async def run_cursor_cli(agent_name, user_prompt, use_chat=True):
    """Запустить Cursor Agent в headless режиме"""

async def run_cursor_cli_create_chat():
    """Создать новый чат в Cursor"""

async def ensure_cursor_chat(agent_name):
    """Получить или создать чат для агента"""
```

### kok/static/index.html — UI логика

```javascript
function sendPrompt() {
    const runtime = getAgentRuntime(currentAgent);
    // runtime = "sonnet", "opus", "haiku", или "cursor"

    if (runtime === 'cursor') {
        // Отправить в /api/send-prompt-cursor
        api('POST', '/api/send-prompt-cursor', {
            name: currentAgent,
            prompt: userInput
        });
    } else {
        // Отправить в /api/send-prompt (Claude)
        api('POST', '/api/send-prompt', {
            name: currentAgent,
            prompt: userInput
        });
    }
}

function getAgentRuntime(agentName) {
    // Получить runtime из конфига агента
    // Может быть: claude (по умолчанию) или cursor
}
```

---

## 🎯 Итоговый поток данных

```
┌─────────────────────────────────────────────────────────────────┐
│                     Tayfa Web Interface                         │
│                                                                 │
│  Agent: developer    [Claude] [Cursor]                          │
│  Message: "Add error handling..."   [Send]                      │
└──────────────────────────┬──────────────────────────────────────┘
                           │
                           │ POST /api/send-prompt-cursor
                           │ {name: "developer", prompt: "..."}
                           ▼
┌──────────────────────────────────────────────────────────────────┐
│              Tayfa Orchestrator (kok/app.py)                     │
│                                                                  │
│  send_prompt_cursor():                                           │
│  1. Проверить .cursor_chats.json                                │
│  2. Если чата нет → run_cursor_cli_create_chat()               │
│  3. run_cursor_cli(agent_name, prompt, use_chat=True)          │
│  4. Сохранить результат в chat_history.json                    │
└──────────────────────────┬──────────────────────────────────────┘
                           │
                           │ WSL: bash -c "agent -p --force --resume '<id>' ..."
                           │
                           ▼
┌──────────────────────────────────────────────────────────────────┐
│            WSL + Cursor CLI                                      │
│                                                                  │
│  $ agent -p --force --resume '<chat_id>' \                      │
│      --output-format json "<prompt>"                            │
│                                                                  │
│  Cursor Agent:                                                   │
│  - Загружает контекст из чата                                   │
│  - Компилирует prompt с контекстом проекта                      │
│  - Запускает Composer model                                     │
│  - Возвращает JSON результат                                    │
└──────────────────────────┬──────────────────────────────────────┘
                           │
                           │ JSON: {"success": true, "result": "..."}
                           ▼
┌──────────────────────────────────────────────────────────────────┐
│              Tayfa Orchestrator                                  │
│                                                                  │
│  - Сохранить в .tayfa/developer/chat_history.json              │
│  - Записать runtime: "cursor"                                   │
│  - Вернуть результат в API                                      │
└──────────────────────────┬──────────────────────────────────────┘
                           │
                           │ JSON response
                           ▼
┌──────────────────────────────────────────────────────────────────┐
│                     Tayfa Web Interface                          │
│                                                                  │
│  ✅ Agent response: "Here's error handling implementation..."   │
│     Runtime: "Cursor CLI"  Duration: 4.2s                       │
└──────────────────────────────────────────────────────────────────┘
```

---

## Заключение

Нажимая **"Cursor"** в Tayfa, ты:
1. **Переключаешь runtime** с Claude API на Cursor CLI
2. **Запускаешь локально** через WSL команду `agent`
3. **Используешь Composer model** (оптимизированный для кода)
4. **Экономишь деньги** (если у тебя подписка на Cursor)
5. **Получаешь быстрый результат** (локальная обработка)

Это позволяет Tayfa быть **гибридной системой**, использующей лучшее из обоих миров: Claude API для сложного анализа и Cursor CLI для быстрой работы с кодом.
