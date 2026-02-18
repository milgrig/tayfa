from fastapi import FastAPI, HTTPException
from typing import Optional
from pydantic import BaseModel
import subprocess
import json
import os
import shutil
import tempfile
import threading
import logging

_LOG_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "claude_api.log")
logging.basicConfig(
    level=logging.DEBUG,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[
        logging.StreamHandler(),
        logging.FileHandler(_LOG_FILE, encoding="utf-8"),
    ]
)
logger = logging.getLogger("claude_api")

app = FastAPI(title="Claude Code API")

AGENTS_FILE = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "claude_agents.json")
_lock = threading.Lock()

# #region debug log (prompt storage vs run)
def _debug_log_api(message: str, data: dict):
    try:
        log_path = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "debug-6f4251.log")
        payload = {"sessionId": "6f4251", "location": "claude_api.py", "message": message, "data": data}
        with open(log_path, "a", encoding="utf-8") as f:
            f.write(json.dumps(payload, ensure_ascii=False) + "\n")
    except Exception:
        pass
# #endregion

# --------------- resolve claude executable (PATH may differ when run from exe/uvicorn) ---------------

_CLAUDE_EXE: Optional[str] = None


def _resolve_claude_exe() -> Optional[str]:
    """Find 'claude' in PATH or common Windows locations. Cached after first success."""
    global _CLAUDE_EXE
    if _CLAUDE_EXE is not None:
        return _CLAUDE_EXE
    # 1) PATH (current process)
    exe = shutil.which("claude")
    if exe:
        _CLAUDE_EXE = exe
        logger.info(f"claude executable: {exe} (from PATH)")
        return exe
    # 2) Windows: Desktop App alias, winget install, npm install paths
    if os.name == "nt":
        localappdata = os.environ.get("LOCALAPPDATA", "")
        userprofile = os.environ.get("USERPROFILE", "")
        candidates = [
            os.path.join(userprofile, ".claude", "local", "claude.exe"),
            os.path.join(localappdata, "Microsoft", "WindowsApps", "claude.exe"),
            os.path.join(localappdata, "Programs", "claude", "claude.exe"),
            os.path.join(os.environ.get("APPDATA", ""), "npm", "claude.cmd"),
        ]
        for path in candidates:
            if path and os.path.isfile(path):
                _CLAUDE_EXE = path
                logger.info(f"claude executable: {path} (Windows path)")
                return path
        # 3) Fallback: use where.exe which searches the full system PATH
        #    (shutil.which may miss paths when running inside a venv)
        try:
            result = subprocess.run(
                ["where.exe", "claude"],
                capture_output=True, text=True, timeout=5,
            )
            if result.returncode == 0:
                found = result.stdout.strip().splitlines()[0]
                if os.path.isfile(found):
                    _CLAUDE_EXE = found
                    logger.info(f"claude executable: {found} (from where.exe)")
                    return found
        except Exception:
            pass
    _CLAUDE_EXE = ""  # mark as "already looked, not found"
    return None


def _get_claude_cmd() -> list:
    """Return [claude_exe] or ['claude']; use for subprocess. First element must be executable path."""
    exe = _resolve_claude_exe()
    return [exe] if exe else ["claude"]


# --------------- schema for structured handoff ---------------

HANDOFF_SCHEMA = {
    "type": "object",
    "properties": {
        "task_id": {
            "type": "string",
            "description": "Task ID in the format T001, T002, etc."
        },
        "status": {
            "type": "string",
            "enum": ["completed", "in_progress", "blocked", "needs_review"],
            "description": "Task execution status by the agent"
        },
        "summary": {
            "type": "string",
            "description": "Brief summary of the work done (2-3 sentences)"
        },
        "files_changed": {
            "type": "array",
            "items": {"type": "string"},
            "description": "List of changed files with relative paths"
        },
        "tests_passed": {
            "type": "boolean",
            "description": "Whether all tests passed (for developer/tester)"
        },
        "handoff_to": {
            "type": "string",
            "enum": ["developer", "tester", "customer", "done"],
            "description": "Who to hand the task off to next"
        },
        "notes": {
            "type": "string",
            "description": "Additional notes for the next agent"
        }
    },
    "required": ["task_id", "status", "summary", "handoff_to"]
}

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
    permission_mode: Optional[str] = ""  # acceptEdits, bypassPermissions, default, delegate, dontAsk, plan
    model: Optional[str] = ""  # opus, sonnet, haiku
    budget_limit: Optional[float] = None  # max budget in USD per request
    use_structured_output: bool = False  # use HANDOFF_SCHEMA for structured JSON response
    timeout: int = 300
    reset: bool = False
    project_path: Optional[str] = ""  # project path for scoping agents per project

