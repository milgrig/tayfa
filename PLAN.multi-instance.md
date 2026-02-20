# План: Multi-Instance поддержка Tayfa

## Проблема

Сейчас Tayfa может работать только с одним проектом за раз. Если запустить `tayfa.bat` дважды — порты разрулятся автоматически (`find_free_port`), но:

1. **`projects.json` → `current` — глобальный** — смена проекта в одном окне ломает другое
2. **`claude_agents.json`** — один файл, `threading.Lock()` не работает между процессами
3. **`settings.json`** — общий, изменения в одном окне влияют на другое
4. **Логи** (`tayfa_server.log`, `claude_api.log`) — пишутся в один файл, мешанина
5. **Claude API (subprocess)** — каждый экземпляр запускает свой, но `stop_claude_api()` может убить чужой процесс
6. **Нет возможности** открыть проект в новом окне из UI

## Архитектурное решение

**Каждый экземпляр Tayfa (процесс) = один проект.** Проект привязывается к процессу, а не к файлу.

### Ключевая идея: Instance ID

При старте генерируется `INSTANCE_ID` (короткий, напр. порт оркестратора: `8008`). Этот ID используется для:
- Изоляции `current project` (in-memory, не через `projects.json`)
- Суффикса лог-файлов
- Идентификации в заголовке вкладки

---

## Этапы реализации

### Этап 1: Изоляция current project (in-memory)

**Проблема:** `project_manager.py` → `get_current_project()` читает `projects.json["current"]`. Если два процесса вызовут `set_current_project()` — перезатрут друг друга.

**Решение:** Хранить current project **в памяти процесса**, не в файле.

**Файлы:**
- `kok/project_manager.py`
  - Добавить `_current_project_path: str | None = None` (модульная переменная)
  - `set_current_project(path)` — записывает в `_current_project_path` И в `projects.json` (для "last opened")
  - `get_current_project()` — читает из `_current_project_path`, НЕ из `projects.json["current"]`
  - При старте (`open_project`) — устанавливается в память процесса
  - `projects.json["current"]` остаётся для backward compat (при первом запуске без явного open — читается оттуда как fallback)

- `kok/app.py` → `_init_files_for_current_project()`
  - Без изменений — уже вызывает `get_current_project()`

**Результат:** Два процесса могут открыть разные проекты, не мешая друг другу.

---

### Этап 2: Межпроцессный file lock для claude_agents.json

**Проблема:** `claude_api.py` использует `threading.Lock()`, который работает только внутри одного процесса. Два экземпляра Claude API могут одновременно писать в `claude_agents.json`.

**Решение:** Использовать `msvcrt.locking()` (Windows) для file-level lock.

**Файлы:**
- `kok/claude_api.py`
  - Заменить `_lock = threading.Lock()` на file-based lock
  - Создать helper: `_file_lock(path)` — context manager с `msvcrt.locking` (Windows) / `fcntl.flock` (Linux/WSL)
  - Все операции load/save agents — через этот lock
  - Агенты уже scoped по проекту (`ProjectName:agent`), конфликтов данных не будет — только конфликт записи файла

---

### Этап 3: Изоляция логов

**Проблема:** `tayfa_server.log` и `claude_api.log` — один файл для всех экземпляров.

**Решение:** Добавить порт в имя файла.

**Файлы:**
- `kok/app_state.py`
  - Логирование настраивается при import (строки 25-46), порт ещё неизвестен
  - **Решение:** Отложить создание file handler. При запуске (`app.py`, после `find_free_port`) вызвать `init_logging(port)`:
    - Переименовать handler → `tayfa_server_{port}.log`
  - Функция `init_logging(port: int)`:
    - Удалить старый file handler
    - Добавить новый: `tayfa_server_{port}.log`

- `kok/claude_api.py`
  - Аналогично: лог → `claude_api_{port}.log`
  - Порт Claude API передаётся через `--port` при запуске subprocess

- `kok/app.py`
  - После `find_free_port()` вызвать `app_state.init_logging(port)`

---

### Этап 4: Безопасный Claude API subprocess

**Проблема:** Каждый экземпляр Tayfa запускает свой Claude API subprocess. При shutdown может убить чужой процесс (теоретически).

**Текущее состояние:** Уже нормально! Каждый процесс хранит `claude_api_process` (PID) в своей памяти. `stop_claude_api()` убивает именно свой PID. Проблема только если один процесс start, а другой stop — но это невозможно, т.к. глобал `claude_api_process` in-memory.

**Решение:** Минимальные изменения:
- Убедиться, что `start_claude_api()` использует `find_free_port()` (✅ уже делает)
- При shutdown — убивать только свой PID (✅ уже делает)
- **Новое:** Каждый Tayfa использует **один общий Claude API** вместо запуска своего

