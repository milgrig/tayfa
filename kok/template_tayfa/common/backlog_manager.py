#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Backlog Manager — backlog manager for project ideas and features for Tayfa Orchestrator.

Manages backlog entries: adding, editing, filtering, prioritizing.
Data is stored in .tayfa/common/backlog.json.

CLI usage examples:

    # Add an entry
    python backlog_manager.py add "Auth feature" --description "OAuth 2.0" --priority high --next-sprint

    # List all entries
    python backlog_manager.py list

    # List next sprint entries
    python backlog_manager.py next-sprint

    # Filter by priority
    python backlog_manager.py list --priority high

    # Get an entry
    python backlog_manager.py get B001

    # Edit an entry
    python backlog_manager.py edit B001 --title "New title" --priority medium

    # Toggle next_sprint flag
    python backlog_manager.py toggle B001

    # Remove an entry
    python backlog_manager.py remove B001

Code usage examples:

    from backlog_manager import add_item, get_items, edit_item

    # Adding
    item = add_item("New feature", priority="high", next_sprint=True)
    print(item["id"])  # B001

    # Getting a list
    items = get_items(next_sprint=True, priority="high")
    for item in items:
        print(f"{item['id']}: {item['title']}")

    # Editing
    result = edit_item("B001", title="Updated title")
    if "error" not in result:
        print(f"Updated: {result['title']}")
