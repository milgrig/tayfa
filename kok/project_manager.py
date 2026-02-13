# project/kok/project_manager.py
"""
Модуль управления проектами Tayfa.

Хранит список проектов, текущий проект, инициализирует .tayfa структуру.
"""

import json
import shutil
import sys
from datetime import datetime
from pathlib import Path
from typing import Any

PROJECTS_FILE = Path(__file__).parent / "projects.json"
TEMPLATE_DIR = Path(__file__).parent / "template_tayfa"
TAYFA_DIR_NAME = ".tayfa"


def _to_wsl_path(path: str) -> str:
    """
    Конвертирует путь в WSL-формат для операций с файловой системой.

    C:\\Users\\... -> /mnt/c/Users/...
    /mnt/c/Users/... -> /mnt/c/Users/... (без изменений)
    """
    path_str = str(path).strip()

    # Уже WSL-путь
    if path_str.startswith("/mnt/"):
        return path_str

    # Windows-путь: C:\Users\... или C:/Users/...
    if len(path_str) >= 2 and path_str[1] == ':':
        drive = path_str[0].lower()
        rest = path_str[2:].replace("\\", "/")
        return f"/mnt/{drive}{rest}"

    # Другие пути (относительные, Unix) — оставляем как есть
    return path_str


def _normalize_path(path: str) -> str:
    """
    Нормализует путь для единообразного сравнения и хранения в projects.json.

    Обрабатывает:
    - Windows-пути (C:\\Users\\...) — сохраняем как есть
    - WSL-пути (/mnt/c/...) — конвертируем в Windows
    - Относительные пути — resolve от текущей директории

    Возвращает путь в Windows-формате (с обратными слешами).
    """
    path_str = str(path).strip()

    # Если это Windows-путь (X:\...) — не трогаем, просто нормализуем слеши
    if len(path_str) >= 2 and path_str[1] == ':':
        # Windows-путь: C:\Users\... или C:/Users/...
        normalized = path_str.replace("/", "\\")
        return normalized

    # Если это WSL-путь (/mnt/c/...) — конвертируем в Windows
    if path_str.startswith("/mnt/") and len(path_str) >= 7:
        # /mnt/c/Users/... -> C:\Users\...
        drive = path_str[5].upper()
        rest = path_str[6:].replace("/", "\\")
        return f"{drive}:{rest}"

    # Относительный или Unix-путь — resolve (для других случаев)
    p = Path(path_str).resolve()
    resolved = str(p)

    # Если resolve дал /mnt/... путь, конвертируем в Windows
    if resolved.startswith("/mnt/") and len(resolved) >= 7:
        drive = resolved[5].upper()
        rest = resolved[6:].replace("/", "\\")
        return f"{drive}:{rest}"

    return resolved


def _load_data() -> dict[str, Any]:
    """Загружает данные из projects.json. Создаёт файл если не существует."""
    if not PROJECTS_FILE.exists():
        # Создаём пустой файл с базовой структурой
        default_data = {"current": None, "projects": []}
        _save_data(default_data)
        return default_data
    try:
        return json.loads(PROJECTS_FILE.read_text(encoding="utf-8"))
    except Exception:
        return {"current": None, "projects": []}


def _save_data(data: dict[str, Any]) -> None:
    """Сохраняет данные в projects.json."""
    # Создаём родительскую директорию если её нет
    PROJECTS_FILE.parent.mkdir(parents=True, exist_ok=True)
    PROJECTS_FILE.write_text(
        json.dumps(data, ensure_ascii=False, indent=2),
        encoding="utf-8"
    )


def _now_iso() -> str:
    """Возвращает текущее время в ISO формате."""
    return datetime.now().strftime("%Y-%m-%dT%H:%M:%S")


def _find_project_index(projects: list[dict], path: str) -> int:
    """Находит индекс проекта по пути. Возвращает -1 если не найден."""
    norm_path = _normalize_path(path)
    for i, proj in enumerate(projects):
        if _normalize_path(proj["path"]) == norm_path:
            return i
    return -1


def is_new_user() -> bool:
    """
    Проверяет, является ли пользователь новым (нет проектов).
    Используется для показа приветственного сообщения.
    """
    data = _load_data()
    projects = data.get("projects", [])
    return len(projects) == 0


def list_projects() -> list[dict]:
    """
    Возвращает список проектов, отсортированный по last_opened DESC.
    """
    data = _load_data()
    projects = data.get("projects", [])
    # Сортировка по last_opened DESC (недавние первые)
    return sorted(
        projects,
        key=lambda p: p.get("last_opened", ""),
        reverse=True
    )


