# project/kok/project_manager.py
"""
Tayfa project management module.

Stores the list of projects, the current project, and initializes the .tayfa structure.
"""

import json
import shutil
import sys
from datetime import datetime
from pathlib import Path
from typing import Any

from file_lock import locked_read_json, locked_write_json

PROJECTS_FILE = Path(__file__).parent / "projects.json"
TEMPLATE_DIR = Path(__file__).parent / "template_tayfa"
TAYFA_DIR_NAME = ".tayfa"


def sanitize_repo_name(name: str) -> str:
    """
    Sanitizes a project name into a valid GitHub repository name.
    Lowercase, spaces/underscores to hyphens, strip special chars,
    collapse multiple hyphens, strip leading/trailing hyphens.
    """
    import re
    name = name.strip().lower()
    name = re.sub(r'[\s_]+', '-', name)       # spaces/underscores -> hyphens
    name = re.sub(r'[^a-z0-9\-.]', '', name)  # strip invalid chars
    name = re.sub(r'-{2,}', '-', name)         # collapse multiple hyphens
    name = name.strip('-.')                     # strip leading/trailing hyphens/dots
    return name or 'unnamed-project'


def _to_wsl_path(path: str) -> str:
    """
    Converts a path to WSL format for filesystem operations.

    C:\\Users\\... -> /mnt/c/Users/...
    /mnt/c/Users/... -> /mnt/c/Users/... (unchanged)
    """
    path_str = str(path).strip()

    # Already a WSL path
    if path_str.startswith("/mnt/"):
        return path_str

    # Windows path: C:\Users\... or C:/Users/...
    if len(path_str) >= 2 and path_str[1] == ':':
        drive = path_str[0].lower()
        rest = path_str[2:].replace("\\", "/")
        return f"/mnt/{drive}{rest}"

    # Other paths (relative, Unix) — leave as is
    return path_str


def _normalize_path(path: str) -> str:
    """
    Normalizes a path for consistent comparison and storage in projects.json.

    Handles:
    - Windows paths (C:\\Users\\...) — kept as is
    - WSL paths (/mnt/c/...) — converted to Windows format
    - Relative paths — resolved from the current directory

    Returns the path in Windows format (with backslashes).
    """
    path_str = str(path).strip()

    # If this is a Windows path (X:\...) — don't touch, just normalize slashes
    if len(path_str) >= 2 and path_str[1] == ':':
        # Windows path: C:\Users\... or C:/Users/...
        normalized = path_str.replace("/", "\\")
        return normalized

    # If this is a WSL path (/mnt/c/...) — convert to Windows
    if path_str.startswith("/mnt/") and len(path_str) >= 7:
        # /mnt/c/Users/... -> C:\Users\...
        drive = path_str[5].upper()
        rest = path_str[6:].replace("/", "\\")
        return f"{drive}:{rest}"

    # Relative or Unix path — resolve (for other cases)
    p = Path(path_str).resolve()
    resolved = str(p)

    # If resolve returned a /mnt/... path, convert to Windows
    if resolved.startswith("/mnt/") and len(resolved) >= 7:
        drive = resolved[5].upper()
        rest = resolved[6:].replace("/", "\\")
        return f"{drive}:{rest}"

    return resolved


def _load_data() -> dict[str, Any]:
    """Loads data from projects.json with cross-process file locking."""
    PROJECTS_FILE.parent.mkdir(parents=True, exist_ok=True)
    data = locked_read_json(
        str(PROJECTS_FILE),
        default={"current": None, "projects": []},
    )
    if not data or not isinstance(data, dict):
        data = {"current": None, "projects": []}
    return data


def _save_data(data: dict[str, Any]) -> None:
    """Saves data to projects.json with cross-process file locking."""
    PROJECTS_FILE.parent.mkdir(parents=True, exist_ok=True)
    locked_write_json(str(PROJECTS_FILE), data)


def _now_iso() -> str:
    """Returns the current time in ISO format."""
    return datetime.now().strftime("%Y-%m-%dT%H:%M:%S")


def _find_project_index(projects: list[dict], path: str) -> int:
    """Finds the project index by path. Returns -1 if not found."""
    norm_path = _normalize_path(path)
    for i, proj in enumerate(projects):
        if _normalize_path(proj["path"]) == norm_path:
            return i
    return -1


def is_new_user() -> bool:
    """
    Checks if the user is new (no projects).
    Used to display a welcome message.
    """
    data = _load_data()
    projects = data.get("projects", [])
    return len(projects) == 0