"""

import argparse
import json
import sys
from datetime import datetime
from pathlib import Path

# Path to backlog.json file
SCRIPT_DIR = Path(__file__).resolve().parent
BACKLOG_FILE = SCRIPT_DIR / "backlog.json"

# Valid priorities
PRIORITIES = ["high", "medium", "low"]


def _now() -> str:
    """Return current time in ISO format (without microseconds)."""
    return datetime.now().isoformat(timespec='seconds')


def _load() -> dict:
    """Load data from backlog.json. Creates the file if it does not exist."""
    if not BACKLOG_FILE.exists():
        # Create the directory if it does not exist
        BACKLOG_FILE.parent.mkdir(parents=True, exist_ok=True)
        # Initialize an empty structure
        initial_data = {"items": [], "next_id": 1}
        _save(initial_data)
        return initial_data

    try:
        with open(BACKLOG_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    except json.JSONDecodeError:
        # File is corrupted, create a new one
        initial_data = {"items": [], "next_id": 1}
        _save(initial_data)
        return initial_data


def _save(data: dict) -> None:
    """Save data to backlog.json."""
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
    Add an entry to the backlog.

    Args:
        title: Name of the idea/feature
        description: Description (optional)
        priority: Priority (high, medium, low), default is medium
        next_sprint: Flag for inclusion in the next sprint
        created_by: Who created the entry

    Returns:
        Created entry with fields: id, title, description, priority, next_sprint,
        created_by, created_at, updated_at
    """
    if priority not in PRIORITIES:
        return {"error": f"Invalid priority '{priority}'. Valid options: {', '.join(PRIORITIES)}"}

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
    Get a list of entries with optional filters.

    Args:
        next_sprint: Filter by next_sprint flag (True/False/None=all)
        priority: Filter by priority (high/medium/low/None=all)

    Returns:
        List of entries matching the filters
    """
    data = _load()
    items = data["items"]

    # Apply filters
    if next_sprint is not None:
        items = [item for item in items if item.get("next_sprint") == next_sprint]

    if priority is not None:
        items = [item for item in items if item.get("priority") == priority]

    return items


def get_item(item_id: str) -> dict | None:
    """
    Get a single entry by ID.

    Args:
        item_id: Entry ID (e.g., B001)

    Returns:
        Entry or None if not found
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
    Edit an entry.

    Args:
        item_id: Entry ID
        title: New title (if None, not changed)
        description: New description (if None, not changed)
        priority: New priority (if None, not changed)

    Returns:
        Updated entry or {"error": ...}
    """
    if priority is not None and priority not in PRIORITIES:
        return {"error": f"Invalid priority '{priority}'. Valid options: {', '.join(PRIORITIES)}"}

    data = _load()

    for item in data["items"]:
        if item["id"] == item_id:
            # Update only the provided fields
            if title is not None:
                item["title"] = title
            if description is not None:
                item["description"] = description
            if priority is not None:
                item["priority"] = priority

            item["updated_at"] = _now()
            _save(data)
            return item

    return {"error": f"Entry {item_id} not found"}


def toggle_next_sprint(item_id: str) -> dict:
    """
    Toggle the next_sprint flag (true <-> false).

    Args:
        item_id: Entry ID

    Returns:
        Updated entry or {"error": ...}
    """
    data = _load()

    for item in data["items"]:
        if item["id"] == item_id:
            item["next_sprint"] = not item.get("next_sprint", False)
            item["updated_at"] = _now()
            _save(data)
            return item

    return {"error": f"Entry {item_id} not found"}


def remove_item(item_id: str) -> dict:
    """
    Remove an entry from the backlog.

    Args:
        item_id: Entry ID

    Returns:
        {"status": "removed", "id": ...} or {"error": ...}
    """
    data = _load()

    # Find and remove the entry
    for i, item in enumerate(data["items"]):
        if item["id"] == item_id:
            data["items"].pop(i)
            _save(data)
            return {"status": "removed", "id": item_id}

    return {"error": f"Entry {item_id} not found"}


def set_backlog_file(path) -> None:
    """Override the default backlog.json path (used by the orchestrator)."""
    global BACKLOG_FILE
    BACKLOG_FILE = Path(path)


# ── Aliases used by kok/app.py ──────────────────────────────────────
get_backlog = get_items
get_backlog_item = get_item
create_backlog_item = add_item
update_backlog_item = edit_item
delete_backlog_item = remove_item


def _format_list(items: list[dict]) -> str:
    """
    Format a list of entries for human-readable output.

    Args:
        items: List of entries

    Returns:
        Formatted string
    """
    if not items:
        return "Backlog is empty."

    lines = [f"Backlog ({len(items)}):"]

    for item in items:
        item_id = item["id"]
        priority = item["priority"]
        flag = "✓" if item.get("next_sprint") else " "
        title = item["title"]

        # Format the line with alignment
        lines.append(f"  [{item_id}] {priority:<6} {flag} {title}")

    return "\n".join(lines)


def main():
    """CLI interface for backlog_manager."""
    parser = argparse.ArgumentParser(
        description="Backlog manager for project ideas and features",
        formatter_class=argparse.RawDescriptionHelpFormatter
    )

    subparsers = parser.add_subparsers(dest="command", help="Commands")

    # Command: add
    parser_add = subparsers.add_parser("add", help="Add an entry to the backlog")
    parser_add.add_argument("title", help="Name of the idea/feature")
    parser_add.add_argument("--description", default="", help="Description")
    parser_add.add_argument(
        "--priority",
        choices=PRIORITIES,
        default="medium",
        help="Priority (default: medium)"
    )
    parser_add.add_argument(
        "--next-sprint",
        action="store_true",
        help="Include in the next sprint"
    )
    parser_add.add_argument(
        "--created-by",
        default="boss",
        help="Who creates the entry (default: boss)"
    )

    # Command: list
    parser_list = subparsers.add_parser("list", help="Show list of entries")
    parser_list.add_argument(
        "--next-sprint",
        action="store_true",
        help="Show only entries for the next sprint"
    )
    parser_list.add_argument(
        "--priority",
        choices=PRIORITIES,
        help="Filter by priority"
    )

    # Command: get
    parser_get = subparsers.add_parser("get", help="Get a single entry")
    parser_get.add_argument("id", help="Entry ID (e.g., B001)")

    # Command: edit
    parser_edit = subparsers.add_parser("edit", help="Edit an entry")
    parser_edit.add_argument("id", help="Entry ID")
    parser_edit.add_argument("--title", help="New title")
    parser_edit.add_argument("--description", help="New description")
    parser_edit.add_argument("--priority", choices=PRIORITIES, help="New priority")

    # Command: toggle
    parser_toggle = subparsers.add_parser("toggle", help="Toggle the next_sprint flag")
    parser_toggle.add_argument("id", help="Entry ID")

    # Command: remove
    parser_remove = subparsers.add_parser("remove", help="Remove an entry")
    parser_remove.add_argument("id", help="Entry ID")

    # Command: next-sprint (alias for list --next-sprint)
    parser_next = subparsers.add_parser("next-sprint", help="Show entries for the next sprint")

    # Parse arguments
    args = parser.parse_args()

    if not args.command:
        parser.print_help()
        sys.exit(1)

    try:
        # Process commands
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
                error = {"error": f"Entry {args.id} not found"}
                print(json.dumps(error, ensure_ascii=False, indent=2), file=sys.stderr)
                sys.exit(1)
            else:
                print(json.dumps(item, ensure_ascii=False, indent=2))
                sys.exit(0)

        elif args.command == "edit":
            # Check that at least one parameter is provided
            if args.title is None and args.description is None and args.priority is None:
                error = {"error": "At least one parameter must be specified for editing: --title, --description, or --priority"}
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
            # Alias for list --next-sprint
            items = get_items(next_sprint=True)
            print(_format_list(items))
            sys.exit(0)

        else:
            parser.print_help()
            sys.exit(1)

    except Exception as e:
        error = {"error": f"Unexpected error: {str(e)}"}
        print(json.dumps(error, ensure_ascii=False, indent=2), file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
