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
import subprocess
import sys
from pathlib import Path
from datetime import datetime

TASKS_FILE = Path(__file__).resolve().parent / "tasks.json"
BACKLOG_FILE = Path(__file__).resolve().parent / "backlog.json"


def _get_project_root() -> Path | None:
    """Получить корень проекта (где .tayfa находится)."""
    # TASKS_FILE: .tayfa/common/tasks.json → .tayfa/common → .tayfa → project_root
    tayfa_dir = TASKS_FILE.parent.parent  # .tayfa
    if tayfa_dir.name == ".tayfa":
        return tayfa_dir.parent
    return None


def _run_git(args: list[str], cwd: Path | None = None) -> dict:
    """Выполнить git-команду. Возвращает {success, stdout, stderr}."""
    if cwd is None:
        cwd = _get_project_root()
    if cwd is None:
        return {"success": False, "stdout": "", "stderr": "Project root not found"}
    try:
        result = subprocess.run(
            ["git"] + args,
            cwd=str(cwd),
            capture_output=True,
            text=True,
            timeout=30,
        )
        return {
            "success": result.returncode == 0,
            "stdout": result.stdout.strip(),
            "stderr": result.stderr.strip(),
        }
    except Exception as e:
        return {"success": False, "stdout": "", "stderr": str(e)}


def _create_sprint_branch(sprint_id: str) -> dict:
    """Создать git-ветку для спринта. Возвращает {success, branch, error}."""
    branch_name = f"sprint/{sprint_id}"

    # Проверяем, инициализирован ли git
    check = _run_git(["rev-parse", "--git-dir"])
    if not check["success"]:
        return {"success": False, "branch": None, "error": "Git не инициализирован"}

    # Проверяем, есть ли коммиты
    check_commits = _run_git(["rev-parse", "HEAD"])
    if not check_commits["success"]:
        return {"success": False, "branch": None, "error": "Нет коммитов в репозитории"}

    # Проверяем, существует ли уже ветка
    check_branch = _run_git(["rev-parse", "--verify", branch_name])
    if check_branch["success"]:
        # Ветка уже существует — переключаемся на неё
        _run_git(["checkout", branch_name])
        return {"success": True, "branch": branch_name, "error": None, "existed": True}

    # Создаём ветку от main (или master, или текущей)
    for base in ["main", "master", "HEAD"]:
        create = _run_git(["checkout", "-b", branch_name, base])
        if create["success"]:
            return {"success": True, "branch": branch_name, "error": None, "existed": False}

    return {"success": False, "branch": None, "error": "Не удалось создать ветку"}


def _release_sprint(sprint_id: str, sprint_title: str = "") -> dict:
    """
    Выполняет релиз спринта: merge в main, тег, push.
    Возвращает {success, version, commit, pushed, error}.
    """
    result = {"success": False, "version": None, "commit": None, "pushed": False}

    source_branch = f"sprint/{sprint_id}"
    target_branch = "main"

    # Проверяем git
    check = _run_git(["rev-parse", "--git-dir"])
    if not check["success"]:
        result["error"] = "Git не инициализирован"
        return result

    # Получаем текущую версию и вычисляем следующую
    tag_result = _run_git(["describe", "--tags", "--abbrev=0"])
    if tag_result["success"] and tag_result["stdout"]:
        current = tag_result["stdout"].lstrip("v")
        parts = current.split(".")
        major = int(parts[0]) if len(parts) > 0 else 0
        minor = int(parts[1]) if len(parts) > 1 else 0
        patch = int(parts[2]) if len(parts) > 2 else 0
        version = f"v{major}.{minor + 1}.{patch}"
    else:
        version = "v0.1.0"

    result["version"] = version
    merge_message = f"Release {version}: {sprint_title}" if sprint_title else f"Release {version}"
    commit_message = f"{sprint_id}: {sprint_title}" if sprint_title else f"{sprint_id}"

    try:
        # 0. Проверяем текущую ветку
        current_branch = _run_git(["rev-parse", "--abbrev-ref", "HEAD"])
        current = current_branch["stdout"].strip() if current_branch["success"] else ""

        # 1. Если есть незакоммиченные изменения — сначала коммитим на текущей ветке
        status = _run_git(["status", "--porcelain"])
        if status["success"] and status["stdout"].strip():
            # Есть изменения — коммитим их на текущей ветке
            _run_git(["add", "-A"])
            commit_result = _run_git(["commit", "-m", commit_message])
            if not commit_result["success"] and "nothing to commit" not in commit_result["stderr"]:
                result["error"] = f"Не удалось закоммитить изменения: {commit_result['stderr']}"
                return result

        # 2. Переключиться на source_branch (ветка спринта)
        if current != source_branch:
            checkout_src = _run_git(["checkout", source_branch])
            if not checkout_src["success"]:
                result["error"] = f"Ветка {source_branch} не найдена"
                return result

        # 3. Переключиться на target_branch (main)
        checkout_tgt = _run_git(["checkout", target_branch])
        if not checkout_tgt["success"]:
            # Создаём main если не существует
            create_tgt = _run_git(["checkout", "-b", target_branch])
            if not create_tgt["success"]:
                _run_git(["checkout", source_branch])
                result["error"] = f"Не удалось переключиться на {target_branch}"
                return result

        # 4. Pull (если есть remote)
        _run_git(["pull", "origin", target_branch])

        # 5. Merge ветки спринта в main
        merge = _run_git(["merge", source_branch, "--no-ff", "-m", merge_message])
        if not merge["success"]:
            _run_git(["merge", "--abort"])
            _run_git(["checkout", source_branch])
            result["error"] = f"Merge conflict: {merge['stderr']}"
            return result

        # 6. Получаем hash коммита
        hash_result = _run_git(["rev-parse", "--short", "HEAD"])
        result["commit"] = hash_result["stdout"] if hash_result["success"] else None

        # 7. Создаём тег версии
        tag_msg = f"Sprint: {sprint_title}" if sprint_title else f"Release {version}"
        _run_git(["tag", "-a", version, "-m", tag_msg])

        # 8. Push в remote
        push = _run_git(["push", "origin", target_branch, "--tags"])
        result["pushed"] = push["success"]

        if not result["pushed"]:
            # Откат при неудачном push (не критично — изменения остаются локально)
            result["push_error"] = push["stderr"]
            # НЕ откатываем — локальные изменения ценнее

        # 9. Возвращаемся на ветку спринта
        _run_git(["checkout", source_branch])

        result["success"] = True
        return result

    except Exception as e:
        _run_git(["checkout", source_branch])
        result["error"] = str(e)
        return result


