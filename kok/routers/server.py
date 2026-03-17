"""
Server management routes (ping, shutdown, status, health, settings, start/stop, launch-instance, CLI tools) — extracted from app.py.
"""

import asyncio
import json
import os
import shutil
import subprocess
import sys
import time as _time
from pathlib import Path

import httpx
from fastapi import APIRouter, HTTPException
from fastapi.responses import JSONResponse, StreamingResponse

import app_state
from app_state import (
    claude_api_process,
    CLAUDE_API_URL,
    ACTUAL_ORCHESTRATOR_PORT,
    ACTUAL_CLAUDE_API_PORT,
    TAYFA_ROOT_WIN,
    KOK_DIR,
    DEFAULT_ORCHESTRATOR_PORT,
    start_claude_api, stop_claude_api,
    get_current_project,
    load_settings, update_settings,
    is_port_in_use,
    list_projects,
    board_subscribe, board_unsubscribe,
    logger,
)
from settings_manager import get_telegram_settings, set_telegram_settings
from telegram_bot import get_bot, start_telegram_bot, stop_telegram_bot

router = APIRouter(tags=["server"])


# ── Ping / Shutdown / Status / Health ──────────────────────────────────────


@router.post("/api/ping")
async def ping():
    """Ping from client. Resets auto-shutdown timer."""
    current_time = _time.time()
    elapsed_since_last = current_time - app_state.last_ping_time
    app_state.last_ping_time = current_time
    # Log each ping with timestamp (only if > 10 sec since last one)
    if elapsed_since_last > 10:
        print(f"  [PING] Received ping from client ({elapsed_since_last:.0f} sec since last)")
    return {"status": "ok", "server_time": current_time}


def _save_all_agent_memories() -> dict:
    """Save memory.md for all agents of the current project.

    Builds a concise session summary (last task, last topic discussed)
    and writes it into .tayfa/{agent}/memory.md.  Does NOT dump raw
    chat history — that's what chat_history.json is for.

    Returns {"agents_updated": [...], "errors": [...]}.
    """
    from datetime import datetime
    from chat_history_manager import _load_history

    result = {"agents_updated": [], "errors": []}
    project = get_current_project()
    if not project:
        result["errors"].append("No current project")
        return result

    project_path = project.get("path", "")
    project_name = project.get("name", "unknown")
    tayfa_dir = Path(project_path) / ".tayfa" if project_path else None
    if not tayfa_dir or not tayfa_dir.exists():
        result["errors"].append(f".tayfa not found at {project_path}")
        return result

    now_str = datetime.now().strftime("%Y-%m-%d %H:%M")

    # Find all agents — subfolders of .tayfa that have chat_history.json
    for agent_dir in tayfa_dir.iterdir():
        if not agent_dir.is_dir() or agent_dir.name == "common":
            continue
        agent_name = agent_dir.name
        history_file = agent_dir / "chat_history.json"
        if not history_file.exists():
            continue

        try:
            history = _load_history(agent_name)
            if not history:
                continue

            memory_path = agent_dir / "memory.md"

            # Read existing memory (preserve sprint blocks and preamble)
            existing = ""
            if memory_path.exists():
                existing = memory_path.read_text(encoding="utf-8")

            # --- Build session summary from last few messages ---
            recent = history[-3:]  # last 3 messages only
            last_task_id = None
            last_topic = None
            for msg in reversed(recent):
                if not last_task_id and msg.get("task_id"):
                    last_task_id = msg["task_id"]
                prompt = (msg.get("prompt") or "").strip()
                if not last_topic and prompt:
                    # First non-empty prompt = last topic
                    last_topic = prompt[:120]

            session_line = f"- [{now_str}] Session closed."
            if last_task_id:
                session_line += f" Last task: {last_task_id}."
            if last_topic:
                session_line += f" Last topic: {last_topic}"

            # --- Update the Session Log section (keep last 3 entries) ---
            SESSION_HEADER = "## Session Log"
            MAX_SESSIONS = 3

            idx = existing.find(SESSION_HEADER)
            if idx == -1:
                preamble = existing.rstrip()
                session_entries = []
            else:
                preamble = existing[:idx].rstrip()
                session_section = existing[idx + len(SESSION_HEADER):]
                # Entries before next ## section
                next_section = session_section.find("\n## ")
                if next_section != -1:
                    entries_text = session_section[:next_section]
                    after_sessions = session_section[next_section:]
                else:
                    entries_text = session_section
                    after_sessions = ""
                session_entries = [l.strip() for l in entries_text.strip().splitlines() if l.strip().startswith("- [")]
                # Re-attach sprint blocks after session log
                if after_sessions.strip():
                    preamble = preamble + "\n\n" + SESSION_HEADER + "\n" + "\n".join(session_entries)
                    # Actually, let's keep it simple: sessions first, then sprint blocks
                    pass

            session_entries.append(session_line)
            if len(session_entries) > MAX_SESSIONS:
                session_entries = session_entries[-MAX_SESSIONS:]

            # If no preamble yet — create a minimal one
            if not preamble.strip():
                preamble = f"# Agent: {agent_name}\nProject: {project_name}\n"

            # Rebuild: keep everything before Session Log, then add session log
            # Find and preserve sprint blocks (## Recent Work Log and ## Sprint)
            sprint_blocks = ""
            work_log_idx = existing.find("## Recent Work Log")
            if work_log_idx != -1:
                sprint_blocks = "\n\n" + existing[work_log_idx:].rstrip()
                # Remove sprint blocks from preamble if duplicated
                preamble_wl = preamble.find("## Recent Work Log")
                if preamble_wl != -1:
                    preamble = preamble[:preamble_wl].rstrip()

            # Also remove old Session Log from preamble
            preamble_sl = preamble.find("## Session Log")
            if preamble_sl != -1:
                preamble = preamble[:preamble_sl].rstrip()

            new_content = (
                preamble + "\n\n"
                + SESSION_HEADER + "\n"
                + "\n".join(session_entries) + "\n"
                + sprint_blocks + "\n"
            )
            memory_path.write_text(new_content.strip() + "\n", encoding="utf-8")
            result["agents_updated"].append(agent_name)
        except Exception as e:
            result["errors"].append(f"{agent_name}: {e}")

    return result


