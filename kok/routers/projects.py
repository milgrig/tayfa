"""
Project, employee, chat-history, and backlog routes — extracted from app.py.
"""

import asyncio
import sys
from pathlib import Path

from fastapi import APIRouter, HTTPException

import app_state
from app_state import (
    list_projects, get_current_project, is_new_user,
    get_project_repo_name, set_project_repo_name,
    open_project, init_project, add_project, remove_project,
    set_tasks_file, set_employees_file, set_backlog_file,
    set_chat_history_tayfa_dir,
    _get_employees, get_employee, register_employee, remove_employee,
    get_chat_history, clear_chat_history,
    get_backlog, get_backlog_item, create_backlog_item,
    update_backlog_item, delete_backlog_item, toggle_next_sprint,
    logger,
)

router = APIRouter(tags=["projects"])


# ── Projects ───────────────────────────────────────────────────────────────────


@router.get("/api/projects")
async def api_list_projects():
    """List of all projects and current project. Includes is_new_user flag."""
    return {
        "projects": list_projects(),
        "current": get_current_project(),
        "is_new_user": is_new_user(),
    }


@router.get("/api/current-project")
async def api_current_project():
    """Get current project (includes repoName with fallback)."""
    project = get_current_project()
    if project and "repoName" not in project:
        # Backward compat: derive repoName for old projects
        project["repoName"] = get_project_repo_name(project.get("path"))
    return {"project": project}


@router.post("/api/projects/open")
async def api_open_project(data: dict):
    """
    Open a project: init_project + set_current_project.
    Recreates agents with the new workdir.
    Body: {"path": "C:\\Projects\\App"}
    """
    # Guard: if instance is locked to a project, reject switching
    if app_state.LOCKED_PROJECT_PATH:
        raise HTTPException(
            status_code=403,
            detail=f"This instance is locked to project: {app_state.LOCKED_PROJECT_PATH}. "
                   f"Cannot switch projects."
        )

    path = data.get("path")
    print(f"[api_open_project] Request: path={path}")

    if not path:
        raise HTTPException(status_code=400, detail="path is required")

    # Open the project (init + set_current)
    result = open_project(path)
    print(f"[api_open_project] open_project result: {result}")

    # If error (folder doesn't exist, etc.) — return it
    if result.get("status") == "error":
        print(f"[api_open_project] Error: {result.get('error')}")
        raise HTTPException(
            status_code=400,
            detail=result.get("error", "Error opening project")
        )

    # Set paths to tasks.json, employees.json, backlog.json and chat_history for the current project
    tayfa_path = result.get("tayfa_path")
    if tayfa_path:
        common_path = Path(tayfa_path) / "common"
        tasks_json_path = common_path / "tasks.json"
        employees_json_path = common_path / "employees.json"
        backlog_json_path = common_path / "backlog.json"
        set_tasks_file(tasks_json_path)
        set_employees_file(employees_json_path)
        set_backlog_file(backlog_json_path)
        set_chat_history_tayfa_dir(tayfa_path)
        print(f"[api_open_project] tasks.json set: {tasks_json_path}")
        print(f"[api_open_project] employees.json set: {employees_json_path}")
        print(f"[api_open_project] chat_history_dir set: {tayfa_path}")

    # Recreate agents with new workdir (errors don't block project opening)
    try:
        from routers.agents import kill_all_agents, ensure_agents
        await kill_all_agents(stop_server=False)
        await ensure_agents()
    except Exception as e:
        print(f"[api_open_project] Error recreating agents (non-critical): {e}")

    response = {
        "status": "opened",
        "project": result.get("project"),
        "init": result.get("init"),
        "tayfa_path": result.get("tayfa_path")
    }
    print(f"[api_open_project] Response: {response}")
    return response


@router.post("/api/projects/init")
async def api_init_project(data: dict):
    """
    Initialize a project (create .tayfa if absent).
    Body: {"path": "C:\\Projects\\App"}
    """
    path = data.get("path")
    if not path:
        raise HTTPException(status_code=400, detail="path is required")

    result = init_project(path)
    return result


