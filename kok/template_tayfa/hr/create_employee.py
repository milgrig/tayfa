#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
HR script: create folder and files for a new employee.
Simplifies onboarding — creates folder structure, templates, registers in employees.json.

Usage:
  python create_employee.py <name> [--model opus|sonnet|haiku]
  python create_employee.py developer_backend --model sonnet
  python create_employee.py architect --model opus

Employee name: Latin letters, lowercase, underscores (e.g. developer_python, designer_ui).
Model: opus (complex tasks), sonnet (default), haiku (simple tasks).
"""

import argparse
import json
import re
import sys
from pathlib import Path
from datetime import date
import urllib.request
import urllib.error

# Base .tayfa folder — one level above hr/
SCRIPT_DIR = Path(__file__).resolve().parent
TAYFA_DIR = SCRIPT_DIR.parent  # .tayfa/
PROJECT_DIR = TAYFA_DIR.parent  # project root

# Import employee manager for registration in the unified registry
sys.path.insert(0, str(TAYFA_DIR / "common"))
from employee_manager import register_employee as _register_in_registry

# Valid Claude models
VALID_MODELS = ("opus", "sonnet", "haiku")
DEFAULT_MODEL = "sonnet"


def notify_orchestrator() -> None:
    """
    Notifies the orchestrator about the need to create an agent.
    On connection error — prints a warning, does not crash.
    """
    try:
        req = urllib.request.Request(
            'http://localhost:8008/api/ensure-agents',
            method='POST',
            data=b'',
            headers={'Content-Type': 'application/json'}
        )
        with urllib.request.urlopen(req, timeout=5) as resp:
            if resp.status == 200:
                print('  [OK] Agent created in orchestrator')
    except (urllib.error.URLError, TimeoutError, OSError):
        print('  [WARN] Orchestrator unavailable, start it and click "Ensure agents"')


def validate_name(name: str) -> bool:
    """Name: Latin letters, lowercase, underscores."""
    return bool(re.fullmatch(r"[a-z][a-z0-9_]*", name))


def human_role_from_name(name: str) -> str:
    """Approximate role name from identifier: developer_frontend -> Frontend Developer."""
    parts = name.split("_")
    if parts[0] == "developer":
        suffix = parts[1] if len(parts) > 1 else ""
        return f"{suffix.capitalize()} Developer" if suffix else "Developer"
    if parts[0] == "designer":
        return "UI/UX Designer"
    if parts[0] == "expert":
        return "Expert"
    if parts[0] == "content":
        return "Content Manager"
    return name.replace("_", " ").title()


def ensure_dir(path: Path) -> None:
    path.mkdir(parents=True, exist_ok=True)


def write_file(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")


def create_employee(name: str, role: str | None = None, model: str | None = None) -> bool:
    """Creates employee folder, files, registers in employees.json."""
    role = role or human_role_from_name(name)
    model = model or DEFAULT_MODEL
    emp_dir = TAYFA_DIR / name

    if emp_dir.exists() and any(emp_dir.iterdir()):
        print(f"  [SKIP] {name}: folder already exists and is not empty.")
        return False

    ensure_dir(emp_dir)

    # source.md
    write_file(emp_dir / "source.md", f"# Employee description: {name}\n\n_Fill in based on role requirements._\n")

    # profile.md
    profile = f"""# Employee Profile

## Name
{name}

## Role
{role}


## Working Folders
- Project: project root (parent folder of .tayfa/)
- Personal folder: `.tayfa/{name}/`

"""
    write_file(emp_dir / "profile.md", profile)

    # prompt.md — template, HR supplements per Rules
    prompt = f"""# {role}

You are {name}, a {role.lower()} on the project.

## Your Role


## Your Skills

See the "Skills" section in `.tayfa/{name}/profile.md`.

## Area of Responsibility

- [Copy from profile.md or specify]

## Knowledge Base

Study the rules: `.tayfa/common/Rules/teamwork.md`, `.tayfa/common/Rules/employees.md`.

## Task System

Tasks are managed via `.tayfa/common/task_manager.py`. Main commands:
- View: `python .tayfa/common/task_manager.py list`
- Result: `python .tayfa/common/task_manager.py result T001 "description"`
- Status: `python .tayfa/common/task_manager.py status T001 <status>`

## Working Folders

- **Project**: project root (parent folder of `.tayfa/`)
- **Personal folder**: `.tayfa/{name}/`


## Rules

- Interaction with other agents — via the task system. Details: `.tayfa/common/Rules/teamwork.md`.
"""
    write_file(emp_dir / "prompt.md", prompt)

    # tasks.md
    write_file(emp_dir / "tasks.md", """# Current Tasks

## Active Tasks

_No active tasks_

## Pending

_No pending tasks_

## History

_No history_
""")

    # notes.md
    today = date.today().isoformat()
    write_file(emp_dir / "notes.md", f"""# Notes

## History

- **{today}**: Employee profile created (onboarding)
""")

    # Registration in the unified employee registry (employees.json)
    reg_result = _register_in_registry(name, role, model)
    if reg_result["status"] == "created":
        print(f"  [OK] {name}: registered in employees.json (model={model})")
        # Automatic agent provisioning in orchestrator
        notify_orchestrator()
    elif reg_result["status"] == "exists":
        print(f"  [INFO] {name}: already in employees.json")

    print(f"  [OK] {name}: folder and files created.")
    return True


def employees_md_block(name: str, role: str | None = None) -> str:
    """Returns a markdown block for insertion into employees.md."""
    role = role or human_role_from_name(name)
    return f"""
## {name}

**Role**: {role}.

**When to contact**:
- [Specify based on role description]

**Who can contact**: everyone / boss only.
"""


def main():
    parser = argparse.ArgumentParser(
        description="Create folder and files for a new employee (onboarding)."
    )
    parser.add_argument(
        "names",
        nargs="+",
        metavar="name",
        help="Employee name (Latin letters, lowercase, underscores), e.g. developer_backend",
    )
    parser.add_argument(
        "--model",
        choices=VALID_MODELS,
        default=DEFAULT_MODEL,
        help=f"Claude model: opus (complex tasks), sonnet (default), haiku (simple tasks)",
    )
    parser.add_argument(
        "--print-employees-block",
        action="store_true",
        help="Print block for insertion into common/Rules/employees.md",
    )
    args = parser.parse_args()

    bad = [n for n in args.names if not validate_name(n)]
    if bad:
        print("Error: invalid name format (Latin letters, lowercase, underscores):", ", ".join(bad))
        sys.exit(1)

    print("Creating employees in", TAYFA_DIR)
    print(f"Model: {args.model}")
    created = 0
    for name in args.names:
        if create_employee(name, model=args.model):
            created += 1

    print(f"\nDone: created {created} of {len(args.names)}.")

    if args.print_employees_block:
        print("\n--- Block for common/Rules/employees.md ---")
        for name in args.names:
            print(employees_md_block(name))
        print("--- End of block ---")


if __name__ == "__main__":
    main()
