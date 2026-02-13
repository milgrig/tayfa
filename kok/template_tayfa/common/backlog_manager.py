#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Backlog Manager — менеджер бэклога проектных идей и фич для Tayfa Orchestrator.

Управление записями бэклога: добавление, редактирование, фильтрация, приоритизация.
Данные хранятся в .tayfa/common/backlog.json.

Примеры использования CLI:

    # Добавить запись
    python backlog_manager.py add "Фича авторизации" --description "OAuth 2.0" --priority high --next-sprint

    # Список всех записей
    python backlog_manager.py list

    # Список следующего спринта
    python backlog_manager.py next-sprint

    # Фильтр по приоритету
    python backlog_manager.py list --priority high

    # Получить запись
    python backlog_manager.py get B001

    # Редактировать
    python backlog_manager.py edit B001 --title "Новое название" --priority medium

    # Переключить флаг next_sprint
    python backlog_manager.py toggle B001

    # Удалить запись
    python backlog_manager.py remove B001

Примеры использования из кода:

    from backlog_manager import add_item, get_items, edit_item

    # Добавление
    item = add_item("Новая фича", priority="high", next_sprint=True)
    print(item["id"])  # B001

    # Получение списка
    items = get_items(next_sprint=True, priority="high")
    for item in items:
        print(f"{item['id']}: {item['title']}")

    # Редактирование
    result = edit_item("B001", title="Обновлённое название")
    if "error" not in result:
        print(f"Обновлено: {result['title']}")
