"""
Tayfa Orchestrator — web application for managing a multi-agent system.

Launches Claude API server (uvicorn), manages agents,
and provides a web interface.
"""

import asyncio
import io
import json
import logging
import os
import re
import signal
import socket
import subprocess
import sys
import webbrowser
from datetime import datetime
from pathlib import Path

# Set UTF-8 for stdout/stderr (for correct operation from exe)
if sys.stdout and hasattr(sys.stdout, 'reconfigure'):
    try:
        sys.stdout.reconfigure(encoding='utf-8', errors='replace')
        sys.stderr.reconfigure(encoding='utf-8', errors='replace')
    except Exception:
        pass

import httpx
from fastapi import Body, FastAPI, HTTPException, Request
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from contextlib import asynccontextmanager

# ── Logging ───────────────────────────────────────────────────────────────

# Determine log directory (next to app.py)
_APP_DIR = Path(__file__).resolve().parent
_LOG_FILE = _APP_DIR / "tayfa_server.log"

# Logger setup — using explicit configuration instead of basicConfig,
# since basicConfig may be a no-op if root logger is already configured
# (e.g., via uvicorn or httpx on import)
_log_formatter = logging.Formatter(
    fmt='%(asctime)s [%(levelname)s] %(message)s',
    datefmt='%Y-%m-%d %H:%M:%S',
)
_file_handler = logging.FileHandler(_LOG_FILE, encoding='utf-8')
_file_handler.setFormatter(_log_formatter)
_file_handler.setLevel(logging.DEBUG)

_stream_handler = logging.StreamHandler(sys.stdout)
_stream_handler.setFormatter(_log_formatter)
_stream_handler.setLevel(logging.INFO)

logger = logging.getLogger("tayfa")
logger.setLevel(logging.DEBUG)
logger.addHandler(_file_handler)
logger.addHandler(_stream_handler)
logger.propagate = False  # don't duplicate to root logger

# Also configure root logger for httpx/uvicorn logs
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s [%(levelname)s] %(message)s',
    datefmt='%Y-%m-%d %H:%M:%S',
    handlers=[_file_handler, _stream_handler],
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

# #region debug log (ensure_agents payload comparison)
_debug_log_ensure_path = None
def _debug_log_ensure(message: str, data: dict, hypothesis_id: str = ""):
    global _debug_log_ensure_path
    for base in (_APP_DIR.parent, Path.cwd()):
        log_path = base / "debug-6f4251.log"
        try:
            with open(log_path, "a", encoding="utf-8") as f:
                f.write(json.dumps({"sessionId": "6f4251", "hypothesisId": hypothesis_id, "location": "app.py ensure_agents", "message": message, "data": data, "timestamp": int(datetime.now().timestamp() * 1000)}, ensure_ascii=False) + "\n")
            if _debug_log_ensure_path is None:
                _debug_log_ensure_path = str(log_path)
                logger.info(f"[debug] ensure_agents log: {log_path}")
            return
        except Exception:
            continue
# #endregion

logger.info("=" * 60)
logger.info(f"Tayfa Orchestrator starting at {datetime.now().isoformat()}")

# ── Configuration ──────────────────────────────────────────────────────────────

# Default ports (will be replaced with actual ones at startup)
DEFAULT_ORCHESTRATOR_PORT = 8008
DEFAULT_CLAUDE_API_PORT = 8788

# Actual ports (set dynamically at startup)
ACTUAL_ORCHESTRATOR_PORT = DEFAULT_ORCHESTRATOR_PORT
ACTUAL_CLAUDE_API_PORT = DEFAULT_CLAUDE_API_PORT

# Claude API URL (updated dynamically)
CLAUDE_API_URL = f"http://localhost:{DEFAULT_CLAUDE_API_PORT}"


def is_port_in_use(port: int) -> bool:
    """Checks if a port is in use (whether a server is listening on it)."""
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.settimeout(0.1)
        try:
            s.connect(('127.0.0.1', port))
            return True  # Connected — port is in use
        except (ConnectionRefusedError, socket.timeout, OSError):
            return False  # Could not connect — port is free


def find_free_port(start_port: int, max_attempts: int = 10) -> int:
    """
    Finds a free port starting from start_port.
    Tries ports start_port, start_port+1, ..., start_port+max_attempts-1.
    If all are in use — returns start_port + max_attempts.
    """
    for offset in range(max_attempts):
        port = start_port + offset
        if not is_port_in_use(port):
            return port
    # Fallback: next port after checked ones
    return start_port + max_attempts
# app.py is located in TayfaNew/kok/
# TAYFA_ROOT_WIN points to the project root (TayfaNew)
# .tayfa inside the project contains common/, boss/, etc.
KOK_DIR = Path(__file__).resolve().parent  # TayfaNew/kok/
TAYFA_ROOT_WIN = KOK_DIR.parent  # TayfaNew/
TAYFA_DATA_DIR = TAYFA_ROOT_WIN / ".tayfa"  # TayfaNew/.tayfa/ — Tayfa data


# Fallback paths (for backward compatibility when no project is selected)
# TAYFA_DATA_DIR points to .tayfa in the Tayfa project root
_FALLBACK_PERSONEL_DIR = TAYFA_DATA_DIR


def get_personel_dir() -> Path:
    """Path to .tayfa of the current project. Fallback: old Personel."""
    project = get_current_project()
    if project:
        return Path(project["path"]) / TAYFA_DIR_NAME
    return _FALLBACK_PERSONEL_DIR


def get_project_dir() -> Path | None:
    """Path to the current project root. None if no project is selected."""
    project = get_current_project()
    return Path(project["path"]) if project else None


def get_agent_workdir() -> str:
    """workdir for agents — project root (Windows path). When no project, use parent of .tayfa so system_prompt_file resolves correctly."""
    project = get_current_project()
    if project:
        return str(Path(project["path"]))
    # Fallback: project root = parent of .tayfa, so .tayfa/<name>/prompt.md resolves
    return str(_FALLBACK_PERSONEL_DIR.parent)


def get_project_path_for_scoping() -> str:
    """Return the current project path string for agent scoping.
    Used to pass project_path to claude_api.py so agents are isolated per project."""
    project = get_current_project()
    if project:
        return str(Path(project["path"]))
    return ""


_DEFAULT_AGENT_TIMEOUT = 600.0


def get_agent_timeout() -> float:
    """Read agent_timeout_seconds from .tayfa/config.json. Fresh on every call (no restart needed).
    Returns default 600 if missing, invalid, or non-positive."""
    try:
        config_path = get_personel_dir() / "config.json"
        if not config_path.exists():
            config_path = TAYFA_DATA_DIR / "config.json"
        if config_path.exists():
            import json as _json
            data = _json.loads(config_path.read_text(encoding="utf-8"))
            val = data.get("agent_timeout_seconds")
            if isinstance(val, (int, float)) and val > 0:
                return float(val)
    except Exception:
        pass
    return _DEFAULT_AGENT_TIMEOUT


# Legacy aliases (for compatibility with existing code, computed dynamically)
# DO NOT use in new code — call the functions directly
PERSONEL_DIR = _FALLBACK_PERSONEL_DIR  # legacy, use get_personel_dir()
TASKS_FILE = PERSONEL_DIR / "boss" / "tasks.md"  # unified task board (legacy)
SKILLS_DIR = PERSONEL_DIR / "common" / "skills"  # skills inside Personel/common/skills/

# COMMON_DIR for module imports — using template_tayfa/common from kok folder
# (these are Tayfa source files, not project data)
TEMPLATE_COMMON_DIR = KOK_DIR / "template_tayfa" / "common"
COMMON_DIR = PERSONEL_DIR / "common"  # legacy — path to current project's common