@router.post("/api/projects/add")
async def api_add_project(data: dict):
    """
    Add a project to the list (without opening it).
    Body: {"path": "...", "name": "..."}
    """
    path = data.get("path")
    if not path:
        raise HTTPException(status_code=400, detail="path is required")

    name = data.get("name")
    result = add_project(path, name)
    return result


@router.post("/api/projects/remove")
async def api_remove_project(data: dict):
    """
    Remove a project from the list (does not delete files).
    Body: {"path": "..."}
    """
    path = data.get("path")
    if not path:
        raise HTTPException(status_code=400, detail="path is required")

    result = remove_project(path)
    return result


@router.post("/api/projects/repo-name")
async def api_set_project_repo_name(data: dict):
    """
    Set the repo name for the current project.
    Body: {"repoName": "my-project"}
    """
    repo_name = data.get("repoName", "").strip()
    if not repo_name:
        raise HTTPException(status_code=400, detail="repoName is required")

    result = set_project_repo_name(repo_name)
    if result is None:
        raise HTTPException(status_code=400, detail="No current project selected")

    return {"status": "updated", "project": result}


@router.get("/api/browse-folder")
async def api_browse_folder():
    """
    Opens system folder selection dialog (Windows FolderBrowserDialog).
    Returns {"path": "..."} or {"path": null, "cancelled": true}.
    """
    # PowerShell script to open FolderBrowserDialog
    ps_script = '''
Add-Type -AssemblyName System.Windows.Forms
$dialog = New-Object System.Windows.Forms.FolderBrowserDialog
$dialog.Description = "Select project folder"
$dialog.ShowNewFolderButton = $true
$result = $dialog.ShowDialog()
if ($result -eq [System.Windows.Forms.DialogResult]::OK) {
    Write-Output $dialog.SelectedPath
} else {
    Write-Output "::CANCELLED::"
}
'''
    try:
        # Run PowerShell directly (if Windows) or via powershell.exe (if WSL)
        if sys.platform == "win32":
            cmd = ["powershell", "-NoProfile", "-Command", ps_script]
        else:
            # WSL: call Windows PowerShell
            cmd = ["powershell.exe", "-NoProfile", "-Command", ps_script]

        proc = await asyncio.create_subprocess_exec(
            *cmd,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )

        # 2 minutes to select a folder
        stdout_bytes, stderr_bytes = await asyncio.wait_for(
            proc.communicate(), timeout=120
        )

        output = (stdout_bytes or b"").decode("utf-8", errors="replace").strip()
        stderr = (stderr_bytes or b"").decode("utf-8", errors="replace").strip()

        # If there's a PowerShell error
        if proc.returncode != 0 and stderr:
            return {"path": None, "error": f"PowerShell error: {stderr}"}

        if output == "::CANCELLED::" or not output:
            return {"path": None, "cancelled": True}

        return {"path": output}

    except asyncio.TimeoutError:
        # Kill the process on timeout
        try:
            proc.kill()
        except Exception:
            pass
        return {"path": None, "error": "Dialog timed out"}
    except FileNotFoundError:
        return {"path": None, "error": "PowerShell not found"}
    except Exception as e:
        return {"path": None, "error": str(e)}


# ── Employees (employees.json) ──────────────────────────────────────────────


@router.get("/api/employees")
async def api_get_employees():
    """List of all registered employees from employees.json."""
    return {"employees": _get_employees()}


@router.get("/api/employees/{name}")
async def api_get_employee(name: str):
    """Get data for one employee."""
    emp = get_employee(name)
    if not emp:
        raise HTTPException(status_code=404, detail=f"Employee '{name}' not found")
    return {"name": name, **emp}


@router.post("/api/employees")
async def api_register_employee(data: dict):
    """Register a new employee (usually via create_employee.py)."""
    name = data.get("name")
    role = data.get("role", "")
    if not name:
        raise HTTPException(status_code=400, detail="name field is required")
    result = register_employee(name, role)

    # Automatically create agent for new employee
    if result.get("status") == "created":
        try:
            from routers.agents import ensure_agents
            await ensure_agents()
            logger.info(f"Agent for '{name}' created automatically")
        except Exception as e:
            logger.warning(f"Failed to automatically create agent for '{name}': {e}")

    return result