# --------------- project scoping helpers ---------------

def _project_key(project_path: str) -> str:
    """Derive a stable project key from project_path (folder name).
    Returns empty string if project_path is empty/None."""
    if not project_path:
        return ""
    # Normalize: strip trailing slashes, get folder name
    p = project_path.replace("\\", "/").rstrip("/")
    return p.rsplit("/", 1)[-1] if "/" in p else p


def _scoped_name(name: str, project_path: str) -> str:
    """Build internal storage key: '{project_key}:{name}' or just '{name}' if no project."""
    key = _project_key(project_path)
    if key:
        return f"{key}:{name}"
    return name


def _unscoped_name(internal_key: str) -> str:
    """Extract the plain agent name from an internal key like 'ProjectX:developer'."""
    if ":" in internal_key:
        return internal_key.split(":", 1)[1]
    return internal_key


def _agents_for_project(agents: dict, project_path: str) -> dict:
    """Return only agents belonging to a project, with plain names as keys.
    If project_path is empty, returns un-prefixed (legacy) entries only."""
    key = _project_key(project_path)
    result = {}
    if key:
        prefix = key + ":"
        for internal_key, config in agents.items():
            if internal_key.startswith(prefix):
                plain_name = internal_key[len(prefix):]
                result[plain_name] = config
    else:
        # No project — return only entries without ':' (legacy)
        for internal_key, config in agents.items():
            if ":" not in internal_key:
                result[internal_key] = config
    return result


# --------------- helpers ---------------

def load_agents() -> dict:
    if os.path.exists(AGENTS_FILE):
        with open(AGENTS_FILE, encoding='utf-8') as f:
            return json.load(f)
    return {}

def save_agents(agents: dict):
    with open(AGENTS_FILE, "w", encoding='utf-8') as f:
        json.dump(agents, f, indent=2, ensure_ascii=False)


def _read_prompt_from_file(workdir: str, system_prompt_file: str) -> str:
    """Read system prompt from file. workdir + system_prompt_file (relative or absolute). Returns "" on error."""
    if not workdir and not os.path.isabs(system_prompt_file):
        return ""
    full = os.path.normpath(os.path.join(workdir, system_prompt_file)) if not os.path.isabs(system_prompt_file) else system_prompt_file
    try:
        with open(full, encoding="utf-8") as f:
            return f.read().strip()
    except Exception as e:
        logger.error(f"_read_prompt_from_file: failed to read {full!r}: {e}")
        return ""


def _resolve_system_prompt(agent: dict) -> str:
    """Read system prompt from file if system_prompt_file is set,
    otherwise return inline system_prompt.
    File is re-read on every call so edits take effect immediately."""
    spf = agent.get("system_prompt_file", "")
    raw_workdir = agent.get("workdir", "")
    logger.info(f"_resolve_system_prompt: system_prompt_file={spf!r}, workdir={raw_workdir!r}")
    if spf:
        workdir = raw_workdir
        logger.info(f"_resolve_system_prompt: resolved workdir={workdir!r}")
        if os.path.isabs(spf):
            full = spf
        else:
            full = os.path.normpath(os.path.join(workdir, spf))
        logger.info(f"_resolve_system_prompt: full path={full!r}, exists={os.path.exists(full)}")
        try:
            with open(full, encoding="utf-8") as f:
                content = f.read().strip()
            logger.info(f"_resolve_system_prompt: read {len(content)} chars from file")
            return content
        except FileNotFoundError:
            logger.error(f"_resolve_system_prompt: NOT FOUND: {full!r}")
            raise HTTPException(500, f"system_prompt_file not found: {full}")
    inline = agent.get("system_prompt", "")
    logger.info(f"_resolve_system_prompt: using inline system_prompt, len={len(inline)}")
    return inline

