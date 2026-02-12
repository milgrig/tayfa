# Tayfa — Описание проекта

## Что такое Tayfa

**Tayfa** — это мультиагентная система на базе Claude Code, где каждый AI-агент выступает в роли «сотрудника» компании. Агенты имеют свои роли (разработчик, тестировщик, архитектор), персистентную память между сессиями и изолированные рабочие папки. Система моделирует командную работу над проектами.

Агенты взаимодействуют друг с другом через файловую систему и общую систему задач. Boss создаёт задачи, назначает исполнителей, а оркестратор автоматически запускает нужного агента на каждом этапе (заказчик → разработчик → тестировщик). Каждый агент читает свой системный промпт из `prompt.md`, что позволяет гибко настраивать поведение без перезапуска.

Tayfa работает в связке WSL + Windows: Claude Code CLI выполняется внутри WSL (Ubuntu), а веб-оркестратор запускается на Windows и управляет агентами через HTTP API.

---

## Технологический стек

```
┌─────────────────────────────────────────────────────────────────┐
│                    Windows (host)                               │
│  ┌─────────────────────────────────────────────────────────┐   │
│  │          Tayfa Orchestrator (app.py)                    │   │
│  │          FastAPI + uvicorn, порт 8008                   │   │
│  │          Веб-интерфейс: http://localhost:8008           │   │
│  └─────────────────────────────────────────────────────────┘   │
│                           │ HTTP                                │
│  ┌─────────────────────────────────────────────────────────┐   │
│  │          WSL (Ubuntu)                                   │   │
│  │  ┌─────────────────────────────────────────────────┐   │   │
│  │  │  Claude API Server (claude_api.py)              │   │   │
│  │  │  FastAPI + uvicorn, порт 8788                   │   │   │
│  │  │  ~/claude_venv/ — Python venv                   │   │   │
│  │  └─────────────────────────────────────────────────┘   │   │
│  │                    │                                   │   │
│  │  ┌─────────────────────────────────────────────────┐   │   │
│  │  │  Claude Code CLI                                │   │   │
│  │  │  claude --resume <session_id> ...               │   │   │
│  │  └─────────────────────────────────────────────────┘   │   │
│  │                                                         │   │
│  │  (опционально) Cursor CLI: agent -p --resume ...       │   │
│  └─────────────────────────────────────────────────────────┘   │
└─────────────────────────────────────────────────────────────────┘
```

**Компоненты:**

| Компонент | Технология | Порт | Описание |
|-----------|------------|------|----------|
| Веб-оркестратор | Python, FastAPI, uvicorn | 8008 | Веб-интерфейс, управление проектами, агентами, задачами |
| Claude API | Python, FastAPI, uvicorn | 8788 | Прослойка для Claude Code CLI, хранит сессии агентов |
| Claude Code CLI | Node.js (WSL) | — | Основной runtime агентов, вызывается с `--resume` |
| Cursor CLI | Go (WSL, опционально) | — | Альтернативный runtime через headless Cursor |
| Хранилище | JSON-файлы | — | tasks.json, employees.json, settings.json |

---

## Основной функционал

### 1. Управление агентами

- **Создание агента**: регистрация в `employees.json` + папка с `prompt.md`
- **Системный промпт**: читается из файла при каждом вызове (можно менять без перезапуска)
- **Память**: сессия сохраняется в `~/claude_agents.json`, поддерживается `--resume`
- **Runtime**: Claude API (по умолчанию) или Cursor CLI (выбор в интерфейсе)

### 2. Система задач

Задачи управляются через `common/task_manager.py`:

```
python task_manager.py create "Название" "Описание" \
    --customer boss --developer dev_frontend --tester qa_tester \
    --sprint S001
```

**Жизненный цикл задачи:**

```
   новая      →      в_работе      →    на_проверке    →    выполнена
 (customer)       (developer)          (tester)
 детализирует     выполняет           проверяет
 требования       работу              результат
```

Каждый статус соответствует роли. При trigger оркестратор определяет, какой агент должен работать, и отправляет ему промпт.

### 3. Спринты

Группировка задач в спринты:

```
python task_manager.py create-sprint "Спринт 1" "Описание" --created-by boss
```

При создании спринта автоматически создаётся задача «Финализировать спринт», которая зависит от всех задач спринта.

### 4. Мультипроектность

Оркестратор поддерживает несколько проектов. Каждый проект имеет свою папку `.tayfa/` с конфигурацией команды:

```
MyProject/
├── src/                    # код проекта
├── package.json
└── .tayfa/                 # папка Tayfa
    ├── common/
    │   ├── tasks.json      # задачи проекта
    │   ├── employees.json  # команда проекта
    │   └── Rules/          # правила
    ├── boss/
    │   └── prompt.md
    └── ...
```

**API проектов:**
- `POST /api/projects/open` — открыть проект (init + set_current)
- `GET /api/projects` — список проектов
- `GET /api/current-project` — текущий проект

### 5. Веб-интерфейс

Одностраничное приложение (`static/index.html`):