@router.post("/api/save-memories")
async def save_memories():
    """Save memory.md for all agents based on recent chat history."""
    return _save_all_agent_memories()


@router.post("/api/shutdown")
async def shutdown():
    """Shut down the server. Saves agent memories before exit."""
    print("\n  Shutdown request received...")
    # Save all agent memories before shutting down
    try:
        mem_result = _save_all_agent_memories()
        print(f"  Memory saved: {mem_result.get('agents_updated', [])}")
    except Exception as e:
        print(f"  Memory save error: {e}")
    stop_claude_api()
    # Shut down server after a short delay (so the response can be sent)
    asyncio.get_event_loop().call_later(0.5, lambda: os._exit(0))
    return {"status": "shutting_down"}


@router.get("/api/status")
async def get_status():
    """System status."""
    claude_api_running = app_state.claude_api_process is not None and app_state.claude_api_process.poll() is None
    project = get_current_project()

    # Read Tayfa template version from sync_manifest.json
    tayfa_version = None
    try:
        manifest_path = KOK_DIR / "template_tayfa" / "sync_manifest.json"
        if manifest_path.exists():
            manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
            tayfa_version = manifest.get("template_version")
    except Exception:
        pass

    return {
        "claude_api_running": claude_api_running,
        "api_running": app_state.api_running,
        "claude_api_pid": app_state.claude_api_process.pid if claude_api_running else None,
        "cursor_cli_ready": app_state.cursor_cli_logged_in,
        "claude_cli_ready": app_state.claude_cli_logged_in,
        "tayfa_root": str(TAYFA_ROOT_WIN),
        "api_url": app_state.CLAUDE_API_URL,
        "orchestrator_port": app_state.ACTUAL_ORCHESTRATOR_PORT,
        "claude_api_port": app_state.ACTUAL_CLAUDE_API_PORT,
        "current_project": project,
        "has_project": project is not None,
        "locked_project": app_state.LOCKED_PROJECT_PATH,
        "tayfa_version": tayfa_version,
    }


@router.get("/api/health")
async def get_health():
    """Live health check: verifies Claude API reachability. Always returns HTTP 200."""
    claude_api_ok = False
    try:
        async with httpx.AsyncClient(timeout=3.0) as client:
            resp = await client.get(f"{app_state.CLAUDE_API_URL}/agents")
            claude_api_ok = resp.status_code == 200
    except Exception:
        claude_api_ok = False
    return JSONResponse(
        status_code=200,
        content={
            "ok": claude_api_ok,
            "claude_api": claude_api_ok,
            "orchestrator": "ok",
        },
    )


# ── Settings ─────────────────────────────────────────────────────────────────


@router.get("/api/settings")
async def get_settings():
    """Get all settings."""
    try:
        return load_settings()
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error reading settings: {str(e)}")


@router.post("/api/settings")
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


# ── Start / Stop Claude API ─────────────────────────────────────────────────


@router.post("/api/start-server")
async def start_server():
    """Start Claude API server."""
    result = start_claude_api()
    # Wait for the server to start
    if result["status"] == "started":
        for _ in range(30):
            await asyncio.sleep(1)
            try:
                async with httpx.AsyncClient(timeout=2) as client:
                    resp = await client.get(f"{app_state.CLAUDE_API_URL}/agents")
                    if resp.status_code == 200:
                        app_state.api_running = True
                        result["api_ready"] = True
                        return result
            except Exception:
                continue
        result["api_ready"] = False
    return result


@router.post("/api/stop-server")
async def stop_server():
    """Stop Claude API server."""
    return stop_claude_api()


# ── Launch Instance ──────────────────────────────────────────────────────

# Port range for orchestrator instances
_INSTANCE_PORT_MIN = 8008
_INSTANCE_PORT_MAX = 8017