def list_projects() -> list[dict]:
    """
    Returns the list of projects, sorted by last_opened DESC.
    """
    data = _load_data()
    projects = data.get("projects", [])
    # Sort by last_opened DESC (most recent first)
    return sorted(
        projects,
        key=lambda p: p.get("last_opened", ""),
        reverse=True
    )


def get_project(path: str) -> dict | None:
    """
    Find a project by path.
    Returns a dict with fields path, name, last_opened, or None.
    """
    data = _load_data()
    idx = _find_project_index(data.get("projects", []), path)
    if idx >= 0:
        return data["projects"][idx]
    return None


def add_project(path: str, name: str | None = None) -> dict:
    """
    Add a project to the list.
    If name is not specified — use basename(path) for new projects.
    If the project already exists — update last_opened (name is not changed unless explicitly provided).
    """
    data = _load_data()
    projects = data.get("projects", [])
    norm_path = _normalize_path(path)

    idx = _find_project_index(projects, path)
    now = _now_iso()

    if idx >= 0:
        # Project exists — update last_opened
        projects[idx]["last_opened"] = now
        # Only update the name if explicitly provided
        if name is not None:
            projects[idx]["name"] = name
        status = "updated"
        project = projects[idx]
    else:
        # New project — use basename if name is not specified
        if name is None:
            # In WSL, Path.name doesn't work for Windows paths, extract manually
            path_str = str(path).replace("\\", "/").rstrip("/")
            name = path_str.split("/")[-1] if "/" in path_str else path_str
        project = {
            "path": norm_path,
            "name": name,
            "last_opened": now,
            "repoName": sanitize_repo_name(name),
        }
        projects.append(project)
        status = "added"

    data["projects"] = projects
    _save_data(data)

    return {"status": status, "project": project}


def remove_project(path: str) -> dict:
    """
    Remove a project from the list (does NOT delete files).
    If this is the current project — reset current to null.
    """
    data = _load_data()
    projects = data.get("projects", [])

    idx = _find_project_index(projects, path)
    if idx < 0:
        return {"status": "not_found"}

    removed = projects.pop(idx)

    # If this was the current project — reset it
    if data.get("current") and _normalize_path(data["current"]) == _normalize_path(path):
        data["current"] = None

    data["projects"] = projects
    _save_data(data)

    return {"status": "removed", "project": removed}


def get_current_project() -> dict | None:
    """
    Return the current project (by the current field).
    If current=null or the project is not found — None.
    """
    data = _load_data()
    current_path = data.get("current")

    if not current_path:
        return None

    return get_project(current_path)


def get_project_dir() -> Path | None:
    """
    Return the path to the current project's directory.
    If no project is selected — None.

    Used for git operations and other filesystem actions.
    """
    project = get_current_project()
    if not project:
        return None

    # Path is stored in Windows format, return as Path
    return Path(project["path"])


def get_project_repo_name(path: str | None = None) -> str:
    """
    Returns the repoName for a project. If not set, falls back to
    sanitized basename of the project path and persists it (AC-6).
    If path is None, uses the current project.
    """
    if path is None:
        project = get_current_project()
    else:
        project = get_project(path)

    if not project:
        return ""

    repo_name = project.get("repoName", "")
    if repo_name:
        return repo_name

    # Fallback: derive from project name or path basename
    fallback = project.get("name", "")
    if not fallback:
        path_str = str(project["path"]).replace("\\", "/").rstrip("/")
        fallback = path_str.split("/")[-1] if "/" in path_str else path_str

    derived = sanitize_repo_name(fallback)

    # Persist derived repoName for future access (AC-6 backward compat)
    set_project_repo_name(derived, project.get("path"))

    return derived


def set_project_repo_name(repo_name: str, path: str | None = None) -> dict | None:
    """
    Sets the repoName for a project.
    If path is None, uses the current project.
    Returns the updated project or None if not found.
    """
    data = _load_data()
    projects = data.get("projects", [])

    if path is None:
        current_path = data.get("current")
        if not current_path:
            return None
        path = current_path

    idx = _find_project_index(projects, path)
    if idx < 0:
        return None

    projects[idx]["repoName"] = repo_name
    data["projects"] = projects
    _save_data(data)
    return projects[idx]


def set_current_project(path: str) -> dict:
    """
    Set a project as the current one.
    Update last_opened.
    If the project is not in the list — add it.
    """
    data = _load_data()
    norm_path = _normalize_path(path)

    # Add/update the project
    result = add_project(path)
    project = result["project"]

    # Set as current
    data = _load_data()  # re-read after add_project
    data["current"] = norm_path
    _save_data(data)

    return {"status": "set", "project": project}