def set_tasks_file(path: str | Path) -> None:
    """Установить путь к файлу tasks.json (для работы с разными проектами)."""
    global TASKS_FILE
    TASKS_FILE = Path(path)


STATUSES = ["новая", "в_работе", "на_проверке", "выполнена", "отменена"]
SPRINT_STATUSES = ["активный", "завершён"]

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


def _load_backlog() -> dict:
    """Загрузить backlog.json. Возвращает {"items": [], "next_id": 1} если не существует."""
    if not BACKLOG_FILE.exists():
        return {"items": [], "next_id": 1}
    try:
        return json.loads(BACKLOG_FILE.read_text(encoding="utf-8"))
    except Exception:
        return {"items": [], "next_id": 1}


def _save_backlog(data: dict) -> None:
    """Сохранить backlog.json."""
    BACKLOG_FILE.parent.mkdir(parents=True, exist_ok=True)
    BACKLOG_FILE.write_text(
        json.dumps(data, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )


# ── Спринты ──────────────────────────────────────────────────────────────────


def create_sprint(
    title: str,
    description: str = "",
    created_by: str = "boss",
    include_backlog: bool = False,
) -> dict:
    """
    Создать новый спринт. Возвращает созданный спринт.
    Автоматически создаёт задачу "Финализировать спринт" и git-ветку sprint/SXXX.

    include_backlog: если True, импортирует записи с next_sprint=true из бэклога.
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

    # Создаём git-ветку для спринта
    git_result = _create_sprint_branch(sprint_id)
    if git_result["success"]:
        sprint["git_branch"] = git_result["branch"]
        if git_result.get("existed"):
            sprint["git_note"] = "Ветка уже существовала"
    else:
        sprint["git_warning"] = git_result.get("error", "Не удалось создать git-ветку")

    # Импортировать задачи из бэклога
    result = {**sprint, "finalize_task": finalize_task}
    if include_backlog:
        imported_tasks = _import_backlog_to_sprint(sprint_id)
        result["imported_from_backlog"] = len(imported_tasks)
        result["imported_tasks"] = imported_tasks

    return result


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


def update_sprint_release(sprint_id: str, version: str) -> dict:
    """
    Обновить спринт после успешного релиза.
    Устанавливает статус 'завершён', записывает версию и время релиза.
    """
    data = _load()
    for sprint in data.get("sprints", []):
        if sprint["id"] == sprint_id:
            sprint["status"] = "завершён"
            sprint["version"] = version
            sprint["released_at"] = _now()
            sprint["updated_at"] = _now()
            _save(data)
            return sprint
    return {"error": f"Спринт {sprint_id} не найден"}


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


def create_task_from_backlog(
    backlog_id: str,
    customer: str,
    developer: str,
    tester: str,
    sprint_id: str,
) -> dict:
    """
    Создать задачу из записи бэклога и удалить запись из бэклога.
    Возвращает созданную задачу или {"error": "..."}.
    """
    # 1. Загрузить бэклог
    backlog_data = _load_backlog()

    # 2. Найти запись
    item = None
    item_index = -1
    for i, b in enumerate(backlog_data.get("items", [])):
        if b["id"] == backlog_id:
            item = b
            item_index = i
            break

    if item is None:
        return {"error": f"Запись {backlog_id} не найдена в бэклоге"}

    # 3. Проверить существование спринта
    if sprint_id:
        sprint = get_sprint(sprint_id)
        if sprint is None:
            return {"error": f"Спринт {sprint_id} не найден"}

    # 4. Создать задачу
    task = create_task(
        title=item["title"],
        description=item["description"],
        customer=customer,
        developer=developer,
        tester=tester,
        sprint_id=sprint_id,
        depends_on=[],
    )

    # 5. Удалить запись из бэклога
    backlog_data["items"].pop(item_index)
    _save_backlog(backlog_data)

    return task


def _import_backlog_to_sprint(sprint_id: str) -> list[dict]:
    """
    Импортировать записи с next_sprint=true в спринт.
    Возвращает список созданных задач.
    """
    backlog_data = _load_backlog()

    # Фильтровать записи для импорта
    items_to_import = [
        item for item in backlog_data.get("items", [])
        if item.get("next_sprint") is True
    ]

    if not items_to_import:
        return []

    # Создать задачи
    created_tasks = []
    for item in items_to_import:
        task = create_task(
            title=item["title"],
            description=item["description"],
            customer="boss",
            developer="TBD",
            tester="TBD",
            sprint_id=sprint_id,
            depends_on=[],
        )
        created_tasks.append(task)

    # Удалить импортированные записи
    backlog_data["items"] = [
        item for item in backlog_data.get("items", [])
        if item.get("next_sprint") is not True
    ]
    _save_backlog(backlog_data)

    return created_tasks


def update_task_status(task_id: str, new_status: str) -> dict:
    """
    Изменить статус задачи.
    new_status: одно из "новая", "в_работе", "на_проверке", "выполнена", "отменена".

    Если это финализирующая задача и new_status == "выполнена",
    проверяет все задачи спринта и выполняет релиз (merge, tag, push).
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

            result = {**task, "old_status": old_status}

            # Автоматический релиз при завершении финализирующей задачи
            if new_status == "выполнена" and task.get("is_finalize"):
                sprint_id = task.get("sprint_id")
                if sprint_id:
                    # Проверяем, все ли задачи спринта выполнены
                    sprint_tasks = get_tasks(sprint_id=sprint_id)
                    all_done = all(t["status"] in ("выполнена", "отменена") for t in sprint_tasks)

                    if all_done:
                        # Получаем название спринта
                        sprint = get_sprint(sprint_id)
                        sprint_title = sprint.get("title", "") if sprint else ""

                        # Выполняем релиз
                        release_result = _release_sprint(sprint_id, sprint_title)

                        if release_result["success"]:
                            # Обновляем статус спринта
                            update_sprint_status(sprint_id, "завершён")
                            result["sprint_released"] = {
                                "sprint_id": sprint_id,
                                "version": release_result["version"],
                                "commit": release_result["commit"],
                                "pushed": release_result["pushed"],
                            }
                        else:
                            result["sprint_release_error"] = release_result.get("error", "Unknown error")

            return result
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

    # create-from-backlog
    p_create_backlog = sub.add_parser("create-from-backlog", help="Создать задачу из записи бэклога")
    p_create_backlog.add_argument("backlog_id", help="ID записи в бэклоге (например B001)")
    p_create_backlog.add_argument("--customer", required=True, help="Заказчик (имя агента)")
    p_create_backlog.add_argument("--developer", required=True, help="Разработчик (имя агента)")
    p_create_backlog.add_argument("--tester", required=True, help="Тестировщик (имя агента)")
    p_create_backlog.add_argument("--sprint", required=True, help="ID спринта (например S001)")

    # create-sprint
    p_sprint = sub.add_parser("create-sprint", help="Создать спринт")
    p_sprint.add_argument("title", help="Название спринта")
    p_sprint.add_argument("description", nargs="?", default="", help="Описание спринта")
    p_sprint.add_argument("--created-by", default="boss", help="Кто создал спринт")
    p_sprint.add_argument("--include-backlog", action="store_true", help="Импортировать записи с next_sprint=true")

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

    elif args.command == "create-from-backlog":
        result = create_task_from_backlog(
            args.backlog_id,
            args.customer,
            args.developer,
            args.tester,
            args.sprint,
        )
        print(json.dumps(result, ensure_ascii=False, indent=2))
        if "error" in result:
            sys.exit(1)

    elif args.command == "create-sprint":
        sprint = create_sprint(
            args.title,
            args.description,
            created_by=args.created_by,
            include_backlog=getattr(args, "include_backlog", False),
        )
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
