"""
Task routes and helpers (tasks-list, trigger, failures, auto-commit) — extracted from app.py.
"""

import asyncio
import json
import time as _time
from datetime import datetime
from pathlib import Path

import httpx
from fastapi import APIRouter, Body, HTTPException

import app_state
from app_state import (
    get_tasks, get_task, get_next_agent,
    create_task, create_backlog, update_task_status, set_task_result,
    create_backlog_item,
    TASK_STATUSES,
    get_personel_dir, get_project_path_for_scoping,
    get_employee,
    get_agent_timeout, get_max_role_triggers, get_artifact_max_lines,
    call_claude_api, stream_claude_api,
    save_chat_message,
    running_tasks, task_trigger_counts, get_agent_lock,
    init_agent_stream, push_agent_stream_event, finish_agent_stream,
    _MODEL_RUNTIMES, _CURSOR_MODELS,
    _RETRYABLE_ERRORS, _MAX_RETRY_ATTEMPTS, _RETRY_DELAY_SEC,
    TASKS_FILE,
    run_git_command,
    logger,
    MAX_FAILURE_LOG_ENTRIES,
)

router = APIRouter(tags=["tasks"])


# ── Agent Failure Logging ─────────────────────────────────────────────────────


def _get_failures_file() -> Path:
    """Path to agent_failures.json for the current project."""
    personel = get_personel_dir()
    return personel / "common" / "agent_failures.json"


def _load_failures() -> list[dict]:
    path = _get_failures_file()
    if not path.exists():
        return []
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        return data if isinstance(data, list) else []
    except Exception:
        return []


def _save_failures(failures: list[dict]) -> None:
    path = _get_failures_file()
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(failures, ensure_ascii=False, indent=2), encoding="utf-8")


def log_agent_failure(
    task_id: str,
    agent: str,
    role: str,
    runtime: str,
    error_type: str,
    message: str,
    attempt: int = 1,
) -> dict:
    """Log an agent failure. Returns the created failure entry."""
    failures = _load_failures()
    fid = f"F{len(failures) + 1:04d}"
    entry = {
        "id": fid,
        "timestamp": datetime.now().isoformat(timespec="seconds"),
        "task_id": task_id,
        "agent": agent,
        "role": role,
        "runtime": runtime,
        "error_type": error_type,
        "message": message,
        "attempt": attempt,
        "resolved": False,
    }
    failures.append(entry)
    # FIFO: keep only last MAX entries
    if len(failures) > MAX_FAILURE_LOG_ENTRIES:
        failures = failures[-MAX_FAILURE_LOG_ENTRIES:]
    _save_failures(failures)
    logger.warning(f"[AgentFailure] {fid} task={task_id} agent={agent} type={error_type} attempt={attempt}: {message}")
    return entry


def get_agent_failures(task_id: str | None = None, resolved: bool | None = None) -> list[dict]:
    """Get failures with optional filters."""
    failures = _load_failures()
    if task_id is not None:
        failures = [f for f in failures if f["task_id"] == task_id]
    if resolved is not None:
        failures = [f for f in failures if f.get("resolved", False) == resolved]
    return failures


def resolve_agent_failure(failure_id: str) -> dict | None:
    """Soft-resolve a failure by ID. Returns the updated entry or None."""
    failures = _load_failures()
    for f in failures:
        if f["id"] == failure_id:
            f["resolved"] = True
            _save_failures(failures)
            return f
    return None


# ── Artifact size check ───────────────────────────────────────────────────────