# Connect employee and task management modules from template (Tayfa sources)
sys.path.insert(0, str(TEMPLATE_COMMON_DIR))
sys.path.insert(0, str(Path(__file__).parent))  # for settings_manager and project_manager
from employee_manager import get_employees as _get_employees, get_employee, register_employee, remove_employee, set_employees_file
from task_manager import (
    create_task, create_backlog, update_task_status,
    set_task_result, get_tasks, get_task, get_next_agent,
    create_sprint, get_sprints, get_sprint, update_sprint_status,
    update_sprint, update_sprint_release,
    delete_sprint,  # for rollback on git branch creation error
    generate_sprint_report,
    STATUSES as TASK_STATUSES, SPRINT_STATUSES,
    set_tasks_file,  # for setting path to current project's tasks.json
)
from chat_history_manager import (
    save_message as save_chat_message,
    get_history as get_chat_history,
    clear_history as clear_chat_history,
    set_tayfa_dir as set_chat_history_tayfa_dir,
)
from backlog_manager import (
    get_backlog, get_backlog_item, create_backlog_item,
    update_backlog_item, delete_backlog_item, toggle_next_sprint,
    set_backlog_file,
)
from settings_manager import (
    load_settings, update_settings, get_orchestrator_port,
    get_current_version, get_next_version, save_version,
    get_auto_shutdown_settings, migrate_remote_url,
)
from project_manager import (
    list_projects, get_project, add_project, remove_project,
    get_current_project, set_current_project, init_project,
    open_project, get_tayfa_dir, has_tayfa, TAYFA_DIR_NAME,
    is_new_user, get_project_repo_name, set_project_repo_name,
)
from git_manager import (
    router as git_router,
    run_git_command,
    create_sprint_branch,
    check_git_state,
    commit_task,
    release_sprint,
)

CURSOR_CLI_PROMPT_FILE = TAYFA_ROOT_WIN / ".cursor_cli_prompt.txt"  # temporary file for prompt
CURSOR_CHATS_FILE = TAYFA_ROOT_WIN / ".cursor_chats.json"  # agent_name -> chat_id (for --resume)
CURSOR_CLI_TIMEOUT = 600.0  # Cursor CLI call timeout (seconds)
CURSOR_CREATE_CHAT_TIMEOUT = 30.0  # create-chat timeout (seconds)

# ── Global state ──────────────────────────────────────────────────────

claude_api_process: subprocess.Popen | None = None
api_running: bool = False

# Tasks currently being executed by agents: { task_id: { agent, role, runtime, started_at } }
import time as _time
running_tasks: dict[str, dict] = {}

# Auto-shutdown when browser tab is closed
last_ping_time: float = _time.time()
SHUTDOWN_TIMEOUT = 120.0  # seconds without ping before shutdown (increased from 15 to 120)

# Max entries in agent_failures.json (FIFO)
MAX_FAILURE_LOG_ENTRIES = 1000


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


# Error types eligible for auto-retry
_RETRYABLE_ERRORS = {"timeout", "unavailable"}
_MAX_RETRY_ATTEMPTS = 3
_RETRY_DELAY_SEC = 5


# ── Lifespan ──────────────────────────────────────────────────────────────────

async def _auto_open_browser():
    """Open browser after server starts (with a short delay)."""
    await asyncio.sleep(1.5)
    url = f"http://localhost:{ACTUAL_ORCHESTRATOR_PORT}"
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


