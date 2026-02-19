"""
Shared state, constants, and utilities for the Tayfa Orchestrator.

All mutable globals and cross-cutting functions live here so that
routers and app.py can import them without circular dependencies.
"""

import asyncio
import json
import logging
import os
import re
import subprocess
import sys
import time as _time
import webbrowser
from datetime import datetime
from pathlib import Path

import httpx
from fastapi import HTTPException

# ── Logging ───────────────────────────────────────────────────────────────

_APP_DIR = Path(__file__).resolve().parent
_LOG_FILE = _APP_DIR / "tayfa_server.log"

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
# Only add handlers if not already present (prevents duplicate logs on reimport)
if not logger.handlers:
    logger.addHandler(_file_handler)
    logger.addHandler(_stream_handler)
logger.propagate = False

# ── Directory paths ───────────────────────────────────────────────────────

KOK_DIR = Path(__file__).resolve().parent          # TayfaWindows/kok/
TAYFA_ROOT_WIN = KOK_DIR.parent                     # TayfaWindows/
TAYFA_DATA_DIR = TAYFA_ROOT_WIN / ".tayfa"           # TayfaWindows/.tayfa/

# ── sys.path setup for manager imports ────────────────────────────────────

TEMPLATE_COMMON_DIR = KOK_DIR / "template_tayfa" / "common"
if str(TEMPLATE_COMMON_DIR) not in sys.path:
    sys.path.insert(0, str(TEMPLATE_COMMON_DIR))
if str(KOK_DIR) not in sys.path:
    sys.path.insert(0, str(KOK_DIR))

# ── External manager imports ─────────────────────────────────────────────

from employee_manager import (  # noqa: E402
    get_employees as _get_employees,
    get_employee,
    register_employee,
    update_employee,
    remove_employee,
    set_employees_file,
)
from task_manager import (  # noqa: E402
    create_task, create_backlog, update_task_status,
    set_task_result, get_tasks, get_task, get_next_agent,
    create_sprint, get_sprints, get_sprint, update_sprint_status,
    update_sprint, update_sprint_release,
    delete_sprint,
    generate_sprint_report,
    STATUSES as TASK_STATUSES, SPRINT_STATUSES,
    set_tasks_file,
)
from chat_history_manager import (  # noqa: E402
    save_message as save_chat_message,
    get_history as get_chat_history,
    clear_history as clear_chat_history,
    set_tayfa_dir as set_chat_history_tayfa_dir,
)
from backlog_manager import (  # noqa: E402
    get_backlog, get_backlog_item, create_backlog_item,
    update_backlog_item, delete_backlog_item, toggle_next_sprint,
    set_backlog_file,
)
from settings_manager import (  # noqa: E402
    load_settings, update_settings, get_orchestrator_port,
    get_current_version, get_next_version, save_version,
    get_auto_shutdown_settings, migrate_remote_url,
)
from project_manager import (  # noqa: E402
    list_projects, get_project, add_project, remove_project,
    get_current_project, set_current_project, init_project,
    open_project, get_tayfa_dir, has_tayfa, TAYFA_DIR_NAME,
    is_new_user, get_project_repo_name, set_project_repo_name,
)
from git_manager import (  # noqa: E402
    router as git_router,
    run_git_command,
    create_sprint_branch,
    check_git_state,
    commit_task,
    release_sprint,
)

# ── Port configuration ────────────────────────────────────────────────────

DEFAULT_ORCHESTRATOR_PORT = 8008
DEFAULT_CLAUDE_API_PORT = 8788

ACTUAL_ORCHESTRATOR_PORT = DEFAULT_ORCHESTRATOR_PORT
ACTUAL_CLAUDE_API_PORT = DEFAULT_CLAUDE_API_PORT
CLAUDE_API_URL = f"http://localhost:{DEFAULT_CLAUDE_API_PORT}"

# ── Path helpers ──────────────────────────────────────────────────────────

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
    """workdir for agents — project root (Windows path)."""
    project = get_current_project()
    if project:
        return str(Path(project["path"]))
    return str(_FALLBACK_PERSONEL_DIR.parent)


def get_project_path_for_scoping() -> str:
    """Return the current project path string for agent scoping."""
    project = get_current_project()
    if project:
        return str(Path(project["path"]))
    return ""


# ── Configuration ─────────────────────────────────────────────────────────

