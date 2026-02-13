# Архивация спринтов

## Цель

После завершения спринта его данные архивируются:
- **Агенты НЕ видят** архивные данные (чтобы не засорять контекст)
- **Пользователь может достать** при необходимости (история сохранена)

---

## Структура

```
.tayfa/
├── common/
│   ├── tasks.json          ← активные задачи и спринты
│   └── archive/            ← архив завершённых спринтов
│       ├── S001/
│       │   ├── sprint.json     ← данные спринта
│       │   ├── tasks.json      ← задачи спринта (snapshot)
│       │   └── summary.md      ← итоги (опционально)
│       ├── S002/
│       └── ...
```

---

## Процесс архивации

### Когда архивируется

Спринт архивируется **автоматически** при выполнении задачи "Финализировать спринт":
1. Все задачи спринта имеют статус `выполнена` или `отменена`
2. Финализирующая задача переводится в `выполнена`
3. Выполняется релиз (merge, tag, push)
4. **→ Архивация спринта**

### Что происходит при архивации

1. **Создаётся папка архива**: `.tayfa/common/archive/S001/`

2. **Сохраняется snapshot спринта**: `sprint.json`
   ```json
   {
     "id": "S001",
     "title": "Название",
     "status": "завершён",
     "version": "v0.1.0",
     "released_at": "2025-01-15T12:00:00",
     "created_by": "boss"
   }
   ```

3. **Сохраняются задачи спринта**: `tasks.json`
   ```json
   [
     {"id": "T001", "title": "...", "status": "выполнена", "result": "..."},
     {"id": "T002", "title": "...", "status": "выполнена", "result": "..."}
   ]
   ```

4. **Удаляются из основного tasks.json**:
   - Задачи спринта удаляются
   - Спринт удаляется из списка спринтов
   - `next_id` и `next_sprint_id` НЕ сбрасываются (ID уникальны)

---

## Правила для агентов

### ⛔ Агенты НЕ смотрят в архив

```
ЗАПРЕЩЕНО для агентов:
- Читать файлы из .tayfa/common/archive/
- Использовать архивные данные в работе
- Ссылаться на архивные задачи
```

**Почему:** Архив — это история для человека. Агентам важны только активные задачи.

### ✅ Агенты работают только с активными данными

```
РАЗРЕШЕНО для агентов:
- Читать .tayfa/common/tasks.json (активные задачи)
- Использовать task_manager.py list/get/status/result
```

---

## Доступ пользователя

Пользователь может в любой момент:

### Посмотреть список архивных спринтов
```bash
ls .tayfa/common/archive/
# S001  S002  S003
```

### Посмотреть данные конкретного спринта
```bash
cat .tayfa/common/archive/S001/sprint.json
cat .tayfa/common/archive/S001/tasks.json
```

### Восстановить спринт (при необходимости)
Ручное восстановление: скопировать данные обратно в `tasks.json`.

---

## Реализация в task_manager.py

Функция `archive_sprint(sprint_id)`:

```python
def archive_sprint(sprint_id: str) -> dict:
    """
    Архивировать завершённый спринт.
    Вызывается автоматически при финализации.
    """
    data = _load()

    # 1. Найти спринт
    sprint = None
    for s in data["sprints"]:
        if s["id"] == sprint_id:
            sprint = s
            break
    if not sprint or sprint["status"] != "завершён":
        return {"error": "Спринт не найден или не завершён"}

    # 2. Собрать задачи спринта
    sprint_tasks = [t for t in data["tasks"] if t.get("sprint_id") == sprint_id]

    # 3. Создать папку архива
    archive_dir = TASKS_FILE.parent / "archive" / sprint_id
    archive_dir.mkdir(parents=True, exist_ok=True)

    # 4. Сохранить sprint.json
    (archive_dir / "sprint.json").write_text(
        json.dumps(sprint, ensure_ascii=False, indent=2),
        encoding="utf-8"
    )

    # 5. Сохранить tasks.json
    (archive_dir / "tasks.json").write_text(
        json.dumps(sprint_tasks, ensure_ascii=False, indent=2),
        encoding="utf-8"
    )

    # 6. Удалить из активных данных
    data["tasks"] = [t for t in data["tasks"] if t.get("sprint_id") != sprint_id]
    data["sprints"] = [s for s in data["sprints"] if s["id"] != sprint_id]

    _save(data)

    return {
        "archived": sprint_id,
        "path": str(archive_dir),
        "tasks_count": len(sprint_tasks)
    }
```

### Интеграция в релиз

В функции `update_task_status()` после успешного релиза:

```python
# После release_result["success"]:
archive_result = archive_sprint(sprint_id)
result["sprint_archived"] = archive_result
```

---

## CLI команды

```bash
# Посмотреть архивные спринты
python .tayfa/common/task_manager.py archived

# Посмотреть конкретный архивный спринт
python .tayfa/common/task_manager.py archived S001
```

---

## Итого

| Аспект | Описание |
|--------|----------|
| **Когда** | Автоматически при финализации спринта |
| **Куда** | `.tayfa/common/archive/S00X/` |
| **Что** | sprint.json + tasks.json |
| **Агенты** | НЕ имеют доступа |
| **Пользователь** | Полный доступ через файловую систему |
| **ID** | Остаются уникальными (не переиспользуются) |