async def _shutdown_check_loop():
    """Checks for active clients. If no pings received — shuts down the server."""
    global last_ping_time
    while True:
        await asyncio.sleep(5)
        # Get auto_shutdown settings
        auto_shutdown_enabled, shutdown_timeout = get_auto_shutdown_settings()

        # If auto-shutdown is disabled — skip the check
        if not auto_shutdown_enabled:
            continue

        elapsed = _time.time() - last_ping_time
        # Warning when elapsed > 50% of timeout
        if elapsed > shutdown_timeout * 0.5 and elapsed < shutdown_timeout * 0.6:
            print(f"  [WARNING] No ping from client for {elapsed:.0f} sec (timeout in {shutdown_timeout - elapsed:.0f} sec)")
        if elapsed > shutdown_timeout:
            print(f"\n  [SHUTDOWN] No active clients for {elapsed:.0f} sec (timeout {shutdown_timeout} sec). Shutting down server...")
            stop_claude_api()
            os._exit(0)


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Start and stop background tasks."""
    global last_ping_time
    last_ping_time = _time.time()

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

    # Start background tasks
    health_task = asyncio.create_task(health_check_loop())
    shutdown_task = asyncio.create_task(_shutdown_check_loop())

    # Open browser automatically
    asyncio.create_task(_auto_open_browser())

    yield
    # Shutdown
    health_task.cancel()
    shutdown_task.cancel()
    stop_claude_api()


app = FastAPI(title="Tayfa Orchestrator", lifespan=lifespan)
app.mount("/static", StaticFiles(directory=Path(__file__).parent / "static"), name="static")
app.include_router(git_router)


# ── Middleware for logging ─────────────────────────────────────────────────

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


# ── Utilities ───────────────────────────────────────────────────────────────────

async def health_check_loop():
    """Periodic health check for Claude API availability."""
    global api_running
    while True:
        try:
            async with httpx.AsyncClient(timeout=3) as client:
                resp = await client.get(f"{CLAUDE_API_URL}/agents")
                api_running = resp.status_code == 200
        except Exception:
            api_running = False
        await asyncio.sleep(5)


async def call_claude_api(method: str, path: str, json_data: dict | None = None, timeout: float = 600.0, params: dict | None = None) -> dict:
    """Sends a request to the Claude API server. On 4xx/5xx from API, raises HTTPException."""
    url = f"{CLAUDE_API_URL}{path}"
    try:
        async with httpx.AsyncClient(timeout=timeout) as client:
            if method == "GET":
                resp = await client.get(url, params=params)
            elif method == "POST":
                resp = await client.post(url, json=json_data, params=params)
            elif method == "DELETE":
                resp = await client.delete(url, params=params)
            else:
                raise ValueError(f"Unknown method: {method}")
            if resp.status_code >= 400:
                try:
                    body = resp.json()
                    detail = body.get("detail", body.get("message", resp.text or "Not Found"))
                except Exception:
                    detail = resp.text or "Not Found"
                if resp.status_code == 404:
                    detail = (
                        "Agent not found in Claude API. Start the server (button 'Start Server'), "
                        "then click 'Ensure Agents' to create agents (boss, hr, etc.)."
                    )
                raise HTTPException(status_code=resp.status_code, detail=detail)
            return resp.json()
    except HTTPException:
        raise
    except httpx.ConnectError:
        raise HTTPException(status_code=503, detail="Claude API server is unavailable. Please start it.")
    except httpx.ReadTimeout:
        raise HTTPException(status_code=504, detail="Claude API: timeout waiting for agent response.")
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Claude API error: {str(e)}")


# ── Claude API (uvicorn) management ──────────────────────────────────────────

def start_claude_api() -> dict:
    """Starts the Claude API server natively on Windows with a dynamic port."""
    global claude_api_process, ACTUAL_CLAUDE_API_PORT, CLAUDE_API_URL

    if claude_api_process and claude_api_process.poll() is None:
        return {"status": "already_running", "pid": claude_api_process.pid, "port": ACTUAL_CLAUDE_API_PORT}

    # Find a free port for Claude API
    ACTUAL_CLAUDE_API_PORT = find_free_port(DEFAULT_CLAUDE_API_PORT)
    CLAUDE_API_URL = f"http://localhost:{ACTUAL_CLAUDE_API_PORT}"

    try:
        claude_api_process = subprocess.Popen(
            [
                sys.executable, "-m", "uvicorn",
                "claude_api:app",
                "--app-dir", str(KOK_DIR),
                "--host", "0.0.0.0",
                "--port", str(ACTUAL_CLAUDE_API_PORT),
            ],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            cwd=str(TAYFA_ROOT_WIN),
            creationflags=subprocess.CREATE_NEW_PROCESS_GROUP,
        )
        return {"status": "started", "pid": claude_api_process.pid, "port": ACTUAL_CLAUDE_API_PORT}
    except Exception as e:
        return {"status": "error", "detail": str(e)}


def stop_claude_api() -> dict:
    """Stops the Claude API server."""
    global claude_api_process, api_running

    if claude_api_process and claude_api_process.poll() is None:
        try:
            claude_api_process.terminate()
            claude_api_process.wait(timeout=10)
        except Exception:
            claude_api_process.kill()
        claude_api_process = None
        api_running = False
        return {"status": "stopped"}
    return {"status": "not_running"}


# ── Cursor CLI via WSL ─────────────────────────────────────────────────────

def _to_wsl_path(path) -> str:
    """Converts a Windows path to WSL format. Used only for Cursor CLI."""
    p = str(path).replace("\\", "/")
    if p.startswith("/mnt/"):
        return p
    if len(p) >= 2 and p[1] == ":":
        return "/mnt/" + p[0].lower() + p[2:]
    return p


def _cursor_cli_base_script() -> str:
    """Base prefix for Cursor CLI commands in WSL: PATH and cd to project.
    We don't use $PATH — in WSL it may contain Windows paths with spaces and parentheses (Program Files (x86)),
    which causes bash to throw syntax error near unexpected token `('.
    """
    wsl_root = _to_wsl_path(TAYFA_ROOT_WIN)
    return (
        'export PATH="$HOME/.local/bin:/usr/local/bin:/usr/bin:/bin" && '
        f'cd "{wsl_root}"'
    )


def _load_cursor_chats() -> dict[str, str]:
    """Reads agent_name -> chat_id mapping from .cursor_chats.json."""
    if not CURSOR_CHATS_FILE.exists():
        return {}
    try:
        data = json.loads(CURSOR_CHATS_FILE.read_text(encoding="utf-8"))
        return dict(data) if isinstance(data, dict) else {}
    except Exception:
        return {}


def _save_cursor_chats(chats: dict[str, str]) -> None:
    """Saves agent_name -> chat_id mapping to .cursor_chats.json."""
    CURSOR_CHATS_FILE.write_text(json.dumps(chats, ensure_ascii=False, indent=2), encoding="utf-8")


async def run_cursor_cli_create_chat() -> dict:
    """
    Creates a chat in Cursor CLI: agent --print --output-format json create-chat.
    Returns { "success": bool, "chat_id": str | None, "raw": str, "stderr": str }.
    Parses JSON from stdout (expects fields chat_id, session_id, or id).
    """
    wsl_script = (
        f"{_cursor_cli_base_script()} && "
        "agent --print --output-format json create-chat"
    )
    try:
        proc = await asyncio.create_subprocess_exec(
            "wsl", "bash",
            stdin=asyncio.subprocess.PIPE,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
            cwd=str(TAYFA_ROOT_WIN),
        )
        stdout, stderr = await asyncio.wait_for(
            proc.communicate(input=wsl_script.encode("utf-8")),
            timeout=CURSOR_CREATE_CHAT_TIMEOUT,
        )
        out_text = (stdout or b"").decode("utf-8", errors="replace").strip()
        err_text = (stderr or b"").decode("utf-8", errors="replace").strip()
    except asyncio.TimeoutError:
        return {
            "success": False,
            "chat_id": None,
            "raw": "",
            "stderr": f"Timeout {CURSOR_CREATE_CHAT_TIMEOUT} sec.",
        }
    except Exception as e:
        return {"success": False, "chat_id": None, "raw": "", "stderr": str(e)}

    chat_id = None
    if out_text and proc.returncode == 0:
        try:
            obj = json.loads(out_text)
            chat_id = (
                obj.get("chat_id")
                or obj.get("session_id")
                or obj.get("id")
                or (obj.get("result") if isinstance(obj.get("result"), str) else None)
            )
            if isinstance(chat_id, dict):
                chat_id = chat_id.get("id") or chat_id.get("chat_id")
        except Exception:
            pass
        # create-chat may return just a UUID string (not JSON)
        if not chat_id and out_text.strip():
            line = out_text.strip().splitlines()[0].strip()
            if len(line) == 36 and line.count("-") == 4:
                chat_id = line

    return {
        "success": proc.returncode == 0 and bool(chat_id),
        "chat_id": str(chat_id) if chat_id else None,
        "raw": out_text,
        "stderr": err_text,
    }


def _build_cursor_cli_prompt(agent_name: str, user_prompt: str) -> str:
    """Builds prompt for Cursor CLI: role (agent name) + context + task."""
    return (
        f"Role: {agent_name}. Working directory: Personel (project/ — code, common/Rules/ — rules). "
        f"Consider context from {agent_name}/prompt.md and common/Rules/. Task: {user_prompt}"
    )


async def ensure_cursor_chat(agent_name: str) -> tuple[str | None, str]:
    """
    Returns (chat_id, error): chat_id for agent from .cursor_chats.json or creates a new one (create-chat).
    On error: (None, error_message).
    """
    chats = _load_cursor_chats()
    if agent_name in chats and chats[agent_name]:
        return chats[agent_name], ""
    create_result = await run_cursor_cli_create_chat()
    if not create_result.get("success") or not create_result.get("chat_id"):
        err = create_result.get("stderr") or create_result.get("raw") or "create-chat did not return chat_id"
        return None, err
    chat_id = create_result["chat_id"]
    chats[agent_name] = chat_id
    _save_cursor_chats(chats)
    return chat_id, ""


async def run_cursor_cli(agent_name: str, user_prompt: str, use_chat: bool = True) -> dict:
    """
    Runs Cursor CLI in WSL in headless mode.
    If use_chat=True, ensures a chat exists for the agent (create-chat if needed)
    and sends a message with --resume <chat_id>. Otherwise — a one-time call without --resume.
    Returns { "success": bool, "result": str, "stderr": str }.
    """
    full_prompt = _build_cursor_cli_prompt(agent_name, user_prompt)
    try:
        CURSOR_CLI_PROMPT_FILE.write_text(full_prompt, encoding="utf-8")
    except Exception as e:
        return {"success": False, "result": "", "stderr": f"Failed to write prompt: {e}"}

    chat_id = None
    chat_error = ""
    if use_chat:
        chat_id, chat_error = await ensure_cursor_chat(agent_name)
        if not chat_id and chat_error:
            # Failed to get chat — return error immediately (don't run agent without --resume)
            return {
                "success": False,
                "result": "",
                "stderr": f"Failed to get Cursor chat for '{agent_name}': {chat_error}",
            }

    # WSL: PATH, cd, then agent with prompt from file (escape quotes in content for bash)
    base = _cursor_cli_base_script()
    safe_id = (chat_id or "").replace("'", "'\"'\"'")
    resume_part = f" --resume '{safe_id}'" if chat_id else ""
    # Read prompt into variable with " escaping for bash, so quotes in text don't break the command
    wsl_script = (
        f"{base} && "
        "content=$(cat .cursor_cli_prompt.txt | sed 's/\"/\\\\\"/g') && "
        f"agent -p --force{resume_part} --output-format json \"$content\""
    )

    try:
        proc = await asyncio.create_subprocess_exec(
            "wsl", "bash",
            stdin=asyncio.subprocess.PIPE,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
            cwd=str(TAYFA_ROOT_WIN),
        )
        stdout, stderr = await asyncio.wait_for(
            proc.communicate(input=wsl_script.encode("utf-8")),
            timeout=CURSOR_CLI_TIMEOUT,
        )
        out_text = (stdout or b"").decode("utf-8", errors="replace").strip()
        err_text = (stderr or b"").decode("utf-8", errors="replace").strip()
    except asyncio.TimeoutError:
        return {
            "success": False,
            "result": "",
            "stderr": f"Timeout {CURSOR_CLI_TIMEOUT} sec. Cursor CLI did not finish in time.",
        }
    except Exception as e:
        return {"success": False, "result": "", "stderr": str(e)}
    finally:
        try:
            if CURSOR_CLI_PROMPT_FILE.exists():
                CURSOR_CLI_PROMPT_FILE.unlink()
        except Exception:
            pass

    # If output is JSON (--output-format json), extract result
    result_text = out_text
    if out_text and proc.returncode == 0:
        try:
            obj = json.loads(out_text)
            if isinstance(obj, dict) and "result" in obj:
                result_text = obj.get("result") or result_text
        except Exception:
            pass

    return {
        "success": proc.returncode == 0,
        "result": result_text,
        "stderr": err_text,
    }


def _extract_md_section(text: str, section_title: str) -> str:
    """Extracts a markdown block from ## section_title line to the next ## or end of text."""
    lines = text.splitlines()
    in_section = False
    result = []
    for line in lines:
        if line.strip().startswith("## ") and section_title.lower() in line.lower():
            in_section = True
            result.append(line)
            continue
        if in_section:
            if line.strip().startswith("## "):
                break
            result.append(line)
    return "\n".join(result).strip() if result else ""


def resolve_skill_path(skill_id: str) -> Path | None:
    """
    By skill identifier (e.g. 'project-decomposer' or 'public/pptx')
    returns the path to SKILL.md in Tayfa/skills/<skill_id>/SKILL.md.
    """
    if not skill_id or not SKILLS_DIR.exists():
        return None
    # Normalize: convert slashes to path separators
    parts = skill_id.replace("\\", "/").strip("/").split("/")
    skill_dir = SKILLS_DIR.joinpath(*parts)
    skill_file = skill_dir / "SKILL.md"
    return skill_file if skill_file.exists() else None


def load_skill_content(skill_id: str) -> str | None:
    """Reads the contents of SKILL.md for the specified skill. Returns None if not found."""
    path = resolve_skill_path(skill_id)
    if path is None:
        return None
    try:
        return path.read_text(encoding="utf-8").strip()
    except Exception:
        return None


def compose_system_prompt(agent_name: str, use_skills: list[str] | None = None, personel_dir: Path | None = None) -> str | None:
    """
    Composes system prompt from prompt.md + 'Skills' block from profile.md (and skills.md).
    If use_skills is provided, appends SKILL.md content from Tayfa/skills/<id>/ to the end of the prompt.
    If personel_dir is provided, use it (e.g. from ensure_agents); else get_personel_dir().
    Returns None if folders/files don't exist — then only system_prompt_file from the request is used.
    """
    if personel_dir is None:
        personel_dir = get_personel_dir()
    agent_dir = personel_dir / agent_name
    prompt_file = agent_dir / "prompt.md"
    profile_file = agent_dir / "profile.md"
    skills_file = agent_dir / "skills.md"

    logger.info(f"[compose_system_prompt] agent={agent_name!r}, prompt_file={prompt_file}, exists={prompt_file.exists()}")

    if not prompt_file.exists():
        logger.warning(f"[compose_system_prompt] {agent_name}: prompt.md NOT FOUND at {prompt_file}")
        return None

    prompt_text = prompt_file.read_text(encoding="utf-8")
    logger.info(f"[compose_system_prompt] {agent_name}: read prompt.md ({len(prompt_text)} chars)")

    # Add working directory structure section (if there's a current project)
    project = get_current_project()
    if project:
        structure_info = f"""## Working directory structure

You are working on the project **{project['name']}**.

- **Project root**: `./` (current working directory, workdir)
- **.tayfa/**: Tayfa team folder
  - `.tayfa/common/`: shared files (tasks.json, employees.json, Rules/)
  - `.tayfa/boss/`, `.tayfa/hr/`: other agents' folders

Project code is at the root (src/, package.json, etc.), and team files are in .tayfa/.

"""
        prompt_text = structure_info + prompt_text

    skills_parts = []
    if profile_file.exists():
        profile_text = profile_file.read_text(encoding="utf-8")
        skills_block = _extract_md_section(profile_text, "Skills")
        if skills_block:
            skills_parts.append(skills_block)
    if skills_file.exists():
        skills_parts.append(skills_file.read_text(encoding="utf-8").strip())

    if skills_parts:
        skills_content = "\n\n".join(skills_parts)
        skills_section = "## Your skills\n\n" + skills_content
        pattern = r"(##\s+Your skills\s*\n)(.*?)(?=\n##\s|\Z)"
        if re.search(pattern, prompt_text, re.DOTALL):
            prompt_text = re.sub(pattern, r"\1\n" + skills_content + "\n\n", prompt_text, flags=re.DOTALL)
        else:
            prompt_text = prompt_text.rstrip() + "\n\n" + skills_section + "\n"

    # Explicitly attached skills from Tayfa/skills/
    if use_skills:
        injected = []
        for skill_id in use_skills:
            content = load_skill_content(skill_id.strip())
            if content:
                injected.append(f"<!-- Skill: {skill_id} -->\n{content}")
        if injected:
            prompt_text = prompt_text.rstrip() + "\n\n## Active skills (Cursor Agent Skills)\n\n" + "\n\n---\n\n".join(injected) + "\n"

    result = prompt_text.strip()
    logger.info(f"[compose_system_prompt] {agent_name}: composed total {len(result)} chars")
    return result


# ── API Endpoints ────────────────────────────────────────────────────────────

@app.get("/", response_class=HTMLResponse)
async def root():
    """Serve the main page."""
    index_path = Path(__file__).parent / "static" / "index.html"
    return HTMLResponse(index_path.read_text(encoding="utf-8"))


@app.post("/api/ping")
async def ping():
    """Ping from client. Resets auto-shutdown timer."""
    global last_ping_time
    current_time = _time.time()
    elapsed_since_last = current_time - last_ping_time
    last_ping_time = current_time
    # Log each ping with timestamp (only if > 10 sec since last one)
    if elapsed_since_last > 10:
        print(f"  [PING] Received ping from client ({elapsed_since_last:.0f} sec since last)")
    return {"status": "ok", "server_time": current_time}


@app.post("/api/shutdown")
async def shutdown():
    """Shut down the server."""
    print("\n  Shutdown request received...")
    stop_claude_api()
    # Shut down server after a short delay (so the response can be sent)
    asyncio.get_event_loop().call_later(0.5, lambda: os._exit(0))
    return {"status": "shutting_down"}


@app.get("/api/status")
async def get_status():
    """System status."""
    global api_running
    claude_api_running = claude_api_process is not None and claude_api_process.poll() is None
    project = get_current_project()
    return {
        "claude_api_running": claude_api_running,
        "api_running": api_running,
        "claude_api_pid": claude_api_process.pid if claude_api_running else None,
        "tayfa_root": str(TAYFA_ROOT_WIN),
        "api_url": CLAUDE_API_URL,
        "orchestrator_port": ACTUAL_ORCHESTRATOR_PORT,
        "claude_api_port": ACTUAL_CLAUDE_API_PORT,
        "current_project": project,
        "has_project": project is not None,
    }


# ── Settings ─────────────────────────────────────────────────────────────────


@app.get("/api/settings")
async def get_settings():
    """Get all settings."""
    try:
        return load_settings()
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error reading settings: {str(e)}")


@app.post("/api/settings")
async def post_settings(data: dict):
    """Update settings (partial update)."""
    if not data:
        raise HTTPException(status_code=400, detail="Empty request")

    try:
        new_settings, error = update_settings(data)
        if error:
            raise HTTPException(status_code=400, detail=error)
        return {"status": "updated", "settings": new_settings}
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error saving settings: {str(e)}")


# ── Projects ───────────────────────────────────────────────────────────────────


@app.get("/api/projects")
async def api_list_projects():
    """List of all projects and current project. Includes is_new_user flag."""
    return {
        "projects": list_projects(),
        "current": get_current_project(),
        "is_new_user": is_new_user(),
    }


@app.get("/api/current-project")
async def api_current_project():
    """Get current project (includes repoName with fallback)."""
    project = get_current_project()
    if project and "repoName" not in project:
        # Backward compat: derive repoName for old projects
        project["repoName"] = get_project_repo_name(project.get("path"))
    return {"project": project}


@app.post("/api/projects/open")
async def api_open_project(data: dict):
    """
    Open a project: init_project + set_current_project.
    Recreates agents with the new workdir.
    Body: {"path": "C:\\Projects\\App"}
    """
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


@app.post("/api/projects/init")
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


@app.post("/api/projects/add")
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


@app.post("/api/projects/remove")
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


@app.post("/api/projects/repo-name")
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


@app.get("/api/browse-folder")
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

        proc = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=120  # 2 minutes to select a folder
        )

        # Check stdout for None before strip()
        output = (proc.stdout or "").strip()
        stderr = (proc.stderr or "").strip()

        # If there's a PowerShell error
        if proc.returncode != 0 and stderr:
            return {"path": None, "error": f"PowerShell error: {stderr}"}

        if output == "::CANCELLED::" or not output:
            return {"path": None, "cancelled": True}

        return {"path": output}

    except subprocess.TimeoutExpired:
        return {"path": None, "error": "Dialog timed out"}
    except FileNotFoundError:
        return {"path": None, "error": "PowerShell not found"}
    except Exception as e:
        return {"path": None, "error": str(e)}


@app.post("/api/start-server")
async def start_server():
    """Start Claude API server."""
    result = start_claude_api()
    # Wait for the server to start
    if result["status"] == "started":
        for _ in range(30):
            await asyncio.sleep(1)
            try:
                async with httpx.AsyncClient(timeout=2) as client:
                    resp = await client.get(f"{CLAUDE_API_URL}/agents")
                    if resp.status_code == 200:
                        global api_running
                        api_running = True
                        result["api_ready"] = True
                        return result
            except Exception:
                continue
        result["api_ready"] = False
    return result


@app.post("/api/stop-server")
async def stop_server():
    """Stop Claude API server."""
    return stop_claude_api()


def _get_agent_runtimes(agent_name: str) -> list[str]:
    """Returns runtimes for the agent. Default is ['claude', 'cursor']."""
    return ["claude", "cursor"]


def _agents_from_registry() -> dict:
    """List of agents from employees.json (those that have prompt.md)."""
    result = {}
    employees = _get_employees()
    personel_dir = get_personel_dir()
    agent_workdir = get_agent_workdir()

    for emp_name, emp_data in employees.items():
        prompt_file = personel_dir / emp_name / "prompt.md"
        if prompt_file.exists():
            result[emp_name] = {
                "system_prompt_file": f"{TAYFA_DIR_NAME}/{emp_name}/prompt.md",
                "workdir": agent_workdir,
                "runtimes": _get_agent_runtimes(emp_name),
                "role": emp_data.get("role", ""),
                "model": emp_data.get("model", "sonnet"),
            }

    return result


@app.get("/api/agents")
async def list_agents():
    """
    List of agents: from employees.json (those that have prompt.md).
    If Claude API is available — enriches with session_id etc. for agents from API.
    """
    result = _agents_from_registry()
    employees = _get_employees()
    pp = get_project_path_for_scoping()
    try:
        raw = await call_claude_api("GET", "/agents", params={"project_path": pp} if pp else None)
        if isinstance(raw, dict):
            for name, config in raw.items():
                if name not in employees:
                    continue
                cfg = dict(config) if isinstance(config, dict) else {}
                cfg["runtimes"] = _get_agent_runtimes(name)
                cfg["role"] = employees[name].get("role", "")
                cfg["model"] = employees[name].get("model", "sonnet")
                result[name] = cfg
    except HTTPException:
        for name in result:
            result[name]["runtimes"] = _get_agent_runtimes(name)
    except Exception:
        for name in result:
            result[name]["runtimes"] = _get_agent_runtimes(name)
    return result


@app.post("/api/create-agent")
async def create_agent(data: dict):
    """Create an agent (pass JSON without prompt). Supports use_skills — array of skill names from Tayfa/skills/."""
    payload = dict(data)
    use_skills = payload.pop("use_skills", None)
    name = payload.get("name")
    # Always try to compose initial system prompt when we have agent name, so agents get their role/context
    if name:
        composed = compose_system_prompt(name, use_skills=use_skills)
        if composed is not None:
            payload.pop("system_prompt_file", None)
            payload["system_prompt"] = composed
        elif not payload.get("system_prompt") and not payload.get("system_prompt_file"):
            # Fallback: point to .tayfa/<name>/prompt.md so claude_api can read from workdir
            payload["system_prompt_file"] = f"{TAYFA_DIR_NAME}/{name}/prompt.md"
    # Inject project_path for scoping if not already present
    if "project_path" not in payload:
        payload["project_path"] = get_project_path_for_scoping()
    return await call_claude_api("POST", "/run", json_data=payload)


@app.post("/api/send-prompt")
async def send_prompt(data: dict):
    """Send a prompt to an agent (Claude API). Saves history to chat_history.json."""
    agent_name = data.get("name") or data.get("agent")
    prompt_text = data.get("prompt", "")
    task_id = data.get("task_id")

    # Inject project_path for scoping if not already present
    if "project_path" not in data:
        data["project_path"] = get_project_path_for_scoping()

    start_time = _time.time()
    api_result = await call_claude_api("POST", "/run", json_data=data, timeout=get_agent_timeout())
    duration_sec = _time.time() - start_time

    # Save to chat history
    if agent_name and prompt_text:
        save_chat_message(
            agent_name=agent_name,
            prompt=prompt_text,
            result=api_result.get("result", ""),
            runtime="claude",
            cost_usd=api_result.get("cost_usd"),
            duration_sec=duration_sec,
            task_id=task_id,
            success=True,
            extra={"num_turns": api_result.get("num_turns")},
        )

    return api_result


@app.post("/api/send-prompt-cursor")
async def send_prompt_cursor(data: dict):
    """
    Send a prompt to Cursor CLI via WSL. Saves history to chat_history.json.
    Agent chat: from .cursor_chats.json (see GET /api/cursor-chats) or created via create-chat on first send.
    Command in WSL: agent -p --force [--resume <chat_id>] --output-format json "<prompt from file>".
    """
    name = data.get("name") or data.get("agent")
    prompt_text = data.get("prompt") or ""
    task_id = data.get("task_id")

    if not name or not prompt_text:
        raise HTTPException(status_code=400, detail="name and prompt are required")

    use_chat = data.get("use_chat", True)

    start_time = _time.time()
    result = await run_cursor_cli(name, prompt_text, use_chat=use_chat)
    duration_sec = _time.time() - start_time

    # Save to chat history
    save_chat_message(
        agent_name=name,
        prompt=prompt_text,
        result=result.get("result", ""),
        runtime="cursor",
        cost_usd=None,  # Cursor CLI doesn't return cost
        duration_sec=duration_sec,
        task_id=task_id,
        success=result.get("success", False),
        extra={"stderr": result.get("stderr")} if result.get("stderr") else None,
    )

    return result


@app.post("/api/cursor-create-chat")
async def cursor_create_chat(data: dict):
    """
    Create a chat in Cursor CLI for one agent: agent --print --output-format json create-chat.
    Chat_id is saved to .cursor_chats.json and used for sending (--resume).
    """
    name = data.get("name") or data.get("agent")
    if not name:
        raise HTTPException(status_code=400, detail="Agent name is required")
    create_result = await run_cursor_cli_create_chat()
    if not create_result.get("success"):
        return {
            "success": False,
            "agent": name,
            "chat_id": None,
            "error": create_result.get("stderr") or create_result.get("raw"),
        }
    chat_id = create_result["chat_id"]
    chats = _load_cursor_chats()
    chats[name] = chat_id
    _save_cursor_chats(chats)
    return {"success": True, "agent": name, "chat_id": chat_id}


@app.post("/api/cursor-create-chats")
async def cursor_create_chats():
    """
    Create chats in Cursor CLI for all employees from employees.json whose runtimes include cursor.
    For each, create-chat is called and chat_id is saved to .cursor_chats.json.
    """
    chats = _load_cursor_chats()
    employees = _get_employees()
    agents_with_cursor = [
        name for name in employees
        if "cursor" in _get_agent_runtimes(name)
    ]
    results = []
    for agent_name in agents_with_cursor:
        if agent_name in chats and chats[agent_name]:
            results.append({"agent": agent_name, "chat_id": chats[agent_name], "created": False})
            continue
        create_result = await run_cursor_cli_create_chat()
        if create_result.get("success") and create_result.get("chat_id"):
            chat_id = create_result["chat_id"]
            chats[agent_name] = chat_id
            results.append({"agent": agent_name, "chat_id": chat_id, "created": True})
        else:
            results.append({
                "agent": agent_name,
                "chat_id": None,
                "created": False,
                "error": create_result.get("stderr") or create_result.get("raw"),
            })
    _save_cursor_chats(chats)
    return {"results": results, "chats": chats}


@app.get("/api/cursor-chats")
async def list_cursor_chats():
    """List of agent -> chat_id bindings (from .cursor_chats.json)."""
    return {"chats": _load_cursor_chats()}


@app.post("/api/reset-agent")
async def reset_agent(data: dict):
    """Reset agent memory."""
    payload = {"name": data["name"], "reset": True, "project_path": get_project_path_for_scoping()}
    return await call_claude_api("POST", "/run", json_data=payload)


@app.delete("/api/agents/{name}")
async def delete_agent(name: str):
    """Delete agent."""
    pp = get_project_path_for_scoping()
    return await call_claude_api("DELETE", f"/agents/{name}", params={"project_path": pp} if pp else None)


@app.post("/api/kill-agents")
async def kill_all_agents(request: Request = None, stop_server: bool = True):
    """Delete all agents for the current project in Claude API and optionally stop the server.
    Accepts optional body {"project_path": "C:\\Project"} to scope by project (same as Ensure agents)."""
    deleted = []
    errors = []
    pp = get_project_path_for_scoping()
    if request is not None:
        try:
            body = await request.json()
        except Exception:
            body = {}
        if isinstance(body, dict) and body.get("project_path"):
            pp = body["project_path"]
    try:
        agents = await call_claude_api("GET", "/agents", params={"project_path": pp} if pp else None)
    except HTTPException:
        agents = {}
    if isinstance(agents, dict):
        names = list(agents.keys())
    elif isinstance(agents, list):
        names = agents
    else:
        names = []
    for name in names:
        try:
            await call_claude_api("DELETE", f"/agents/{name}", params={"project_path": pp} if pp else None)
            deleted.append(name)
        except Exception as e:
            errors.append({"name": name, "error": str(e)})
    stop_result = None
    if stop_server:
        stop_result = stop_claude_api()
    return {
        "deleted": deleted,
        "errors": errors,
        "stop_server": stop_result,
    }


@app.post("/api/refresh-agent-prompt/{name}")
async def refresh_agent_prompt(name: str, data: dict = Body(default_factory=dict)):
    """Rebuild agent system prompt from prompt.md + profile.md (skills) and optionally use_skills, then update the agent."""
    use_skills = data.get("use_skills")
    composed = compose_system_prompt(name, use_skills=use_skills)
    if composed is None:
        raise HTTPException(
            status_code=404,
            detail=f"No prompt.md in {name}/",
        )
    payload = {
        "name": name,
        "system_prompt": composed,
        "workdir": get_agent_workdir(),
        "project_path": get_project_path_for_scoping(),
    }
    return await call_claude_api("POST", "/run", json_data=payload)


@app.get("/api/tasks")
async def get_tasks_board():
    """Unified task board — contents of Personel/boss/tasks.md. User sees all tasks."""
    if not TASKS_FILE.exists():
        return {"content": "# Tasks\n\nTask board is empty. Boss tracks tasks in this file.", "path": str(TASKS_FILE)}
    try:
        content = TASKS_FILE.read_text(encoding="utf-8")
        return {"content": content, "path": str(TASKS_FILE)}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/api/ensure-agents")
async def ensure_agents(request: Request = None):
    """Check and create agents for all employees from employees.json who have prompt.md."""
    results = []

    # Try to get project_path from request body (CLI passes it)
    project_path_str = None
    if request is not None:
        body = {}
        try:
            body = await request.json()
        except Exception:
            pass
        project_path_str = body.get("project_path") if isinstance(body, dict) else None

    if project_path_str:
        _proj = Path(project_path_str)
        personel_dir = _proj / TAYFA_DIR_NAME
        agent_workdir = str(_proj)
        _source = "project_path"
    else:
        personel_dir = get_personel_dir()
        agent_workdir = get_agent_workdir()
        project_path_str = get_project_path_for_scoping()
        _source = "current_project"

    logger.info(f"[ensure_agents] START personel_dir={personel_dir}, agent_workdir={agent_workdir!r}, project_path={project_path_str!r}, source={_source}")
    # #region agent log
    _debug_log_ensure("ensure_agents START", {"personel_dir": str(personel_dir), "agent_workdir": agent_workdir, "project_path_str": project_path_str, "source": _source}, "Tayfa")
    # #endregion

    # Query params for scoped GET/DELETE requests
    _scope_params = {"project_path": project_path_str} if project_path_str else None

    # Get current list of agents from Claude API (scoped to project)
    try:
        agents = await call_claude_api("GET", "/agents", params=_scope_params)
        logger.info(f"[ensure_agents] Existing agents: {list(agents.keys()) if isinstance(agents, dict) else agents}")
    except Exception as e:
        logger.warning(f"[ensure_agents] Failed to get agents: {e}")
        agents = {}

    # Check employees.json — create agents for employees without a running agent
    # For existing ones — check and fix workdir (protection from /mnt//nt/ etc.)
    employees = _get_employees()
    logger.info(f"[ensure_agents] Employees: {list(employees.keys())}")
    for emp_name in employees:
        if isinstance(agents, dict) and emp_name in agents:
            existing = agents[emp_name]
            if isinstance(existing, dict) and existing.get("workdir") != agent_workdir:
                # Workdir differs — update (fix broken path)
                # Also update model, system_prompt and system_prompt_file
                emp_data = employees.get(emp_name, {})
                model = emp_data.get("model", "sonnet")
                allowed_tools = emp_data.get("allowed_tools", "Read Edit Bash")
                permission_mode = emp_data.get("permission_mode", "bypassPermissions")
                composed = compose_system_prompt(emp_name, personel_dir=personel_dir)
                update_payload = {
                    "name": emp_name,
                    "workdir": agent_workdir,
                    "model": model,
                    "allowed_tools": allowed_tools,
                    "permission_mode": permission_mode,
                    "project_path": project_path_str or "",
                }
                # Always use system_prompt_file so prompt.md edits take effect immediately
                update_payload["system_prompt_file"] = f"{TAYFA_DIR_NAME}/{emp_name}/prompt.md"
                logger.info(f"[ensure_agents] {emp_name}: workdir_fix + system_prompt_file={update_payload['system_prompt_file']!r}")
                try:
                    # #region agent log
                    _debug_log_ensure("ensure_agents workdir_fix payload", {"path": "workdir_fix", "emp_name": emp_name, "payload_keys": list(update_payload.keys()), "has_system_prompt": bool(update_payload.get("system_prompt")), "system_prompt_len": len(update_payload.get("system_prompt") or ""), "workdir": update_payload.get("workdir"), "project_path": update_payload.get("project_path")}, "Tayfa")
                    # #endregion
                    log_upd = {k: (v[:200] + "..." if isinstance(v, str) and len(v) > 200 else v)
                               for k, v in update_payload.items()}
                    logger.info(f"[ensure_agents] {emp_name}: UPDATE payload={log_upd}")
                    await call_claude_api("POST", "/run", json_data=update_payload)
                    results.append({"agent": emp_name, "status": "workdir_fixed",
                                    "old_workdir": existing.get("workdir"), "new_workdir": agent_workdir})
                except Exception as e:
                    logger.error(f"[ensure_agents] {emp_name}: workdir fix FAILED: {e}")
                    results.append({"agent": emp_name, "status": "already_exists", "workdir_mismatch": True})
            else:
                # Check: does the agent have a system_prompt (inline) — if not, rebuild it
                has_inline = bool((existing or {}).get("system_prompt"))
                spf = (existing or {}).get("system_prompt_file") or ""
                expected_spf = f"{TAYFA_DIR_NAME}/{emp_name}/prompt.md"
                logger.info(f"[ensure_agents] {emp_name}: already exists, has_inline_prompt={has_inline}, system_prompt_file={spf!r}")

                # Migrate: if agent uses stale inline prompt or wrong file path,
                # switch to system_prompt_file so prompt.md edits take effect immediately
                if has_inline or spf != expected_spf:
                    try:
                        _fix_payload = {
                            "name": emp_name,
                            "system_prompt_file": expected_spf,
                            "project_path": project_path_str or "",
                        }
                        _debug_log_ensure("ensure_agents prompt_to_file payload", {"path": "prompt_to_file", "emp_name": emp_name, "had_inline": has_inline, "old_spf": spf, "new_spf": expected_spf, "project_path": project_path_str or ""}, "Tayfa")
                        await call_claude_api("POST", "/run", json_data=_fix_payload)
                        logger.info(f"[ensure_agents] {emp_name}: switched to system_prompt_file={expected_spf!r} (had_inline={has_inline}, old_spf={spf!r})")
                        results.append({"agent": emp_name, "status": "prompt_switched_to_file"})
                    except Exception as e:
                        logger.error(f"[ensure_agents] {emp_name}: prompt switch FAILED: {e}")
                        results.append({"agent": emp_name, "status": "already_exists"})
                else:
                    results.append({"agent": emp_name, "status": "already_exists"})
            continue

        # Check for prompt.md existence
        prompt_file = personel_dir / emp_name / "prompt.md"
        logger.info(f"[ensure_agents] {emp_name}: checking prompt.md at {prompt_file}, exists={prompt_file.exists()}")
        if not prompt_file.exists():
            results.append({
                "agent": emp_name,
                "status": "skipped",
                "detail": f"File {emp_name}/prompt.md not found",
            })
            continue

        # Compose system prompt and create agent (use same personel_dir as for this request)
        try:
            composed = compose_system_prompt(emp_name, personel_dir=personel_dir)
            # Model and permissions from employees.json
            emp_data = employees.get(emp_name, {})
            model = emp_data.get("model", "sonnet")
            allowed_tools = emp_data.get("allowed_tools", "Read Edit Bash")
            permission_mode = emp_data.get("permission_mode", "bypassPermissions")
            # Do not pass session_id — new agent starts with a fresh session (e.g. after Kill all agents)
            payload = {
                "name": emp_name,
                "workdir": agent_workdir,
                "allowed_tools": allowed_tools,
                "permission_mode": permission_mode,
                "model": model,
                "project_path": project_path_str or "",
            }
            # Always use system_prompt_file so edits to prompt.md take effect
            # immediately without needing to re-run ensure_agents.
            payload["system_prompt_file"] = f"{TAYFA_DIR_NAME}/{emp_name}/prompt.md"
            logger.info(
                f"[ensure_agents] {emp_name}: CREATE with system_prompt_file="
                f"{payload['system_prompt_file']!r}, workdir={agent_workdir!r}, model={model!r}"
            )

            # #region agent log
            _debug_log_ensure("ensure_agents CREATE payload", {"path": "create", "emp_name": emp_name, "payload_keys": list(payload.keys()), "has_system_prompt": bool(payload.get("system_prompt")), "system_prompt_len": len(payload.get("system_prompt") or ""), "workdir": payload.get("workdir"), "project_path": payload.get("project_path")}, "Tayfa")
            # #endregion
            # Log full payload (system_prompt truncated to 200 chars for readability)
            log_payload = {k: (v[:200] + "..." if isinstance(v, str) and len(v) > 200 else v)
                           for k, v in payload.items()}
            logger.info(f"[ensure_agents] {emp_name}: CREATE payload={log_payload}")
            create_result = await call_claude_api("POST", "/run", json_data=payload)
            logger.info(f"[ensure_agents] {emp_name}: CREATE result={create_result}")
            results.append({
                "agent": emp_name,
                "status": "created",
                "detail": create_result,
            })
        except Exception as e:
            logger.error(f"[ensure_agents] {emp_name}: CREATE FAILED: {e}")
            results.append({
                "agent": emp_name,
                "status": "error",
                "detail": str(e),
            })

    logger.info(f"[ensure_agents] DONE results={results}")
    return {"results": results, "current_agents": list(agents.keys()) if isinstance(agents, dict) else agents}


# ── Employees (employees.json) ──────────────────────────────────────────────


@app.get("/api/employees")
async def api_get_employees():
    """List of all registered employees from employees.json."""
    return {"employees": _get_employees()}


@app.get("/api/employees/{name}")
async def api_get_employee(name: str):
    """Get data for one employee."""
    emp = get_employee(name)
    if not emp:
        raise HTTPException(status_code=404, detail=f"Employee '{name}' not found")
    return {"name": name, **emp}


@app.post("/api/employees")
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
            await ensure_agents()
            logger.info(f"Agent for '{name}' created automatically")
        except Exception as e:
            logger.warning(f"Failed to automatically create agent for '{name}': {e}")

    return result


@app.delete("/api/employees/{name}")
async def api_remove_employee(name: str):
    """Remove employee from registry."""
    result = remove_employee(name)
    if result.get("status") == "error":
        raise HTTPException(status_code=400, detail=result["message"])
    if result.get("status") == "not_found":
        raise HTTPException(status_code=404, detail=f"Employee '{name}' not found")
    return result


# ── Chat history (chat_history) ───────────────────────────────────────────────


@app.get("/api/chat-history/{agent_name}")
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


@app.post("/api/chat-history/{agent_name}/clear")
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


# ── Sprints ──────────────────────────────────────────────────────────────────


@app.get("/api/sprints")
async def api_get_sprints():
    """List all sprints."""
    sprints = get_sprints()
    return {"sprints": sprints, "statuses": SPRINT_STATUSES}


@app.get("/api/sprints/{sprint_id}")
async def api_get_sprint(sprint_id: str):
    """Get sprint by ID."""
    sprint = get_sprint(sprint_id)
    if not sprint:
        raise HTTPException(status_code=404, detail=f"Sprint {sprint_id} not found")
    return sprint


@app.post("/api/sprints")
async def api_create_sprint(data: dict):
    """
    Create sprint. Body: {"title": "...", "description": "...", "created_by": "boss"}.

    Automatically creates git branch sprint/SXXX from main.

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

    # Create sprint
    sprint = create_sprint(
        title=title,
        description=data.get("description", ""),
        created_by=data.get("created_by", "boss"),
        ready_to_execute=bool(data.get("ready_to_execute", False)),
    )

    sprint_id = sprint.get("id")
    if not sprint_id:
        return sprint  # Sprint created but without ID (should not happen)

    # Create git branch for sprint
    branch_result = create_sprint_branch(sprint_id)

    if branch_result["success"]:
        sprint["git_branch"] = branch_result["branch"]
        sprint["git_status"] = branch_result["git_status"]
        if branch_result["git_warning"]:
            sprint["git_warning"] = branch_result["git_warning"]
    else:
        # Branch creation error — rollback sprint
        delete_result = delete_sprint(sprint_id)
        if delete_result.get("error"):
            # Failed to rollback sprint (unlikely)
            raise HTTPException(
                status_code=500,
                detail=f"Failed to create git branch: {branch_result['error']}. "
                       f"Error occurred while rolling back sprint: {delete_result['error']}"
            )
        # Rollback successful — return error without creating sprint
        raise HTTPException(
            status_code=400,
            detail=f"Failed to create git branch: {branch_result['error']}"
        )

    return sprint


@app.put("/api/sprints/{sprint_id}/status")
async def api_update_sprint_status(sprint_id: str, data: dict):
    """Change sprint status. Body: {"status": "completed"}."""
    new_status = data.get("status")
    if not new_status:
        raise HTTPException(status_code=400, detail="status field is required")
    result = update_sprint_status(sprint_id, new_status)
    if "error" in result:
        raise HTTPException(status_code=400, detail=result["error"])
    return result


@app.put("/api/sprints/{sprint_id}")
async def api_update_sprint(sprint_id: str, data: dict):
    """Update sprint fields (title, description, ready_to_execute). Body: partial dict."""
    result = update_sprint(sprint_id, data)
    if "error" in result:
        raise HTTPException(status_code=400, detail=result["error"])
    return result


@app.get("/api/sprints/{sprint_id}/release-ready")
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


@app.get("/api/sprints/{sprint_id}/report")
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


@app.post("/api/sprints/{sprint_id}/report")
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


# ── Auto-commit ────────────────────────────────────────────────────────────────


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
    Performs automatic git commit when moving task to review.

    Returns dict with result:
    - success: bool
    - hash: str (on success)
    - message: str (commit message)
    - files_changed: int (number of changed files)
    - error: str (on error)
    """
    # 1. Check if git is initialized
    from project_manager import get_project_dir
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
    developer = task.get("developer", "")

    commit_message = f"{task_id}: {task_title}"
    if developer:
        commit_message += f"\n\nStatus: in_review\nDeveloper: {developer}"
    else:
        commit_message += f"\n\nStatus: in_review"

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


# ── Tasks (tasks.json) ─────────────────────────────────────────────────────


@app.get("/api/tasks-list")
async def api_get_tasks(status: str | None = None, sprint_id: str | None = None):
    """List of tasks. Optional filter ?status=new&sprint_id=S001."""
    tasks = get_tasks(status=status, sprint_id=sprint_id)
    return {"tasks": tasks, "statuses": TASK_STATUSES}


@app.get("/api/tasks-list/{task_id}")
async def api_get_task(task_id: str):
    """Get one task by ID."""
    task = get_task(task_id)
    if not task:
        raise HTTPException(status_code=404, detail=f"Task {task_id} not found")
    return task


@app.post("/api/tasks-list")
async def api_create_tasks(data: dict):
    """
    Create task or task backlog.
    If data contains "tasks" (list) — creates backlog.
    Otherwise — a single task from fields title, description, customer, developer, tester, sprint_id, depends_on.
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
        customer=data.get("customer", "boss"),
        developer=data.get("developer", ""),
        tester=data.get("tester", ""),
        sprint_id=data.get("sprint_id", ""),
        depends_on=data.get("depends_on"),
    )
    return task


@app.put("/api/tasks-list/{task_id}/status")
async def api_update_task_status(task_id: str, data: dict):
    """
    Change task status. Body: {"status": "in_progress"}.

    Automatic git actions:
    - "in_review": git add -A && git commit "TXXX: Title"
    - "completed" (finalizing): merge into main + tag + push (via task_manager)

    On transition to "in_review" returns git_commit:
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

    # update_task_status now handles release on its own when completing a finalizing task
    result = update_task_status(task_id, new_status)
    if "error" in result:
        raise HTTPException(status_code=400, detail=result["error"])

    # Auto-commit on transition to "in_review"
    if new_status == "in_review":
        task = get_task(task_id)
        if task:
            git_commit_result = _perform_auto_commit(task_id, task)
            result["git_commit"] = git_commit_result

    # Release results are already in result (sprint_released or sprint_release_error)
    # Rename for frontend compatibility
    if "sprint_released" in result:
        result["sprint_finalized"] = result.pop("sprint_released")

    return result


@app.put("/api/tasks-list/{task_id}/result")
async def api_set_task_result(task_id: str, data: dict):
    """Write work result to task. Body: {"result": "text"}."""
    result_text = data.get("result", "")
    result = set_task_result(task_id, result_text)
    if "error" in result:
        raise HTTPException(status_code=400, detail=result["error"])
    return result


@app.get("/api/running-tasks")
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


@app.post("/api/tasks-list/{task_id}/trigger")
async def api_trigger_task(task_id: str, data: dict = Body(default_factory=dict)):
    """
    Trigger the next agent for a task.
    Determines who should work based on current status and sends them a prompt.
    Supports runtime: data.get("runtime", "claude") — "claude" or "cursor".

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
    role_label = {"customer": "requester", "developer": "developer", "tester": "tester"}.get(
        next_info["role"], next_info["role"]
    )
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
    if next_info["role"] == "customer":
        prompt_parts.append(
            "You are the requester. Detail the task requirements. "
            "When done, call:\n"
            f"  python common/task_manager.py result {task['id']} \"<detailed description>\"\n"
            f"  python common/task_manager.py status {task['id']} in_progress"
        )
    elif next_info["role"] == "developer":
        prompt_parts.append(
            "You are the developer. Complete the task according to the description. "
            "When done, call:\n"
            f"  python common/task_manager.py result {task['id']} \"<description of what was done>\"\n"
            f"  python common/task_manager.py status {task['id']} in_review"
        )
    elif next_info["role"] == "tester":
        prompt_parts.append(
            "You are the tester. Review the work result. "
            "If everything is good, call:\n"
            f"  python common/task_manager.py result {task['id']} \"<review result>\"\n"
            f"  python common/task_manager.py status {task['id']} done\n"
            "If there are issues:\n"
            f"  python common/task_manager.py result {task['id']} \"<description of issues>\"\n"
            f"  python common/task_manager.py status {task['id']} in_progress"
        )

    full_prompt = "\n".join(p for p in prompt_parts if p is not None)

    runtime = data.get("runtime", "claude")

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
                    # Claude API
                    api_result = await call_claude_api("POST", "/run", json_data={
                        "name": agent_name,
                        "prompt": full_prompt,
                        "project_path": get_project_path_for_scoping(),
                    }, timeout=get_agent_timeout())
                    duration_sec = _time.time() - start_time

                    # Save to chat history
                    save_chat_message(
                        agent_name=agent_name,
                        prompt=full_prompt,
                        result=api_result.get("result", ""),
                        runtime="claude",
                        cost_usd=api_result.get("cost_usd"),
                        duration_sec=duration_sec,
                        task_id=task_id,
                        success=True,
                        extra={"role": role_label, "num_turns": api_result.get("num_turns")},
                    )

                    return {
                        "task_id": task_id,
                        "agent": agent_name,
                        "role": role_label,
                        "runtime": "claude",
                        "success": True,
                        "result": api_result.get("result", ""),
                        "cost_usd": api_result.get("cost_usd"),
                        "num_turns": api_result.get("num_turns"),
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


# ── Agent Failures API ─────────────────────────────────────────────────────────


@app.get("/api/agent-failures")
async def api_get_agent_failures(task_id: str | None = None, resolved: bool | None = None):
    """
    Get agent failure log entries.

    Query params:
        ?task_id=T001 — filter by task
        ?resolved=false — filter unresolved only
    """
    failures = get_agent_failures(task_id=task_id, resolved=resolved)
    return {"failures": failures, "count": len(failures)}


@app.delete("/api/agent-failures/{failure_id}")
async def api_resolve_agent_failure(failure_id: str):
    """Soft-resolve (mark as resolved) an agent failure entry."""
    entry = resolve_agent_failure(failure_id)
    if not entry:
        raise HTTPException(status_code=404, detail=f"Failure {failure_id} not found")
    return entry


# ── Backlog (backlog.json) ────────────────────────────────────────────────────


@app.get("/api/backlog")
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


@app.get("/api/backlog/{item_id}")
async def api_get_backlog_item(item_id: str):
    """Get one backlog item by ID."""
    item = get_backlog_item(item_id)
    if not item:
        raise HTTPException(status_code=404, detail=f"Backlog item {item_id} not found")
    return item


@app.post("/api/backlog")
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


@app.put("/api/backlog/{item_id}")
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


@app.delete("/api/backlog/{item_id}")
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


@app.post("/api/backlog/{item_id}/toggle")
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


# ── Startup ────────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    import uvicorn

    # Find free port for orchestrator
    port = find_free_port(DEFAULT_ORCHESTRATOR_PORT)
    ACTUAL_ORCHESTRATOR_PORT = port

    logger.info(f"Starting uvicorn on port {port}")
    print(f"\n  Tayfa Orchestrator")
    print(f"  http://localhost:{port}")
    if port != DEFAULT_ORCHESTRATOR_PORT:
        print(f"  (port {DEFAULT_ORCHESTRATOR_PORT} busy, using {port})")
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