def get_project(path: str) -> dict | None:
    """
    Найти проект по пути.
    Возвращает dict с полями path, name, last_opened или None.
    """
    data = _load_data()
    idx = _find_project_index(data.get("projects", []), path)
    if idx >= 0:
        return data["projects"][idx]
    return None


def add_project(path: str, name: str | None = None) -> dict:
    """
    Добавить проект в список.
    Если name не указан — использовать basename(path) для новых проектов.
    Если проект уже есть — обновить last_opened (name не меняется, если не передан явно).
    """
    data = _load_data()
    projects = data.get("projects", [])
    norm_path = _normalize_path(path)

    idx = _find_project_index(projects, path)
    now = _now_iso()

    if idx >= 0:
        # Проект существует — обновляем last_opened
        projects[idx]["last_opened"] = now
        # Имя обновляем только если передано явно
        if name is not None:
            projects[idx]["name"] = name
        status = "updated"
        project = projects[idx]
    else:
        # Новый проект — используем basename если name не указан
        if name is None:
            # В WSL Path.name не работает для Windows-путей, извлекаем вручную
            path_str = str(path).replace("\\", "/").rstrip("/")
            name = path_str.split("/")[-1] if "/" in path_str else path_str
        project = {
            "path": norm_path,
            "name": name,
            "last_opened": now
        }
        projects.append(project)
        status = "added"

    data["projects"] = projects
    _save_data(data)

    return {"status": status, "project": project}


def remove_project(path: str) -> dict:
    """
    Удалить проект из списка (НЕ удаляет файлы).
    Если это current — сбросить current в null.
    """
    data = _load_data()
    projects = data.get("projects", [])

    idx = _find_project_index(projects, path)
    if idx < 0:
        return {"status": "not_found"}

    removed = projects.pop(idx)

    # Если это был текущий проект — сбрасываем
    if data.get("current") and _normalize_path(data["current"]) == _normalize_path(path):
        data["current"] = None

    data["projects"] = projects
    _save_data(data)

    return {"status": "removed", "project": removed}


def get_current_project() -> dict | None:
    """
    Вернуть текущий проект (по полю current).
    Если current=null или проект не найден — None.
    """
    data = _load_data()
    current_path = data.get("current")

    if not current_path:
        return None

    return get_project(current_path)


def get_project_dir() -> Path | None:
    """
    Вернуть путь к директории текущего проекта.
    Если проект не выбран — None.

    Используется для git-операций и других действий с файловой системой.
    """
    project = get_current_project()
    if not project:
        return None

    # Путь хранится в Windows-формате, возвращаем как Path
    return Path(project["path"])


def set_current_project(path: str) -> dict:
    """
    Установить проект как текущий.
    Обновить last_opened.
    Если проекта нет в списке — добавить.
    """
    data = _load_data()
    norm_path = _normalize_path(path)

    # Добавляем/обновляем проект
    result = add_project(path)
    project = result["project"]

    # Устанавливаем как текущий
    data = _load_data()  # перечитываем после add_project
    data["current"] = norm_path
    _save_data(data)

    return {"status": "set", "project": project}


def get_tayfa_dir(path: str) -> Path:
    """
    Вернуть путь к .tayfa для проекта.

    ВАЖНО: Используем оригинальный путь (Windows или WSL), не конвертируя.
    Path() в Windows Python не понимает /mnt/... пути.
    """
    # Нормализуем путь — получаем Windows-формат для единообразия
    norm_path = _normalize_path(path)
    return Path(norm_path) / TAYFA_DIR_NAME


def has_tayfa(path: str) -> bool:
    """Проверить, есть ли .tayfa в проекте."""
    return get_tayfa_dir(path).exists()