"""

import argparse
import json
import sys
from datetime import datetime
from pathlib import Path

# Путь к файлу backlog.json
SCRIPT_DIR = Path(__file__).resolve().parent
BACKLOG_FILE = SCRIPT_DIR / "backlog.json"

# Допустимые приоритеты
PRIORITIES = ["high", "medium", "low"]


def _now() -> str:
    """Возвращает текущее время в ISO формате (без микросекунд)."""
    return datetime.now().isoformat(timespec='seconds')


def _load() -> dict:
    """Загрузить данные из backlog.json. Создаёт файл если не существует."""
    if not BACKLOG_FILE.exists():
        # Создаём папку если не существует
        BACKLOG_FILE.parent.mkdir(parents=True, exist_ok=True)
        # Инициализируем пустую структуру
        initial_data = {"items": [], "next_id": 1}
        _save(initial_data)
        return initial_data

    try:
        with open(BACKLOG_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    except json.JSONDecodeError:
        # Файл повреждён, создаём новый
        initial_data = {"items": [], "next_id": 1}
        _save(initial_data)
        return initial_data


def _save(data: dict) -> None:
    """Сохранить данные в backlog.json."""
    BACKLOG_FILE.parent.mkdir(parents=True, exist_ok=True)
    with open(BACKLOG_FILE, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)


def add_item(
    title: str,
    description: str = "",
    priority: str = "medium",
    next_sprint: bool = False,
    created_by: str = "boss"
) -> dict:
    """
    Добавить запись в бэклог.

    Args:
        title: Название идеи/фичи
        description: Описание (опционально)
        priority: Приоритет (high, medium, low), по умолчанию medium
        next_sprint: Флаг включения в следующий спринт
        created_by: Кто создал запись

    Returns:
        Созданная запись с полями: id, title, description, priority, next_sprint,
        created_by, created_at, updated_at
    """
    if priority not in PRIORITIES:
        return {"error": f"Недопустимый приоритет '{priority}'. Допустимые: {', '.join(PRIORITIES)}"}

    data = _load()
    item_id = f"B{data['next_id']:03d}"

    item = {
        "id": item_id,
        "title": title,
        "description": description,
        "priority": priority,
        "next_sprint": next_sprint,
        "created_by": created_by,
        "created_at": _now(),
        "updated_at": _now()
    }

    data["items"].append(item)
    data["next_id"] += 1
    _save(data)

    return item


def get_items(next_sprint: bool | None = None, priority: str | None = None) -> list[dict]:
    """
    Получить список записей с опциональными фильтрами.

    Args:
        next_sprint: Фильтр по флагу next_sprint (True/False/None=все)
        priority: Фильтр по приоритету (high/medium/low/None=все)

    Returns:
        Список записей, удовлетворяющих фильтрам
    """
    data = _load()
    items = data["items"]

    # Применяем фильтры
    if next_sprint is not None:
        items = [item for item in items if item.get("next_sprint") == next_sprint]

    if priority is not None:
        items = [item for item in items if item.get("priority") == priority]

    return items


def get_item(item_id: str) -> dict | None:
    """
    Получить одну запись по ID.

    Args:
        item_id: ID записи (например, B001)

    Returns:
        Запись или None если не найдена
    """
    data = _load()
    for item in data["items"]:
        if item["id"] == item_id:
            return item
    return None


def edit_item(
    item_id: str,
    title: str | None = None,
    description: str | None = None,
    priority: str | None = None
) -> dict:
    """
    Редактировать запись.

    Args:
        item_id: ID записи
        title: Новое название (если None, не меняется)
        description: Новое описание (если None, не меняется)
        priority: Новый приоритет (если None, не меняется)

    Returns:
        Обновлённая запись или {"error": ...}
    """
    if priority is not None and priority not in PRIORITIES:
        return {"error": f"Недопустимый приоритет '{priority}'. Допустимые: {', '.join(PRIORITIES)}"}

    data = _load()

    for item in data["items"]:
        if item["id"] == item_id:
            # Обновляем только переданные поля
            if title is not None:
                item["title"] = title
            if description is not None:
                item["description"] = description
            if priority is not None:
                item["priority"] = priority

            item["updated_at"] = _now()
            _save(data)
            return item

    return {"error": f"Запись {item_id} не найдена"}


def toggle_next_sprint(item_id: str) -> dict:
    """
    Переключить флаг next_sprint (true ↔ false).

    Args:
        item_id: ID записи

    Returns:
        Обновлённая запись или {"error": ...}
    """
    data = _load()

    for item in data["items"]:
        if item["id"] == item_id:
            item["next_sprint"] = not item.get("next_sprint", False)
            item["updated_at"] = _now()
            _save(data)
            return item

    return {"error": f"Запись {item_id} не найдена"}


def remove_item(item_id: str) -> dict:
    """
    Удалить запись из бэклога.

    Args:
        item_id: ID записи

    Returns:
        {"status": "removed", "id": ...} или {"error": ...}
    """
    data = _load()

    # Ищем и удаляем запись
    for i, item in enumerate(data["items"]):
        if item["id"] == item_id:
            data["items"].pop(i)
            _save(data)
            return {"status": "removed", "id": item_id}

    return {"error": f"Запись {item_id} не найдена"}


def _format_list(items: list[dict]) -> str:
    """
    Форматировать список записей для человекочитаемого вывода.

    Args:
        items: Список записей

    Returns:
        Отформатированная строка
    """
    if not items:
        return "Бэклог пуст."

    lines = [f"Бэклог ({len(items)}):"]

    for item in items:
        item_id = item["id"]
        priority = item["priority"]
        flag = "✓" if item.get("next_sprint") else " "
        title = item["title"]

        # Форматируем строку с выравниванием
        lines.append(f"  [{item_id}] {priority:<6} {flag} {title}")

    return "\n".join(lines)


def main():
    """CLI интерфейс для backlog_manager."""
    parser = argparse.ArgumentParser(
        description="Менеджер бэклога проектных идей и фич",
        formatter_class=argparse.RawDescriptionHelpFormatter
    )

    subparsers = parser.add_subparsers(dest="command", help="Команды")

    # Команда: add
    parser_add = subparsers.add_parser("add", help="Добавить запись в бэклог")
    parser_add.add_argument("title", help="Название идеи/фичи")
    parser_add.add_argument("--description", default="", help="Описание")
    parser_add.add_argument(
        "--priority",
        choices=PRIORITIES,
        default="medium",
        help="Приоритет (по умолчанию: medium)"
    )
    parser_add.add_argument(
        "--next-sprint",
        action="store_true",
        help="Включить в следующий спринт"
    )
    parser_add.add_argument(
        "--created-by",
        default="boss",
        help="Кто создаёт запись (по умолчанию: boss)"
    )

    # Команда: list
    parser_list = subparsers.add_parser("list", help="Показать список записей")
    parser_list.add_argument(
        "--next-sprint",
        action="store_true",
        help="Показать только записи для следующего спринта"
    )
    parser_list.add_argument(
        "--priority",
        choices=PRIORITIES,
        help="Фильтр по приоритету"
    )

    # Команда: get
    parser_get = subparsers.add_parser("get", help="Получить одну запись")
    parser_get.add_argument("id", help="ID записи (например, B001)")

    # Команда: edit
    parser_edit = subparsers.add_parser("edit", help="Редактировать запись")
    parser_edit.add_argument("id", help="ID записи")
    parser_edit.add_argument("--title", help="Новое название")
    parser_edit.add_argument("--description", help="Новое описание")
    parser_edit.add_argument("--priority", choices=PRIORITIES, help="Новый приоритет")

    # Команда: toggle
    parser_toggle = subparsers.add_parser("toggle", help="Переключить флаг next_sprint")
    parser_toggle.add_argument("id", help="ID записи")

    # Команда: remove
    parser_remove = subparsers.add_parser("remove", help="Удалить запись")
    parser_remove.add_argument("id", help="ID записи")

    # Команда: next-sprint (alias для list --next-sprint)
    parser_next = subparsers.add_parser("next-sprint", help="Показать записи для следующего спринта")

    # Парсим аргументы
    args = parser.parse_args()

    if not args.command:
        parser.print_help()
        sys.exit(1)

    try:
        # Обработка команд
        if args.command == "add":
            result = add_item(
                title=args.title,
                description=args.description,
                priority=args.priority,
                next_sprint=args.next_sprint,
                created_by=args.created_by
            )
            if "error" in result:
                print(json.dumps(result, ensure_ascii=False, indent=2), file=sys.stderr)
                sys.exit(1)
            else:
                print(json.dumps(result, ensure_ascii=False, indent=2))
                sys.exit(0)

        elif args.command == "list":
            items = get_items(
                next_sprint=args.next_sprint if args.next_sprint else None,
                priority=args.priority
            )
            print(_format_list(items))
            sys.exit(0)

        elif args.command == "get":
            item = get_item(args.id)
            if item is None:
                error = {"error": f"Запись {args.id} не найдена"}
                print(json.dumps(error, ensure_ascii=False, indent=2), file=sys.stderr)
                sys.exit(1)
            else:
                print(json.dumps(item, ensure_ascii=False, indent=2))
                sys.exit(0)

        elif args.command == "edit":
            # Проверяем что хотя бы один параметр передан
            if args.title is None and args.description is None and args.priority is None:
                error = {"error": "Необходимо указать хотя бы один параметр для редактирования: --title, --description или --priority"}
                print(json.dumps(error, ensure_ascii=False, indent=2), file=sys.stderr)
                sys.exit(1)

            result = edit_item(
                item_id=args.id,
                title=args.title,
                description=args.description,
                priority=args.priority
            )
            if "error" in result:
                print(json.dumps(result, ensure_ascii=False, indent=2), file=sys.stderr)
                sys.exit(1)
            else:
                print(json.dumps(result, ensure_ascii=False, indent=2))
                sys.exit(0)

        elif args.command == "toggle":
            result = toggle_next_sprint(args.id)
            if "error" in result:
                print(json.dumps(result, ensure_ascii=False, indent=2), file=sys.stderr)
                sys.exit(1)
            else:
                print(json.dumps(result, ensure_ascii=False, indent=2))
                sys.exit(0)

        elif args.command == "remove":
            result = remove_item(args.id)
            if "error" in result:
                print(json.dumps(result, ensure_ascii=False, indent=2), file=sys.stderr)
                sys.exit(1)
            else:
                print(json.dumps(result, ensure_ascii=False, indent=2))
                sys.exit(0)

        elif args.command == "next-sprint":
            # Alias для list --next-sprint
            items = get_items(next_sprint=True)
            print(_format_list(items))
            sys.exit(0)

        else:
            parser.print_help()
            sys.exit(1)

    except Exception as e:
        error = {"error": f"Неожиданная ошибка: {str(e)}"}
        print(json.dumps(error, ensure_ascii=False, indent=2), file=sys.stderr)
        sys.exit(1)


# =============================================================================
# Алиасы для совместимости с app.py
# =============================================================================

def set_backlog_file(path: str) -> None:
    """
    Установить путь к файлу бэклога.

    Args:
        path: Путь к файлу backlog.json (абсолютный или относительный)

    Note:
        Используется app.py для указания пути к бэклогу текущего проекта.
    """
    global BACKLOG_FILE
    BACKLOG_FILE = Path(path)


# Алиасы функций для обратной совместимости с app.py
get_backlog = get_items
get_backlog_item = get_item
create_backlog_item = add_item
update_backlog_item = edit_item
delete_backlog_item = remove_item


if __name__ == "__main__":
    main()