@router.delete("/api/employees/{name}")
async def api_remove_employee(name: str):
    """Remove employee from registry."""
    result = remove_employee(name)
    if result.get("status") == "error":
        raise HTTPException(status_code=400, detail=result["message"])
    if result.get("status") == "not_found":
        raise HTTPException(status_code=404, detail=f"Employee '{name}' not found")
    return result


# ── Chat history (chat_history) ───────────────────────────────────────────────


@router.get("/api/chat-history/{agent_name}")
async def api_get_chat_history(agent_name: str, limit: int = 50, offset: int = 0):
    """
    Get chat history with an agent.
    Parameters: ?limit=50&offset=0 (pagination)
    Response: {"messages": [...], "total": 123, "limit": 50, "offset": 0}
    """
    # Check that agent exists
    emp = get_employee(agent_name)
    if not emp:
        raise HTTPException(status_code=404, detail=f"Agent '{agent_name}' not found")

    history = get_chat_history(agent_name, limit=limit, offset=offset)
    return history


@router.post("/api/chat-history/{agent_name}/clear")
async def api_clear_chat_history(agent_name: str):
    """
    Clear chat history with an agent.
    Response: {"status": "cleared", "deleted_count": 50}
    """
    # Check that agent exists
    emp = get_employee(agent_name)
    if not emp:
        raise HTTPException(status_code=404, detail=f"Agent '{agent_name}' not found")

    result = clear_chat_history(agent_name)
    if result.get("status") == "error":
        raise HTTPException(status_code=500, detail=result.get("error", "Error clearing history"))
    return result


# ── Backlog (backlog.json) ────────────────────────────────────────────────────


@router.get("/api/backlog")
async def api_get_backlog(priority: str | None = None, next_sprint: bool | None = None):
    """
    Get list of backlog items with filtering.

    Query params:
        ?priority=high/medium/low
        ?next_sprint=true/false
    """
    try:
        items = get_backlog(priority=priority, next_sprint=next_sprint)
        return {"items": items, "count": len(items)}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/api/backlog/{item_id}")
async def api_get_backlog_item(item_id: str):
    """Get one backlog item by ID."""
    item = get_backlog_item(item_id)
    if not item:
        raise HTTPException(status_code=404, detail=f"Backlog item {item_id} not found")
    return item


@router.post("/api/backlog")
async def api_create_backlog_item(data: dict):
    """
    Create a new backlog item.

    Body: {
        "title": "...",
        "description": "...",
        "priority": "high/medium/low",
        "next_sprint": true/false,
        "created_by": "boss"
    }
    """
    title = data.get("title")
    if not title:
        raise HTTPException(status_code=400, detail="title field is required")

    try:
        item = create_backlog_item(
            title=title,
            description=data.get("description", ""),
            priority=data.get("priority", "medium"),
            next_sprint=data.get("next_sprint", False),
            created_by=data.get("created_by", "boss"),
        )
        return item
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.put("/api/backlog/{item_id}")
async def api_update_backlog_item(item_id: str, data: dict):
    """
    Update backlog item.

    Body: {
        "title": "...",
        "description": "...",
        "priority": "high/medium/low",
        "next_sprint": true/false
    }
    """
    try:
        result = update_backlog_item(item_id, **data)
        if "error" in result:
            raise HTTPException(status_code=400, detail=result["error"])
        return result
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.delete("/api/backlog/{item_id}")
async def api_delete_backlog_item(item_id: str):
    """Delete backlog item."""
    try:
        result = delete_backlog_item(item_id)
        if "error" in result:
            raise HTTPException(status_code=404, detail=result["error"])
        return result
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/api/backlog/{item_id}/toggle")
async def api_toggle_next_sprint(item_id: str):
    """Toggle 'for next sprint' flag."""
    try:
        result = toggle_next_sprint(item_id)
        if "error" in result:
            raise HTTPException(status_code=404, detail=result["error"])
        return result
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