def init_project(path: str) -> dict:
    """
    Инициализировать проект (создать .tayfa если нет).
    Если .tayfa уже существует — не трогать.
    Копирует template_tayfa/ в path/.tayfa/.

    Возвращает:
        - status: "initialized", "already_exists", "error"
        - tayfa_path: путь к .tayfa
        - error: сообщение об ошибке (если status == "error")
    """
    # ВАЖНО: Используем нормализованный Windows-путь, НЕ конвертируем в WSL.
    # Path() в Windows Python не понимает /mnt/... пути и создаёт
    # относительные папки вместо работы с абсолютными путями.
    norm_path = _normalize_path(path)
    project_path = Path(norm_path)
    tayfa_path = project_path / TAYFA_DIR_NAME

    # Проверяем, существует ли директория проекта
    if not project_path.exists():
        return {
            "status": "error",
            "error": f"Папка не существует: {path}",
            "tayfa_path": str(tayfa_path)
        }

    if not project_path.is_dir():
        return {
            "status": "error",
            "error": f"Путь не является папкой: {path}",
            "tayfa_path": str(tayfa_path)
        }

    if tayfa_path.exists():
        return {
            "status": "already_exists",
            "tayfa_path": str(tayfa_path)
        }

    try:
        # Проверяем наличие шаблона
        if not TEMPLATE_DIR.exists():
            # Создаём минимальную структуру если шаблона нет
            tayfa_path.mkdir(parents=True, exist_ok=True)
            (tayfa_path / "config.json").write_text(
                '{"version": "1.0"}\n',
                encoding="utf-8"
            )
        else:
            # Копируем шаблон
            shutil.copytree(TEMPLATE_DIR, tayfa_path)

        return {
            "status": "initialized",
            "tayfa_path": str(tayfa_path)
        }
    except PermissionError:
        return {
            "status": "error",
            "error": f"Нет прав на запись в папку: {path}",
            "tayfa_path": str(tayfa_path)
        }
    except Exception as e:
        return {
            "status": "error",
            "error": f"Ошибка создания .tayfa: {str(e)}",
            "tayfa_path": str(tayfa_path)
        }


def open_project(path: str) -> dict:
    """
    Открыть проект: init + set_current.
    Комбинированная операция для удобства.

    Сначала инициализирует .tayfa (если нужно), затем устанавливает как текущий.
    При ошибке инициализации возвращает status="error".
    """
    # Сначала инициализируем
    init_result = init_project(path)

    # Если ошибка инициализации — возвращаем её
    if init_result.get("status") == "error":
        return {
            "status": "error",
            "error": init_result.get("error", "Ошибка инициализации проекта"),
            "init": "error",
            "tayfa_path": init_result.get("tayfa_path")
        }

    # Затем устанавливаем как текущий
    set_result = set_current_project(path)

    return {
        "status": "opened",
        "init": init_result["status"],
        "project": set_result["project"],
        "tayfa_path": init_result["tayfa_path"]
    }


# ── CLI интерфейс ─────────────────────────────────────────────────────────────

def _cli_list():
    """Список проектов."""
    projects = list_projects()
    if not projects:
        print("Нет проектов")
        return
    print(json.dumps(projects, ensure_ascii=False, indent=2))


def _cli_current():
    """Текущий проект."""
    project = get_current_project()
    if not project:
        print("Текущий проект не выбран")
        return
    print(json.dumps(project, ensure_ascii=False, indent=2))


def _cli_add(path: str, name: str | None = None):
    """Добавить проект."""
    result = add_project(path, name)
    print(json.dumps(result, ensure_ascii=False, indent=2))


def _cli_open(path: str):
    """Открыть проект (set_current + init)."""
    result = open_project(path)
    print(json.dumps(result, ensure_ascii=False, indent=2))


def _cli_init(path: str):
    """Инициализировать проект."""
    result = init_project(path)
    print(json.dumps(result, ensure_ascii=False, indent=2))


def _cli_remove(path: str):
    """Удалить проект из списка."""
    result = remove_project(path)
    print(json.dumps(result, ensure_ascii=False, indent=2))


def _print_usage():
    """Выводит справку по использованию CLI."""
    print("""Использование:
    python project_manager.py list                      # список проектов
    python project_manager.py current                   # текущий проект
    python project_manager.py add "C:\\Projects\\App"   # добавить
    python project_manager.py open "C:\\Projects\\App"  # открыть (set_current + init)
    python project_manager.py init "C:\\Projects\\App"  # только init
    python project_manager.py remove "C:\\Projects\\App" # удалить из списка
""")


if __name__ == "__main__":
    args = sys.argv[1:]

    if not args:
        _print_usage()
        sys.exit(0)

    cmd = args[0].lower()

    if cmd == "list":
        _cli_list()
    elif cmd == "current":
        _cli_current()
    elif cmd == "add" and len(args) >= 2:
        name = args[2] if len(args) >= 3 else None
        _cli_add(args[1], name)
    elif cmd == "open" and len(args) >= 2:
        _cli_open(args[1])
    elif cmd == "init" and len(args) >= 2:
        _cli_init(args[1])
    elif cmd == "remove" and len(args) >= 2:
        _cli_remove(args[1])
    else:
        _print_usage()
        sys.exit(1)
