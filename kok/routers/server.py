"""
Server management routes (ping, shutdown, status, health, settings, start/stop, launch-instance) — extracted from app.py.
"""

import asyncio
import os
import subprocess
import sys
import time as _time
from pathlib import Path

import httpx
from fastapi import APIRouter, HTTPException
from fastapi.responses import JSONResponse

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


@router.post("/api/shutdown")
async def shutdown():
    """Shut down the server."""
    print("\n  Shutdown request received...")
    stop_claude_api()
    # Shut down server after a short delay (so the response can be sent)
    asyncio.get_event_loop().call_later(0.5, lambda: os._exit(0))
    return {"status": "shutting_down"}


@router.get("/api/status")
async def get_status():
    """System status."""
    claude_api_running = app_state.claude_api_process is not None and app_state.claude_api_process.poll() is None
    project = get_current_project()
    return {
        "claude_api_running": claude_api_running,
        "api_running": app_state.api_running,
        "claude_api_pid": app_state.claude_api_process.pid if claude_api_running else None,
        "tayfa_root": str(TAYFA_ROOT_WIN),
        "api_url": app_state.CLAUDE_API_URL,
        "orchestrator_port": app_state.ACTUAL_ORCHESTRATOR_PORT,
        "claude_api_port": app_state.ACTUAL_CLAUDE_API_PORT,
        "current_project": project,
        "has_project": project is not None,
        "locked_project": app_state.LOCKED_PROJECT_PATH,
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
