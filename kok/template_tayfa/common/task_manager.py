#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Task and sprint management. Agents call these functions to create and update tasks.

Task statuses:
  pending      — task created, not yet started
  in_progress  — developer is working on the task
  in_review    — tester is reviewing the result
  done         — task completed and accepted
  cancelled    — task cancelled

Task roles:
  customer   (requester)  — details requirements
  developer  (developer)  — implements the task
  tester     (tester)     — reviews the result

Sprints:
  A sprint is a group of tasks united by a common goal.
  When a sprint is created, a "Finalize sprint" task is automatically created,
  which depends on all tasks in the sprint.
  All tasks are linked to a sprint (sprint_id).
  A task has a depends_on field — a list of task IDs it depends on.

CLI usage:
  python task_manager.py create "Title" "Description" --customer boss --developer dev_frontend --tester qa_tester --sprint S001
  python task_manager.py backlog tasks.json           # bulk creation from JSON file
  python task_manager.py list [--status pending] [--sprint S001]
  python task_manager.py get T001
  python task_manager.py status T001 in_progress
  python task_manager.py result T001 "Result description"
  python task_manager.py create-sprint "Sprint name" "Description" --created_by boss [--include-backlog]
  python task_manager.py create-from-backlog B001 --customer analyst --developer dev --tester qa --sprint S001
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
DISCUSSIONS_DIR = Path(__file__).resolve().parent / "discussions"


def _get_project_root() -> Path | None:
    """Get the project root (where .tayfa is located)."""
    # TASKS_FILE: .tayfa/common/tasks.json -> .tayfa/common -> .tayfa -> project_root
    tayfa_dir = TASKS_FILE.parent.parent  # .tayfa
    if tayfa_dir.name == ".tayfa":
        return tayfa_dir.parent
    return None


def _get_github_token() -> str:
    """Get GitHub token from kok/secret_settings.json."""
    project_root = _get_project_root()
    if not project_root:
        return ""
    secret_path = project_root / "kok" / "secret_settings.json"
    if not secret_path.exists():
        return ""
    try:
        settings = json.loads(secret_path.read_text(encoding="utf-8"))
        return settings.get("githubToken", "").strip()
    except Exception:
        return ""


def _get_authenticated_push_url() -> str | None:
    """Get push URL with token. Returns None if token is not configured."""
    token = _get_github_token()
    if not token:
        return None
    # Get current remote origin URL
    result = _run_git(["remote", "get-url", "origin"])
    if not result["success"]:
        return None
    remote_url = result["stdout"].strip()
    # Add token to URL
    if remote_url.startswith("https://github.com/"):
        return remote_url.replace("https://github.com/", f"https://{token}@github.com/")
    return None


def _run_git(args: list[str], cwd: Path | None = None) -> dict:
    """Execute a git command. Returns {success, stdout, stderr}."""
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
    """Create a git branch for the sprint. Returns {success, branch, error}."""
    branch_name = f"sprint/{sprint_id}"

    # Check if git is initialized
    check = _run_git(["rev-parse", "--git-dir"])
    if not check["success"]:
        return {"success": False, "branch": None, "error": "Git is not initialized"}

    # Check if there are any commits
    check_commits = _run_git(["rev-parse", "HEAD"])
    if not check_commits["success"]:
        return {"success": False, "branch": None, "error": "No commits in the repository"}

    # Check if the branch already exists
    check_branch = _run_git(["rev-parse", "--verify", branch_name])
    if check_branch["success"]:
        # Branch already exists — switch to it
        _run_git(["checkout", branch_name])
        return {"success": True, "branch": branch_name, "error": None, "existed": True}

    # Create branch from main (or master, or current)
    for base in ["main", "master", "HEAD"]:
        create = _run_git(["checkout", "-b", branch_name, base])
        if create["success"]:
            return {"success": True, "branch": branch_name, "error": None, "existed": False}

    return {"success": False, "branch": None, "error": "Failed to create branch"}


