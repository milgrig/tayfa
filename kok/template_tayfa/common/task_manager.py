#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Управление задачами и спринтами. Агенты вызывают эти функции для создания и обновления задач.

Статусы задач:
  новая        — задача создана, ещё не начата
  в_работе     — разработчик выполняет задачу
  на_проверке  — тестировщик проверяет результат
  выполнена    — задача завершена и принята
  отменена     — задача отменена

Роли в задаче:
  customer   (заказчик)    — детализирует требования
  developer  (разработчик) — выполняет задачу
  tester     (тестировщик) — проверяет результат

Спринты:
  Спринт — группа задач, объединённых общей целью.
  При создании спринта автоматически создаётся задача "Финализировать спринт",
  которая зависит от всех задач спринта.
  Все задачи привязаны к спринту (sprint_id).
  У задачи есть поле depends_on — список ID задач, от которых она зависит.

CLI использование:
  python task_manager.py create "Заголовок" "Описание" --customer boss --developer dev_frontend --tester qa_tester --sprint S001
  python task_manager.py backlog tasks.json           # массовое создание из JSON-файла
  python task_manager.py list [--status новая] [--sprint S001]
  python task_manager.py get T001
  python task_manager.py status T001 в_работе
  python task_manager.py result T001 "Описание результата"
  python task_manager.py create-sprint "Название спринта" "Описание" --created_by boss
  python task_manager.py sprints
  python task_manager.py sprint S001
"""

import argparse
import json
import sys
from pathlib import Path
from datetime import datetime

TASKS_FILE = Path(__file__).resolve().parent / "tasks.json"
DISCUSSIONS_DIR = Path(__file__).resolve().parent / "discussions"


def set_tasks_file(path: str | Path) -> None:
    """Установить путь к файлу tasks.json (для работы с разными проектами)."""
    global TASKS_FILE, DISCUSSIONS_DIR
    TASKS_FILE = Path(path)
    # Автоматически устанавливаем путь к discussions рядом с tasks.json
    DISCUSSIONS_DIR = TASKS_FILE.parent / "discussions"


STATUSES = ["новая", "в_работе", "на_проверке", "выполнена", "отменена"]
SPRINT_STATUSES = ["активный", "завершён", "релиз"]

# Какой статус ставится при «следующем шаге» и кто отвечает за текущий шаг
STATUS_FLOW = {
    "новая":       {"agent_role": "customer",  "next_status": "в_работе"},
    "в_работе":    {"agent_role": "developer", "next_status": "на_проверке"},
    "на_проверке": {"agent_role": "tester",    "next_status": "выполнена"},
}


def _load() -> dict:
    """Загрузить файл задач."""
    if not TASKS_FILE.exists():
        return {"tasks": [], "sprints": [], "next_id": 1, "next_sprint_id": 1}
    try:
        data = json.loads(TASKS_FILE.read_text(encoding="utf-8"))
        # Обратная совместимость: добавляем поля, если их нет
        if "sprints" not in data:
            data["sprints"] = []
        if "next_sprint_id" not in data:
            data["next_sprint_id"] = 1
        return data
    except Exception:
        return {"tasks": [], "sprints": [], "next_id": 1, "next_sprint_id": 1}


def _save(data: dict) -> None:
    """Сохранить файл задач."""
    TASKS_FILE.parent.mkdir(parents=True, exist_ok=True)
    TASKS_FILE.write_text(
        json.dumps(data, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )


def _now() -> str:
    return datetime.now().isoformat(timespec="seconds")


def _now_formatted() -> str:
    """Возвращает текущее время в формате 'YYYY-MM-DD HH:MM'."""
    return datetime.now().strftime("%Y-%m-%d %H:%M")


def _create_discussion_file(task: dict) -> bool:
    """
    Создать файл обсуждения для задачи.

    Путь: .tayfa/common/discussions/{task_id}.md
    Создаёт файл с шаблоном, включающим описание задачи.
    Если файл уже существует — не перезаписывает.

    Args:
        task: Словарь с данными задачи (id, title, description, customer)

    Returns:
        True если файл создан, False если уже существовал или ошибка
    """
    task_id = task.get("id", "")
    if not task_id:
        return False

    discussion_file = DISCUSSIONS_DIR / f"{task_id}.md"

    # Не перезаписываем существующий файл
    if discussion_file.exists():
        return False

    # Убедимся, что папка discussions существует
    DISCUSSIONS_DIR.mkdir(parents=True, exist_ok=True)

    # Формируем шаблон
    title = task.get("title", "")
    description = task.get("description", "")
    customer = task.get("customer", "boss")
    date = _now_formatted()

    template = f"""# Обсуждение задачи {task_id}: {title}