_DEFAULT_AGENT_TIMEOUT = 600.0
_DEFAULT_MAX_ROLE_TRIGGERS = 2
_DEFAULT_ARTIFACT_MAX_LINES = 300


def _read_config_value(key: str, default, validator=None):
    """Read a value from .tayfa/config.json. Fresh on every call."""
    try:
        config_path = get_personel_dir() / "config.json"
        if not config_path.exists():
            config_path = TAYFA_DATA_DIR / "config.json"
        if config_path.exists():
            data = json.loads(config_path.read_text(encoding="utf-8"))
            val = data.get(key)
            if val is not None and (validator is None or validator(val)):
                return type(default)(val)
    except Exception:
        pass
    return default


def get_agent_timeout() -> float:
    return _read_config_value(
        "agent_timeout_seconds", _DEFAULT_AGENT_TIMEOUT,
        lambda v: isinstance(v, (int, float)) and v > 0,
    )


def get_max_role_triggers() -> int:
    return _read_config_value(
        "max_role_triggers", _DEFAULT_MAX_ROLE_TRIGGERS,
        lambda v: isinstance(v, int) and v > 0,
    )


def get_artifact_max_lines() -> int:
    return _read_config_value(
        "artifact_max_lines", _DEFAULT_ARTIFACT_MAX_LINES,
        lambda v: isinstance(v, int) and v > 0,
    )


# Legacy aliases
PERSONEL_DIR = _FALLBACK_PERSONEL_DIR
TASKS_FILE = PERSONEL_DIR / "boss" / "tasks.md"
SKILLS_DIR = PERSONEL_DIR / "common" / "skills"
COMMON_DIR = PERSONEL_DIR / "common"

# ── Cursor CLI constants ──────────────────────────────────────────────────

CURSOR_CLI_PROMPT_FILE = TAYFA_ROOT_WIN / ".cursor_cli_prompt.txt"
CURSOR_CHATS_FILE = TAYFA_ROOT_WIN / ".cursor_chats.json"
CURSOR_CLI_TIMEOUT = 600.0
CURSOR_CLI_MODEL = "Composer-1.5"
CURSOR_CREATE_CHAT_TIMEOUT = 30.0

# ── Mutable global state ─────────────────────────────────────────────────

claude_api_process: subprocess.Popen | None = None
api_running: bool = False

running_tasks: dict[str, dict] = {}
agent_locks: dict[str, asyncio.Semaphore] = {}
task_trigger_counts: dict[str, dict[str, int]] = {}

# ── Per-agent stream buffers ─────────────────────────────────────────────
# When a task trigger runs with streaming, events are buffered here so that
# the frontend can connect at any time and replay + follow the live stream.
# Structure: { agent_name: { "events": [dict, ...], "done": bool, "subscribers": [asyncio.Queue, ...] } }
agent_stream_buffers: dict[str, dict] = {}

last_ping_time: float = _time.time()
SHUTDOWN_TIMEOUT = 120.0

MAX_FAILURE_LOG_ENTRIES = 1000

_MODEL_RUNTIMES = ["opus", "sonnet", "haiku"]
_CURSOR_MODELS = {"composer"}  # Models that run via Cursor CLI instead of Claude API

# Error types eligible for auto-retry (used by tasks router)
_RETRYABLE_ERRORS = {"timeout", "unavailable"}
_MAX_RETRY_ATTEMPTS = 3
_RETRY_DELAY_SEC = 5


def get_agent_lock(agent_name: str) -> asyncio.Semaphore:
    """Return a Semaphore(1) for the given agent, creating it on first access."""
    if agent_name not in agent_locks:
        agent_locks[agent_name] = asyncio.Semaphore(1)
    return agent_locks[agent_name]


def init_agent_stream(agent_name: str) -> None:
    """Initialize a stream buffer for an agent (called when task trigger starts)."""
    agent_stream_buffers[agent_name] = {
        "events": [],
        "done": False,
        "subscribers": [],
    }


def push_agent_stream_event(agent_name: str, event: dict) -> None:
    """Push a stream event to the agent's buffer and notify all subscribers."""
    buf = agent_stream_buffers.get(agent_name)
    if not buf:
        return
    buf["events"].append(event)
    # Notify all waiting subscribers
    for q in buf["subscribers"]:
        try:
            q.put_nowait(event)
        except Exception:
            pass