**Оптимизация (опционально, этап 4b):** Не запускать второй Claude API, если уже работает:
- `start_claude_api()` проверяет, жив ли процесс на `DEFAULT_CLAUDE_API_PORT`
- Если да — переиспользует (не запускает новый)
- Это экономит ресурсы

---

### Этап 5: Кнопка «Открыть в новом окне»

**Задача:** В UI добавить возможность открыть проект в новом окне (новый экземпляр Tayfa).

**Решение:** Новый API endpoint + кнопка в project picker.

**Файлы:**

- `kok/routers/projects.py` — новый endpoint:
  ```python
  @router.post("/api/projects/open-in-new-window")
  async def api_open_in_new_window(data: dict):
      """Запускает новый экземпляр Tayfa с указанным проектом."""
      path = data.get("path")
      # Запускает новый процесс: python app.py --project "path"
      # Процесс сам найдёт свободный порт, откроет браузер
      subprocess.Popen([sys.executable, "app.py", "--project", path],
                       cwd=KOK_DIR, creationflags=CREATE_NEW_PROCESS_GROUP)
      return {"status": "launched"}
  ```

- `kok/app.py` — поддержка `--project` аргумента:
  ```python
  if __name__ == "__main__":
      import argparse
      parser = argparse.ArgumentParser()
      parser.add_argument("--project", help="Path to project to open")
      args = parser.parse_args()

      if args.project:
          # Устанавливаем проект ДО запуска сервера
          from project_manager import set_current_project_in_memory
          set_current_project_in_memory(args.project)
  ```

- `kok/static/js/projects.js` — кнопка «Open in new window»:
  - В `renderProjectsList()` добавить иконку/кнопку рядом с каждым проектом
  - При клике → `POST /api/projects/open-in-new-window`
  - Текущее окно остаётся как есть

- `kok/static/index.html` — кнопка в project picker

---

### Этап 6: Заголовок вкладки с именем проекта

**Задача:** Различать вкладки — в `<title>` показывать имя проекта.

**Файлы:**
- `kok/static/js/projects.js` → `openProject()`:
  - После успешного открытия: `document.title = "Tayfa — " + projectName`

- `kok/static/js/init.js`:
  - При загрузке: запросить `/api/status` → если `has_project`, установить title

- `kok/routers/server.py` → `/api/status`:
  - Уже возвращает `current_project` с `name` — фронтенд может использовать

---

### Этап 7: Settings изоляция

**Проблема:** `settings.json` общий для всех экземпляров.

**Решение:** Настройки делятся на:
- **Глобальные** (theme, language, ports range) — общие, ОК
- **Per-instance** (autoShutdown timeout) — НЕ критично, можно оставить общими

**Минимальное действие:** Ничего не менять. Settings — это предпочтения пользователя, не состояние процесса. Одинаковая тема/язык во всех окнах — нормально.

---

## Порядок реализации

| # | Этап | Приоритет | Сложность | Файлы |
|---|------|-----------|-----------|-------|
| 1 | In-memory current project | КРИТИЧНЫЙ | Низкая | `project_manager.py` |
| 2 | File lock для agents | ВЫСОКИЙ | Средняя | `claude_api.py` |
| 3 | Изоляция логов | СРЕДНИЙ | Низкая | `app_state.py`, `claude_api.py`, `app.py` |
| 4 | Claude API subprocess | НИЗКИЙ | Низкая | `app_state.py` (проверка) |
| 5 | Кнопка "новое окно" | ВЫСОКИЙ | Средняя | `projects.py`, `app.py`, `projects.js`, `index.html` |
| 6 | Title вкладки | НИЗКИЙ | Низкая | `init.js`, `projects.js` |
| 7 | Settings | НИЗКИЙ | — | Без изменений |

## Что НЕ нужно менять

- ✅ `find_free_port()` — уже работает, порты не конфликтуют
- ✅ `API_BASE = location.origin` — фронтенд уже привязан к своему порту
- ✅ Ping/auto-shutdown — каждая вкладка пингует свой сервер
- ✅ Agent scoping (`ProjectName:agent`) — уже изолировано в `claude_agents.json`
- ✅ `.tayfa/` данные — каждый проект имеет свою папку

## Риски

1. **File lock на Windows** — `msvcrt.locking()` блокирует участок файла, не весь файл. Нужно использовать `.lock` файл-семафор или `msvcrt.locking` на весь файл через `os.open()`.
2. **Два Claude API процесса** — потребляют память (по ~100MB каждый). Оптимизация (этап 4b) решает это.
3. **projects.json race condition** — при добавлении проекта из двух экземпляров. Маловероятно, но возможно. Решение: file lock аналогично claude_agents.json.
