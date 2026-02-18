#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
HR script: create employee folder structure and register in employees.json.

Usage:
  python create_employee.py <name> [--model opus|sonnet|haiku]
  python create_employee.py developer_backend --model sonnet
  python create_employee.py architect --model opus

Employee name: latin, lowercase, underscores (e.g. developer_python, designer_ui).
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

# Base folder .tayfa — one level above hr/
SCRIPT_DIR = Path(__file__).resolve().parent
TAYFA_DIR = SCRIPT_DIR.parent  # .tayfa/
PROJECT_DIR = TAYFA_DIR.parent  # project root

# Import employee manager for registry registration
sys.path.insert(0, str(TAYFA_DIR / "common"))
from employee_manager import register_employee as _register_in_registry

# Valid Claude models
VALID_MODELS = ("opus", "sonnet", "haiku")
DEFAULT_MODEL = "sonnet"


def notify_orchestrator() -> None:
    """
    Notify orchestrator to create/update agent.
    On connection error — prints warning, does not crash.
    """
    try:
        body = json.dumps({"project_path": str(PROJECT_DIR)}).encode()
        req = urllib.request.Request(
            'http://localhost:8008/api/ensure-agents',
            method='POST',
            data=body,
            headers={'Content-Type': 'application/json'}
        )
        with urllib.request.urlopen(req, timeout=5) as resp:
            if resp.status == 200:
                print('  [OK] Agent created in orchestrator')
    except (urllib.error.URLError, TimeoutError, OSError):
        print('  [WARN] Orchestrator unavailable, start it and click "Ensure agents"')


def validate_name(name: str) -> bool:
    """Name: latin, lowercase, underscores."""
    return bool(re.fullmatch(r"[a-z][a-z0-9_]*", name))


def human_role_from_name(name: str) -> str:
    """Derive human-readable role from name: developer_frontend -> Frontend Developer."""
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
    """Create employee folder, files, register in employees.json."""
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

## Responsibilities
- [Define based on role requirements]

## Skills
- [Define based on role requirements]

## Working Directories
- Project: project root (parent of .tayfa/)
- Personal folder: `.tayfa/{name}/`
"""
    write_file(emp_dir / "profile.md", profile)

    # prompt.md — template, HR fills in
    prompt = f"""# {role}

You are **{name}**, {role.lower()} in this project.

## Your Role

[Describe role based on requirements]

## Skills and Responsibilities

See `.tayfa/{name}/profile.md` for complete list of skills and responsibilities.

## Base Rules

**MANDATORY**: Study `.tayfa/common/Rules/agent-base.md` — contains common rules for all agents (task system, communication, testing requirements).

Additional team rules:
- `.tayfa/common/Rules/teamwork.md` — workflow and handoff formats
- `.tayfa/common/Rules/employees.md` — employee list

## Task System

Tasks are managed via `.tayfa/common/task_manager.py`. Main commands:
- View: `python .tayfa/common/task_manager.py list`
- Result: `python .tayfa/common/task_manager.py result T001 "description"`
- Status: `python .tayfa/common/task_manager.py status T001 <status>`

## Working Directories

- **Project**: project root (parent of `.tayfa/`)
- **Personal folder**: `.tayfa/{name}/`

## Communication

Use discussions file: `.tayfa/common/discussions/{{task_id}}.md`
Interaction with other agents — via the task system. Details: `.tayfa/common/Rules/teamwork.md`.
"""
    write_file(emp_dir / "prompt.md", prompt)

    # notes.md
    today = date.today().isoformat()
    write_file(emp_dir / "notes.md", f"""# Notes

## History

- **{today}**: Employee profile created (onboarding)
""")

    # Register in employees.json
    reg_result = _register_in_registry(name, role, model)
    if reg_result["status"] == "created":
        print(f"  [OK] {name}: registered in employees.json (model={model})")
        # NOTE: Do NOT call notify_orchestrator() here — prompt.md is still a template.
        # HR must fill in prompt.md first, then click "Ensure agents" in the UI
        # or run notify_orchestrator() manually.
        print(f'  [INFO] Fill in .tayfa/{name}/prompt.md, then click "Ensure agents"')
    elif reg_result["status"] == "exists":
        print(f"  [INFO] {name}: already in employees.json")

    print(f"  [OK] {name}: folder and files created.")
    return True


def employees_md_block(name: str, role: str | None = None) -> str:
    """Return markdown block for employees.md."""
    role = role or human_role_from_name(name)
    return f"""
## {name}

**Role**: {role}.

**When to contact**:
- [Define based on role description]

**Who can contact**: all / boss only.
"""


def main():
    parser = argparse.ArgumentParser(
        description="Create employee folder and files (onboarding)."
    )
    parser.add_argument(
        "names",
        nargs="+",
        metavar="name",
        help="Employee name (latin, lowercase, underscores), e.g. developer_backend",
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
        help="Print block for common/Rules/employees.md",
    )
    args = parser.parse_args()

    bad = [n for n in args.names if not validate_name(n)]
    if bad:
        print("Error: invalid name format (latin, lowercase, underscores):", ", ".join(bad))
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
