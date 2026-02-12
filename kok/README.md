# Tayfa — мультиагентная система на Claude Code

## Обзор

Tayfa — система AI-агентов, где каждый агент — это «сотрудник» со своей ролью, памятью и рабочей папкой. Агенты общаются через файлы и управляются через единый HTTP API.

**Стек**: Claude Code CLI (WSL) + FastAPI (uvicorn)

---

## Архитектура

```
┌──────────────┐     POST /run      ┌─────────────────┐     claude CLI      ┌───────────┐
│  Оркестратор │ ──────────────────→ │  claude_api.py  │ ──────────────────→ │  Claude   │
│              │ ←────────────────── │  (FastAPI:8788) │ ←────────────────── │  Code     │
└──────────────┘     JSON ответ      └─────────────────┘     JSON результат  └───────────┘
                                            │
                                            ▼
                                    ~/claude_agents.json
                                    (реестр агентов, session_id)
```

Файловая система — основной способ общения между агентами:

```
Tayfa/
  Personel/
    Rules/          — общие правила для всех агентов
    Income/         — входящие описания новых сотрудников (для hr)
    boss/           — руководитель
    hr/             — HR-менеджер
    <имя>/          — папка любого сотрудника
      prompt.md     — системный промт (роль агента)
      income/       — входящие задания
      done/         — выполненные задания
```

---

## 1. Запуск WSL

Claude Code работает внутри WSL (Ubuntu). WSL вызывается из PowerShell:

```powershell
# Одиночная команда
wsl bash -c "команда"

# С login shell (нужно для claude CLI, который установлен через npm/nvm)
wsl bash -lc "команда"
```

Пути Windows в WSL:
- Пути конвертируются автоматически: `C:\Path\To\Tayfa` → `/mnt/c/Path/To/Tayfa`

---

## 2. Настройка uvicorn (Claude API сервер)

### Расположение файлов

| Файл | Путь | Описание |
|---|---|---|
| `claude_api.py` | `~/claude_api.py` (WSL home) | FastAPI-приложение |
| `claude_run.sh` | `~/claude_run.sh` (WSL home) | Legacy-скрипт для `/run` без агента |
| `claude_agents.json` | `~/claude_agents.json` (WSL home) | Реестр агентов (создаётся автоматически) |
| Virtual env | `~/claude_venv/` | Python venv с uvicorn и fastapi |

### Запуск

```bash
# В WSL:
source ~/claude_venv/bin/activate
python -m uvicorn claude_api:app --app-dir ~ --host 0.0.0.0 --port 8788
```

Из PowerShell одной командой:
```powershell
wsl bash -lc "source ~/claude_venv/bin/activate && cd <WSL-путь-к-Tayfa> && python -m uvicorn claude_api:app --app-dir ~ --host 0.0.0.0 --port 8788"
```

### Логи

uvicorn пишет логи в stderr. При запуске через скрипт можно перенаправить:
```powershell
$proc = Start-Process -FilePath "wsl" `
  -ArgumentList "bash", "-c", "`"source ~/claude_venv/bin/activate && cd <WSL-путь-к-Tayfa> && python -m uvicorn claude_api:app --app-dir ~ --host 0.0.0.0 --port 8788`"" `
  -PassThru -WindowStyle Hidden `
  -RedirectStandardOutput "claude-api.out.log" -RedirectStandardError "claude-api.err.log"
```

---

## 3. API — работа с агентами

Все операции через один эндпоинт:

```
POST http://localhost:8788/run
Content-Type: application/json
```

### Создать агента

```json
{
  "name": "developer_python",
  "system_prompt_file": "Personel/developer_python/prompt.md",
  "workdir": "<WSL-путь-к-Tayfa>",
  "allowed_tools": "Read Edit Bash"
}
```

Ответ: `{"status": "created", "agent": "developer_python"}`

### Отправить задачу агенту

Агент помнит историю диалога (через session_id + `--resume`).

```json
{
  "name": "developer_python",
  "prompt": "Напиши парсер для CSV файлов"
}
```

Ответ:
```json
{
  "code": 0,
  "result": "Текст ответа агента...",
  "session_id": "uuid",
  "cost_usd": 0.05,
  "is_error": false,
  "num_turns": 3
}
```

### Сбросить память агента

Сбрасывает историю диалога. Системный промт и настройки сохраняются.

```json
{
  "name": "developer_python",
  "reset": true
}
```