def _check_artifact_size(task_id: str, agent_name: str, result_text: str) -> None:
    """Check if agent output exceeds artifact_max_lines. If so, log warning and create backlog item."""
    if not result_text:
        return
    max_lines = get_artifact_max_lines()
    actual_lines = len(result_text.splitlines())
    if actual_lines <= max_lines:
        return

    # Log warning
    logger.warning(
        f"Agent output for {task_id} exceeds {max_lines} lines "
        f"({actual_lines} lines). Creating backlog item."
    )

    # Create backlog item
    try:
        create_backlog_item(
            title=f"Decompose {task_id}: oversized output ({actual_lines} lines)",
            description=(
                f"Task {task_id} produced oversized output ({actual_lines} lines, "
                f"limit {max_lines}). Consider decomposing into smaller sub-tasks."
            ),
            priority="medium",
            created_by="orchestrator",
        )
    except Exception as e:
        logger.error(f"Failed to create backlog item for oversized output: {e}")

    # Append note to discussion file
    try:
        disc_dir = get_personel_dir() / "common" / "discussions"
        disc_file = disc_dir / f"{task_id}.md"
        if disc_file.exists():
            note = (
                f"\n\n## [{datetime.now().strftime('%Y-%m-%d %H:%M')}] orchestrator (system)\n\n"
                f"\u26a0\ufe0f **Oversized output warning**: Agent `{agent_name}` produced "
                f"{actual_lines} lines (limit: {max_lines}). "
                f"Consider decomposing this task into smaller sub-tasks.\n"
            )
            with open(disc_file, "a", encoding="utf-8") as f:
                f.write(note)
    except Exception as e:
        logger.error(f"Failed to write size warning to discussion {task_id}: {e}")


# ── Error classification ──────────────────────────────────────────────────────


def _classify_error(exc: Exception) -> str:
    """Classify an exception into an error_type string."""
    if isinstance(exc, HTTPException):
        status = exc.status_code
        detail = str(exc.detail or "").lower()
        if status == 504 or "timeout" in detail:
            return "timeout"
        if status == 503 or "unavailable" in detail:
            return "unavailable"
        if "context" in detail and ("overflow" in detail or "length" in detail or "too long" in detail):
            return "context_overflow"
        if "budget" in detail or "billing" in detail or "rate" in detail:
            return "budget"
        if status == 400 or "config" in detail or "not registered" in detail or "not found" in detail:
            return "config"
        return "internal"
    if isinstance(exc, httpx.ReadTimeout):
        return "timeout"
    if isinstance(exc, httpx.ConnectError):
        return "unavailable"
    return "internal"


# ── Auto-commit helpers ───────────────────────────────────────────────────────


def _get_current_branch() -> str | None:
    """Returns current git branch name or None on error."""
    result = run_git_command(["branch", "--show-current"])
    if result["success"] and result["stdout"]:
        return result["stdout"].strip()
    return None


def _get_commit_hash() -> str | None:
    """Returns short hash of the last commit or None."""
    result = run_git_command(["rev-parse", "--short", "HEAD"])
    if result["success"] and result["stdout"]:
        return result["stdout"].strip()
    return None


def _get_files_changed_count() -> int:
    """Returns number of changed files in the last commit."""
    result = run_git_command(["diff-tree", "--no-commit-id", "--name-only", "-r", "HEAD"])
    if result["success"] and result["stdout"]:
        return len([f for f in result["stdout"].strip().split("\n") if f])
    return 0