- Статус сервера (WSL, API)
- Список агентов с runtimes
- Отправка промптов агентам
- Управление задачами и спринтами
- Переключение проектов
- Настройки (тема, порт)

---

## Как запустить

### Запуск через tayfa.bat

```cmd
cd project\kok
tayfa.bat
```

**Что происходит:**

1. Проверяется наличие Python
2. Создаётся/активируется venv
3. Устанавливаются зависимости из `requirements.txt`
4. Запускается `app.py` (uvicorn на порту 8008)
5. При старте автоматически:
   - Запускается Claude API сервер в WSL (порт 8788)
   - Открывается браузер на http://localhost:8008

### Ручной запуск

**Windows (оркестратор):**
```cmd
cd project\kok
python -m venv venv
venv\Scripts\activate
pip install -r requirements.txt
python app.py
```

**WSL (Claude API):**
```bash
source ~/claude_venv/bin/activate
cd /mnt/c/путь/к/проекту
python -m uvicorn claude_api:app --app-dir ~ --host 0.0.0.0 --port 8788
```

### Зависимости

**requirements.txt:**
```
fastapi
uvicorn
httpx
```

**WSL (claude_venv):**
- Python 3.11+
- fastapi, uvicorn
- Claude Code CLI (`npm install -g @anthropic-ai/claude-code`)

---

## Как использовать

### 1. Создание агента через веб-интерфейс

1. Открыть http://localhost:8008
2. В разделе «Сотрудники» нажать «Добавить сотрудника»
3. Указать имя (например `dev_backend`) и роль
4. Создать папку `.tayfa/dev_backend/` с файлом `prompt.md`
5. Нажать «Обеспечить агентов» — агент появится в списке

### 2. Отправка задачи агенту

**Через веб-интерфейс:**
1. Выбрать агента в списке
2. Написать промпт в текстовое поле
3. Выбрать runtime (Claude / Cursor)
4. Нажать «Отправить»

**Через систему задач:**
1. Создать задачу с назначением исполнителей
2. Нажать «Trigger» — оркестратор определит агента и отправит ему промпт
3. Агент выполнит работу и обновит статус

**Через API:**
```bash
# Claude API
curl -X POST http://localhost:8008/api/send-prompt \
  -H "Content-Type: application/json" \
  -d '{"name": "dev_frontend", "prompt": "Создай компонент кнопки"}'

# Cursor CLI
curl -X POST http://localhost:8008/api/send-prompt-cursor \
  -H "Content-Type: application/json" \
  -d '{"name": "dev_frontend", "prompt": "Создай компонент кнопки"}'
```

### 3. Просмотр результатов

- **В чате**: ответ агента отображается сразу после выполнения
- **В задаче**: результат записывается в поле `result` через task_manager
- **В файлах**: агент может создавать файлы в рабочей папке проекта

**CLI для задач:**
```bash
# Посмотреть задачу
python common/task_manager.py get T001

# Список задач спринта
python common/task_manager.py list --sprint S001

# История изменений в result
python common/task_manager.py get T001 | jq .result
```

---

## Структура проекта

```
Personel/                          # Корневая папка системы
├── common/
│   ├── task_manager.py           # CLI/API управления задачами
│   ├── employee_manager.py       # CLI/API управления сотрудниками
│   ├── tasks.json                # База задач
│   ├── employees.json            # Реестр сотрудников
│   └── Rules/                    # Общие правила для агентов
│       ├── teamwork.md
│       └── employees.md
├── boss/                         # Папка агента boss
│   ├── prompt.md                 # Системный промпт
│   ├── profile.md                # Профиль и навыки
│   ├── income/                   # Входящие задания
│   └── done/                     # Выполненные
├── hr/
├── architect/
├── developer_frontend/
├── developer_backend/
├── qa_tester/
├── devops/
└── project/
    └── kok/                      # Веб-оркестратор
        ├── app.py                # FastAPI-приложение
        ├── settings_manager.py   # Управление настройками
        ├── project_manager.py    # Мультипроектность
        ├── tayfa.bat             # Точка входа (Windows)
        ├── settings.json         # Настройки
        ├── projects.json         # Список проектов
        └── static/
            └── index.html        # Веб-интерфейс
```

---

## Шпаргалка

| Действие | Команда/URL |
|----------|-------------|
| Запустить систему | `tayfa.bat` |
| Веб-интерфейс | http://localhost:8008 |
| Статус API | `GET /api/status` |
| Список агентов | `GET /api/agents` |
| Отправить промпт (Claude) | `POST /api/send-prompt` |
| Отправить промпт (Cursor) | `POST /api/send-prompt-cursor` |
| Создать задачу | `python task_manager.py create "Название" "Описание" --customer boss --developer dev --tester qa` |
| Список задач | `python task_manager.py list` |
| Изменить статус | `python task_manager.py status T001 в_работе` |
| Записать результат | `python task_manager.py result T001 "Готово"` |
| Создать спринт | `python task_manager.py create-sprint "Название"` |
| Список сотрудников | `python employee_manager.py list` |