### Разовый запрос (без агента)

Без истории, без системного промта.

```json
{
  "prompt": "Какой сейчас год?"
}
```

### Список агентов

```
GET http://localhost:8788/agents
```

### Удалить агента

```
DELETE http://localhost:8788/agents/developer_python
```

---

## 4. Как работает system_prompt_file

Если у агента указан `system_prompt_file` — промт читается из md-файла при **каждом** вызове `/run`. Это значит:

- Отредактировали `prompt.md` → следующий вызов агента уже с новым промтом.
- Не нужно пересоздавать агента.
- Путь относительно `workdir` (обычно `<WSL-путь-к-Tayfa>`).

---

## 5. Как агенты общаются между собой

Агенты взаимодействуют через **систему задач** (`common/task_manager.py`). Boss создаёт задачу с указанием заказчика, разработчика и тестировщика. Оркестратор на каждом этапе запускает соответствующего агента.

Также агенты могут оставлять задания друг другу через папку `income/`.

---

## 6. Cursor CLI через WSL

Оркестратор может отправлять запросы не только в Claude API, но и в **Cursor CLI** (headless). В интерфейсе при выборе агента можно указать «Куда отправить: Claude / Cursor». При выборе Cursor запрос выполняется через WSL.

### Установка Cursor CLI в WSL

```bash
# В WSL:
curl https://cursor.com/install -fsSL | bash
# Добавить в PATH (в ~/.bashrc):
export PATH="$HOME/.local/bin:$PATH"
source ~/.bashrc
# Проверка:
agent --version
```

Для headless-режима в скриптах нужен API-ключ: `export CURSOR_API_KEY=...` (см. [документацию Cursor](https://cursor.com/docs/cli/headless)).

### Создание чатов (create-chat)

Перед отправкой сообщений в Cursor для каждого агента нужен свой чат. Команда в WSL:

```bash
bash -lc 'export PATH="$HOME/.local/bin:$PATH"; cd <WSL-путь-к-Tayfa>; agent --print --output-format json create-chat'
```

Ответ — JSON с полем `chat_id` (или `session_id` / `id`). Оркестратор сохраняет привязку «агент → chat_id» в `.cursor_chats.json` в корне Tayfa.

В интерфейсе: кнопка **«Создать чаты Cursor (WSL)»** вызывает для всех агентов с runtime Cursor команду `create-chat` и сохраняет chat_id. Можно создать чат для одного агента: `POST /api/cursor-create-chat` с телом `{ "name": "имя_агента" }`.

### Как вызывается отправка

Оркестратор при отправке в Cursor:

1. Для агента берёт или создаёт чат (create-chat при отсутствии записи в `.cursor_chats.json`).
2. Формирует промпт с ролью и заданием, записывает в `.cursor_cli_prompt.txt`.
3. Запускает в WSL: `agent -p --force --resume <chat_id> --output-format json "$(cat .cursor_cli_prompt.txt)"` из папки проекта.
4. Парсит JSON ответа, возвращает поле `result` в чат, удаляет временный файл.

Таймаут вызова: 600 с. Команда `agent` должна быть в `PATH` в WSL (обычно `~/.local/bin`).

---

## 7. Краткая шпаргалка

| Действие | Как |
|---|---|
| Запустить API | `wsl bash -lc "source ~/claude_venv/bin/activate && cd <WSL-путь-к-Tayfa> && python -m uvicorn claude_api:app --app-dir ~ --host 0.0.0.0 --port 8788"` |
| Создать агента | `POST /run` с `name` + `system_prompt_file` (без `prompt`) |
| Задача агенту (Claude) | `POST /run` с `name` + `prompt` |
| Задача агенту (Cursor CLI) | `POST /api/send-prompt-cursor` с `name` + `prompt` (использует чат агента, при необходимости create-chat) |
| Создать чат Cursor для агента | `POST /api/cursor-create-chat` с `{ "name": "агент" }` |
| Создать чаты Cursor для всех | `POST /api/cursor-create-chats` |
| Список чатов Cursor | `GET /api/cursor-chats` |
| Сброс памяти | `POST /run` с `name` + `reset: true` |
| Список агентов | `GET /agents` |
| Удалить агента | `DELETE /agents/<name>` |
| Реестр агентов | `~/claude_agents.json` (WSL) |
| Правила агентов | `<путь-к-Tayfa>\Personel\Rules\` |