def _run_claude(prompt: str, workdir: str, allowed_tools: str,
                system_prompt: Optional[str] = "", session_id: str = "",
                model: str = "", permission_mode: str = "bypassPermissions",
                budget_limit: Optional[float] = None,
                use_structured_output: bool = False, timeout: int = 300) -> dict:
    """Run claude CLI natively on Windows."""
    logger.info(
        f"_run_claude: workdir={workdir!r}, "
        f"model={model!r}, session_id={session_id!r}, "
        f"system_prompt_len={len(system_prompt) if system_prompt else 0}, "
        f"has_system_prompt={bool(system_prompt)}"
    )

    cmd_parts = _get_claude_cmd() + [
        "-p",
        "--output-format", "json",
        "--permission-mode", permission_mode or "bypassPermissions",
        "--allowedTools", allowed_tools,
    ]

    if model:
        cmd_parts.extend(["--model", model])
        fallback_map = {"opus": "sonnet", "sonnet": "haiku"}
        if model in fallback_map:
            cmd_parts.extend(["--fallback-model", fallback_map[model]])

    if budget_limit is not None and budget_limit > 0:
        cmd_parts.extend(["--max-budget-usd", str(budget_limit)])

    if use_structured_output:
        schema_json = json.dumps(HANDOFF_SCHEMA)
        cmd_parts.extend(["--json-schema", schema_json])

    if session_id:
        cmd_parts.extend(["--resume", session_id])
        logger.info(f"_run_claude: resuming session {session_id!r}")

    # Always send system prompt when we have one.
    # Use --system-prompt (replaces default) so agents adopt their role identity.
    # For long prompts (or any with newlines on Windows), use temp file to avoid CLI/argv issues.
    _SYSTEM_PROMPT_FILE_THRESHOLD = 2000  # chars; above this use temp file (was 6000; hr ~3188 was passed inline, could break on Windows)
    system_prompt_temp_path: Optional[str] = None  # set only when using temp file; cleaned in finally
    if system_prompt:
        if len(system_prompt) > _SYSTEM_PROMPT_FILE_THRESHOLD:
            # Write to temp file and pass content via --system-prompt
            # Read it back to pass as argument (avoids Windows cmd line limit)
            fd, system_prompt_temp_path = tempfile.mkstemp(suffix=".txt", prefix="claude_system_", text=True)
            try:
                with os.fdopen(fd, "w", encoding="utf-8") as f:
                    f.write(system_prompt)
                # Read back and pass via --system-prompt; temp file is just a buffer
                with open(system_prompt_temp_path, "r", encoding="utf-8") as f:
                    sp_content = f.read()
                cmd_parts.extend(["--system-prompt", sp_content])
                logger.info(f"_run_claude: --system-prompt via file ({len(system_prompt)} chars)")
            except Exception:
                if system_prompt_temp_path and os.path.isfile(system_prompt_temp_path):
                    try:
                        os.unlink(system_prompt_temp_path)
                    except Exception:
                        pass
                raise
        else:
            cmd_parts.extend(["--system-prompt", system_prompt])
            logger.info(f"_run_claude: --system-prompt ({len(system_prompt)} chars)")

    try:
        proc = subprocess.run(
            cmd_parts,
            input=prompt,
            text=True,
            capture_output=True,
            timeout=timeout,
            cwd=workdir or None,
            encoding="utf-8",
            shell=False,
        )
    except OSError as e:
        return {
            "code": -1,
            "result": "",
            "error": f"Failed to run Claude CLI: {e}",
            "session_id": "",
        }
    except subprocess.TimeoutExpired:
        return {"code": -1, "result": "", "error": "timeout", "session_id": ""}
    except FileNotFoundError:
        return {
            "code": -1,
            "result": "",
            "error": "claude command not found. Install Claude Code (winget install Anthropic.ClaudeCode or https://claude.ai/install) and ensure it is in PATH or in %LOCALAPPDATA%\\Microsoft\\WindowsApps.",
            "session_id": "",
        }
    finally:
        if system_prompt_temp_path and os.path.isfile(system_prompt_temp_path):
            try:
                os.unlink(system_prompt_temp_path)
            except Exception:
                pass

    logger.info(
        f"_run_claude: finished, returncode={proc.returncode}, "
        f"stdout_len={len(proc.stdout)}, stderr_len={len(proc.stderr)}, "
        f"stderr_preview={proc.stderr[:300]!r}"
    )

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
        logger.error(
            f"_run_claude: JSON decode failed, stdout={proc.stdout[:500]!r}, "
            f"stderr={proc.stderr[:500]!r}"
        )
        return {
            "code":       proc.returncode,
            "result":     proc.stdout,
            "session_id": "",
            "error":      proc.stderr,
        }

