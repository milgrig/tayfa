#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Скрипт для HR: создание папки и файлов нового сотрудника.
Упрощает онбординг — создаёт структуру папки, шаблоны, регистрирует в employees.json.

Использование:
  python create_employee.py <имя> [имя2 ...]
  python create_employee.py developer_backend designer_ui content_manager

Имя сотрудника: латиница, нижний регистр, подчёркивания (например developer_python, designer_ui).
"""

import argparse
import json
import re
import sys
from pathlib import Path
from datetime import date

# Базовая папка .tayfa — на уровень выше hr/
SCRIPT_DIR = Path(__file__).resolve().parent
TAYFA_DIR = SCRIPT_DIR.parent  # .tayfa/
PROJECT_DIR = TAYFA_DIR.parent  # корень проекта
INCOME_DIR = SCRIPT_DIR / "Income"

# Импортируем менеджер сотрудников для регистрации в едином реестре
sys.path.insert(0, str(TAYFA_DIR / "common"))
from employee_manager import register_employee as _register_in_registry


def validate_name(name: str) -> bool:
    """Имя: латиница, нижний регистр, подчёркивания."""
    return bool(re.fullmatch(r"[a-z][a-z0-9_]*", name))


def human_role_from_name(name: str) -> str:
    """Примерное название роли из имени: developer_frontend -> Frontend-разработчик."""
    parts = name.split("_")
    if parts[0] == "developer":
        suffix = parts[1] if len(parts) > 1 else ""
        return f"{suffix.capitalize()}-разработчик" if suffix else "Разработчик"
    if parts[0] == "designer":
        return "UI/UX дизайнер"
    if parts[0] == "expert":
        return "Эксперт"
    if parts[0] == "content":
        return "Контент-менеджер"
    return name.replace("_", " ").title()


def ensure_dir(path: Path) -> None:
    path.mkdir(parents=True, exist_ok=True)


def write_file(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")


def create_employee(name: str, role: str | None = None) -> bool:
    """Создаёт папку сотрудника, файлы, регистрирует в employees.json."""
    role = role or human_role_from_name(name)
    emp_dir = TAYFA_DIR / name

    if emp_dir.exists() and any(emp_dir.iterdir()):
        print(f"  [ПРОПУСК] {name}: папка уже существует и не пуста.")
        return False

    ensure_dir(emp_dir)
    ensure_dir(emp_dir / "income")
    ensure_dir(emp_dir / "done")
    ensure_dir(emp_dir / "request")

    # source.md — копируем из Income, если есть
    source_path = emp_dir / "source.md"
    income_md = INCOME_DIR / f"{name}.md"
    if income_md.exists():
        source_path.write_text(income_md.read_text(encoding="utf-8"), encoding="utf-8")
    else:
        write_file(source_path, f"# Описание сотрудника: {name}\n\n_Заполни по заданию из Income._\n")

    # profile.md
    profile = f"""# Профиль сотрудника

## Имя
{name}

## Роль
{role}

## Зона ответственности
- [Укажи по описанию из Income]

## Навыки
- [Укажи по описанию из Income]

## Рабочие папки
- Проект: корень проекта (родительская папка .tayfa/)
- Личная папка: `.tayfa/{name}/`
- Входящие задания: `.tayfa/{name}/income/`
- Выполненные: `.tayfa/{name}/done/`
"""
    write_file(emp_dir / "profile.md", profile)

    # prompt.md — шаблон, HR дополняет по Rules
    prompt = f"""# {role}

Ты — {name}, {role.lower()} в проекте.

## Твоя роль

[Опиши роль по заданию из Income / source.md]

## Твои навыки

См. секцию «Навыки» в `.tayfa/{name}/profile.md`.

## Зона ответственности

- [Скопируй из profile.md или уточни]

## База знаний

Изучи правила: `.tayfa/common/Rules/teamwork.md`, `.tayfa/common/Rules/employees.md`.

## Система задач

Задачи управляются через `.tayfa/common/task_manager.py`. Основные команды:
- Просмотр: `python .tayfa/common/task_manager.py list`
- Результат: `python .tayfa/common/task_manager.py result T001 "описание"`
- Статус: `python .tayfa/common/task_manager.py status T001 <статус>`

## Рабочие папки

- **Проект**: корень проекта (родительская папка `.tayfa/`)
- **Личная папка**: `.tayfa/{name}/`
- **Входящие**: `.tayfa/{name}/income/`
- **Выполненные**: `.tayfa/{name}/done/`

## Правила

- Входящие задания проверяй в `income/`, после выполнения переноси в `done/`.
- Взаимодействие с другими агентами — через систему задач. Детали: `.tayfa/common/Rules/teamwork.md`.
"""
    write_file(emp_dir / "prompt.md", prompt)

    # tasks.md
    write_file(emp_dir / "tasks.md", """# Текущие задачи

## Активные задачи

_Нет активных задач_

## Ожидающие

_Нет задач в ожидании_

## История

_Нет истории_
""")

    # notes.md
    today = date.today().isoformat()
    write_file(emp_dir / "notes.md", f"""# Заметки

## История

- **{today}**: Создан профиль сотрудника (онбординг)
""")

    # .gitkeep в подпапках
    for sub in ("income", "done", "request"):
        write_file(emp_dir / sub / ".gitkeep", "")

    # Регистрация в едином реестре сотрудников (employees.json)
    reg_result = _register_in_registry(name, role)
    if reg_result["status"] == "created":
        print(f"  [OK] {name}: зарегистрирован в employees.json")
    elif reg_result["status"] == "exists":
        print(f"  [INFO] {name}: уже в employees.json")

    print(f"  [OK] {name}: папка и файлы созданы.")
    return True


def employees_md_block(name: str, role: str | None = None) -> str:
    """Возвращает блок markdown для вставки в employees.md."""
    role = role or human_role_from_name(name)
    return f"""
## {name}

**Роль**: {role}.

**Когда обращаться**:
- [Укажи по описанию роли]

**Кто может обращаться**: все / только boss.
"""


def main():
    parser = argparse.ArgumentParser(
        description="Создание папки и файлов нового сотрудника (онбординг)."
    )
    parser.add_argument(
        "names",
        nargs="+",
        metavar="имя",
        help="Имя сотрудника (латиница, нижний регистр, подчёркивания), например developer_backend",
    )
    parser.add_argument(
        "--print-employees-block",
        action="store_true",
        help="Вывести блок для вставки в common/Rules/employees.md",
    )
    args = parser.parse_args()

    bad = [n for n in args.names if not validate_name(n)]
    if bad:
        print("Ошибка: неверный формат имени (латиница, нижний регистр, подчёркивания):", ", ".join(bad))
        sys.exit(1)

    print("Создание сотрудников в", TAYFA_DIR)
    created = 0
    for name in args.names:
        if create_employee(name):
            created += 1

    print(f"\nГотово: создано {created} из {len(args.names)}.")

    if args.print_employees_block:
        print("\n--- Блок для common/Rules/employees.md ---")
        for name in args.names:
            print(employees_md_block(name))
        print("--- Конец блока ---")


if __name__ == "__main__":
    main()