def get_tayfa_dir(path: str) -> Path:
    """
    Return the path to .tayfa for a project.

    IMPORTANT: We use the original path (Windows or WSL) without converting.
    Path() in Windows Python does not understand /mnt/... paths.
    """
    # Normalize the path — get Windows format for consistency
    norm_path = _normalize_path(path)
    return Path(norm_path) / TAYFA_DIR_NAME


def has_tayfa(path: str) -> bool:
    """Check if .tayfa exists in the project."""
    return get_tayfa_dir(path).exists()


def init_project(path: str) -> dict:
    """
    Initialize a project (create .tayfa if it doesn't exist).
    If .tayfa already exists — leave it alone.
    Copies template_tayfa/ into path/.tayfa/.

    Returns:
        - status: "initialized", "already_exists", "error"
        - tayfa_path: path to .tayfa
        - error: error message (if status == "error")
    """
    # IMPORTANT: We use the normalized Windows path, do NOT convert to WSL.
    # Path() in Windows Python does not understand /mnt/... paths and creates
    # relative folders instead of working with absolute paths.
    norm_path = _normalize_path(path)
    project_path = Path(norm_path)
    tayfa_path = project_path / TAYFA_DIR_NAME

    # Check if the project directory exists
    if not project_path.exists():
        return {
            "status": "error",
            "error": f"Folder does not exist: {path}",
            "tayfa_path": str(tayfa_path)
        }

    if not project_path.is_dir():
        return {
            "status": "error",
            "error": f"Path is not a folder: {path}",
            "tayfa_path": str(tayfa_path)
        }

    if tayfa_path.exists():
        return {
            "status": "already_exists",
            "tayfa_path": str(tayfa_path)
        }

    try:
        # Check if the template exists
        if not TEMPLATE_DIR.exists():
            # Create a minimal structure if the template doesn't exist
            tayfa_path.mkdir(parents=True, exist_ok=True)
            (tayfa_path / "config.json").write_text(
                '{"version": "1.0"}\n',
                encoding="utf-8"
            )
        else:
            # Copy the template
            shutil.copytree(TEMPLATE_DIR, tayfa_path)

        return {
            "status": "initialized",
            "tayfa_path": str(tayfa_path)
        }
    except PermissionError:
        return {
            "status": "error",
            "error": f"No write permission for folder: {path}",
            "tayfa_path": str(tayfa_path)
        }
    except Exception as e:
        return {
            "status": "error",
            "error": f"Error creating .tayfa: {str(e)}",
            "tayfa_path": str(tayfa_path)
        }


def open_project(path: str) -> dict:
    """
    Open a project: init + set_current.
    A combined operation for convenience.

    First initializes .tayfa (if needed), then sets it as the current project.
    On initialization error, returns status="error".
    """
    # First, initialize
    init_result = init_project(path)

    # If initialization error — return it
    if init_result.get("status") == "error":
        return {
            "status": "error",
            "error": init_result.get("error", "Project initialization error"),
            "init": "error",
            "tayfa_path": init_result.get("tayfa_path")
        }

    # Then set as current
    set_result = set_current_project(path)

    return {
        "status": "opened",
        "init": init_result["status"],
        "project": set_result["project"],
        "tayfa_path": init_result["tayfa_path"]
    }


# ── CLI interface ─────────────────────────────────────────────────────────────

def _cli_list():
    """List projects."""
    projects = list_projects()
    if not projects:
        print("No projects")
        return
    print(json.dumps(projects, ensure_ascii=False, indent=2))


def _cli_current():
    """Current project."""
    project = get_current_project()
    if not project:
        print("No current project selected")
        return
    print(json.dumps(project, ensure_ascii=False, indent=2))


def _cli_add(path: str, name: str | None = None):
    """Add a project."""
    result = add_project(path, name)
    print(json.dumps(result, ensure_ascii=False, indent=2))


def _cli_open(path: str):
    """Open a project (set_current + init)."""
    result = open_project(path)
    print(json.dumps(result, ensure_ascii=False, indent=2))


def _cli_init(path: str):
    """Initialize a project."""
    result = init_project(path)
    print(json.dumps(result, ensure_ascii=False, indent=2))


def _cli_remove(path: str):
    """Remove a project from the list."""
    result = remove_project(path)
    print(json.dumps(result, ensure_ascii=False, indent=2))


def _print_usage():
    """Prints CLI usage help."""
    print("""Usage:
    python project_manager.py list                      # list projects
    python project_manager.py current                   # current project
    python project_manager.py add "C:\\Projects\\App"   # add
    python project_manager.py open "C:\\Projects\\App"  # open (set_current + init)
    python project_manager.py init "C:\\Projects\\App"  # init only
    python project_manager.py remove "C:\\Projects\\App" # remove from list
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