## [{date}] {customer} (заказчик)

### Описание задачи

{description}

### Критерии приёмки

[Будут уточнены заказчиком]

---
"""

    try:
        discussion_file.write_text(template, encoding="utf-8")
        return True
    except OSError:
        return False


# ── Спринты ──────────────────────────────────────────────────────────────────


def create_sprint(
    title: str,
    description: str = "",
    created_by: str = "boss",
) -> dict:
    """
    Создать новый спринт. Возвращает созданный спринт.
    Автоматически создаёт задачу "Финализировать спринт".
    """
    data = _load()
    sprint_id = f"S{data['next_sprint_id']:03d}"
    sprint = {
        "id": sprint_id,
        "title": title,
        "description": description,
        "status": "активный",
        "created_by": created_by,
        "created_at": _now(),
        "updated_at": _now(),
    }
    data["sprints"].append(sprint)
    data["next_sprint_id"] += 1

    # Создаём задачу "Финализировать спринт"
    finalize_task_id = f"T{data['next_id']:03d}"
    finalize_task = {
        "id": finalize_task_id,
        "title": f"Финализировать спринт: {title}",
        "description": f"Финальная задача спринта {sprint_id}. Зависит от всех остальных задач спринта. "
                       f"Когда все задачи спринта выполнены — проверить результаты и закрыть спринт.",
        "status": "новая",
        "customer": created_by,
        "developer": created_by,
        "tester": created_by,
        "result": "",
        "sprint_id": sprint_id,
        "depends_on": [],  # Будет обновляться при добавлении задач в спринт
        "is_finalize": True,
        "created_at": _now(),
        "updated_at": _now(),
    }
    data["tasks"].append(finalize_task)
    data["next_id"] += 1

    sprint["finalize_task_id"] = finalize_task_id
    _save(data)
    return {**sprint, "finalize_task": finalize_task}


def get_sprints() -> list[dict]:
    """Получить все спринты."""
    data = _load()
    return data.get("sprints", [])


def get_sprint(sprint_id: str) -> dict | None:
    """Получить спринт по ID."""
    data = _load()
    for sprint in data.get("sprints", []):
        if sprint["id"] == sprint_id:
            return sprint
    return None


def update_sprint_status(sprint_id: str, new_status: str) -> dict:
    """Изменить статус спринта."""
    if new_status not in SPRINT_STATUSES:
        return {"error": f"Неверный статус спринта. Допустимые: {', '.join(SPRINT_STATUSES)}"}
    data = _load()
    for sprint in data.get("sprints", []):
        if sprint["id"] == sprint_id:
            sprint["status"] = new_status
            sprint["updated_at"] = _now()
            _save(data)
            return sprint
    return {"error": f"Спринт {sprint_id} не найден"}


def update_sprint_release(sprint_id: str, version: str, pushed: bool = True) -> dict:
    """
    Обновить спринт после успешного релиза.
    - pushed=True → статус 'релиз' (успешный push в GitHub)
    - pushed=False → статус 'завершён' (локальный релиз без push)
    """
    data = _load()
    for sprint in data.get("sprints", []):
        if sprint["id"] == sprint_id:
            sprint["status"] = "релиз" if pushed else "завершён"
            sprint["version"] = version
            sprint["released_at"] = _now()
            sprint["updated_at"] = _now()
            _save(data)
            return sprint
    return {"error": f"Спринт {sprint_id} не найден"}


def delete_sprint(sprint_id: str) -> dict:
    """
    Удалить спринт и связанную финализирующую задачу.
    Используется для отката при ошибке создания git-ветки.

    Возвращает:
    - {"success": True} если спринт удалён
    - {"error": "..."} если спринт не найден
    """
    data = _load()

    # Найти спринт
    sprint_index = None
    finalize_task_id = None
    for i, sprint in enumerate(data.get("sprints", [])):
        if sprint["id"] == sprint_id:
            sprint_index = i
            finalize_task_id = sprint.get("finalize_task_id")
            break

    if sprint_index is None:
        return {"error": f"Спринт {sprint_id} не найден"}

    # Удалить спринт
    data["sprints"].pop(sprint_index)

    # Удалить финализирующую задачу
    if finalize_task_id:
        data["tasks"] = [t for t in data["tasks"] if t["id"] != finalize_task_id]

    _save(data)
    return {"success": True}


def _update_finalize_depends(data: dict, sprint_id: str) -> None:
    """Обновить depends_on у финализирующей задачи спринта."""
    # Найти все задачи спринта (кроме финализирующей)
    sprint_task_ids = [
        t["id"] for t in data["tasks"]
        if t.get("sprint_id") == sprint_id and not t.get("is_finalize")
    ]
    # Найти финализирующую задачу
    for task in data["tasks"]:
        if task.get("sprint_id") == sprint_id and task.get("is_finalize"):
            task["depends_on"] = sprint_task_ids
            task["updated_at"] = _now()
            break


# ── Основные функции (вызываются агентами) ───────────────────────────────────


def create_task(
    title: str,
    description: str,
    customer: str,
    developer: str,
    tester: str,
    sprint_id: str = "",
    depends_on: list[str] | None = None,
) -> dict:
    """
    Создать новую задачу. Только boss может создавать задачи.
    sprint_id: ID спринта, к которому привязана задача.
    depends_on: список ID задач, от которых зависит эта задача.
    Возвращает созданную задачу.
    """
    data = _load()
    task_id = f"T{data['next_id']:03d}"
    task = {
        "id": task_id,
        "title": title,
        "description": description,
        "status": "новая",
        "customer": customer,
        "developer": developer,
        "tester": tester,
        "result": "",
        "sprint_id": sprint_id,
        "depends_on": depends_on or [],
        "created_at": _now(),
        "updated_at": _now(),
    }
    data["tasks"].append(task)
    data["next_id"] += 1

    # Обновить depends_on у финализирующей задачи спринта
    if sprint_id:
        _update_finalize_depends(data, sprint_id)

    _save(data)

    # Создать файл обсуждения для задачи
    _create_discussion_file(task)

    return task


def create_backlog(tasks_list: list[dict]) -> list[dict]:
    """
    Создать несколько задач за раз (бэклог).
    tasks_list: список словарей с полями title, description, customer, developer, tester,
                опционально sprint_id и depends_on.
    Возвращает список созданных задач.
    """
    results = []
    for t in tasks_list:
        task = create_task(
            title=t["title"],
            description=t.get("description", ""),
            customer=t["customer"],
            developer=t["developer"],
            tester=t["tester"],
            sprint_id=t.get("sprint_id", ""),
            depends_on=t.get("depends_on"),
        )
        results.append(task)
    return results


def update_task_status(task_id: str, new_status: str) -> dict:
    """
    Изменить статус задачи.
    new_status: одно из "новая", "в_работе", "на_проверке", "выполнена", "отменена".
    """
    if new_status not in STATUSES:
        return {"error": f"Неверный статус. Допустимые: {', '.join(STATUSES)}"}
    data = _load()
    for task in data["tasks"]:
        if task["id"] == task_id:
            old_status = task["status"]
            task["status"] = new_status
            task["updated_at"] = _now()
            _save(data)
            return {**task, "old_status": old_status}
    return {"error": f"Задача {task_id} не найдена"}


def set_task_result(task_id: str, result_text: str) -> dict:
    """Записать результат работы в задачу."""
    data = _load()
    for task in data["tasks"]:
        if task["id"] == task_id:
            task["result"] = result_text
            task["updated_at"] = _now()
            _save(data)
            return task
    return {"error": f"Задача {task_id} не найдена"}


def get_tasks(status: str | None = None, sprint_id: str | None = None) -> list[dict]:
    """Получить список задач, опционально отфильтрованных по статусу и/или спринту."""
    data = _load()
    tasks = data["tasks"]
    if status:
        tasks = [t for t in tasks if t["status"] == status]
    if sprint_id:
        tasks = [t for t in tasks if t.get("sprint_id") == sprint_id]
    return tasks


def get_task(task_id: str) -> dict | None:
    """Получить одну задачу по ID."""
    data = _load()
    for task in data["tasks"]:
        if task["id"] == task_id:
            return task
    return None


def get_next_agent(task_id: str) -> dict | None:
    """
    Определить, какой агент должен работать над задачей на текущем шаге.
    Возвращает {"agent": <имя>, "role": <роль>, "next_status": <новый статус>} или None.
    """
    task = get_task(task_id)
    if not task:
        return None
    flow = STATUS_FLOW.get(task["status"])
    if not flow:
        return None  # задача выполнена или отменена
    agent_role = flow["agent_role"]
    agent_name = task.get(agent_role, "")
    return {
        "agent": agent_name,
        "role": agent_role,
        "next_status": flow["next_status"],
        "task": task,
    }


# ── CLI ──────────────────────────────────────────────────────────────────────


def _cli():
    parser = argparse.ArgumentParser(description="Управление задачами и спринтами Tayfa")
    sub = parser.add_subparsers(dest="command", help="Команда")

    # create
    p_create = sub.add_parser("create", help="Создать задачу")
    p_create.add_argument("title", help="Заголовок задачи")
    p_create.add_argument("description", nargs="?", default="", help="Описание задачи")
    p_create.add_argument("--customer", required=True, help="Заказчик (имя агента)")
    p_create.add_argument("--developer", required=True, help="Разработчик (имя агента)")
    p_create.add_argument("--tester", required=True, help="Тестировщик (имя агента)")
    p_create.add_argument("--sprint", default="", help="ID спринта (например S001)")
    p_create.add_argument("--depends-on", nargs="*", default=[], help="ID задач-зависимостей")

    # backlog
    p_backlog = sub.add_parser("backlog", help="Создать бэклог из JSON-файла")
    p_backlog.add_argument("file", help="JSON-файл со списком задач")

    # list
    p_list = sub.add_parser("list", help="Список задач")
    p_list.add_argument("--status", choices=STATUSES, help="Фильтр по статусу")
    p_list.add_argument("--sprint", default=None, help="Фильтр по спринту")

    # get
    p_get = sub.add_parser("get", help="Получить задачу по ID")
    p_get.add_argument("task_id", help="ID задачи (например T001)")

    # status
    p_status = sub.add_parser("status", help="Изменить статус задачи")
    p_status.add_argument("task_id", help="ID задачи")
    p_status.add_argument("new_status", choices=STATUSES, help="Новый статус")

    # result
    p_result = sub.add_parser("result", help="Записать результат работы")
    p_result.add_argument("task_id", help="ID задачи")
    p_result.add_argument("text", help="Текст результата")

    # create-sprint
    p_sprint = sub.add_parser("create-sprint", help="Создать спринт")
    p_sprint.add_argument("title", help="Название спринта")
    p_sprint.add_argument("description", nargs="?", default="", help="Описание спринта")
    p_sprint.add_argument("--created-by", default="boss", help="Кто создал спринт")

    # sprints
    sub.add_parser("sprints", help="Список спринтов")

    # sprint (get)
    p_sprint_get = sub.add_parser("sprint", help="Получить спринт по ID")
    p_sprint_get.add_argument("sprint_id", help="ID спринта (например S001)")

    args = parser.parse_args()

    if not args.command:
        parser.print_help()
        sys.exit(1)

    if args.command == "create":
        task = create_task(
            args.title, args.description,
            args.customer, args.developer, args.tester,
            sprint_id=args.sprint,
            depends_on=args.depends_on if args.depends_on else None,
        )
        print(json.dumps(task, ensure_ascii=False, indent=2))

    elif args.command == "backlog":
        file_path = Path(args.file)
        if not file_path.exists():
            print(f"Файл не найден: {file_path}")
            sys.exit(1)
        tasks_list = json.loads(file_path.read_text(encoding="utf-8"))
        results = create_backlog(tasks_list)
        print(json.dumps(results, ensure_ascii=False, indent=2))
        print(f"\nСоздано {len(results)} задач.")

    elif args.command == "list":
        tasks = get_tasks(status=args.status, sprint_id=args.sprint)
        if not tasks:
            print("Задач не найдено.")
        else:
            print(f"Задачи ({len(tasks)}):")
            for t in tasks:
                sprint_info = f" [{t.get('sprint_id', '')}]" if t.get('sprint_id') else ""
                deps = f" зависит от: {', '.join(t.get('depends_on', []))}" if t.get('depends_on') else ""
                print(f"  [{t['id']}]{sprint_info} {t['status']:14s} | {t['title']}{deps}")
                print(f"         заказчик: {t['customer']}, разработчик: {t['developer']}, тестировщик: {t['tester']}")

    elif args.command == "get":
        task = get_task(args.task_id)
        if task:
            print(json.dumps(task, ensure_ascii=False, indent=2))
        else:
            print(f"Задача {args.task_id} не найдена.")
            sys.exit(1)

    elif args.command == "status":
        result = update_task_status(args.task_id, args.new_status)
        print(json.dumps(result, ensure_ascii=False, indent=2))

    elif args.command == "result":
        result = set_task_result(args.task_id, args.text)
        print(json.dumps(result, ensure_ascii=False, indent=2))

    elif args.command == "create-sprint":
        sprint = create_sprint(args.title, args.description, created_by=args.created_by)
        print(json.dumps(sprint, ensure_ascii=False, indent=2))

    elif args.command == "sprints":
        sprints = get_sprints()
        if not sprints:
            print("Спринтов не найдено.")
        else:
            print(f"Спринты ({len(sprints)}):")
            for s in sprints:
                print(f"  [{s['id']}] {s['status']:12s} | {s['title']} (создал: {s.get('created_by', '?')})")

    elif args.command == "sprint":
        sprint = get_sprint(args.sprint_id)
        if sprint:
            print(json.dumps(sprint, ensure_ascii=False, indent=2))
        else:
            print(f"Спринт {args.sprint_id} не найден.")
            sys.exit(1)


if __name__ == "__main__":
    _cli()
