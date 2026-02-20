"""
Tayfa Orchestrator — web application for managing a multi-agent system.

Launches Claude API server (uvicorn), manages agents,
and provides a web interface.
"""

import argparse
import asyncio
import logging
import os
import sys
import time as _time
import webbrowser
from contextlib import asynccontextmanager
from pathlib import Path

# Set UTF-8 for stdout/stderr (for correct operation from exe)
if sys.stdout and hasattr(sys.stdout, 'reconfigure'):
    try:
        sys.stdout.reconfigure(encoding='utf-8', errors='replace')
        sys.stderr.reconfigure(encoding='utf-8', errors='replace')
    except Exception:
        pass

import httpx
from fastapi import FastAPI, Request
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles

# ── Import shared state ──────────────────────────────────────────────────────
import app_state
from app_state import (
    logger,
    KOK_DIR, TAYFA_ROOT_WIN,
    CLAUDE_API_URL,
    DEFAULT_ORCHESTRATOR_PORT, ACTUAL_ORCHESTRATOR_PORT,
    start_claude_api, stop_claude_api,
    get_current_project, get_tayfa_dir, set_tasks_file,
    set_employees_file, set_backlog_file, set_chat_history_tayfa_dir,
    migrate_remote_url, get_project_repo_name, set_project_repo_name,
    get_auto_shutdown_settings,
    find_free_port,
    _read_config_value,
    git_router,
)
from settings_manager import get_telegram_settings
from telegram_bot import start_telegram_bot, stop_telegram_bot

# ── Import routers ───────────────────────────────────────────────────────────
from routers.server import router as server_router
from routers.agents import router as agents_router
from routers.tasks import router as tasks_router
from routers.sprints import router as sprints_router
from routers.projects import router as projects_router


# ── Logging setup ────────────────────────────────────────────────────────────

# Also configure root logger for httpx/uvicorn logs
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s [%(levelname)s] %(message)s',
    datefmt='%Y-%m-%d %H:%M:%S',
    handlers=logger.handlers,
    force=True,
)

# Catch unhandled exceptions
def _exception_handler(exc_type, exc_value, exc_tb):
    """Logs unhandled exceptions before crashing."""
    import traceback
    error_msg = ''.join(traceback.format_exception(exc_type, exc_value, exc_tb))
    logger.critical(f"UNCAUGHT EXCEPTION:\n{error_msg}")
    sys.__excepthook__(exc_type, exc_value, exc_tb)

sys.excepthook = _exception_handler

from datetime import datetime
logger.info("=" * 60)
logger.info(f"Tayfa Orchestrator starting at {datetime.now().isoformat()}")


# ── Lifespan ──────────────────────────────────────────────────────────────────


async def _auto_open_browser():
    """Open browser after server starts (with a short delay)."""
    await asyncio.sleep(1.5)
    url = f"http://localhost:{app_state.ACTUAL_ORCHESTRATOR_PORT}"
    print(f"  Opening browser: {url}")
    webbrowser.open(url)


def _init_files_for_current_project():
    """Initialize paths to tasks.json, employees.json, backlog.json and chat_history for the current project (at startup)."""
    # One-time migration: extract repoName from legacy remoteUrl
    migrated_repo_name = migrate_remote_url()
    if migrated_repo_name:
        project = get_current_project()
        if project and not project.get("repoName"):
            set_project_repo_name(migrated_repo_name)
            print(f"  [migration] remoteUrl -> repoName='{migrated_repo_name}' for current project")

    project = get_current_project()
    if project:
        tayfa_path = get_tayfa_dir(project["path"])
        if tayfa_path:
            common_path = Path(tayfa_path) / "common"
            tasks_json_path = common_path / "tasks.json"
            employees_json_path = common_path / "employees.json"
            backlog_json_path = common_path / "backlog.json"
            set_tasks_file(tasks_json_path)
            set_employees_file(employees_json_path)
            set_backlog_file(backlog_json_path)
            set_chat_history_tayfa_dir(tayfa_path)
            print(f"  tasks.json set: {tasks_json_path}")
            print(f"  employees.json set: {employees_json_path}")
            print(f"  backlog.json set: {backlog_json_path}")
            print(f"  chat_history_dir set: {tayfa_path}")


