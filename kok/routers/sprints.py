"""
Sprint routes — extracted from app.py.
"""

from fastapi import APIRouter, HTTPException

from app_state import (
    get_sprints, get_sprint, create_sprint, update_sprint_status,
    update_sprint, delete_sprint, generate_sprint_report,
    get_tasks, SPRINT_STATUSES,
    get_next_version, get_personel_dir,
    check_git_state,
    logger,
)

router = APIRouter(tags=["sprints"])


@router.get("/api/sprints")
async def api_get_sprints():
    """List all sprints."""
    sprints = get_sprints()
    return {"sprints": sprints, "statuses": SPRINT_STATUSES}


@router.get("/api/sprints/{sprint_id}")
async def api_get_sprint(sprint_id: str):
    """Get sprint by ID."""
    sprint = get_sprint(sprint_id)
    if not sprint:
        raise HTTPException(status_code=404, detail=f"Sprint {sprint_id} not found")
    return sprint


@router.post("/api/sprints")
async def api_create_sprint(data: dict):
    """
    Create sprint. Body: {"title": "...", "description": "...", "created_by": "boss"}.

    Automatically creates git branch sprint/SXXX from main.
    create_sprint() in task_manager handles both the DB record and the git branch.

    Requirements:
    - Git must be initialized (otherwise HTTP 400)
    - Branch main or master must exist
    - If remote is unavailable — branch is created locally with a warning

    Response:
    - Success: {"id": "S002", "git_branch": "sprint/S002", "git_status": "ok"}
    - Warning: {..., "git_warning": "Remote unavailable..."}
    - Error: HTTP 400 with detail
    """
    title = data.get("title")
    if not title:
        raise HTTPException(status_code=400, detail="title field is required")

    # First check git state (before creating sprint)
    git_state = check_git_state()
    if git_state["error"]:
        raise HTTPException(status_code=400, detail=git_state["error"])

    # create_sprint() handles both DB record AND git branch creation
    # via _create_sprint_branch() which reuses existing branches gracefully.
    sprint = create_sprint(
        title=title,
        description=data.get("description", ""),
        created_by=data.get("created_by", "boss"),
        ready_to_execute=bool(data.get("ready_to_execute", False)),
    )

    sprint_id = sprint.get("id")
    if not sprint_id:
        return sprint

    # Check if git branch was created successfully
    if sprint.get("git_warning") and not sprint.get("git_branch"):
        # Branch creation failed inside create_sprint — rollback
        delete_result = delete_sprint(sprint_id)
        detail = sprint.get("git_warning", "Failed to create git branch")
        if delete_result.get("error"):
            raise HTTPException(
                status_code=500,
                detail=f"{detail}. Rollback error: {delete_result['error']}"
            )
        raise HTTPException(status_code=400, detail=detail)

    # Fill git_status for the response
    if sprint.get("git_branch"):
        sprint["git_status"] = "ok"
        if sprint.get("git_note"):
            sprint["git_status"] = "warning"
            sprint["git_warning"] = sprint["git_note"]

    return sprint


@router.put("/api/sprints/{sprint_id}/status")
async def api_update_sprint_status(sprint_id: str, data: dict):
    """Change sprint status. Body: {"status": "completed"}."""
    new_status = data.get("status")
    if not new_status:
        raise HTTPException(status_code=400, detail="status field is required")
    result = update_sprint_status(sprint_id, new_status)
    if "error" in result:
        raise HTTPException(status_code=400, detail=result["error"])
    return result


@router.put("/api/sprints/{sprint_id}")
async def api_update_sprint(sprint_id: str, data: dict):
    """Update sprint fields (title, description, ready_to_execute). Body: partial dict."""
    result = update_sprint(sprint_id, data)
    if "error" in result:
        raise HTTPException(status_code=400, detail=result["error"])
    return result


@router.get("/api/sprints/{sprint_id}/release-ready")
async def api_sprint_release_ready(sprint_id: str):
    """
    Check if sprint is ready for release.
    Returns: ready (bool), pending_tasks (list), next_version (str).
    """
    sprint = get_sprint(sprint_id)
    if not sprint:
        raise HTTPException(status_code=404, detail=f"Sprint {sprint_id} not found")

    # Get all sprint tasks (except finalizing one)
    tasks = get_tasks(sprint_id=sprint_id)
    pending_tasks = [
        {"id": t["id"], "title": t["title"], "status": t["status"]}
        for t in tasks
        if not t.get("is_finalize") and t["status"] not in ("done", "cancelled")
    ]

    ready = len(pending_tasks) == 0
    next_version = get_next_version() if ready else None

    return {
        "sprint_id": sprint_id,
        "sprint_title": sprint.get("title", ""),
        "ready": ready,
        "pending_tasks": pending_tasks,
        "next_version": next_version,
        "current_status": sprint.get("status"),
    }


@router.get("/api/sprints/{sprint_id}/report")
async def api_get_sprint_report(sprint_id: str):
    """
    Retrieve a sprint report as text/markdown.
    Returns 404 if not yet generated.
    """
    from fastapi.responses import PlainTextResponse

    personel_dir = get_personel_dir()
    report_path = personel_dir / "common" / "sprint_reports" / f"{sprint_id}_report.md"
    if not report_path.exists():
        raise HTTPException(status_code=404, detail="Report not found")
    content = report_path.read_text(encoding="utf-8")
    return PlainTextResponse(content, media_type="text/markdown")


@router.post("/api/sprints/{sprint_id}/report")
async def api_generate_sprint_report(sprint_id: str):
    """
    Manually (re-)generate a sprint report.
    Returns {"path": "...", "generated": true}.
    """
    sprint = get_sprint(sprint_id)
    if not sprint:
        raise HTTPException(status_code=404, detail=f"Sprint {sprint_id} not found")
    result = generate_sprint_report(sprint_id)
    if result.get("error"):
        raise HTTPException(status_code=500, detail=result["error"])
    return result