@router.post("/api/launch-instance")
async def launch_instance(data: dict):
    """
    Launch a new Tayfa Orchestrator instance for a given project.

    Body: {"path": "C:\\Projects\\MyApp"}

    Validates the path, checks for existing instances on ports 8008-8017,
    spawns a subprocess with --project flag, discovers the port, returns URL.
    """
    path = data.get("path")
    if not path:
        raise HTTPException(status_code=400, detail="path is required")

    # Validate that the path exists and is a directory
    project_path = Path(path).resolve()
    if not project_path.exists():
        raise HTTPException(status_code=400, detail=f"Path does not exist: {path}")
    if not project_path.is_dir():
        raise HTTPException(status_code=400, detail=f"Path is not a directory: {path}")

    project_path_str = str(project_path)

    # Check if there is already a running instance for this project
    # by scanning orchestrator ports 8008-8017
    for port in range(_INSTANCE_PORT_MIN, _INSTANCE_PORT_MAX + 1):
        if not is_port_in_use(port):
            continue
        try:
            async with httpx.AsyncClient(timeout=2.0) as client:
                resp = await client.get(f"http://localhost:{port}/api/status")
                if resp.status_code == 200:
                    status = resp.json()
                    existing_locked = status.get("locked_project")
                    if existing_locked and str(Path(existing_locked).resolve()) == project_path_str:
                        # Instance already running for this project
                        return {
                            "status": "already_running",
                            "url": f"http://localhost:{port}",
                            "port": port,
                            "project": project_path_str,
                        }
        except Exception:
            continue

    # Spawn a new subprocess
    app_py = KOK_DIR / "app.py"
    try:
        proc = subprocess.Popen(
            [sys.executable, str(app_py), "--project", project_path_str],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            cwd=str(TAYFA_ROOT_WIN),
            creationflags=getattr(subprocess, "CREATE_NEW_PROCESS_GROUP", 0),
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to spawn instance: {e}")

    # Wait for the new instance to start (poll ports for up to 15 seconds)
    discovered_port = None
    for attempt in range(30):
        await asyncio.sleep(0.5)

        # Check if the process died
        if proc.poll() is not None:
            raise HTTPException(
                status_code=500,
                detail=f"Instance process exited with code {proc.returncode}"
            )

        # Scan ports to find the new instance
        for port in range(_INSTANCE_PORT_MIN, _INSTANCE_PORT_MAX + 1):
            if not is_port_in_use(port):
                continue
            try:
                async with httpx.AsyncClient(timeout=1.0) as client:
                    resp = await client.get(f"http://localhost:{port}/api/status")
                    if resp.status_code == 200:
                        status = resp.json()
                        locked = status.get("locked_project")
                        if locked and str(Path(locked).resolve()) == project_path_str:
                            discovered_port = port
                            break
            except Exception:
                continue

        if discovered_port:
            break

    if not discovered_port:
        # Kill the process if we couldn't discover it
        try:
            proc.terminate()
        except Exception:
            pass
        raise HTTPException(
            status_code=500,
            detail="Instance started but could not discover its port within 15 seconds"
        )

    logger.info(f"[launch-instance] New instance for {project_path_str} on port {discovered_port} (pid={proc.pid})")

    return {
        "status": "launched",
        "url": f"http://localhost:{discovered_port}",
        "port": discovered_port,
        "pid": proc.pid,
        "project": project_path_str,
    }


# ── Board SSE (push-notifications for task/sprint changes) ───────────────────


@router.get("/api/board-events")
async def board_events_sse():
    """SSE endpoint: pushes lightweight events when board data changes.
    Frontend subscribes via EventSource."""

    q = board_subscribe()

    async def event_stream():
        try:
            while True:
                try:
                    event = await asyncio.wait_for(q.get(), timeout=30)
                    yield f"data: {json.dumps(event)}\n\n"
                except asyncio.TimeoutError:
                    yield ": keepalive\n\n"
        except asyncio.CancelledError:
            pass
        finally:
            board_unsubscribe(q)

    return StreamingResponse(event_stream(), media_type="text/event-stream")


# ── Telegram Bot ─────────────────────────────────────────────────────────────


@router.get("/api/telegram-settings")
async def get_telegram_settings_api():
    """Get Telegram bot settings (token is masked)."""
    token, chat_id = get_telegram_settings()
    bot = get_bot()
    return {
        "configured": bool(token and chat_id),
        "botToken": (token[:10] + "..." + token[-5:]) if token and len(token) > 15 else ("***" if token else ""),
        "chatId": chat_id,
        "running": bot is not None,
    }


@router.post("/api/telegram-settings")
async def post_telegram_settings(data: dict):
    """Update Telegram bot settings and restart the bot."""
    token = data.get("botToken", "").strip()
    chat_id = data.get("chatId", "").strip()

    if not token or not chat_id:
        raise HTTPException(status_code=400, detail="Both botToken and chatId are required")

    # Save to secret_settings.json
    set_telegram_settings(token, chat_id)

    # Restart bot with new settings
    await stop_telegram_bot()

    # Create answer callback (sends answer as prompt to agent via local HTTP)
    # Must fully consume streaming response so sse_generator runs to completion
    async def _answer_cb(agent_name: str, answer_text: str):
        try:
            port = app_state.ACTUAL_ORCHESTRATOR_PORT
            async with httpx.AsyncClient(timeout=httpx.Timeout(None, connect=10.0)) as client:
                async with client.stream(
                    "POST",
                    f"http://localhost:{port}/api/send-prompt-stream",
                    json={"name": agent_name, "prompt": answer_text, "runtime": "opus", "_from_telegram": True},
                ) as resp:
                    async for _chunk in resp.aiter_bytes():
                        pass
        except Exception as e:
            import logging
            logging.getLogger("tayfa").error(f"[Telegram] answer callback error: {e}")

    bot = await start_telegram_bot(token, chat_id, _answer_cb)

    # Send a test message
    if bot:
        await bot.send_notification("✅ Tayfa Telegram bot connected!")

    return {
        "status": "updated",
        "configured": True,
        "running": bot is not None,
    }


@router.post("/api/telegram-test")
async def telegram_test():
    """Send a test message to Telegram."""
    bot = get_bot()
    if not bot:
        raise HTTPException(status_code=400, detail="Telegram bot is not configured or not running")

    success = await bot.send_notification("🧪 Test message from Tayfa!")
    if success:
        return {"status": "sent"}
    else:
        raise HTTPException(status_code=500, detail="Failed to send test message")


@router.post("/api/telegram-disconnect")
async def telegram_disconnect():
    """Stop and disconnect the Telegram bot."""
    await stop_telegram_bot()
    set_telegram_settings("", "")
    return {"status": "disconnected"}


# ── CLI Tools (Claude & Cursor) ──────────────────────────────────────────────


def _find_claude_exe() -> str | None:
    """Find claude CLI executable on the system."""
    found = shutil.which("claude")
    if found:
        return found
    if os.name == "nt":
        localappdata = os.environ.get("LOCALAPPDATA", "")
        userprofile = os.environ.get("USERPROFILE", "")
        candidates = [
            os.path.join(userprofile, ".claude", "local", "claude.exe"),
            os.path.join(localappdata, "Microsoft", "WindowsApps", "claude.exe"),
            os.path.join(localappdata, "Programs", "claude", "claude.exe"),
            os.path.join(os.environ.get("APPDATA", ""), "npm", "claude.cmd"),
        ]
        for p in candidates:
            if p and os.path.isfile(p):
                return p
    return None


def _find_cursor_agent_exe() -> str | None:
    """Find cursor-agent CLI executable on the system."""
    localappdata = os.environ.get("LOCALAPPDATA", "")
    if localappdata:
        for name in ("agent.cmd", "cursor-agent.cmd"):
            p = os.path.join(localappdata, "cursor-agent", name)
            if os.path.isfile(p):
                return p
    return shutil.which("agent") or shutil.which("cursor-agent")


async def _run_cli(cmd: list[str], timeout: float = 15) -> dict:
    """Run a CLI command and return stdout/stderr/returncode.
    Kills the subprocess on timeout to prevent zombie processes on Windows."""
    proc = None
    try:
        proc = await asyncio.create_subprocess_exec(
            *cmd,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        stdout, stderr = await asyncio.wait_for(proc.communicate(), timeout=timeout)
        return {
            "returncode": proc.returncode,
            "stdout": (stdout or b"").decode("utf-8", errors="replace").strip(),
            "stderr": (stderr or b"").decode("utf-8", errors="replace").strip(),
        }
    except asyncio.TimeoutError:
        if proc:
            try:
                proc.kill()
                await proc.wait()
            except Exception:
                pass
        return {"returncode": -1, "stdout": "", "stderr": f"Timeout ({timeout}s)"}
    except Exception as e:
        if proc and proc.returncode is None:
            try:
                proc.kill()
                await proc.wait()
            except Exception:
                pass
        return {"returncode": -1, "stdout": "", "stderr": str(e)}


def _parse_claude_auth_status(output: str) -> dict:
    """Parse JSON output of 'claude auth status'."""
    info: dict = {"logged_in": False, "account": ""}
    try:
        obj = json.loads(output)
        info["logged_in"] = obj.get("loggedIn", False)
        info["account"] = obj.get("email", "")
    except (json.JSONDecodeError, TypeError):
        lower = output.lower()
        if "not logged in" in lower:
            return info
        if "@" in output:
            info["logged_in"] = True
            for line in output.splitlines():
                for p in line.split():
                    if "@" in p and "." in p:
                        info["account"] = p.strip("(),\"")
                        break
    return info


_ANSI_RE = __import__("re").compile(r'\x1b\[[0-9;]*[A-Za-z]')


def _parse_cursor_about(output: str) -> dict:
    """Parse text output of 'agent about' — extracts email and version."""
    info: dict = {"logged_in": False, "account": "", "version": ""}
    for line in output.splitlines():
        clean = _ANSI_RE.sub('', line).strip()
        low = clean.lower()
        if low.startswith("user email"):
            parts = clean.split(None, 2)
            email = parts[2].strip() if len(parts) > 2 else ""
            if email and email.lower() != "not logged in":
                info["logged_in"] = True
                info["account"] = email
        elif low.startswith("cli version"):
            parts = clean.split(None, 2)
            info["version"] = parts[2].strip() if len(parts) > 2 else ""
    return info


def _parse_cursor_models(output: str) -> list[dict]:
    """Parse text output of 'agent models' into a list of {id, name, current, default}."""
    models = []
    for line in output.splitlines():
        clean = _ANSI_RE.sub('', line).strip()
        if not clean or clean.startswith("Available") or clean.startswith("Tip:"):
            continue
        parts = clean.split(" - ", 1)
        if len(parts) != 2:
            continue
        model_id = parts[0].strip()
        rest = parts[1].strip()
        current = "(current)" in rest
        default = "(default)" in rest
        name = rest.replace("(current)", "").replace("(default)", "").strip()
        models.append({"id": model_id, "name": name, "current": current, "default": default})
    return models


_CLI_STATUS_TIMEOUT = 15  # timeout for CLI status checks (agent models/about can be slow)


async def _check_claude_login(exe: str) -> dict:
    """Check Claude login status + version (runs with tight timeout)."""
    r_status = _run_cli([exe, "auth", "status"], timeout=_CLI_STATUS_TIMEOUT)
    r_version = _run_cli([exe, "--version"], timeout=_CLI_STATUS_TIMEOUT)
    status_result, version_result = await asyncio.gather(r_status, r_version, return_exceptions=True)

    info: dict = {"logged_in": False, "account": "", "version": ""}
    if not isinstance(status_result, Exception):
        combined = (status_result["stdout"] + "\n" + status_result["stderr"]).strip()
        info.update(_parse_claude_auth_status(combined))
    if not isinstance(version_result, Exception) and version_result["returncode"] == 0:
        info["version"] = version_result["stdout"].strip()
    return info


async def _check_cursor_login(exe: str) -> dict:
    """Check Cursor login status + version + models (runs with tight timeout)."""
    r_about = _run_cli([exe, "about"], timeout=_CLI_STATUS_TIMEOUT)
    r_models = _run_cli([exe, "models"], timeout=_CLI_STATUS_TIMEOUT)
    about_result, models_result = await asyncio.gather(r_about, r_models, return_exceptions=True)

    info: dict = {"logged_in": False, "account": "", "version": "", "models": []}
    if not isinstance(about_result, Exception):
        combined = (about_result["stdout"] + "\n" + about_result["stderr"]).strip()
        info.update(_parse_cursor_about(combined))
    if not isinstance(models_result, Exception):
        combined = (models_result["stdout"] + "\n" + models_result["stderr"]).strip()
        info["models"] = _parse_cursor_models(combined)
    return info


@router.get("/api/cli-tools/status")
async def cli_tools_status():
    """Check installation and login status for Claude CLI and Cursor Agent CLI.
    Runs both checks in parallel with a short timeout."""
    claude_exe = _find_claude_exe()
    cursor_exe = _find_cursor_agent_exe()

    result = {
        "claude": {
            "installed": bool(claude_exe),
            "path": claude_exe or "",
            "logged_in": False,
            "account": "",
            "version": "",
            "dashboard_url": "https://console.anthropic.com/settings/billing",
        },
        "cursor": {
            "installed": bool(cursor_exe),
            "path": cursor_exe or "",
            "logged_in": False,
            "account": "",
            "version": "",
            "models": [],
            "dashboard_url": "https://www.cursor.com/settings",
        },
    }

    tasks = []
    if claude_exe:
        tasks.append(("claude", _check_claude_login(claude_exe)))
    if cursor_exe:
        tasks.append(("cursor", _check_cursor_login(cursor_exe)))

    if tasks:
        results = await asyncio.gather(*(t[1] for t in tasks), return_exceptions=True)
        for (tool, _), res in zip(tasks, results):
            if isinstance(res, Exception):
                continue
            for key in ("logged_in", "account", "version", "model", "models"):
                if key in res:
                    result[tool][key] = res[key]

    # Cache login status for fast access in /api/status
    app_state.claude_cli_logged_in = result["claude"]["logged_in"]
    app_state.cursor_cli_logged_in = result["cursor"]["logged_in"]

    return result


@router.post("/api/cli-tools/install")
async def cli_tools_install(data: dict):
    """Install Claude CLI or Cursor Agent CLI.
    Body: { "tool": "claude" | "cursor" }
    """
    tool = data.get("tool", "").lower()
    if tool not in ("claude", "cursor"):
        raise HTTPException(status_code=400, detail="tool must be 'claude' or 'cursor'")

    if tool == "claude":
        if _find_claude_exe():
            return {"status": "already_installed", "tool": "claude"}
        # Install via winget (Windows)
        if os.name == "nt":
            r = await _run_cli(["winget", "install", "Anthropic.ClaudeCode", "--accept-source-agreements", "--accept-package-agreements"], timeout=120)
            if r["returncode"] == 0:
                return {"status": "installed", "tool": "claude", "output": r["stdout"]}
            return {"status": "error", "tool": "claude", "error": r["stderr"] or r["stdout"],
                    "hint": "Try installing manually: winget install Anthropic.ClaudeCode or visit https://claude.ai/download"}
        else:
            r = await _run_cli(["bash", "-c", "curl -fsSL https://claude.ai/install | bash"], timeout=120)
            if r["returncode"] == 0:
                return {"status": "installed", "tool": "claude", "output": r["stdout"]}
            return {"status": "error", "tool": "claude", "error": r["stderr"] or r["stdout"]}

    else:  # cursor
        if _find_cursor_agent_exe():
            return {"status": "already_installed", "tool": "cursor"}
        if os.name == "nt":
            # PowerShell install script
            r = await _run_cli(
                ["powershell", "-NoProfile", "-ExecutionPolicy", "Bypass", "-Command",
                 "irm 'https://cursor.com/install?win32=true' | iex"],
                timeout=120,
            )
            if r["returncode"] == 0:
                return {"status": "installed", "tool": "cursor", "output": r["stdout"]}
            return {"status": "error", "tool": "cursor", "error": r["stderr"] or r["stdout"],
                    "hint": "Try running manually in PowerShell: irm 'https://cursor.com/install?win32=true' | iex"}
        else:
            r = await _run_cli(["bash", "-c", "curl https://cursor.com/install -fsSL | bash"], timeout=120)
            if r["returncode"] == 0:
                return {"status": "installed", "tool": "cursor", "output": r["stdout"]}
            return {"status": "error", "tool": "cursor", "error": r["stderr"] or r["stdout"]}


@router.post("/api/cli-tools/login")
async def cli_tools_login(data: dict):
    """Initiate login for Claude CLI or Cursor Agent CLI.
    Body: { "tool": "claude" | "cursor" }
    Login opens a browser for OAuth — returns the login URL or status.
    """
    tool = data.get("tool", "").lower()
    if tool not in ("claude", "cursor"):
        raise HTTPException(status_code=400, detail="tool must be 'claude' or 'cursor'")

    if tool == "claude":
        exe = _find_claude_exe()
        if not exe:
            raise HTTPException(status_code=400, detail="Claude CLI is not installed. Install it first.")
        r = await _run_cli([exe, "auth", "login"], timeout=30)
        combined = (r["stdout"] + "\n" + r["stderr"]).strip()
        return {"status": "login_initiated" if r["returncode"] == 0 else "error",
                "tool": "claude", "output": combined}

    else:  # cursor
        exe = _find_cursor_agent_exe()
        if not exe:
            raise HTTPException(status_code=400, detail="Cursor Agent CLI is not installed. Install it first.")
        r = await _run_cli([exe, "login"], timeout=30)
        combined = (r["stdout"] + "\n" + r["stderr"]).strip()
        return {"status": "login_initiated" if r["returncode"] == 0 else "error",
                "tool": "cursor", "output": combined}


@router.post("/api/cli-tools/logout")
async def cli_tools_logout(data: dict):
    """Logout from Claude CLI or Cursor Agent CLI.
    Body: { "tool": "claude" | "cursor" }
    """
    tool = data.get("tool", "").lower()
    if tool not in ("claude", "cursor"):
        raise HTTPException(status_code=400, detail="tool must be 'claude' or 'cursor'")

    if tool == "claude":
        exe = _find_claude_exe()
        if not exe:
            raise HTTPException(status_code=400, detail="Claude CLI is not installed")
        r = await _run_cli([exe, "auth", "logout"], timeout=15)
        combined = (r["stdout"] + "\n" + r["stderr"]).strip()
        return {"status": "logged_out" if r["returncode"] == 0 else "error",
                "tool": "claude", "output": combined}

    else:  # cursor
        exe = _find_cursor_agent_exe()
        if not exe:
            raise HTTPException(status_code=400, detail="Cursor Agent CLI is not installed")
        r = await _run_cli([exe, "logout"], timeout=15)
        combined = (r["stdout"] + "\n" + r["stderr"]).strip()
        return {"status": "logged_out" if r["returncode"] == 0 else "error",
                "tool": "cursor", "output": combined}


# ── Ollama (Local LLM) management ─────────────────────────────────────────


def _find_ollama_exe() -> str | None:
    """Find ollama executable on the system."""
    localappdata = os.environ.get("LOCALAPPDATA", "")
    if localappdata:
        p = os.path.join(localappdata, "Programs", "Ollama", "ollama.exe")
        if os.path.isfile(p):
            return p
    return shutil.which("ollama")


@router.get("/api/cli-tools/ollama-status")
async def ollama_status():
    """Check Ollama installation, running state, and list downloaded models."""
    exe = _find_ollama_exe()
    result = {
        "installed": bool(exe),
        "path": exe or "",
        "running": False,
        "models": [],
        "version": "",
    }
    if not exe:
        return result

    # Get version
    try:
        r = await _run_cli([exe, "--version"], timeout=5)
        if r["returncode"] == 0:
            result["version"] = r["stdout"].strip()
    except Exception:
        pass

    # Check if running and list models via API
    import ollama_provider
    result["running"] = await ollama_provider.check_available()
    if result["running"]:
        models = await ollama_provider.list_models()
        result["models"] = [
            {
                "name": m.get("name", ""),
                "size": m.get("size", 0),
                "modified_at": m.get("modified_at", ""),
            }
            for m in models
        ]
    return result


@router.post("/api/cli-tools/ollama-install")
async def ollama_install():
    """Install Ollama via winget (Windows) or curl (Linux/Mac)."""
    if _find_ollama_exe():
        return {"status": "already_installed"}

    if os.name == "nt":
        r = await _run_cli(
            ["winget", "install", "Ollama.Ollama",
             "--accept-source-agreements", "--accept-package-agreements"],
            timeout=180,
        )
        if r["returncode"] == 0:
            return {"status": "installed", "output": r["stdout"]}
        return {"status": "error", "error": r["stderr"] or r["stdout"],
                "hint": "Try installing manually: winget install Ollama.Ollama or visit https://ollama.com/download"}
    else:
        r = await _run_cli(["bash", "-c", "curl -fsSL https://ollama.com/install.sh | sh"], timeout=180)
        if r["returncode"] == 0:
            return {"status": "installed", "output": r["stdout"]}
        return {"status": "error", "error": r["stderr"] or r["stdout"]}


@router.post("/api/cli-tools/ollama-pull")
async def ollama_pull(data: dict):
    """Download an Ollama model. Body: { "model": "qwen2.5-coder:14b" }"""
    model = data.get("model", "").strip()
    if not model:
        raise HTTPException(400, "model is required")

    exe = _find_ollama_exe()
    if not exe:
        raise HTTPException(400, "Ollama is not installed")

    r = await _run_cli([exe, "pull", model], timeout=600)
    if r["returncode"] == 0:
        return {"status": "pulled", "model": model, "output": r["stdout"]}
    return {"status": "error", "model": model,
            "error": r["stderr"] or r["stdout"]}


@router.post("/api/cli-tools/ollama-delete")
async def ollama_delete(data: dict):
    """Delete an Ollama model. Body: { "model": "qwen2.5-coder:14b" }"""
    model = data.get("model", "").strip()
    if not model:
        raise HTTPException(400, "model is required")

    exe = _find_ollama_exe()
    if not exe:
        raise HTTPException(400, "Ollama is not installed")

    r = await _run_cli([exe, "rm", model], timeout=30)
    if r["returncode"] == 0:
        return {"status": "deleted", "model": model}
    return {"status": "error", "model": model,
            "error": r["stderr"] or r["stdout"]}


@router.post("/api/cli-tools/ollama-start")
async def ollama_start():
    """Start Ollama server if not running."""
    import ollama_provider
    if await ollama_provider.check_available():
        return {"status": "already_running"}

    exe = _find_ollama_exe()
    if not exe:
        raise HTTPException(400, "Ollama is not installed")

    try:
        subprocess.Popen(
            [exe, "serve"],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            creationflags=subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0,
        )
    except Exception as e:
        return {"status": "error", "error": str(e)}

    # Wait up to 10s for it to come up
    for _ in range(20):
        await asyncio.sleep(0.5)
        if await ollama_provider.check_available():
            return {"status": "started"}
    return {"status": "error", "error": "Ollama started but API not responding after 10s"}


# ── Updates ───────────────────────────────────────────────────────────────────


def _find_git_root() -> Path | None:
    """Find the git root directory for Tayfa.
    Searches: TAYFA_ROOT_WIN itself, parent dirs (up to 5 levels),
    and sibling dirs with 'tayfa' in the name (e.g. ../Tayfa alongside ../Tayfa_new)."""
    resolved = TAYFA_ROOT_WIN.resolve()

    # 1. Walk up from TAYFA_ROOT_WIN
    current = resolved
    for _ in range(5):
        if (current / ".git").exists():
            return current
        parent = current.parent
        if parent == current:
            break
        current = parent

    # 2. Check sibling directories (same parent) with "tayfa" in name
    parent_dir = resolved.parent
    if parent_dir.exists():
        for sibling in parent_dir.iterdir():
            if sibling.is_dir() and "tayfa" in sibling.name.lower() and (sibling / ".git").exists():
                return sibling

    return None


def _get_configured_repo_url() -> str | None:
    """Build the expected GitHub remote URL from settings (githubOwner) and
    project config (repoName).  Returns e.g. 'https://github.com/milgrig/tayfa'
    or None when the config is incomplete."""
    from settings_manager import load_public_settings
    from project_manager import get_project_repo_name

    settings = load_public_settings()
    owner = (settings.get("git", {}).get("githubOwner") or "").strip()
    repo = (get_project_repo_name() or "").strip()
    if owner and repo:
        return f"https://github.com/{owner}/{repo}"
    return None


def _find_tayfa_remote(cwd: str) -> str:
    """Find the git remote whose fetch URL matches the configured GitHub repo.
    When a configured URL is available, it is compared against every remote;
    if none matches, a temporary remote 'tayfa-updates' is created so that
    fetch/pull work correctly.  Falls back to 'origin' when config is absent."""
    configured_url = _get_configured_repo_url()

    try:
        proc = subprocess.run(
            ["git", "remote", "-v"],
            cwd=cwd, capture_output=True, text=True, timeout=10, encoding="utf-8",
        )
        if proc.returncode != 0:
            return "origin"

        remotes: list[tuple[str, str]] = []
        for line in proc.stdout.strip().split("\n"):
            parts = line.split()
            if len(parts) >= 2 and "(fetch)" in line:
                remotes.append((parts[0], parts[1].rstrip("/")))

        if configured_url:
            norm = configured_url.lower().removesuffix(".git")
            for name, url in remotes:
                if url.lower().removesuffix(".git") == norm:
                    return name

            # No existing remote matches — create or update 'tayfa-updates'
            remote_exists = any(n == "tayfa-updates" for n, _ in remotes)
            if remote_exists:
                _run_git(["remote", "set-url", "tayfa-updates", configured_url + ".git"], cwd)
            else:
                _run_git(["remote", "add", "tayfa-updates", configured_url + ".git"], cwd)
            return "tayfa-updates"

        # Fallback: look for any remote with "tayfa" in the repo name
        for name, url in remotes:
            repo_name = url.rsplit("/", 1)[-1].removesuffix(".git").lower()
            if repo_name == "tayfa":
                return name

    except Exception:
        pass
    return "origin"


def _run_git(args: list[str], cwd: str) -> dict:
    """Run a git command and return stdout/stderr/returncode."""
    try:
        proc = subprocess.run(
            ["git"] + args,
            cwd=cwd,
            capture_output=True,
            text=True,
            timeout=30,
            encoding="utf-8",
        )
        return {
            "returncode": proc.returncode,
            "stdout": proc.stdout.strip(),
            "stderr": proc.stderr.strip(),
        }
    except Exception as e:
        return {"returncode": -1, "stdout": "", "stderr": str(e)}


@router.get("/api/updates/check")
async def check_for_updates():
    """
    Check if a new Tayfa version is available on GitHub.
    Does git fetch + compares local HEAD vs remote HEAD.
    Returns: current_version, latest_version, has_update, changelog (commit messages).
    """
    git_root = _find_git_root()
    if not git_root:
        raise HTTPException(status_code=400, detail="Git repository not found. Cannot check for updates.")

    cwd = str(git_root)
    remote = _find_tayfa_remote(cwd)

    # Fetch latest from remote
    fetch = _run_git(["fetch", remote, "--quiet"], cwd)
    if fetch["returncode"] != 0:
        raise HTTPException(
            status_code=502,
            detail=f"Failed to fetch from remote '{remote}': {fetch['stderr']}"
        )

    # Get current branch
    branch_result = _run_git(["branch", "--show-current"], cwd)
    branch = branch_result["stdout"] or "main"

    # Get local and remote HEADs
    local_head = _run_git(["rev-parse", "HEAD"], cwd)["stdout"]
    remote_head = _run_git(["rev-parse", f"{remote}/{branch}"], cwd)["stdout"]

    if not local_head or not remote_head:
        raise HTTPException(status_code=500, detail="Could not determine local/remote versions")

    has_update = local_head != remote_head

    # Get commit count and messages between local and remote
    changelog = []
    commits_behind = 0
    if has_update:
        log_result = _run_git(
            ["log", f"HEAD..{remote}/{branch}", "--oneline", "--no-decorate"],
            cwd
        )
        if log_result["stdout"]:
            changelog = log_result["stdout"].split("\n")
            commits_behind = len(changelog)

    # Get current Tayfa version from sync_manifest
    tayfa_version = None
    try:
        manifest_path = KOK_DIR / "template_tayfa" / "sync_manifest.json"
        if manifest_path.exists():
            manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
            tayfa_version = manifest.get("template_version")
    except Exception:
        pass

    return {
        "has_update": has_update,
        "current_commit": local_head[:8],
        "latest_commit": remote_head[:8],
        "commits_behind": commits_behind,
        "changelog": changelog[:20],  # max 20 entries
        "branch": branch,
        "tayfa_version": tayfa_version,
    }


@router.post("/api/updates/install")
async def install_update():
    """
    Install the latest Tayfa update: git pull origin <branch>.
    Returns the pull result and suggests a server restart.
    """
    git_root = _find_git_root()
    if not git_root:
        raise HTTPException(status_code=400, detail="Git repository not found.")

    cwd = str(git_root)
    remote = _find_tayfa_remote(cwd)

    # Get current branch
    branch = _run_git(["branch", "--show-current"], cwd)["stdout"] or "main"

    # Check for uncommitted changes
    status = _run_git(["status", "--porcelain"], cwd)
    if status["stdout"]:
        # Stash changes before pull
        _run_git(["stash", "push", "-m", "tayfa-auto-update"], cwd)

    # Pull
    pull = _run_git(["pull", remote, branch, "--ff-only"], cwd)

    if pull["returncode"] != 0:
        # Try to restore stash if we stashed
        if status["stdout"]:
            _run_git(["stash", "pop"], cwd)
        raise HTTPException(
            status_code=500,
            detail=f"Update failed: {pull['stderr']}. Try updating manually with 'git pull'."
        )

    # Pop stash if we stashed
    stash_restored = False
    if status["stdout"]:
        pop = _run_git(["stash", "pop"], cwd)
        stash_restored = pop["returncode"] == 0

    # Read new version after update
    new_version = None
    try:
        manifest_path = KOK_DIR / "template_tayfa" / "sync_manifest.json"
        if manifest_path.exists():
            manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
            new_version = manifest.get("template_version")
    except Exception:
        pass

    return {
        "status": "updated",
        "pull_output": pull["stdout"],
        "new_version": new_version,
        "stash_restored": stash_restored,
        "restart_required": True,
        "message": "Update installed! Restart the server to apply changes.",
    }