async def _telegram_answer_callback(agent_name: str, answer_text: str):
    """Called when user answers a question via Telegram. Sends the answer as a prompt to the agent.
    Uses streaming endpoint and fully reads the response to ensure sse_generator completes."""
    try:
        port = app_state.ACTUAL_ORCHESTRATOR_PORT
        # IMPORTANT: Must fully consume the streaming response, otherwise
        # sse_generator() gets killed early and save_chat_message / forward_to_telegram never run.
        async with httpx.AsyncClient(timeout=httpx.Timeout(None, connect=10.0)) as client:
            async with client.stream(
                "POST",
                f"http://localhost:{port}/api/send-prompt-stream",
                json={
                    "name": agent_name,
                    "prompt": answer_text,
                    "runtime": "opus",
                    "_from_telegram": True,
                },
            ) as resp:
                if resp.status_code == 200:
                    logger.info(f"[Telegram] Answer forwarded to {agent_name}: {answer_text[:50]}")
                    # Read through the entire stream so sse_generator runs to completion
                    async for _chunk in resp.aiter_bytes():
                        pass  # We don't need the content, just need to drain the stream
                    logger.info(f"[Telegram] Stream completed for {agent_name}")
                else:
                    body = await resp.aread()
                    logger.error(f"[Telegram] Failed to forward answer: {resp.status_code} {body[:200]}")
    except Exception as e:
        logger.error(f"[Telegram] Error forwarding answer to {agent_name}: {e}")


async def _start_telegram_integration():
    """Start Telegram bot if token and chat_id are configured."""
    token, chat_id = get_telegram_settings()
    if token and chat_id:
        bot = await start_telegram_bot(token, chat_id, _telegram_answer_callback)
        if bot:
            logger.info(f"[Telegram] Bot started (chat_id={chat_id[:6]}...)")
        else:
            logger.warning("[Telegram] Bot failed to start")
    else:
        logger.info("[Telegram] Not configured (no token or chat_id in secret_settings.json)")


async def _shutdown_check_loop():
    """Checks for active clients. If no pings received — shuts down the server."""
    while True:
        await asyncio.sleep(5)
        # Get auto_shutdown settings
        auto_shutdown_enabled, shutdown_timeout = get_auto_shutdown_settings()

        # If auto-shutdown is disabled — skip the check
        if not auto_shutdown_enabled:
            continue

        elapsed = _time.time() - app_state.last_ping_time
        # Warning when elapsed > 50% of timeout
        if elapsed > shutdown_timeout * 0.5 and elapsed < shutdown_timeout * 0.6:
            print(f"  [WARNING] No ping from client for {elapsed:.0f} sec (timeout in {shutdown_timeout - elapsed:.0f} sec)")
        if elapsed > shutdown_timeout:
            print(f"\n  [SHUTDOWN] No active clients for {elapsed:.0f} sec (timeout {shutdown_timeout} sec). Shutting down server...")
            stop_claude_api()
            os._exit(0)


