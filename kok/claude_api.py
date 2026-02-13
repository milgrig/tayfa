from fastapi import FastAPI, HTTPException
from typing import Optional
from pydantic import BaseModel
import subprocess
import json
import os
import shlex
import threading

app = FastAPI(title="Claude Code API")

AGENTS_FILE = os.path.expanduser("~/claude_agents.json")
_lock = threading.Lock()

# --------------- models ---------------

class UnifiedRequest(BaseModel):
    """Single request model for all operations.
    - name only                          → get agent info
    - name + config fields (no prompt)   → create / update agent
    - name + prompt                      → run agent
    - name + reset=True                  → reset conversation
    - prompt only (no name)              → legacy single-shot
    """
    name: Optional[str] = ""
    prompt: Optional[str] = ""
    system_prompt: Optional[str] = ""
    system_prompt_file: Optional[str] = ""
    workdir: Optional[str] = ""
    allowed_tools: Optional[str] = ""
    model: Optional[str] = ""  # opus, sonnet, haiku
    timeout: int = 300
    reset: bool = False

# --------------- helpers ---------------

def load_agents() -> dict:
    if os.path.exists(AGENTS_FILE):
        with open(AGENTS_FILE) as f:
            return json.load(f)
    return {}

def save_agents(agents: dict):
    with open(AGENTS_FILE, "w") as f:
        json.dump(agents, f, indent=2, ensure_ascii=False)

def _resolve_system_prompt(agent: dict) -> str:
    """Read system prompt from file if system_prompt_file is set,
    otherwise return inline system_prompt.
    File is re-read on every call so edits take effect immediately."""
    spf = agent.get("system_prompt_file", "")
    if spf:
        workdir = agent.get("workdir", "")
        if spf.startswith("/"):
            full = spf
        else:
            full = os.path.join(workdir, spf)
        try:
            with open(full, encoding="utf-8") as f:
                return f.read().strip()
        except FileNotFoundError:
            raise HTTPException(500, f"system_prompt_file not found: {full}")
    return agent.get("system_prompt", "")

def _run_claude(prompt: str, workdir: str, allowed_tools: str,
                system_prompt: Optional[str] = "", session_id: str = "",
                model: str = "", timeout: int = 300) -> dict:
    """Run claude CLI and return parsed result."""
    parts = [
        "claude", "-p",
        "--output-format", "json",
        "--permission-mode", "acceptEdits",
        "--allowedTools", shlex.quote(allowed_tools),
    ]

    if model:
        parts.extend(["--model", model])

    if session_id:
        parts.extend(["--resume", shlex.quote(session_id)])
    if system_prompt and not session_id:
        parts.extend(["--system-prompt", shlex.quote(system_prompt)])

    cmd = "cd {} && {}".format(shlex.quote(workdir), " ".join(parts))

    try:
        proc = subprocess.run(
            ["bash", "-lc", cmd],
            input=prompt, text=True,
            capture_output=True, timeout=timeout,
        )
    except subprocess.TimeoutExpired:
        return {"code": -1, "result": "", "error": "timeout", "session_id": ""}

    try:
        data = json.loads(proc.stdout)
        return {
            "code":       proc.returncode,
            "result":     data.get("result", ""),
            "session_id": data.get("session_id", ""),
            "cost_usd":   data.get("cost_usd", 0),
            "is_error":   data.get("is_error", False),
            "num_turns":  data.get("num_turns", 0),
        }
    except json.JSONDecodeError:
        return {
            "code":       proc.returncode,
            "result":     proc.stdout,
            "session_id": "",
            "error":      proc.stderr,
        }

def _save_session(name: str, session_id: str):
    """Save session_id for an agent."""
    with _lock:
        agents = load_agents()
        if name in agents:
            agents[name]["session_id"] = session_id
            save_agents(agents)

# --------------- single endpoint ---------------

@app.post("/run")
def run(req: UnifiedRequest):

    # --- legacy: no name, just prompt → old behavior ---
    if not req.name and req.prompt:
        p = subprocess.run(
            ["bash", "-lc", "~/claude_run.sh"],
            input=req.prompt, text=True, capture_output=True,
        )
        return {"code": p.returncode, "stdout": p.stdout, "stderr": p.stderr}

    if not req.name:
        raise HTTPException(400, "Field 'name' is required")

    agents = load_agents()
    exists = req.name in agents

    # --- reset conversation ---
    if req.reset:
        if not exists:
            raise HTTPException(404, f"Agent '{req.name}' not found")
        _save_session(req.name, None)
        return {"status": "reset", "agent": req.name}

    # --- create / update agent (no prompt) ---
    if not req.prompt:
        with _lock:
            agents = load_agents()
            if exists:
                # update
                a = agents[req.name]
                if req.system_prompt:
                    a["system_prompt"] = req.system_prompt
                    a["session_id"] = None
                if req.system_prompt_file:
                    a["system_prompt_file"] = req.system_prompt_file
                    a["session_id"] = None
                if req.workdir:
                    a["workdir"] = req.workdir
                if req.allowed_tools:
                    a["allowed_tools"] = req.allowed_tools
                if req.model is not None:
                    a["model"] = req.model
                save_agents(agents)
                return {"status": "updated", "agent": req.name}
            else:
                # create
                agents[req.name] = {
                    "system_prompt":      req.system_prompt,
                    "system_prompt_file": req.system_prompt_file,
                    "workdir":            req.workdir or "/mnt/c/Cursor/Tayfa",
                    "allowed_tools":      req.allowed_tools or "Read Edit Bash",
                    "model":              req.model or "",
                    "session_id":         None,
                }
                save_agents(agents)
                return {"status": "created", "agent": req.name}

    # --- run agent ---
    if not exists:
        raise HTTPException(404, f"Agent '{req.name}' not found. Create it first (send without 'prompt').")

    agent = agents[req.name]
    system_prompt = _resolve_system_prompt(agent)

    result = _run_claude(
        prompt=req.prompt,
        workdir=agent["workdir"],
        allowed_tools=agent.get("allowed_tools", "Read Edit Bash"),
        system_prompt=system_prompt,
        session_id=agent.get("session_id") or "",
        model=agent.get("model", ""),
        timeout=req.timeout,
    )

    new_sid = result.get("session_id")
    if new_sid:
        _save_session(req.name, new_sid)
    elif agent.get("session_id") and result.get("code") != 0:
        # Session stale — retry without resume
        _save_session(req.name, None)
        result = _run_claude(
            prompt=req.prompt,
            workdir=agent["workdir"],
            allowed_tools=agent.get("allowed_tools", "Read Edit Bash"),
            system_prompt=system_prompt,
            model=agent.get("model", ""),
            timeout=req.timeout,
        )
        new_sid = result.get("session_id")
        if new_sid:
            _save_session(req.name, new_sid)

    return result

# --- list agents ---

@app.get("/agents")
def list_agents():
    return load_agents()

# --- delete agent ---

@app.delete("/agents/{name}")
def delete_agent(name: str):
    with _lock:
        agents = load_agents()
        if name not in agents:
            raise HTTPException(404, f"Agent '{name}' not found")
        del agents[name]
        save_agents(agents)
    return {"status": "deleted", "agent": name}