def _release_sprint(sprint_id: str, sprint_title: str = "") -> dict:
    """
    Perform sprint release: merge into main, tag, push.
    Returns {success, version, commit, pushed, error}.
    """
    result = {"success": False, "version": None, "commit": None, "pushed": False}

    source_branch = f"sprint/{sprint_id}"
    target_branch = "main"

    # Check git
    check = _run_git(["rev-parse", "--git-dir"])
    if not check["success"]:
        result["error"] = "Git is not initialized"
        return result

    # Get current version and calculate next one
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
        # 0. Check current branch
        current_branch = _run_git(["rev-parse", "--abbrev-ref", "HEAD"])
        current = current_branch["stdout"].strip() if current_branch["success"] else ""

        # 1. If there are uncommitted changes — commit them on the current branch first
        status = _run_git(["status", "--porcelain"])
        if status["success"] and status["stdout"].strip():
            # There are changes — commit them on the current branch
            _run_git(["add", "-A"])
            commit_result = _run_git(["commit", "-m", commit_message])
            if not commit_result["success"] and "nothing to commit" not in commit_result["stderr"]:
                result["error"] = f"Failed to commit changes: {commit_result['stderr']}"
                return result

        # 2. Switch to source_branch (sprint branch)
        if current != source_branch:
            checkout_src = _run_git(["checkout", source_branch])
            if not checkout_src["success"]:
                result["error"] = f"Branch {source_branch} not found"
                return result

        # 3. Switch to target_branch (main)
        checkout_tgt = _run_git(["checkout", target_branch])
        if not checkout_tgt["success"]:
            # Create main if it doesn't exist
            create_tgt = _run_git(["checkout", "-b", target_branch])
            if not create_tgt["success"]:
                _run_git(["checkout", source_branch])
                result["error"] = f"Failed to switch to {target_branch}"
                return result

        # 4. Pull (if remote exists)
        _run_git(["pull", "origin", target_branch])

        # 5. Merge sprint branch into main
        merge = _run_git(["merge", source_branch, "--no-ff", "-m", merge_message])
        if not merge["success"]:
            _run_git(["merge", "--abort"])
            _run_git(["checkout", source_branch])
            result["error"] = f"Merge conflict: {merge['stderr']}"
            return result

        # 6. Get commit hash
        hash_result = _run_git(["rev-parse", "--short", "HEAD"])
        result["commit"] = hash_result["stdout"] if hash_result["success"] else None

        # 7. Create version tag
        tag_msg = f"Sprint: {sprint_title}" if sprint_title else f"Release {version}"
        _run_git(["tag", "-a", version, "-m", tag_msg])

        # 8. Push to remote (with token for authentication)
        auth_url = _get_authenticated_push_url()
        if auth_url:
            # Push with token directly in URL
            push = _run_git(["push", auth_url, target_branch, "--tags"])
        else:
            # Fallback: regular push (may require credentials)
            push = _run_git(["push", "origin", target_branch, "--tags"])
        result["pushed"] = push["success"]

        if not result["pushed"]:
            # Rollback on failed push (not critical — changes remain local)
            result["push_error"] = push["stderr"]
            # Switch back to sprint branch on failed push
            _run_git(["checkout", source_branch])
        else:
            # 9. On successful push — stay on main and delete the sprint branch
            _run_git(["branch", "-d", source_branch])
            result["branch_deleted"] = True

        result["success"] = True
        return result

    except Exception as e:
        _run_git(["checkout", source_branch])
        result["error"] = str(e)
        return result


def set_tasks_file(path: str | Path) -> None:
    """Set path to tasks.json file (for working with different projects)."""
    global TASKS_FILE, DISCUSSIONS_DIR
    TASKS_FILE = Path(path)
    # Automatically set discussions path next to tasks.json
    DISCUSSIONS_DIR = TASKS_FILE.parent / "discussions"


STATUSES = ["pending", "in_progress", "in_review", "done", "cancelled"]
SPRINT_STATUSES = ["active", "completed", "released"]

# Which status is set at the "next step" and who is responsible for the current step
STATUS_FLOW = {
    "pending":     {"agent_role": "customer",  "next_status": "in_progress"},
    "in_progress": {"agent_role": "developer", "next_status": "in_review"},
    "in_review":   {"agent_role": "tester",    "next_status": "done"},
}


def _load() -> dict:
    """Load the tasks file."""
    if not TASKS_FILE.exists():
        return {"tasks": [], "sprints": [], "next_id": 1, "next_sprint_id": 1}
    try:
        data = json.loads(TASKS_FILE.read_text(encoding="utf-8"))
        # Backward compatibility: add fields if missing
        if "sprints" not in data:
            data["sprints"] = []
        if "next_sprint_id" not in data:
            data["next_sprint_id"] = 1
        return data
    except Exception:
        return {"tasks": [], "sprints": [], "next_id": 1, "next_sprint_id": 1}