async def health_check_loop():
    """Periodic health check for Claude API availability."""
    while True:
        try:
            async with httpx.AsyncClient(timeout=3) as client:
                resp = await client.get(f"{app_state.CLAUDE_API_URL}/agents")
                app_state.api_running = resp.status_code == 200
        except Exception:
            app_state.api_running = False
        await asyncio.sleep(5)


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Start and stop background tasks."""
    app_state.last_ping_time = _time.time()

    # If --project was passed, init + register the project but do NOT change
    # the global "current" field in projects.json.  The locked instance
    # resolves its own project via get_current_project() override in app_state.
    if app_state.LOCKED_PROJECT_PATH:
        from app_state import init_project as _init_project, add_project as _add_project
        init_result = _init_project(app_state.LOCKED_PROJECT_PATH)
        if init_result.get("status") == "error":
            logger.error(f"Failed to init locked project {app_state.LOCKED_PROJECT_PATH!r}: {init_result.get('error')}")
        else:
            _add_project(app_state.LOCKED_PROJECT_PATH)
            logger.info(f"Locked project registered (current NOT changed): {app_state.LOCKED_PROJECT_PATH!r}")

    # Set paths to tasks.json and employees.json for current project
    _init_files_for_current_project()

    # Auto-start Claude API server
    print("  Starting Claude API server...")
    result = start_claude_api()
    if result.get("status") == "started":
        print(f"  Claude API: started (pid={result.get('pid')}, port={result.get('port')})")
    elif result.get("status") == "already_running":
        print(f"  Claude API: already running (pid={result.get('pid')}, port={result.get('port')})")
    else:
        print(f"  Claude API: {result.get('status', 'error')} — {result.get('detail', '')}")

    # Startup health check: wait for Claude API to become ready
    startup_retries = _read_config_value(
        "claude_api_startup_retries", 10,
        lambda v: isinstance(v, int) and v > 0,
    )
    logger.info(f"Waiting for Claude API to become ready (max {startup_retries} retries)...")
    claude_api_ready = False
    for attempt in range(1, startup_retries + 1):
        try:
            async with httpx.AsyncClient(timeout=2.0) as client:
                resp = await client.get(f"{app_state.CLAUDE_API_URL}/agents")
                if resp.status_code == 200:
                    logger.info("Claude API ready.")
                    claude_api_ready = True
                    break
        except Exception:
            pass
        if attempt < startup_retries:
            await asyncio.sleep(1)
    if not claude_api_ready:
        logger.critical(
            f"Claude API did not become ready after {startup_retries} retries - tasks may fail"
        )

    # Start background tasks
    health_task = asyncio.create_task(health_check_loop())
    shutdown_task = asyncio.create_task(_shutdown_check_loop())

    # Open browser automatically
    asyncio.create_task(_auto_open_browser())

    # Start Telegram bot if configured
    await _start_telegram_integration()

    yield
    # Shutdown
    health_task.cancel()
    shutdown_task.cancel()
    await stop_telegram_bot()
    stop_claude_api()


# ── FastAPI app ──────────────────────────────────────────────────────────────

app = FastAPI(title="Tayfa Orchestrator", lifespan=lifespan)
app.mount("/static", StaticFiles(directory=Path(__file__).parent / "static"), name="static")

# Include routers
app.include_router(git_router)
app.include_router(server_router)
app.include_router(agents_router)
app.include_router(tasks_router)
app.include_router(sprints_router)
app.include_router(projects_router)


# ── Middleware ────────────────────────────────────────────────────────────────

@app.middleware("http")
async def log_requests(request: Request, call_next):
    """Logs all HTTP requests and errors."""
    import time
    start_time = time.time()

    # Log the request
    logger.info(f"→ {request.method} {request.url.path}")

    try:
        response = await call_next(request)
        duration = time.time() - start_time
        logger.info(f"← {request.method} {request.url.path} [{response.status_code}] {duration:.2f}s")
        return response
    except Exception as e:
        duration = time.time() - start_time
        logger.error(f"✗ {request.method} {request.url.path} EXCEPTION after {duration:.2f}s: {e}")
        import traceback
        logger.error(traceback.format_exc())
        raise


# ── Root route ───────────────────────────────────────────────────────────────

@app.get("/", response_class=HTMLResponse)
async def root():
    """Serve the main page."""
    index_path = Path(__file__).parent / "static" / "index.html"
    return HTMLResponse(index_path.read_text(encoding="utf-8"))


# ── Backward compatibility re-exports ─────────────────────────────────────────
# Tests and other code do: from app import log_agent_failure, agent_locks, ...

from app_state import (  # noqa: E402, F401
    running_tasks,
    agent_locks,
    get_agent_lock,
    call_claude_api,
    get_personel_dir,
    get_agent_workdir,
    get_project_path_for_scoping,
    PERSONEL_DIR,
    TASKS_FILE,
    COMMON_DIR,
    SKILLS_DIR,
)

from routers.tasks import (  # noqa: E402, F401
    log_agent_failure,
    _classify_error,
    _load_failures,
    get_agent_failures,
    resolve_agent_failure,
    api_trigger_task,
    _RETRYABLE_ERRORS,
    _MAX_RETRY_ATTEMPTS,
    _RETRY_DELAY_SEC,
)

from routers.agents import (  # noqa: E402, F401
    compose_system_prompt,
    ensure_agents,
    kill_all_agents,
    run_cursor_cli,
)


# ── Startup ────────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    import uvicorn

    # Parse CLI arguments
    parser = argparse.ArgumentParser(description="Tayfa Orchestrator")
    parser.add_argument(
        "--project",
        type=str,
        default=None,
        help="Path to project folder. Locks this instance to the given project.",
    )
    args = parser.parse_args()

    if args.project:
        project_path = str(Path(args.project).resolve())
        app_state.LOCKED_PROJECT_PATH = project_path
        logger.info(f"Instance locked to project: {project_path}")

    # Find free port for orchestrator
    port = find_free_port(DEFAULT_ORCHESTRATOR_PORT)
    app_state.ACTUAL_ORCHESTRATOR_PORT = port

    logger.info(f"Starting uvicorn on port {port}")
    print(f"\n  Tayfa Orchestrator")
    print(f"  http://localhost:{port}")
    if port != DEFAULT_ORCHESTRATOR_PORT:
        print(f"  (port {DEFAULT_ORCHESTRATOR_PORT} busy, using {port})")
    if app_state.LOCKED_PROJECT_PATH:
        print(f"  Project: {app_state.LOCKED_PROJECT_PATH}")
    print()

    try:
        uvicorn.run(app, host="0.0.0.0", port=port)
    except Exception as e:
        logger.critical(f"UVICORN CRASHED: {e}")
        import traceback
        logger.critical(traceback.format_exc())
        print(f"\n  [!] ERROR: {e}")
        traceback.print_exc()
        input("\n  Press Enter to exit...")
        raise
    finally:
        logger.info("Tayfa Orchestrator shutting down")
