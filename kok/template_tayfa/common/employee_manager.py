#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Employee registry management.

This is the single source of truth for who is an employee in the system.
The orchestrator only shows those who are in employees.json.
HR adds employees via create_employee.py, which calls register_employee().

CLI usage:
  python employee_manager.py list
  python employee_manager.py register <name> <role>
  python employee_manager.py remove <name>
  python employee_manager.py get <name>
"""

import json
import sys
import argparse
from pathlib import Path
from datetime import date

# Validation constants
VALID_MODELS = {"opus", "sonnet", "haiku"}
VALID_PERMISSION_MODES = {
    "acceptEdits", "bypassPermissions", "default",
    "delegate", "dontAsk", "plan"
}
DEFAULT_ALLOWED_TOOLS = "Read Edit Bash"
DEFAULT_PERMISSION_MODE = "bypassPermissions"

# Path to employees.json — defaults to next to this file, but can be overridden
_employees_file: Path | None = None


def get_employees_file() -> Path:
    """Get the path to employees.json. Uses the configured path or the default."""
    global _employees_file
    if _employees_file is not None:
        return _employees_file
    return Path(__file__).resolve().parent / "employees.json"


def set_employees_file(path: Path | str) -> None:
    """Set the path to employees.json (for multi-project architecture)."""
    global _employees_file
    _employees_file = Path(path) if isinstance(path, str) else path


# For backward compatibility (CLI and direct execution)
EMPLOYEES_FILE = Path(__file__).resolve().parent / "employees.json"


def _load() -> dict:
    """Load the employee registry."""
    employees_file = get_employees_file()
    if not employees_file.exists():
        return {"employees": {}}
    try:
        return json.loads(employees_file.read_text(encoding="utf-8"))
    except Exception:
        return {"employees": {}}


def _save(data: dict) -> None:
    """Save the employee registry."""
    employees_file = get_employees_file()
    employees_file.parent.mkdir(parents=True, exist_ok=True)
    employees_file.write_text(
        json.dumps(data, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )


def get_employees() -> dict:
    """Get a dictionary of all employees: {name: {role, created_at}}."""
    return _load()["employees"]


def get_employee(name: str) -> dict | None:
    """Get data for a single employee or None."""
    employees = get_employees()
    return employees.get(name)


def register_employee(
    name: str,
    role: str,
    model: str = "sonnet",
    fallback_model: str = "",
    max_budget_usd: float = 0.0,
    permission_mode: str = DEFAULT_PERMISSION_MODE,
    allowed_tools: str = DEFAULT_ALLOWED_TOOLS,
) -> dict:
    """
    Register a new employee.
    Returns {"status": "created"|"exists"|"error", "name": ..., ...}.

    Args:
        name: Employee name (Latin characters, lowercase, underscores)
        role: Employee role (e.g. "Python developer")
        model: Claude model - opus, sonnet (default), haiku
        fallback_model: Fallback model when overloaded (opus, sonnet, haiku, or empty)
        max_budget_usd: Budget limit for API calls (>= 0, 0 = no limit)
        permission_mode: Permission mode (acceptEdits, bypassPermissions, default, delegate, dontAsk, plan)
        allowed_tools: List of allowed tools separated by spaces
    """
    # Validate model
    if model not in VALID_MODELS:
        return {"status": "error", "message": f"Invalid model: {model}. Allowed: {', '.join(VALID_MODELS)}"}

    # Validate fallback_model
    if fallback_model and fallback_model not in VALID_MODELS:
        return {"status": "error", "message": f"Invalid fallback model: {fallback_model}. Allowed: {', '.join(VALID_MODELS)}"}

    # Validate max_budget_usd
    if max_budget_usd < 0:
        return {"status": "error", "message": f"max_budget_usd must be >= 0, got: {max_budget_usd}"}

    # Validate permission_mode
    if permission_mode not in VALID_PERMISSION_MODES:
        return {"status": "error", "message": f"Invalid permission_mode: {permission_mode}. Allowed: {', '.join(VALID_PERMISSION_MODES)}"}

    # Validate allowed_tools
    if not allowed_tools or not allowed_tools.strip():
        return {"status": "error", "message": "allowed_tools cannot be empty"}

    data = _load()
    if name in data["employees"]:
        return {"status": "exists", "name": name, "role": data["employees"][name]["role"]}

    data["employees"][name] = {
        "role": role,
        "model": model,
        "fallback_model": fallback_model,
        "max_budget_usd": max_budget_usd,
        "permission_mode": permission_mode,
        "allowed_tools": allowed_tools,
        "created_at": date.today().isoformat(),
    }
    _save(data)
    return {
        "status": "created",
        "name": name,
        "role": role,
        "model": model,
        "fallback_model": fallback_model,
        "max_budget_usd": max_budget_usd,
        "permission_mode": permission_mode,
        "allowed_tools": allowed_tools,
    }


def remove_employee(name: str) -> dict:
    """
    Remove an employee from the registry.
    Boss and HR cannot be removed.
    """
    data = _load()
    if name not in data["employees"]:
        return {"status": "not_found", "name": name}
    if name in ("boss", "hr"):
        return {"status": "error", "message": "Cannot remove boss or hr"}
    del data["employees"][name]
    _save(data)
    return {"status": "removed", "name": name}


def _format_employee_line(name: str, info: dict) -> str:
    """Format an output line for an employee."""
    model = info.get('model', 'sonnet')
    fallback = info.get('fallback_model', '')
    budget = info.get('max_budget_usd', 0.0)
    mode = info.get('permission_mode', DEFAULT_PERMISSION_MODE)
    tools = info.get('allowed_tools', DEFAULT_ALLOWED_TOOLS)
    created = info.get('created_at', '?')

    # Format model with fallback
    model_str = f"[{model}→{fallback}]" if fallback else f"[{model}]"

    # Format tools (replace spaces with commas for compactness)
    tools_short = tools.replace(' ', ',')

    return f"  {name}: {info['role']} {model_str} budget=${budget} mode={mode} tools={tools_short} (since {created})"


def _cli():
    """CLI entry point."""
    parser = argparse.ArgumentParser(
        description="Employee registry management",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  python employee_manager.py list
  python employee_manager.py register dev_backend "Python developer" --model opus
  python employee_manager.py register tester "QA engineer" --model sonnet --fallback-model haiku --max-budget 5.0
  python employee_manager.py remove dev_backend
  python employee_manager.py get developer
        """
    )

    subparsers = parser.add_subparsers(dest="command", help="Available commands")

    # list
    subparsers.add_parser("list", help="Show all employees")

    # register
    register_parser = subparsers.add_parser("register", help="Register a new employee")
    register_parser.add_argument("name", help="Employee name (Latin characters, lowercase)")
    register_parser.add_argument("role", help="Employee role")
    register_parser.add_argument("--model", default="sonnet", choices=list(VALID_MODELS),
                                  help="Claude model (default: sonnet)")
    register_parser.add_argument("--fallback-model", default="", choices=["", "opus", "sonnet", "haiku"],
                                  help="Fallback model when overloaded")
    register_parser.add_argument("--max-budget", type=float, default=0.0,
                                  help="Budget limit USD (0 = no limit)")
    register_parser.add_argument("--permission-mode", default=DEFAULT_PERMISSION_MODE,
                                  choices=list(VALID_PERMISSION_MODES),
                                  help=f"Permission mode (default: {DEFAULT_PERMISSION_MODE})")
    register_parser.add_argument("--allowed-tools", default=DEFAULT_ALLOWED_TOOLS,
                                  help=f"Allowed tools separated by spaces (default: {DEFAULT_ALLOWED_TOOLS})")

    # remove
    remove_parser = subparsers.add_parser("remove", help="Remove an employee")
    remove_parser.add_argument("name", help="Employee name")

    # get
    get_parser = subparsers.add_parser("get", help="Get information about an employee")
    get_parser.add_argument("name", help="Employee name")

    args = parser.parse_args()

    if not args.command:
        parser.print_help()
        sys.exit(1)

    if args.command == "list":
        employees = get_employees()
        if not employees:
            print("Employee registry is empty.")
        else:
            print(f"Employees ({len(employees)}):")
            for name, info in employees.items():
                print(_format_employee_line(name, info))

    elif args.command == "register":
        result = register_employee(
            name=args.name,
            role=args.role,
            model=args.model,
            fallback_model=args.fallback_model,
            max_budget_usd=args.max_budget,
            permission_mode=args.permission_mode,
            allowed_tools=args.allowed_tools,
        )
        print(json.dumps(result, ensure_ascii=False, indent=2))
        if result.get("status") == "error":
            sys.exit(1)

    elif args.command == "remove":
        result = remove_employee(args.name)
        print(json.dumps(result, ensure_ascii=False, indent=2))
        if result.get("status") != "removed":
            sys.exit(1)

    elif args.command == "get":
        emp = get_employee(args.name)
        if emp:
            print(json.dumps(emp, ensure_ascii=False, indent=2))
        else:
            print(f"Employee '{args.name}' not found.")
            sys.exit(1)


if __name__ == "__main__":
    _cli()
