"""
Server management routes (ping, shutdown, status, health, settings, start/stop) — extracted from app.py.
"""

import asyncio
import os
import time as _time

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
    start_claude_api, stop_claude_api,
    get_current_project,
    load_settings, update_settings,
)

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