def _perform_auto_commit(task_id: str, task: dict) -> dict:
    """
    Performs automatic git commit when task is marked done.

    Returns dict with result:
    - success: bool
    - hash: str (on success)
    - message: str (commit message)
    - files_changed: int (number of changed files)
    - error: str (on error)
    """
    # 1. Check if git is initialized
    from app_state import get_project_dir
    project_dir = get_project_dir()
    if project_dir is None:
        return {
            "success": False,
            "error": "No project selected"
        }

    git_dir = project_dir / ".git"
    if not git_dir.exists():
        return {
            "success": False,
            "error": "Git is not initialized in the project"
        }

    # 2. Check current branch (if task is linked to a sprint)
    sprint_id = task.get("sprint_id")
    if sprint_id:
        current_branch = _get_current_branch()
        expected_branch = f"sprint/{sprint_id}"
        if current_branch and current_branch != expected_branch:
            # Warning, but do not block commit
            # (branch may differ for legitimate reasons)
            pass  # Can add warning to log

    # 3. Compose commit message
    task_title = task.get("title", "Task completed")
    executor = task.get("executor", "")

    commit_message = f"{task_id}: {task_title}"
    if executor:
        commit_message += f"\n\nStatus: done\nExecutor: {executor}"
    else:
        commit_message += f"\n\nStatus: done"

    # 4. git add -A
    add_result = run_git_command(["add", "-A"])
    if not add_result["success"]:
        return {
            "success": False,
            "error": f"git add failed: {add_result.get('stderr', 'Unknown error')}"
        }

    # 5. Check if there is anything to commit (git status --porcelain)
    status_result = run_git_command(["status", "--porcelain"])
    if status_result["success"] and not status_result["stdout"].strip():
        # No changes — this is not an error
        return {
            "success": True,
            "hash": "",
            "message": f"{task_id}: {task_title}",
            "files_changed": 0
        }

    # 6. git commit
    commit_result = run_git_command(["commit", "-m", commit_message])

    # 7. Process result
    stdout_stderr = (commit_result.get("stdout", "") + commit_result.get("stderr", "")).lower()

    if commit_result["success"]:
        # Successful commit
        commit_hash = _get_commit_hash() or ""
        files_changed = _get_files_changed_count()

        return {
            "success": True,
            "hash": commit_hash,
            "message": f"{task_id}: {task_title}",
            "files_changed": files_changed
        }
    elif "nothing to commit" in stdout_stderr:
        # No changes — not an error
        return {
            "success": True,
            "hash": "",
            "message": f"{task_id}: {task_title}",
            "files_changed": 0
        }
    else:
        # Actual commit error
        return {
            "success": False,
            "error": commit_result.get("stderr") or commit_result.get("stdout") or "Commit failed"
        }


# ── Task routes ───────────────────────────────────────────────────────────────


@router.get("/api/tasks")
async def get_tasks_board():
    """Unified task board — contents of Personel/boss/tasks.md. User sees all tasks."""
    if not TASKS_FILE.exists():
        return {"content": "# Tasks\n\nTask board is empty. Boss tracks tasks in this file.", "path": str(TASKS_FILE)}
    try:
        content = TASKS_FILE.read_text(encoding="utf-8")
        return {"content": content, "path": str(TASKS_FILE)}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/api/tasks-list")
async def api_get_tasks(status: str | None = None, sprint_id: str | None = None):
    """List of tasks. Optional filter ?status=new&sprint_id=S001."""
    tasks = get_tasks(status=status, sprint_id=sprint_id)
    return {"tasks": tasks, "statuses": TASK_STATUSES}


@router.get("/api/tasks-list/{task_id}")
async def api_get_task(task_id: str):
    """Get one task by ID."""
    task = get_task(task_id)
    if not task:
        raise HTTPException(status_code=404, detail=f"Task {task_id} not found")
    return task


@router.post("/api/tasks-list")
async def api_create_tasks(data: dict):
    """
    Create task or task backlog.
    If data contains "tasks" (list) — creates backlog.
    Otherwise — a single task from fields title, description, author, executor, sprint_id, depends_on.
    """
    if "tasks" in data and isinstance(data["tasks"], list):
        results = create_backlog(data["tasks"])
        return {"created": results, "count": len(results)}

    title = data.get("title")
    if not title:
        raise HTTPException(status_code=400, detail="title field is required")

    task = create_task(
        title=title,
        description=data.get("description", ""),
        author=data.get("author", "boss"),
        executor=data.get("executor", ""),
        sprint_id=data.get("sprint_id", ""),
        depends_on=data.get("depends_on"),
    )
    return task


@router.put("/api/tasks-list/{task_id}/status")
async def api_update_task_status(task_id: str, data: dict):
    """
    Change task status. Body: {"status": "done"}.

    Automatic git actions:
    - "done": git add -A && git commit "TXXX: Title"
    - "done" (finalizing): merge into main + tag + push (via task_manager)

    On transition to "done" returns git_commit:
    {
        "success": true,
        "hash": "abc1234",
        "message": "T008: Task title",
        "files_changed": 5
    }
    """
    new_status = data.get("status")
    if not new_status:
        raise HTTPException(status_code=400, detail="status field is required")

    # Reset loop counter when task is completed or cancelled
    if new_status in ("done", "cancelled"):
        task_trigger_counts.pop(task_id, None)

    # update_task_status now handles release on its own when completing a finalizing task
    result = update_task_status(task_id, new_status)
    if "error" in result:
        raise HTTPException(status_code=400, detail=result["error"])

    # Auto-commit on transition to "done"
    if new_status == "done":
        task = get_task(task_id)
        if task:
            git_commit_result = _perform_auto_commit(task_id, task)
            result["git_commit"] = git_commit_result

    # Release results are already in result (sprint_released or sprint_release_error)
    # Rename for frontend compatibility
    if "sprint_released" in result:
        result["sprint_finalized"] = result.pop("sprint_released")

    return result