def finish_agent_stream(agent_name: str) -> None:
    """Mark the agent's stream as done and notify subscribers with a sentinel."""
    buf = agent_stream_buffers.get(agent_name)
    if not buf:
        return
    buf["done"] = True
    for q in buf["subscribers"]:
        try:
            q.put_nowait(None)  # sentinel: stream finished
        except Exception:
            pass


def subscribe_agent_stream(agent_name: str) -> tuple[list[dict], asyncio.Queue | None]:
    """Subscribe to an agent's stream. Returns (past_events, queue_for_new_events).
    If no stream is active, returns ([], None)."""
    buf = agent_stream_buffers.get(agent_name)
    if not buf:
        return [], None
    past = list(buf["events"])  # snapshot of buffered events
    if buf["done"]:
        return past, None  # stream already finished, no queue needed
    q: asyncio.Queue = asyncio.Queue()
    buf["subscribers"].append(q)
    return past, q


def unsubscribe_agent_stream(agent_name: str, q: asyncio.Queue) -> None:
    """Remove a subscriber queue from the agent's stream buffer."""
    buf = agent_stream_buffers.get(agent_name)
    if buf and q in buf["subscribers"]:
        buf["subscribers"].remove(q)


# ── Port helpers ──────────────────────────────────────────────────────────

def is_port_in_use(port: int) -> bool:
    import socket
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.settimeout(0.1)
        try:
            s.connect(('127.0.0.1', port))
            return True
        except (ConnectionRefusedError, socket.timeout, OSError):
            return False


def find_free_port(start_port: int, max_attempts: int = 10) -> int:
    for offset in range(max_attempts):
        port = start_port + offset
        if not is_port_in_use(port):
            return port
    return start_port + max_attempts


# ── Claude API communication ─────────────────────────────────────────────

async def call_claude_api(method: str, path: str, json_data: dict | None = None,
                          timeout: float = 600.0, params: dict | None = None) -> dict:
    """Sends a request to the Claude API server."""
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


async def stream_claude_api(path: str, json_data: dict):
    """Async generator that proxies SSE from claude_api server. No timeout — agent runs until done."""
    url = f"{CLAUDE_API_URL}{path}"
    try:
        async with httpx.AsyncClient(timeout=httpx.Timeout(None, connect=10.0)) as client:
            async with client.stream("POST", url, json=json_data) as resp:
                if resp.status_code >= 400:
                    body = await resp.aread()
                    try:
                        detail = json.loads(body).get("detail", body.decode())
                    except Exception:
                        detail = body.decode()
                    yield f'{{"type":"error","error":{json.dumps(detail)}}}'
                    return
                async for line in resp.aiter_lines():
                    if line.startswith("data: "):
                        yield line[6:]
                    elif line.strip():
                        yield line
    except httpx.ConnectError:
        yield '{"type":"error","error":"Claude API server is unavailable. Please start it."}'
    except httpx.ReadTimeout:
        yield '{"type":"error","error":"Claude API: timeout waiting for agent response."}'
    except Exception as e:
        yield f'{{"type":"error","error":{json.dumps(str(e))}}}'


# ── Claude API process management ────────────────────────────────────────

def start_claude_api() -> dict:
    """Starts the Claude API server natively on Windows with a dynamic port."""
    global claude_api_process, ACTUAL_CLAUDE_API_PORT, CLAUDE_API_URL

    if claude_api_process and claude_api_process.poll() is None:
        return {"status": "already_running", "pid": claude_api_process.pid, "port": ACTUAL_CLAUDE_API_PORT}

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


# ── Debug logging ─────────────────────────────────────────────────────────

_debug_log_ensure_path = None

def _debug_log_ensure(message: str, data: dict, hypothesis_id: str = ""):
    global _debug_log_ensure_path
    for base in (_APP_DIR.parent, Path.cwd()):
        log_path = base / "debug-6f4251.log"
        try:
            with open(log_path, "a", encoding="utf-8") as f:
                f.write(json.dumps({"sessionId": "6f4251", "hypothesisId": hypothesis_id,
                                    "location": "app.py ensure_agents", "message": message,
                                    "data": data,
                                    "timestamp": int(datetime.now().timestamp() * 1000)},
                                   ensure_ascii=False) + "\n")
            if _debug_log_ensure_path is None:
                _debug_log_ensure_path = str(log_path)
                logger.info(f"[debug] ensure_agents log: {log_path}")
            return
        except Exception:
            continue
