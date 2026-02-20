from fastapi import FastAPI, HTTPException
from fastapi.responses import StreamingResponse
from typing import Optional
from pydantic import BaseModel
import subprocess
import json
import os
import shutil
import tempfile
import logging
from file_lock import locked_read_json, locked_write_json, locked_update_json

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
    return locked_read_json(AGENTS_FILE, default={})

def save_agents(agents: dict):
    locked_write_json(AGENTS_FILE, agents)


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
    File is re-read on every call so edits take effect immediately.
    If the file cannot be read, falls back to inline system_prompt (if any)
    so the agent always receives its role identity."""
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
            inline = agent.get("system_prompt", "")
            if inline:
                logger.warning(
                    f"_resolve_system_prompt: file NOT FOUND: {full!r} — "
                    f"falling back to inline system_prompt ({len(inline)} chars)"
                )
                return inline
            logger.error(f"_resolve_system_prompt: file NOT FOUND and no inline fallback: {full!r}")
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

def _run_claude_stream(prompt: str, workdir: str, allowed_tools: str,
                       system_prompt: Optional[str] = "", session_id: str = "",
                       model: str = "", permission_mode: str = "bypassPermissions",
                       budget_limit: Optional[float] = None,
                       timeout: int = 0):
    """Run claude CLI with streaming output. Yields JSON-line dicts as they arrive.
    No timeout by default — agent runs until completion (budget_limit controls cost)."""
    logger.info(f"_run_claude_stream: workdir={workdir!r}, model={model!r}, session_id={session_id!r}")

    cmd_parts = _get_claude_cmd() + [
        "-p",
        "--verbose",
        "--output-format", "stream-json",
        "--include-partial-messages",
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

    if session_id:
        cmd_parts.extend(["--resume", session_id])

    # System prompt handling (same as _run_claude)
    system_prompt_temp_path: Optional[str] = None
    _SYSTEM_PROMPT_FILE_THRESHOLD = 2000
    if system_prompt:
        if len(system_prompt) > _SYSTEM_PROMPT_FILE_THRESHOLD:
            fd, system_prompt_temp_path = tempfile.mkstemp(suffix=".txt", prefix="claude_system_", text=True)
            try:
                with os.fdopen(fd, "w", encoding="utf-8") as f:
                    f.write(system_prompt)
                with open(system_prompt_temp_path, "r", encoding="utf-8") as f:
                    sp_content = f.read()
                cmd_parts.extend(["--system-prompt", sp_content])
            except Exception:
                if system_prompt_temp_path and os.path.isfile(system_prompt_temp_path):
                    try:
                        os.unlink(system_prompt_temp_path)
                    except Exception:
                        pass
                raise
        else:
            cmd_parts.extend(["--system-prompt", system_prompt])

    try:
        proc = subprocess.Popen(
            cmd_parts,
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            cwd=workdir or None,
            encoding="utf-8",
            errors="replace",
            shell=False,
        )
    except (OSError, FileNotFoundError) as e:
        yield {"type": "error", "error": f"Failed to run Claude CLI: {e}"}
        return
    finally:
        if system_prompt_temp_path and os.path.isfile(system_prompt_temp_path):
            try:
                os.unlink(system_prompt_temp_path)
            except Exception:
                pass

    # Write prompt to stdin and close
    try:
        proc.stdin.write(prompt)
        proc.stdin.close()
    except Exception as e:
        yield {"type": "error", "error": f"Failed to write prompt: {e}"}
        proc.kill()
        return

    try:
        # readline() reads one line at a time without prefetching.
        # for line in proc.stdout would buffer ~8KB before yielding — no real-time streaming.
        while True:
            raw_line = proc.stdout.readline()
            if not raw_line:
                break  # EOF — process finished or pipe closed
            line = raw_line.strip()
            if not line:
                continue
            try:
                event = json.loads(line)
                yield event
            except json.JSONDecodeError:
                # Non-JSON output — yield as raw text
                yield {"type": "raw", "content": line}

        proc.wait()
        stderr_text = proc.stderr.read() if proc.stderr else ""
        logger.info(f"_run_claude_stream: finished, returncode={proc.returncode}, stderr_len={len(stderr_text)}")

        if proc.returncode != 0 and stderr_text:
            yield {"type": "error", "error": stderr_text}
    except Exception as e:
        yield {"type": "error", "error": str(e)}


def _get_session_id(agent: dict, model: str, permission_mode: str = "") -> str:
    """Get session_id for a specific model and permission_mode from nested dict or legacy formats."""
    sid = agent.get("session_id")
    if isinstance(sid, dict):
        model_sessions = sid.get(model)
        if isinstance(model_sessions, dict):
            # New structure: { "opus": { "bypassPermissions": "sid1", ... } }
            return model_sessions.get(permission_mode) or ""
        # Old structure: { "opus": "sid1" } — backward compat
        return model_sessions or ""
    # Legacy string format — return as-is
    return sid or ""


def _save_session(name: str, session_id: Optional[str], project_path: str = "", model: str = "", permission_mode: str = ""):
    """Save session_id for an agent, scoped per model and permission_mode.

    session_id is stored as a nested dict:
      {"opus": {"bypassPermissions": "sid1", "default": "sid2"}, "sonnet": {...}}.
    Backward compat: migrates old string/None and flat per-model formats on first write.
    """
    internal_key = _scoped_name(name, project_path)

    def _updater(agents):
        if internal_key in agents:
            current = agents[internal_key].get("session_id")
            # Migrate legacy string/None → dict
            if not isinstance(current, dict):
                current = {}
            if model:
                if permission_mode:
                    # New nested structure: { model: { permission_mode: sid } }
                    if not isinstance(current.get(model), dict):
                        current[model] = {}
                    current[model][permission_mode] = session_id
                else:
                    # No permission_mode → clear all sessions for this model
                    current[model] = {}
            else:
                # No model specified → clear all sessions
                current = {}
            agents[internal_key]["session_id"] = current
        return agents

    locked_update_json(AGENTS_FILE, _updater, default=dict)

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
        # If model specified, reset only that model's session; otherwise reset all
        _save_session(req.name, None, project_path, model=req.model or "")
        return {"status": "reset", "agent": req.name}

    # --- create / update agent (no prompt) ---
    if not req.prompt:
        _create_update_result = [None]  # mutable container for updater result

        def _create_or_update_agent(agents):
            if internal_key in agents:
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
                if req.system_prompt and req.system_prompt_file:
                    a["system_prompt"] = req.system_prompt
                    a["system_prompt_file"] = req.system_prompt_file
                    a["session_id"] = {}
                    logger.info(f"UPDATE agent={req.name!r}: set BOTH system_prompt ({len(req.system_prompt)} chars) and system_prompt_file={req.system_prompt_file!r}")
                elif req.system_prompt:
                    a["system_prompt"] = req.system_prompt
                    a["system_prompt_file"] = ""
                    a["session_id"] = {}
                    logger.info(f"UPDATE agent={req.name!r}: set inline system_prompt, cleared system_prompt_file")
                elif req.system_prompt_file:
                    a["system_prompt_file"] = req.system_prompt_file
                    a["system_prompt"] = ""
                    a["session_id"] = {}
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
                a["session_id"] = {}
                # #region agent log
                _debug_log_api("UPDATE saved", {"internal_key": internal_key, "stored_prompt_len": len(a["system_prompt"])})
                # #endregion
                _create_update_result[0] = {"status": "updated", "agent": req.name}
            else:
                # create
                # #region agent log
                _debug_log_api("CREATE request", {"internal_key": internal_key, "req_system_prompt_len": len(req.system_prompt or ""), "req_system_prompt_file": req.system_prompt_file or ""})
                # #endregion
                inline_prompt = (req.system_prompt or "").strip()
                has_inline = bool(inline_prompt)
                has_file = bool(req.system_prompt_file)
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
                    logger.info(f"CREATE agent={req.name!r}: BOTH system_prompt and system_prompt_file set — storing both (file preferred at runtime).")
                agents[internal_key] = {
                    "system_prompt":      inline_prompt,
                    "system_prompt_file": req.system_prompt_file or "",
                    "workdir":            req.workdir or "",
                    "allowed_tools":      req.allowed_tools or "Read Edit Bash",
                    "permission_mode":    req.permission_mode or "bypassPermissions",
                    "model":              req.model or "",
                    "budget_limit":       req.budget_limit if req.budget_limit is not None else 10.0,
                    "session_id":         {},
                }
                # #region agent log
                _debug_log_api("CREATE saved", {"internal_key": internal_key, "stored_prompt_len": len(agents[internal_key]["system_prompt"]), "req_prompt_len": len(req.system_prompt or "")})
                # #endregion
                _create_update_result[0] = {"status": "created", "agent": req.name}
            return agents

        locked_update_json(AGENTS_FILE, _create_or_update_agent, default=dict)
        return _create_update_result[0]

    # --- run agent ---
    if not exists:
        raise HTTPException(404, f"Agent '{req.name}' not found. Create it first (send without 'prompt').")

    agent = agents[internal_key]

    # Migrate legacy string session_id → per-model dict.
    # Before S031 sessions were stored as a plain UUID string. With S031 per-model dict was
    # introduced, but existing agents kept the old string. When Claude CLI is called with
    # --resume <old_sid> it IGNORES --system-prompt (session already has its own context),
    # so agents that were never migrated never receive their role prompt.
    # Fix: if session_id is still a plain string, reset it to an empty dict so the next run
    # starts a fresh session and picks up --system-prompt correctly.
    if isinstance(agent.get("session_id"), str):
        logger.info(f"RUN migrate legacy session_id for agent={internal_key!r}: resetting string sid → {{}}")

        def _migrate_session(agents):
            if internal_key in agents and isinstance(agents[internal_key].get("session_id"), str):
                agents[internal_key]["session_id"] = {}
            return agents

        agents = locked_update_json(AGENTS_FILE, _migrate_session, default=dict)
        agent = agents[internal_key]

    system_prompt = _resolve_system_prompt(agent)
    # Transient model override: use req.model if provided (from UI model selector),
    # otherwise fall back to agent's stored model. Does NOT persist to agent config.
    run_model = req.model or agent.get("model", "")

    # Per-model sessions: each model has its own session_id, so no model-change guard needed.
    # Switching models simply resumes that model's own session (or starts fresh if none).
    run_permission_mode = agent.get("permission_mode", "bypassPermissions")
    model_session_id = _get_session_id(agent, run_model, run_permission_mode)
    # #region agent log
    _debug_log_api("RUN resolve", {"internal_key": internal_key, "agent_prompt_len": len(agent.get("system_prompt") or ""), "resolved_prompt_len": len(system_prompt), "project_path": project_path, "run_model": run_model, "model_session_id": model_session_id[:8] if model_session_id else ""})
    # #endregion

    result = _run_claude(
        prompt=req.prompt,
        workdir=agent["workdir"],
        allowed_tools=agent.get("allowed_tools", "Read Edit Bash"),
        system_prompt=system_prompt,
        session_id=model_session_id,
        model=run_model,
        permission_mode=run_permission_mode,
        budget_limit=agent.get("budget_limit", 10.0),
        use_structured_output=req.use_structured_output,
        timeout=req.timeout,
    )

    new_sid = result.get("session_id")
    if new_sid:
        _save_session(req.name, new_sid, project_path, model=run_model, permission_mode=run_permission_mode)
    elif model_session_id and result.get("code") != 0:
        # Session stale — retry without resume (clear only this model's session)
        _save_session(req.name, None, project_path, model=run_model, permission_mode=run_permission_mode)
        result = _run_claude(
            prompt=req.prompt,
            workdir=agent["workdir"],
            allowed_tools=agent.get("allowed_tools", "Read Edit Bash"),
            system_prompt=system_prompt,
            model=run_model,
            permission_mode=run_permission_mode,
            budget_limit=agent.get("budget_limit", 10.0),
            use_structured_output=req.use_structured_output,
            timeout=req.timeout,
        )
        new_sid = result.get("session_id")
        if new_sid:
            _save_session(req.name, new_sid, project_path, model=run_model, permission_mode=run_permission_mode)

    return result

# --- stream run (SSE) ---

@app.post("/run-stream")
def run_stream(req: UnifiedRequest):
    """Run an agent with streaming output via SSE."""
    if not req.name:
        raise HTTPException(400, "Field 'name' is required")
    if not req.prompt:
        raise HTTPException(400, "Field 'prompt' is required for streaming")

    project_path = req.project_path or ""
    internal_key = _scoped_name(req.name, project_path)

    agents = load_agents()
    if internal_key not in agents:
        raise HTTPException(404, f"Agent '{req.name}' not found")

    agent = agents[internal_key]

    # Migrate legacy string session_id → dict
    if isinstance(agent.get("session_id"), str):

        def _migrate_session_stream(agents):
            if internal_key in agents and isinstance(agents[internal_key].get("session_id"), str):
                agents[internal_key]["session_id"] = {}
            return agents

        agents = locked_update_json(AGENTS_FILE, _migrate_session_stream, default=dict)
        agent = agents[internal_key]

    system_prompt = _resolve_system_prompt(agent)
    run_model = req.model or agent.get("model", "")
    run_permission_mode = agent.get("permission_mode", "bypassPermissions")
    model_session_id = _get_session_id(agent, run_model, run_permission_mode)

    def event_generator():
        last_session_id = None
        for event in _run_claude_stream(
            prompt=req.prompt,
            workdir=agent["workdir"],
            allowed_tools=agent.get("allowed_tools", "Read Edit Bash"),
            system_prompt=system_prompt,
            session_id=model_session_id,
            model=run_model,
            permission_mode=run_permission_mode,
            budget_limit=agent.get("budget_limit", 10.0),
            timeout=req.timeout,
        ):
            # Track session_id from result events
            if event.get("session_id"):
                last_session_id = event["session_id"]
            yield f"data: {json.dumps(event, ensure_ascii=False)}\n\n"

        # Save session after stream completes
        if last_session_id:
            _save_session(req.name, last_session_id, project_path, model=run_model, permission_mode=run_permission_mode)

    return StreamingResponse(event_generator(), media_type="text/event-stream")

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
    _deleted = [False]

    def _delete_updater(agents):
        if internal_key not in agents:
            return agents  # not found — don't modify
        del agents[internal_key]
        _deleted[0] = True
        return agents

    locked_update_json(AGENTS_FILE, _delete_updater, default=dict)
    if not _deleted[0]:
        raise HTTPException(404, f"Agent '{name}' not found")
    return {"status": "deleted", "agent": name}