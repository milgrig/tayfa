"""
Backlog Manager — модуль для работы с бэклогом в Tayfa.

Управляет записями бэклога (идеи, задачи на будущее, требования).
Хранит данные в backlog.json.
"""

import json
from datetime import datetime
from pathlib import Path

# По умолчанию в текущей директории (будет переопределяться через set_backlog_file)
BACKLOG_FILE = Path(__file__).parent / "backlog.json"


def _now() -> str:
    """Возвращает текущую дату-время в ISO 8601 формате."""
    return datetime.now().isoformat()


def _load() -> dict:
    """Загружает данные из backlog.json."""
    if not BACKLOG_FILE.exists():
        return {"items": [], "next_id": 1}
    try:
        with open(BACKLOG_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    except (json.JSONDecodeError, IOError):
        return {"items": [], "next_id": 1}


def _save(data: dict) -> None:
    """Сохраняет данные в backlog.json."""
    BACKLOG_FILE.parent.mkdir(parents=True, exist_ok=True)
    with open(BACKLOG_FILE, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)


def get_backlog(priority: str | None = None, next_sprint: bool | None = None) -> list[dict]:
    """
    Получить список записей бэклога с фильтрацией.

    Args:
        priority: Фильтр по приоритету ("high", "medium", "low")
        next_sprint: Фильтр по флагу "в следующий спринт" (True/False)

    Returns:
        Список записей бэклога, отсортированный по приоритету и дате
    """
    data = _load()
    items = data.get("items", [])

    # Фильтрация по приоритету
    if priority:
        items = [item for item in items if item.get("priority") == priority]

    # Фильтрация по next_sprint
    if next_sprint is not None:
        items = [item for item in items if item.get("next_sprint", False) == next_sprint]

    # Сортировка: high → medium → low, затем по дате создания (новые выше)
    priority_order = {"high": 0, "medium": 1, "low": 2}
    items.sort(key=lambda x: (
        priority_order.get(x.get("priority", "medium"), 1),
        x.get("created_at", "")
    ), reverse=False)

    return items


def get_backlog_item(item_id: str) -> dict | None:
    """Получить конкретную запись бэклога по ID."""
    data = _load()
    for item in data.get("items", []):
        if item.get("id") == item_id:
            return item
    return None


def create_backlog_item(
    title: str,
    description: str = "",
    priority: str = "medium",
    next_sprint: bool = False,
    created_by: str = "boss"
) -> dict:
    """
    Создать новую запись в бэклоге.

    Args:
        title: Название (обязательное)
        description: Описание
        priority: Приоритет ("high", "medium", "low")
        next_sprint: Флаг "в следующий спринт"
        created_by: Кто создал (роль агента)

    Returns:
        Созданная запись
    """
    if not title or not title.strip():
        raise ValueError("Title is required")

    # Валидация приоритета
    if priority not in ("high", "medium", "low"):
        priority = "medium"

    data = _load()
    item_id = f"B{data['next_id']:03d}"

    item = {
        "id": item_id,
        "title": title.strip(),
        "description": description.strip(),
        "priority": priority,
        "next_sprint": bool(next_sprint),
        "created_by": created_by,
        "created_at": _now(),
        "updated_at": _now(),
    }

    data["items"].append(item)
    data["next_id"] += 1
    _save(data)

    return item


def update_backlog_item(item_id: str, **fields) -> dict:
    """
    Обновить запись в бэклоге.

    Args:
        item_id: ID записи
        **fields: Поля для обновления (title, description, priority, next_sprint)

    Returns:
        Обновлённая запись или {"error": "..."}
    """
    data = _load()

    for item in data["items"]:
        if item["id"] == item_id:
            # Обновляем разрешённые поля
            if "title" in fields:
                title = fields["title"].strip() if fields["title"] else ""
                if not title:
                    return {"error": "Title cannot be empty"}
                item["title"] = title

            if "description" in fields:
                item["description"] = fields["description"].strip() if fields["description"] else ""

            if "priority" in fields:
                priority = fields["priority"]
                if priority in ("high", "medium", "low"):
                    item["priority"] = priority

            if "next_sprint" in fields:
                item["next_sprint"] = bool(fields["next_sprint"])

            item["updated_at"] = _now()
            _save(data)
            return item

    return {"error": f"Backlog item {item_id} not found"}


def delete_backlog_item(item_id: str) -> dict:
    """
    Удалить запись из бэклога.

    Args:
        item_id: ID записи

    Returns:
        {"status": "deleted", "id": "..."} или {"error": "..."}
    """
    data = _load()

    for i, item in enumerate(data["items"]):
        if item["id"] == item_id:
            data["items"].pop(i)
            _save(data)
            return {"status": "deleted", "id": item_id}

    return {"error": f"Backlog item {item_id} not found"}


def toggle_next_sprint(item_id: str) -> dict:
    """
    Переключить флаг "в следующий спринт".

    Args:
        item_id: ID записи

    Returns:
        Обновлённая запись или {"error": "..."}
    """
    data = _load()

    for item in data["items"]:
        if item["id"] == item_id:
            item["next_sprint"] = not item.get("next_sprint", False)
            item["updated_at"] = _now()
            _save(data)
            return item

    return {"error": f"Backlog item {item_id} not found"}


def set_backlog_file(path: str | Path) -> None:
    """Установить путь к файлу backlog.json (для работы с разными проектами)."""
    global BACKLOG_FILE
    BACKLOG_FILE = Path(path)


# ── Для CLI использования ────────────────────────────────────────────────────

if __name__ == "__main__":
    import sys

    if len(sys.argv) < 2:
        print("Usage: python backlog_manager.py <command> [args]")
        print("Commands: list, add, update, delete, toggle")
        sys.exit(1)

    command = sys.argv[1]

    if command == "list":
        items = get_backlog()
        for item in items:
            print(f"{item['id']}: {item['title']} [{item['priority']}] {'✓' if item['next_sprint'] else ''}")

    elif command == "add":
        if len(sys.argv) < 3:
            print("Usage: python backlog_manager.py add <title> [description] [priority] [next_sprint]")
            sys.exit(1)
        title = sys.argv[2]
        description = sys.argv[3] if len(sys.argv) > 3 else ""
        priority = sys.argv[4] if len(sys.argv) > 4 else "medium"
        next_sprint = sys.argv[5].lower() == "true" if len(sys.argv) > 5 else False

        item = create_backlog_item(title, description, priority, next_sprint)
        print(f"Created: {item['id']}")

    elif command == "update":
        if len(sys.argv) < 3:
            print("Usage: python backlog_manager.py update <id> [title=...] [priority=...]")
            sys.exit(1)
        item_id = sys.argv[2]
        fields = {}
        for arg in sys.argv[3:]:
            if "=" in arg:
                key, value = arg.split("=", 1)
                fields[key] = value

        result = update_backlog_item(item_id, **fields)
        if "error" in result:
            print(f"Error: {result['error']}")
        else:
            print(f"Updated: {result['id']}")

    elif command == "delete":
        if len(sys.argv) < 3:
            print("Usage: python backlog_manager.py delete <id>")
            sys.exit(1)
        item_id = sys.argv[2]
        result = delete_backlog_item(item_id)
        if "error" in result:
            print(f"Error: {result['error']}")
        else:
            print(f"Deleted: {result['id']}")

    elif command == "toggle":
        if len(sys.argv) < 3:
            print("Usage: python backlog_manager.py toggle <id>")
            sys.exit(1)
        item_id = sys.argv[2]
        result = toggle_next_sprint(item_id)
        if "error" in result:
            print(f"Error: {result['error']}")
        else:
            print(f"Toggled: {result['id']} → next_sprint={result['next_sprint']}")

    else:
        print(f"Unknown command: {command}")
        sys.exit(1)