@router.put("/api/tasks-list/{task_id}/result")
async def api_set_task_result(task_id: str, data: dict):
    """Write work result to task. Body: {"result": "text"}."""
    result_text = data.get("result", "")
    result = set_task_result(task_id, result_text)
    if "error" in result:
        raise HTTPException(status_code=400, detail=result["error"])
    return result


@router.get("/api/running-tasks")
async def api_running_tasks():
    """List of tasks currently being executed by agents (during trigger)."""
    now = _time.time()
    result = {}
    for tid, info in running_tasks.items():
        result[tid] = {
            **info,
            "elapsed_seconds": round(now - info.get("started_at", now)),
        }
    return {"running": result}


@router.post("/api/tasks-list/{task_id}/trigger")
async def api_trigger_task(task_id: str, data: dict = Body(default_factory=dict)):
    """
    Trigger the next agent for a task.
    Determines who should work based on current status and sends them a prompt.
    Supports runtime: data.get("runtime", "claude") — "opus", "sonnet", "haiku", "cursor", or legacy "claude".

    Error recovery:
    - Classifies errors (timeout/unavailable/internal/context_overflow/budget/config)
    - Auto-retries timeout and unavailable up to 3 attempts with 5s delay
    - Logs all failures to agent_failures.json
    """
    # Check if task is already running
    if task_id in running_tasks:
        raise HTTPException(
            status_code=409,
            detail=f"Task {task_id} is already being executed by agent {running_tasks[task_id].get('agent', '?')}",
        )

    next_info = get_next_agent(task_id)
    if not next_info:
        raise HTTPException(
            status_code=400,
            detail="Task not found or already completed / cancelled",
        )

    agent_name = next_info["agent"]
    role_label = next_info["role"]
    task = next_info["task"]

    if not agent_name:
        raise HTTPException(
            status_code=400,
            detail=f"No {role_label} assigned for task {task_id}",
        )

    # Check if agent is registered
    emp = get_employee(agent_name)
    if not emp:
        raise HTTPException(
            status_code=400,
            detail=f"Agent '{agent_name}' is not registered in employees.json",
        )

    # ── Loop detection ──────────────────────────────────────────────────────
    max_triggers = get_max_role_triggers()
    if task_id not in task_trigger_counts:
        task_trigger_counts[task_id] = {}
    role_counts = task_trigger_counts[task_id]
    role_counts[role_label] = role_counts.get(role_label, 0) + 1
    trigger_count = role_counts[role_label]

    if trigger_count > max_triggers:
        loop_msg = (
            f"LOOP DETECTED: Task {task_id} has been triggered {trigger_count} times "
            f"for role '{role_label}'. Likely too complex for single execution. "
            f"Recommend decomposing into smaller tasks."
        )
        logger.warning(f"[Loop] {loop_msg}")

        # Reset task to new and clear counter so it can be re-triggered after review
        set_task_result(task_id, loop_msg)
        update_task_status(task_id, "new")
        task_trigger_counts.pop(task_id, None)

        # Create backlog item suggesting decomposition
        try:
            create_backlog_item(
                title=f"Decompose: {task.get('title', task_id)}",
                description=(
                    f"Task {task_id} was auto-stopped after {trigger_count} triggers for role '{role_label}'. "
                    f"Original description: {task.get('description', 'N/A')}. "
                    f"Suggested action: break into 2-3 smaller tasks with artifacts under 300 lines each."
                ),
                priority="high",
                created_by="system",
            )
        except Exception as e:
            logger.warning(f"[Loop] Failed to create backlog item for {task_id}: {e}")

        return {
            "task_id": task_id,
            "loop_detected": True,
            "triggers": trigger_count,
            "role": role_label,
            "message": loop_msg,
        }

    # Build prompt for agent
    prompt_parts = [
        f"Task {task['id']}: {task['title']}",
        f"Description: {task['description']}" if task.get("description") else "",
        f"Your role: {role_label}",
        f"Current status: {task['status']}",
    ]
    if task.get("result"):
        prompt_parts.append(f"Previous result: {task['result']}")

    prompt_parts.append("")
    prompt_parts.append(
        f"You are the {role_label}. Complete the task according to the description.\n"
        "When done successfully, call:\n"
        f"  python common/task_manager.py result {task['id']} \"<description of what was done>\"\n"
        f"  python common/task_manager.py status {task['id']} done\n\n"
        "If you CANNOT complete the task (missing permissions, unclear requirements, blocked), call:\n"
        f"  python common/task_manager.py result {task['id']} \"<detailed explanation of what is needed>\"\n"
        f"  python common/task_manager.py status {task['id']} questions"
    )

    full_prompt = "\n".join(p for p in prompt_parts if p is not None)

    runtime = data.get("runtime", "claude")

    # ── Resolve model name from runtime ─────────────────────────────
    # Model-specific runtimes (opus/sonnet/haiku) → use directly as model name.
    # Legacy 'claude' runtime → fall back to model from employees.json.
    if runtime in _MODEL_RUNTIMES:
        resolved_model = runtime
    else:
        resolved_model = emp.get("model", "sonnet")

    # If resolved model is a Cursor model (e.g. composer), route via cursor CLI
    if resolved_model in _CURSOR_MODELS:
        runtime = "cursor"

    # Acquire per-agent semaphore so only 1 task runs per agent at a time
    async with get_agent_lock(agent_name):
        # Register task as 'running'
        running_tasks[task_id] = {
            "agent": agent_name,
            "role": role_label,
            "runtime": runtime,
            "started_at": _time.time(),
        }

        try:
            last_error: Exception | None = None
            for attempt in range(1, _MAX_RETRY_ATTEMPTS + 1):
                start_time = _time.time()
                try:
                    if runtime == "cursor":
                        from routers.agents import run_cursor_cli
                        result = await run_cursor_cli(agent_name, full_prompt)
                        duration_sec = _time.time() - start_time

                        # Fix cursor timeout silent-success bug: check success flag
                        if not result.get("success"):
                            stderr = result.get("stderr", "")
                            error_msg = stderr or result.get("result", "") or "Cursor CLI returned failure"
                            raise HTTPException(status_code=502, detail=f"Cursor CLI error: {error_msg}")

                        # Save to chat history
                        save_chat_message(
                            agent_name=agent_name,
                            prompt=full_prompt,
                            result=result.get("result", ""),
                            runtime="cursor",
                            cost_usd=None,
                            duration_sec=duration_sec,
                            task_id=task_id,
                            success=True,
                            extra={"role": role_label, "stderr": result.get("stderr")} if result.get("stderr") else {"role": role_label},
                        )

                        return {
                            "task_id": task_id,
                            "agent": agent_name,
                            "role": role_label,
                            "runtime": "cursor",
                            "success": True,
                            "result": result.get("result", ""),
                            "stderr": result.get("stderr", ""),
                        }
                    else:
                        # Claude API — use STREAMING so frontend can see agent's thoughts live
                        init_agent_stream(agent_name)
                        full_result = ""
                        cost_usd = 0
                        num_turns = 0

                        try:
                            async for chunk in stream_claude_api("/run-stream", json_data={
                                "name": agent_name,
                                "prompt": full_prompt,
                                "project_path": get_project_path_for_scoping(),
                                "model": resolved_model,
                            }):
                                # Parse chunk and buffer for subscribers
                                try:
                                    event = json.loads(chunk)
                                except (json.JSONDecodeError, ValueError):
                                    continue

                                etype = event.get("type", "")

                                # Unwrap stream_event wrapper
                                if etype == "stream_event" and isinstance(event.get("event"), dict):
                                    event = event["event"]
                                    etype = event.get("type", "")

                                # Push to subscribers (frontend)
                                push_agent_stream_event(agent_name, event)

                                # Extract result/cost from stream events
                                if etype == "result":
                                    full_result = event.get("result", full_result)
                                    cost_usd = event.get("cost_usd", 0)
                                    num_turns = event.get("num_turns", 0)
                                elif etype == "assistant" and event.get("subtype") == "text":
                                    full_result = event.get("text", full_result)
                                elif etype == "streamlined_text":
                                    full_result = event.get("text", full_result)
                                elif etype == "error":
                                    error_text = event.get("error", "Stream error")
                                    raise HTTPException(status_code=502, detail=error_text)
                        finally:
                            finish_agent_stream(agent_name)

                        duration_sec = _time.time() - start_time

                        # Save to chat history (actual model, not generic 'claude')
                        save_chat_message(
                            agent_name=agent_name,
                            prompt=full_prompt,
                            result=full_result,
                            runtime=resolved_model,
                            cost_usd=cost_usd,
                            duration_sec=duration_sec,
                            task_id=task_id,
                            success=True,
                            extra={"role": role_label, "num_turns": num_turns},
                        )

                        # ── Artifact size check ──────────────────────────
                        _check_artifact_size(task_id, agent_name, full_result)

                        return {
                            "task_id": task_id,
                            "agent": agent_name,
                            "role": role_label,
                            "runtime": resolved_model,
                            "success": True,
                            "result": full_result,
                            "cost_usd": cost_usd,
                            "num_turns": num_turns,
                        }

                except Exception as exc:
                    last_error = exc
                    error_type = _classify_error(exc)
                    error_msg = str(getattr(exc, "detail", None) or exc)

                    # Log every attempt
                    log_agent_failure(
                        task_id=task_id,
                        agent=agent_name,
                        role=role_label,
                        runtime=runtime,
                        error_type=error_type,
                        message=error_msg,
                        attempt=attempt,
                    )

                    # Non-retryable errors: return immediately
                    if error_type not in _RETRYABLE_ERRORS:
                        break

                    # Retryable but last attempt: give up
                    if attempt >= _MAX_RETRY_ATTEMPTS:
                        logger.warning(f"[Trigger] {task_id}: all {_MAX_RETRY_ATTEMPTS} attempts exhausted ({error_type})")
                        break

                    # Wait before retry
                    logger.info(f"[Trigger] {task_id}: attempt {attempt} failed ({error_type}), retrying in {_RETRY_DELAY_SEC}s...")
                    await asyncio.sleep(_RETRY_DELAY_SEC)

            # All attempts failed — re-raise last error
            if last_error is not None:
                if isinstance(last_error, HTTPException):
                    raise last_error
                raise HTTPException(status_code=500, detail=str(last_error))

        finally:
            # Remove task from 'running' regardless of outcome
            running_tasks.pop(task_id, None)


@router.post("/api/tasks-list/{task_id}/reset-loop-counter")
async def api_reset_loop_counter(task_id: str):
    """Reset the loop-detection trigger counter for a task so it can be re-triggered."""
    removed = task_trigger_counts.pop(task_id, None)
    return {
        "task_id": task_id,
        "reset": removed is not None,
        "message": f"Loop counter cleared for {task_id}" if removed else f"No counter found for {task_id}",
    }


# ── Agent Failures API ─────────────────────────────────────────────────────────


@router.get("/api/agent-failures")
async def api_get_agent_failures(task_id: str | None = None, resolved: bool | None = None):
    """
    Get agent failure log entries.

    Query params:
        ?task_id=T001 — filter by task
        ?resolved=false — filter unresolved only
    """
    failures = get_agent_failures(task_id=task_id, resolved=resolved)
    return {"failures": failures, "count": len(failures)}


@router.delete("/api/agent-failures/{failure_id}")
async def api_resolve_agent_failure(failure_id: str):
    """Soft-resolve (mark as resolved) an agent failure entry."""
    entry = resolve_agent_failure(failure_id)
    if not entry:
        raise HTTPException(status_code=404, detail=f"Failure {failure_id} not found")
    return entry