def _save(data: dict) -> None:
    """Save the tasks file."""
    TASKS_FILE.parent.mkdir(parents=True, exist_ok=True)
    TASKS_FILE.write_text(
        json.dumps(data, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )


def _now() -> str:
    return datetime.now().isoformat(timespec="seconds")


def _now_formatted() -> str:
    """Return current time in 'YYYY-MM-DD HH:MM' format."""
    return datetime.now().strftime("%Y-%m-%d %H:%M")


def _create_discussion_file(task: dict) -> bool:
    """
    Create a discussion file for a task.

    Path: .tayfa/common/discussions/{task_id}.md
    Creates a file with a template including the task description.
    Does not overwrite if the file already exists.

    Args:
        task: Dictionary with task data (id, title, description, customer)

    Returns:
        True if the file was created, False if it already existed or on error
    """
    task_id = task.get("id", "")
    if not task_id:
        return False

    discussion_file = DISCUSSIONS_DIR / f"{task_id}.md"

    # Do not overwrite existing file
    if discussion_file.exists():
        return False

    # Ensure the discussions directory exists
    DISCUSSIONS_DIR.mkdir(parents=True, exist_ok=True)

    # Build the template
    title = task.get("title", "")
    description = task.get("description", "")
    customer = task.get("customer", "boss")
    date = _now_formatted()

    template = f"""# Task discussion {task_id}: {title}

## [{date}] {customer} (requester)

### Task description

{description}

### Acceptance criteria

[To be clarified by the requester]

---
"""

    try:
        discussion_file.write_text(template, encoding="utf-8")
        return True
    except OSError:
        return False


def _load_backlog() -> dict:
    """Load backlog.json. Returns {"items": [], "next_id": 1} if it doesn't exist."""
    if not BACKLOG_FILE.exists():
        return {"items": [], "next_id": 1}
    try:
        return json.loads(BACKLOG_FILE.read_text(encoding="utf-8"))
    except Exception:
        return {"items": [], "next_id": 1}


def _save_backlog(data: dict) -> None:
    """Save backlog.json."""
    BACKLOG_FILE.parent.mkdir(parents=True, exist_ok=True)
    BACKLOG_FILE.write_text(
        json.dumps(data, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )


def create_task_from_backlog(
    backlog_id: str,
    customer: str,
    developer: str,
    tester: str,
    sprint_id: str,
) -> dict:
    """
    Create a task from a backlog entry and remove the entry from the backlog.
    Returns the created task or {"error": "..."}.
    """
    # 1. Load backlog
    backlog_data = _load_backlog()

    # 2. Find entry
    item = None
    item_index = -1
    for i, b in enumerate(backlog_data.get("items", [])):
        if b["id"] == backlog_id:
            item = b
            item_index = i
            break

    if item is None:
        return {"error": f"Entry {backlog_id} not found in backlog"}

    # 3. Check sprint existence
    if sprint_id:
        sprint = get_sprint(sprint_id)
        if sprint is None:
            return {"error": f"Sprint {sprint_id} not found"}

    # 4. Create task
    task = create_task(
        title=item["title"],
        description=item["description"],
        customer=customer,
        developer=developer,
        tester=tester,
        sprint_id=sprint_id,
        depends_on=[],
    )

    # 5. Remove entry from backlog
    backlog_data["items"].pop(item_index)
    _save_backlog(backlog_data)

    return task


# ── Sprints ──────────────────────────────────────────────────────────────────


def _import_backlog_to_sprint(sprint_id: str) -> list[dict]:
    """
    Import entries with next_sprint=true into the sprint.
    Returns a list of created tasks.
    """
    backlog_data = _load_backlog()

    # Filter entries for import
    items_to_import = [
        item for item in backlog_data.get("items", [])
        if item.get("next_sprint") is True
    ]

    if not items_to_import:
        return []

    # Create tasks
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

    # Remove imported entries
    backlog_data["items"] = [
        item for item in backlog_data.get("items", [])
        if item.get("next_sprint") is not True
    ]
    _save_backlog(backlog_data)

    return created_tasks


def create_sprint(
    title: str,
    description: str = "",
    created_by: str = "boss",
    include_backlog: bool = False,
    ready_to_execute: bool = False,
) -> dict:
    """
    Create a new sprint. Returns the created sprint.
    Automatically creates a "Finalize sprint" task and a git branch sprint/SXXX.

    include_backlog: if True, imports entries with next_sprint=true from the backlog.
    ready_to_execute: if True, marks the sprint as ready for automatic execution.
    """
    data = _load()
    sprint_id = f"S{data['next_sprint_id']:03d}"
    sprint = {
        "id": sprint_id,
        "title": title,
        "description": description,
        "status": "active",
        "ready_to_execute": ready_to_execute,
        "created_by": created_by,
        "created_at": _now(),
        "updated_at": _now(),
    }
    data["sprints"].append(sprint)
    data["next_sprint_id"] += 1

    # Create "Finalize sprint" task
    finalize_task_id = f"T{data['next_id']:03d}"
    finalize_task = {
        "id": finalize_task_id,
        "title": f"Finalize sprint: {title}",
        "description": f"Final task of sprint {sprint_id}. Depends on all other tasks in the sprint. "
                       f"When all sprint tasks are done — review results and close the sprint.",
        "status": "pending",
        "customer": created_by,
        "developer": created_by,
        "tester": created_by,
        "result": "",
        "sprint_id": sprint_id,
        "depends_on": [],  # Will be updated when tasks are added to the sprint
        "is_finalize": True,
        "created_at": _now(),
        "updated_at": _now(),
    }
    data["tasks"].append(finalize_task)
    data["next_id"] += 1

    sprint["finalize_task_id"] = finalize_task_id
    _save(data)

    # Create git branch for the sprint
    git_result = _create_sprint_branch(sprint_id)
    if git_result["success"]:
        sprint["git_branch"] = git_result["branch"]
        if git_result.get("existed"):
            sprint["git_note"] = "Branch already existed"
    else:
        sprint["git_warning"] = git_result.get("error", "Failed to create git branch")

    # Import from backlog
    result = {**sprint, "finalize_task": finalize_task}
    if include_backlog:
        imported_tasks = _import_backlog_to_sprint(sprint_id)
        result["imported_from_backlog"] = len(imported_tasks)
        result["imported_tasks"] = imported_tasks

    return result


def get_sprints() -> list[dict]:
    """Get all sprints."""
    data = _load()
    return data.get("sprints", [])


def get_sprint(sprint_id: str) -> dict | None:
    """Get a sprint by ID."""
    data = _load()
    for sprint in data.get("sprints", []):
        if sprint["id"] == sprint_id:
            return sprint
    return None


def update_sprint_status(sprint_id: str, new_status: str) -> dict:
    """Change sprint status."""
    if new_status not in SPRINT_STATUSES:
        return {"error": f"Invalid sprint status. Allowed: {', '.join(SPRINT_STATUSES)}"}
    data = _load()
    for sprint in data.get("sprints", []):
        if sprint["id"] == sprint_id:
            sprint["status"] = new_status
            sprint["updated_at"] = _now()
            _save(data)
            return sprint
    return {"error": f"Sprint {sprint_id} not found"}


def update_sprint(sprint_id: str, updates: dict) -> dict:
    """Update arbitrary sprint fields (title, description, ready_to_execute).
    Does NOT allow changing status (use update_sprint_status for that)."""
    allowed_fields = {"title", "description", "ready_to_execute"}
    filtered = {k: v for k, v in updates.items() if k in allowed_fields}
    if not filtered:
        return {"error": f"No valid fields to update. Allowed: {', '.join(sorted(allowed_fields))}"}
    data = _load()
    for sprint in data.get("sprints", []):
        if sprint["id"] == sprint_id:
            sprint.update(filtered)
            sprint["updated_at"] = _now()
            _save(data)
            return sprint
    return {"error": f"Sprint {sprint_id} not found"}


def update_sprint_release(sprint_id: str, version: str, pushed: bool = True) -> dict:
    """
    Update sprint after a successful release.
    - pushed=True -> status 'released' (successful push to GitHub)
    - pushed=False -> status 'completed' (local release without push)
    """
    data = _load()
    for sprint in data.get("sprints", []):
        if sprint["id"] == sprint_id:
            sprint["status"] = "released" if pushed else "completed"
            sprint["version"] = version
            sprint["released_at"] = _now()
            sprint["updated_at"] = _now()
            _save(data)
            return sprint
    return {"error": f"Sprint {sprint_id} not found"}


def delete_sprint(sprint_id: str) -> dict:
    """
    Delete a sprint and the associated finalization task.
    Used for rollback on git branch creation error.
    """
    data = _load()

    # Find and delete sprint
    sprint_found = None
    for i, sprint in enumerate(data.get("sprints", [])):
        if sprint["id"] == sprint_id:
            sprint_found = data["sprints"].pop(i)
            break

    if not sprint_found:
        return {"error": f"Sprint {sprint_id} not found"}

    # Delete sprint finalization task
    finalize_task_id = sprint_found.get("finalize_task_id")
    if finalize_task_id:
        data["tasks"] = [t for t in data["tasks"] if t["id"] != finalize_task_id]

    # Delete all tasks linked to this sprint
    tasks_deleted = [t["id"] for t in data["tasks"] if t.get("sprint_id") == sprint_id]
    data["tasks"] = [t for t in data["tasks"] if t.get("sprint_id") != sprint_id]

    _save(data)

    return {
        "success": True,
        "deleted_sprint": sprint_id,
        "deleted_finalize_task": finalize_task_id,
        "deleted_tasks": tasks_deleted,
    }


def _update_finalize_depends(data: dict, sprint_id: str) -> None:
    """Update depends_on for the sprint finalization task."""
    # Find all sprint tasks (except the finalization task)
    sprint_task_ids = [
        t["id"] for t in data["tasks"]
        if t.get("sprint_id") == sprint_id and not t.get("is_finalize")
    ]
    # Find the finalization task
    for task in data["tasks"]:
        if task.get("sprint_id") == sprint_id and task.get("is_finalize"):
            task["depends_on"] = sprint_task_ids
            task["updated_at"] = _now()
            break


# ── Core functions (called by agents) ────────────────────────────────────────


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
    Create a new task. Only boss can create tasks.
    sprint_id: ID of the sprint the task is linked to.
    depends_on: list of task IDs this task depends on.
    Returns the created task.
    """
    data = _load()
    task_id = f"T{data['next_id']:03d}"
    task = {
        "id": task_id,
        "title": title,
        "description": description,
        "status": "pending",
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

    # Update depends_on for the sprint finalization task
    if sprint_id:
        _update_finalize_depends(data, sprint_id)

    _save(data)

    # Create discussion file for the task
    _create_discussion_file(task)

    return task


def create_backlog(tasks_list: list[dict]) -> list[dict]:
    """
    Create multiple tasks at once (backlog).
    tasks_list: list of dicts with fields title, description, customer, developer, tester,
                optionally sprint_id and depends_on.
    Returns a list of created tasks.
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
    Change the task status.
    new_status: one of "pending", "in_progress", "in_review", "done", "cancelled".

    If this is a finalization task and new_status == "done",
    checks all sprint tasks and performs a release (merge, tag, push).
    """
    if new_status not in STATUSES:
        return {"error": f"Invalid status. Allowed: {', '.join(STATUSES)}"}
    data = _load()
    for task in data["tasks"]:
        if task["id"] == task_id:
            old_status = task["status"]
            task["status"] = new_status
            task["updated_at"] = _now()
            _save(data)

            result = {**task, "old_status": old_status}

            # Automatic release when finalization task is completed
            if new_status == "done" and task.get("is_finalize"):
                sprint_id = task.get("sprint_id")
                if sprint_id:
                    # Check if all sprint tasks are done
                    sprint_tasks = get_tasks(sprint_id=sprint_id)
                    all_done = all(t["status"] in ("done", "cancelled") for t in sprint_tasks)

                    if all_done:
                        # Get sprint title
                        sprint = get_sprint(sprint_id)
                        sprint_title = sprint.get("title", "") if sprint else ""

                        # Perform release
                        release_result = _release_sprint(sprint_id, sprint_title)

                        if release_result["success"]:
                            # Update sprint status (released if push succeeded, completed if not)
                            update_sprint_release(
                                sprint_id,
                                release_result["version"],
                                pushed=release_result["pushed"]
                            )
                            result["sprint_released"] = {
                                "sprint_id": sprint_id,
                                "version": release_result["version"],
                                "commit": release_result["commit"],
                                "pushed": release_result["pushed"],
                            }
                        else:
                            result["sprint_release_error"] = release_result.get("error", "Unknown error")

                        # Generate sprint report (never blocks completion)
                        try:
                            report_result = generate_sprint_report(sprint_id)
                            if report_result.get("generated"):
                                result["sprint_report"] = report_result["path"]
                        except Exception:
                            pass  # Report failure must not block task completion

            return result
    return {"error": f"Task {task_id} not found"}


def set_task_result(task_id: str, result_text: str) -> dict:
    """Record work result in the task."""
    data = _load()
    for task in data["tasks"]:
        if task["id"] == task_id:
            task["result"] = result_text
            task["updated_at"] = _now()
            _save(data)
            return task
    return {"error": f"Task {task_id} not found"}


def get_tasks(status: str | None = None, sprint_id: str | None = None) -> list[dict]:
    """Get a list of tasks, optionally filtered by status and/or sprint."""
    data = _load()
    tasks = data["tasks"]
    if status:
        tasks = [t for t in tasks if t["status"] == status]
    if sprint_id:
        tasks = [t for t in tasks if t.get("sprint_id") == sprint_id]
    return tasks


def get_task(task_id: str) -> dict | None:
    """Get a single task by ID."""
    data = _load()
    for task in data["tasks"]:
        if task["id"] == task_id:
            return task
    return None


def get_next_agent(task_id: str) -> dict | None:
    """
    Determine which agent should work on the task at the current step.
    Returns {"agent": <name>, "role": <role>, "next_status": <new status>} or None.
    """
    task = get_task(task_id)
    if not task:
        return None
    flow = STATUS_FLOW.get(task["status"])
    if not flow:
        return None  # task is done or cancelled
    agent_role = flow["agent_role"]
    agent_name = task.get(agent_role, "")
    return {
        "agent": agent_name,
        "role": agent_role,
        "next_status": flow["next_status"],
        "task": task,
    }


# ── Sprint report generation ─────────────────────────────────────────────────

# Role synonyms for tester detection (Russian + English)
_TESTER_ROLES = {"tester", "тестер", "тестировщик", "qa", "qa_tester"}

# Stop words for error pattern extraction
_STOP_WORDS = {
    "the", "a", "an", "is", "was", "were", "are", "been", "be", "have", "has",
    "had", "do", "does", "did", "will", "would", "could", "should", "may",
    "might", "shall", "can", "need", "must", "in", "to", "and", "or", "not",
    "that", "it", "of", "for", "on", "with", "at", "by", "from", "as", "into",
    "this", "but", "if", "no", "so", "up", "out", "about", "than", "then",
    "when", "what", "which", "who", "how", "all", "each", "every", "both",
    "few", "more", "most", "some", "any", "such", "only", "same", "also",
    "just", "after", "before", "during", "while", "new", "old", "task",
    "file", "code", "test", "tests", "error", "done", "status", "result",
    "there", "here", "still", "already", "very",
    # Russian stop words
    "и", "в", "не", "на", "что", "это", "он", "она", "они", "мы", "вы",
    "но", "да", "нет", "по", "из", "за", "до", "от", "для", "при", "без",
    "все", "так", "как", "или", "уже", "ещё", "еще", "его", "её", "их",
    "был", "была", "были", "быть", "есть", "нужно", "надо", "тоже", "также",
}


def _format_duration(seconds: float) -> str:
    """Format seconds into a human-readable duration string."""
    if seconds <= 0:
        return "0s"
    hours = int(seconds // 3600)
    minutes = int((seconds % 3600) // 60)
    secs = int(seconds % 60)
    if hours > 0:
        return f"{hours}h {minutes:02d}m {secs:02d}s"
    if minutes > 0:
        return f"{minutes}m {secs:02d}s"
    return f"{secs}s"


def _collect_chat_history_for_sprint(
    tayfa_dir: Path, task_ids: set[str]
) -> dict[str, list[dict]]:
    """
    Scan all agent chat_history.json files in tayfa_dir and collect messages
    for the given task IDs. Returns {task_id: [messages]}.
    """
    result: dict[str, list[dict]] = {tid: [] for tid in task_ids}

    if not tayfa_dir or not tayfa_dir.exists():
        return result

    for agent_dir in tayfa_dir.iterdir():
        if not agent_dir.is_dir():
            continue
        history_file = agent_dir / "chat_history.json"
        if not history_file.exists():
            continue
        try:
            data = json.loads(history_file.read_text(encoding="utf-8"))
            messages = data if isinstance(data, list) else data.get("messages", [])
            for msg in messages:
                tid = msg.get("task_id", "")
                if tid in result:
                    result[tid].append(msg)
        except Exception:
            continue

    return result


def _count_tester_returns(messages: list[dict]) -> int:
    """
    Count tester returns for a task from its chat history messages.
    Returns = max(0, tester_message_count - 1).
    """
    tester_count = 0
    for msg in messages:
        role = str(msg.get("role", "")).lower().strip()
        if role in _TESTER_ROLES:
            tester_count += 1
    return max(0, tester_count - 1)


def _extract_error_patterns(tasks: list[dict], returns_map: dict[str, int]) -> list[tuple[str, int]]:
    """
    Extract common error pattern words from result text of tasks with returns > 0.
    Returns top 5 [(word, count)] sorted by frequency desc.
    """
    import re as _re

    word_freq: dict[str, int] = {}
    for task in tasks:
        tid = task.get("id", "")
        if returns_map.get(tid, 0) <= 0:
            continue
        text = task.get("result", "")
        if not text:
            continue
        words = _re.findall(r'[a-zA-Zа-яА-ЯёЁ]{4,}', text.lower())
        for word in words:
            if word not in _STOP_WORDS:
                word_freq[word] = word_freq.get(word, 0) + 1

    sorted_words = sorted(word_freq.items(), key=lambda x: x[1], reverse=True)
    return sorted_words[:5]


def generate_sprint_report(sprint_id: str) -> dict:
    """
    Generate a sprint analytics report and save it as Markdown.

    Returns {"path": str, "generated": bool, "error": str|None}.
    """
    # Get sprint metadata
    sprint = get_sprint(sprint_id)
    if not sprint:
        return {"path": "", "generated": False, "error": f"Sprint {sprint_id} not found"}

    # Get sprint tasks (excluding finalize)
    all_tasks = get_tasks(sprint_id=sprint_id)
    tasks = [t for t in all_tasks if not t.get("is_finalize")]

    # Determine tayfa_dir from TASKS_FILE location
    tayfa_dir = TASKS_FILE.parent.parent  # tasks.json -> common -> .tayfa

    # Collect chat history for all task IDs
    task_ids = {t["id"] for t in tasks}
    history_map = _collect_chat_history_for_sprint(tayfa_dir, task_ids)

    # Compute per-task metrics
    task_metrics = []
    total_cost = 0.0
    total_duration = 0.0
    total_returns = 0
    tasks_with_returns = 0
    agent_stats: dict[str, dict] = {}  # agent -> {messages, duration, cost}
    returns_map: dict[str, int] = {}

    for task in tasks:
        tid = task["id"]
        msgs = history_map.get(tid, [])

        # Duration: sum of duration_sec
        duration = sum(m.get("duration_sec", 0) or 0 for m in msgs)
        # Cost: sum of cost_usd
        cost = sum(m.get("cost_usd", 0) or 0 for m in msgs)
        # Tester returns
        returns = _count_tester_returns(msgs)
        returns_map[tid] = returns

        total_cost += cost
        total_duration += duration
        total_returns += returns
        if returns > 0:
            tasks_with_returns += 1

        task_metrics.append({
            "id": tid,
            "title": task.get("title", ""),
            "developer": task.get("developer", "N/A"),
            "duration": duration,
            "cost": cost,
            "returns": returns,
            "status": task.get("status", ""),
            "has_history": len(msgs) > 0,
        })

        # Agent stats aggregation
        for msg in msgs:
            agent_role = str(msg.get("role", "unknown")).lower().strip()
            if agent_role not in agent_stats:
                agent_stats[agent_role] = {"messages": 0, "duration": 0.0, "cost": 0.0}
            agent_stats[agent_role]["messages"] += 1
            agent_stats[agent_role]["duration"] += msg.get("duration_sec", 0) or 0
            agent_stats[agent_role]["cost"] += msg.get("cost_usd", 0) or 0

    # Counts
    completed = sum(1 for t in tasks if t.get("status") == "done")
    cancelled = sum(1 for t in tasks if t.get("status") == "cancelled")

    # Slowest tasks (top 3, with history only)
    slowest = sorted(
        [m for m in task_metrics if m["has_history"]],
        key=lambda x: x["duration"],
        reverse=True,
    )[:3]

    # Most returned tasks (top 3, returns > 0)
    most_returned = sorted(
        [m for m in task_metrics if m["returns"] > 0],
        key=lambda x: x["returns"],
        reverse=True,
    )[:3]

    # Error patterns
    error_patterns = _extract_error_patterns(tasks, returns_map)

    # Build Markdown report
    version = sprint.get("version", "N/A")
    status = sprint.get("status", "active")
    title = sprint.get("title", sprint_id)
    generated_at = _now()

    lines = []
    lines.append(f"# Sprint {sprint_id} Report: {title}")
    lines.append(f"Generated: {generated_at}")
    lines.append(f"Status: {status}  Version: {version}")
    lines.append("")

    # Summary
    lines.append("## Summary")
    lines.append(f"- Total tasks: {len(tasks)} (excluding finalize task)")
    lines.append(f"- Completed: {completed}  Cancelled: {cancelled}")
    lines.append(f"- Tester returns (total): {total_returns}  (tasks sent back at least once: {tasks_with_returns})")
    lines.append(f"- Total cost: ${total_cost:.2f} USD")
    lines.append(f"- Total duration: {_format_duration(total_duration)}")
    lines.append("")

    # Tasks table
    lines.append("## Tasks")
    lines.append("| ID | Title | Developer | Duration | Cost | Tester Returns | Status |")
    lines.append("|----|-------|-----------|----------|------|----------------|--------|")
    for m in task_metrics:
        dur_str = _format_duration(m["duration"]) if m["has_history"] else "N/A"
        cost_str = f"${m['cost']:.2f}" if m["has_history"] else "N/A"
        lines.append(f"| {m['id']} | {m['title']} | {m['developer']} | {dur_str} | {cost_str} | {m['returns']} | {m['status']} |")
    lines.append("")

    # Slowest tasks
    lines.append("## Slowest Tasks (top 3)")
    if slowest:
        for i, m in enumerate(slowest, 1):
            lines.append(f"{i}. {m['id']} — {_format_duration(m['duration'])}")
    else:
        lines.append("No task duration data available.")
    lines.append("")

    # Most returned tasks
    lines.append("## Most Returned Tasks (top 3)")
    if most_returned:
        for i, m in enumerate(most_returned, 1):
            lines.append(f"{i}. {m['id']} — returned {m['returns']} time{'s' if m['returns'] != 1 else ''}")
    else:
        lines.append("No tester returns — all tasks passed on first review.")
    lines.append("")

    # Error patterns
    lines.append("## Common Error Patterns")
    lines.append("*(Approximate pattern detection from result text of returned tasks)*")
    if error_patterns:
        for word, count in error_patterns:
            lines.append(f'- "{word}" — {count} occurrence{"s" if count != 1 else ""}')
    else:
        lines.append("No error patterns detected (no tasks returned by tester, or no result text available).")
    lines.append("")

    # Cost breakdown by agent/role
    lines.append("## Cost Breakdown")
    lines.append("| Role | Messages | Duration | Cost |")
    lines.append("|------|----------|----------|------|")
    for role_name in sorted(agent_stats.keys()):
        st = agent_stats[role_name]
        lines.append(f"| {role_name} | {st['messages']} | {_format_duration(st['duration'])} | ${st['cost']:.2f} |")
    if not agent_stats:
        lines.append("| N/A | 0 | N/A | $0.00 |")
    lines.append("")

    report_content = "\n".join(lines)

    # Save report
    reports_dir = tayfa_dir / "common" / "sprint_reports"
    reports_dir.mkdir(parents=True, exist_ok=True)
    report_path = reports_dir / f"{sprint_id}_report.md"

    try:
        report_path.write_text(report_content, encoding="utf-8")
        return {"path": str(report_path), "generated": True, "error": None}
    except Exception as e:
        return {"path": str(report_path), "generated": False, "error": str(e)}


# ── CLI ──────────────────────────────────────────────────────────────────────


def _cli():
    parser = argparse.ArgumentParser(description="Tayfa task and sprint management")
    sub = parser.add_subparsers(dest="command", help="Command")

    # create
    p_create = sub.add_parser("create", help="Create a task")
    p_create.add_argument("title", help="Task title")
    p_create.add_argument("description", nargs="?", default="", help="Task description")
    p_create.add_argument("--customer", required=True, help="Customer (agent name)")
    p_create.add_argument("--developer", required=True, help="Developer (agent name)")
    p_create.add_argument("--tester", required=True, help="Tester (agent name)")
    p_create.add_argument("--sprint", default="", help="Sprint ID (e.g. S001)")
    p_create.add_argument("--depends-on", nargs="*", default=[], help="Dependency task IDs")

    # backlog
    p_backlog = sub.add_parser("backlog", help="Create backlog from JSON file")
    p_backlog.add_argument("file", help="JSON file with task list")

    # list
    p_list = sub.add_parser("list", help="List tasks")
    p_list.add_argument("--status", choices=STATUSES, help="Filter by status")
    p_list.add_argument("--sprint", default=None, help="Filter by sprint")

    # get
    p_get = sub.add_parser("get", help="Get task by ID")
    p_get.add_argument("task_id", help="Task ID (e.g. T001)")

    # status
    p_status = sub.add_parser("status", help="Change task status")
    p_status.add_argument("task_id", help="Task ID")
    p_status.add_argument("new_status", choices=STATUSES, help="New status")

    # result
    p_result = sub.add_parser("result", help="Record work result")
    p_result.add_argument("task_id", help="Task ID")
    p_result.add_argument("text", help="Result text")

    # create-sprint
    p_sprint = sub.add_parser("create-sprint", help="Create a sprint")
    p_sprint.add_argument("title", help="Sprint name")
    p_sprint.add_argument("description", nargs="?", default="", help="Sprint description")
    p_sprint.add_argument("--created-by", default="boss", help="Who created the sprint")
    p_sprint.add_argument("--include-backlog", action="store_true", help="Import entries with next_sprint=true")

    # create-from-backlog
    p_create_backlog = sub.add_parser("create-from-backlog", help="Create task from backlog entry")
    p_create_backlog.add_argument("backlog_id", help="Backlog entry ID (e.g. B001)")
    p_create_backlog.add_argument("--customer", required=True, help="Customer (agent name)")
    p_create_backlog.add_argument("--developer", required=True, help="Developer (agent name)")
    p_create_backlog.add_argument("--tester", required=True, help="Tester (agent name)")
    p_create_backlog.add_argument("--sprint", required=True, help="Sprint ID (e.g. S001)")

    # sprints
    sub.add_parser("sprints", help="List sprints")

    # sprint (get)
    p_sprint_get = sub.add_parser("sprint", help="Get sprint by ID")
    p_sprint_get.add_argument("sprint_id", help="Sprint ID (e.g. S001)")

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
            print(f"File not found: {file_path}")
            sys.exit(1)
        tasks_list = json.loads(file_path.read_text(encoding="utf-8"))
        results = create_backlog(tasks_list)
        print(json.dumps(results, ensure_ascii=False, indent=2))
        print(f"\nCreated {len(results)} tasks.")

    elif args.command == "list":
        tasks = get_tasks(status=args.status, sprint_id=args.sprint)
        if not tasks:
            print("No tasks found.")
        else:
            print(f"Tasks ({len(tasks)}):")
            for t in tasks:
                sprint_info = f" [{t.get('sprint_id', '')}]" if t.get('sprint_id') else ""
                deps = f" depends on: {', '.join(t.get('depends_on', []))}" if t.get('depends_on') else ""
                print(f"  [{t['id']}]{sprint_info} {t['status']:14s} | {t['title']}{deps}")
                print(f"         customer: {t['customer']}, developer: {t['developer']}, tester: {t['tester']}")

    elif args.command == "get":
        task = get_task(args.task_id)
        if task:
            print(json.dumps(task, ensure_ascii=False, indent=2))
        else:
            print(f"Task {args.task_id} not found.")
            sys.exit(1)

    elif args.command == "status":
        result = update_task_status(args.task_id, args.new_status)
        print(json.dumps(result, ensure_ascii=False, indent=2))

    elif args.command == "result":
        result = set_task_result(args.task_id, args.text)
        print(json.dumps(result, ensure_ascii=False, indent=2))

    elif args.command == "create-sprint":
        sprint = create_sprint(
            args.title,
            args.description,
            created_by=args.created_by,
            include_backlog=getattr(args, "include_backlog", False),
        )
        print(json.dumps(sprint, ensure_ascii=False, indent=2))

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

    elif args.command == "sprints":
        sprints = get_sprints()
        if not sprints:
            print("No sprints found.")
        else:
            print(f"Sprints ({len(sprints)}):")
            for s in sprints:
                print(f"  [{s['id']}] {s['status']:12s} | {s['title']} (created by: {s.get('created_by', '?')})")

    elif args.command == "sprint":
        sprint = get_sprint(args.sprint_id)
        if sprint:
            print(json.dumps(sprint, ensure_ascii=False, indent=2))
        else:
            print(f"Sprint {args.sprint_id} not found.")
            sys.exit(1)


if __name__ == "__main__":
    _cli()
