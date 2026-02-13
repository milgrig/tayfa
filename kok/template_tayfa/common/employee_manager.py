#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Управление реестром сотрудников.

Это единственный источник правды о том, кто является сотрудником системы.
Оркестратор показывает только тех, кто есть в employees.json.
HR добавляет сотрудников через create_employee.py, который вызывает register_employee().

CLI использование:
  python employee_manager.py list
  python employee_manager.py register <name> <role>
  python employee_manager.py remove <name>
  python employee_manager.py get <name>
"""

import json
import sys
from pathlib import Path
from datetime import date

# Путь к employees.json — по умолчанию рядом с этим файлом, но может быть переопределён
_employees_file: Path | None = None


def get_employees_file() -> Path:
    """Получить путь к employees.json. Использует установленный путь или дефолтный."""
    global _employees_file
    if _employees_file is not None:
        return _employees_file
    return Path(__file__).resolve().parent / "employees.json"


def set_employees_file(path: Path | str) -> None:
    """Установить путь к employees.json (для мультипроектной архитектуры)."""
    global _employees_file
    _employees_file = Path(path) if isinstance(path, str) else path


# Для обратной совместимости (CLI и прямой запуск)
EMPLOYEES_FILE = Path(__file__).resolve().parent / "employees.json"


def _load() -> dict:
    """Загрузить реестр сотрудников."""
    employees_file = get_employees_file()
    if not employees_file.exists():
        return {"employees": {}}
    try:
        return json.loads(employees_file.read_text(encoding="utf-8"))
    except Exception:
        return {"employees": {}}


def _save(data: dict) -> None:
    """Сохранить реестр сотрудников."""
    employees_file = get_employees_file()
    employees_file.parent.mkdir(parents=True, exist_ok=True)
    employees_file.write_text(
        json.dumps(data, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )


def get_employees() -> dict:
    """Получить словарь всех сотрудников: {name: {role, created_at}}."""
    return _load()["employees"]


def get_employee(name: str) -> dict | None:
    """Получить данные одного сотрудника или None."""
    employees = get_employees()
    return employees.get(name)


def register_employee(name: str, role: str, model: str = "sonnet") -> dict:
    """
    Зарегистрировать нового сотрудника.
    Возвращает {"status": "created"|"exists", "name": ..., "role": ..., "model": ...}.

    Args:
        name: Имя сотрудника (латиница, нижний регистр, подчёркивания)
        role: Роль сотрудника (например "Python-разработчик")
        model: Модель Claude - opus, sonnet (по умолчанию), haiku
    """
    data = _load()
    if name in data["employees"]:
        return {"status": "exists", "name": name, "role": data["employees"][name]["role"]}
    data["employees"][name] = {
        "role": role,
        "model": model,
        "created_at": date.today().isoformat(),
    }
    _save(data)
    return {"status": "created", "name": name, "role": role, "model": model}


def remove_employee(name: str) -> dict:
    """
    Удалить сотрудника из реестра.
    Boss и HR удалить нельзя.
    """
    data = _load()
    if name not in data["employees"]:
        return {"status": "not_found", "name": name}
    if name in ("boss", "hr"):
        return {"status": "error", "message": "Нельзя удалить boss или hr"}
    del data["employees"][name]
    _save(data)
    return {"status": "removed", "name": name}


def _cli():
    """Точка входа CLI."""
    if len(sys.argv) < 2:
        print("Использование:")
        print("  python employee_manager.py list")
        print("  python employee_manager.py register <name> <role>")
        print("  python employee_manager.py remove <name>")
        print("  python employee_manager.py get <name>")
        sys.exit(1)

    cmd = sys.argv[1]

    if cmd == "list":
        employees = get_employees()
        if not employees:
            print("Реестр сотрудников пуст.")
        else:
            print(f"Сотрудники ({len(employees)}):")
            for name, info in employees.items():
                model = info.get('model', 'sonnet')
                print(f"  {name}: {info['role']} [{model}] (с {info.get('created_at', '?')})")

    elif cmd == "register":
        if len(sys.argv) < 4:
            print("Ошибка: нужно имя и роль. Пример: python employee_manager.py register dev_backend Разработчик")
            sys.exit(1)
        name = sys.argv[2]
        role = " ".join(sys.argv[3:])
        result = register_employee(name, role)
        print(json.dumps(result, ensure_ascii=False, indent=2))

    elif cmd == "remove":
        if len(sys.argv) < 3:
            print("Ошибка: нужно имя. Пример: python employee_manager.py remove dev_backend")
            sys.exit(1)
        result = remove_employee(sys.argv[2])
        print(json.dumps(result, ensure_ascii=False, indent=2))

    elif cmd == "get":
        if len(sys.argv) < 3:
            print("Ошибка: нужно имя.")
            sys.exit(1)
        emp = get_employee(sys.argv[2])
        if emp:
            print(json.dumps(emp, ensure_ascii=False, indent=2))
        else:
            print(f"Сотрудник '{sys.argv[2]}' не найден.")
            sys.exit(1)

    else:
        print(f"Неизвестная команда: {cmd}")
        sys.exit(1)


if __name__ == "__main__":
    _cli()