def _save_session(name: str, session_id: Optional[str], project_path: str = ""):
    """Save session_id for an agent (uses scoped internal key)."""
    internal_key = _scoped_name(name, project_path)
    with _lock:
        agents = load_agents()
        if internal_key in agents:
            agents[internal_key]["session_id"] = session_id
            save_agents(agents)

# --------------- single endpoint ---------------

@app.post("/run")
def run(req: UnifiedRequest):

    # --- legacy: no name, just prompt → run claude directly ---
    if not req.name and req.prompt:
        cmd = _get_claude_cmd() + ["-p"]
        try:
            p = subprocess.run(
                cmd,
                input=req.prompt,
                text=True,
                capture_output=True,
                encoding='utf-8'
            )
            return {"code": p.returncode, "stdout": p.stdout, "stderr": p.stderr}
        except FileNotFoundError:
            raise HTTPException(
                500,
                "claude command not found. Install Claude Code (winget install Anthropic.ClaudeCode or https://claude.ai/install) and ensure it is in PATH."
            )

    if not req.name:
        raise HTTPException(400, "Field 'name' is required")

    # Build internal scoped key: '{project_key}:{name}' or just '{name}'
    project_path = req.project_path or ""
    internal_key = _scoped_name(req.name, project_path)

    agents = load_agents()
    exists = internal_key in agents

    # --- reset conversation ---
    if req.reset:
        if not exists:
            raise HTTPException(404, f"Agent '{req.name}' not found")
        _save_session(req.name, None, project_path)
        return {"status": "reset", "agent": req.name}

    # --- create / update agent (no prompt) ---
    if not req.prompt:
        with _lock:
            agents = load_agents()
            exists = internal_key in agents
            if exists:
                # update
                a = agents[internal_key]
                prompt_preview_upd = (req.system_prompt[:120] + "...") if req.system_prompt and len(req.system_prompt) > 120 else req.system_prompt
                logger.info(
                    f"UPDATE agent={req.name!r} (key={internal_key!r}), "
                    f"system_prompt_len={len(req.system_prompt) if req.system_prompt else 0}, "
                    f"system_prompt_preview={prompt_preview_upd!r}, "
                    f"system_prompt_file={req.system_prompt_file!r}, "
                    f"workdir={req.workdir!r}, model={req.model!r}"
                )
                if req.system_prompt:
                    a["system_prompt"] = req.system_prompt
                    a["system_prompt_file"] = ""  # inline prompt takes priority, clear file ref
                    a["session_id"] = None
                    logger.info(f"UPDATE agent={req.name!r}: set inline system_prompt, cleared system_prompt_file")
                if req.system_prompt_file:
                    a["system_prompt_file"] = req.system_prompt_file
                    a["system_prompt"] = ""  # file prompt takes priority, clear inline
                    a["session_id"] = None
                    logger.info(f"UPDATE agent={req.name!r}: set system_prompt_file={req.system_prompt_file!r}, cleared inline")
                if req.workdir:
                    a["workdir"] = req.workdir
                if req.allowed_tools:
                    a["allowed_tools"] = req.allowed_tools
                if req.permission_mode:
                    a["permission_mode"] = req.permission_mode
                if req.model is not None:
                    a["model"] = req.model
                if req.budget_limit is not None:
                    a["budget_limit"] = req.budget_limit
                # Always clear session on update so next run starts a new session (e.g. after Kill + Ensure)
                a["session_id"] = None
                save_agents(agents)
                # #region agent log
                _debug_log_api("UPDATE saved", {"internal_key": internal_key, "stored_prompt_len": len(a["system_prompt"])})
                # #endregion
                return {"status": "updated", "agent": req.name}
            else:
                # create
                # #region agent log
                _debug_log_api("CREATE request", {"internal_key": internal_key, "req_system_prompt_len": len(req.system_prompt or ""), "req_system_prompt_file": req.system_prompt_file or ""})
                # #endregion
                inline_prompt = (req.system_prompt or "").strip()
                has_inline = bool(inline_prompt)
                has_file = bool(req.system_prompt_file)
                workdir = (req.workdir or "").strip()
                prompt_preview = (inline_prompt[:120] + "...") if inline_prompt and len(inline_prompt) > 120 else (inline_prompt or "")
                logger.info(
                    f"CREATE agent={req.name!r} (key={internal_key!r}), "
                    f"has_inline_prompt={has_inline}, "
                    f"system_prompt_len={len(inline_prompt)}, "
                    f"system_prompt_preview={prompt_preview!r}, "
                    f"system_prompt_file={req.system_prompt_file!r}, "
                    f"workdir={req.workdir!r}, model={req.model!r}, "
                    f"allowed_tools={req.allowed_tools!r}"
                )
                if has_inline and has_file:
                    logger.warning(f"CREATE agent={req.name!r}: BOTH system_prompt and system_prompt_file set! Using inline.")
                # Store inline prompt when we have it (from request or from file); keep system_prompt_file as fallback for run
                agents[internal_key] = {
                    "system_prompt":      inline_prompt if has_inline else "",
                    "system_prompt_file": "" if has_inline else (req.system_prompt_file or ""),
                    "workdir":            req.workdir or "",
                    "allowed_tools":      req.allowed_tools or "Read Edit Bash",
                    "permission_mode":    req.permission_mode or "bypassPermissions",
                    "model":              req.model or "",
                    "budget_limit":       req.budget_limit if req.budget_limit is not None else 10.0,
                    "session_id":         None,
                }
                save_agents(agents)
                # #region agent log
                _debug_log_api("CREATE saved", {"internal_key": internal_key, "stored_prompt_len": len(agents[internal_key]["system_prompt"]), "req_prompt_len": len(req.system_prompt or "")})
                # #endregion
                return {"status": "created", "agent": req.name}

    # --- run agent ---
    if not exists:
        raise HTTPException(404, f"Agent '{req.name}' not found. Create it first (send without 'prompt').")

    agent = agents[internal_key]
    system_prompt = _resolve_system_prompt(agent)
    # #region agent log
    _debug_log_api("RUN resolve", {"internal_key": internal_key, "agent_prompt_len": len(agent.get("system_prompt") or ""), "resolved_prompt_len": len(system_prompt), "project_path": project_path})
    # #endregion

    result = _run_claude(
        prompt=req.prompt,
        workdir=agent["workdir"],
        allowed_tools=agent.get("allowed_tools", "Read Edit Bash"),
        system_prompt=system_prompt,
        session_id=agent.get("session_id") or "",
        model=agent.get("model", ""),
        permission_mode=agent.get("permission_mode", "bypassPermissions"),
        budget_limit=agent.get("budget_limit", 10.0),
        use_structured_output=req.use_structured_output,
        timeout=req.timeout,
    )

    new_sid = result.get("session_id")
    if new_sid:
        _save_session(req.name, new_sid, project_path)
    elif agent.get("session_id") and result.get("code") != 0:
        # Session stale — retry without resume
        _save_session(req.name, None, project_path)
        result = _run_claude(
            prompt=req.prompt,
            workdir=agent["workdir"],
            allowed_tools=agent.get("allowed_tools", "Read Edit Bash"),
            system_prompt=system_prompt,
            model=agent.get("model", ""),
            permission_mode=agent.get("permission_mode", "bypassPermissions"),
            budget_limit=agent.get("budget_limit", 10.0),
            use_structured_output=req.use_structured_output,
            timeout=req.timeout,
        )
        new_sid = result.get("session_id")
        if new_sid:
            _save_session(req.name, new_sid, project_path)

    return result

# --- list agents ---

@app.get("/agents")
def list_agents(project_path: str = ""):
    """List agents. If project_path is provided, returns only agents scoped to that project
    with plain names. Otherwise returns all agents (raw internal keys)."""
    agents = load_agents()
    if project_path:
        return _agents_for_project(agents, project_path)
    return agents

# --- delete agent ---

@app.delete("/agents/{name}")
def delete_agent(name: str, project_path: str = ""):
    """Delete an agent. If project_path is provided, deletes the scoped agent."""
    internal_key = _scoped_name(name, project_path)
    with _lock:
        agents = load_agents()
        if internal_key not in agents:
            raise HTTPException(404, f"Agent '{name}' not found")
        del agents[internal_key]
        save_agents(agents)
    return {"status": "deleted", "agent": name}