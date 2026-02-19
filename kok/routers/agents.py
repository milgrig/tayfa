"""
Agent routes and Cursor CLI helpers — extracted from app.py.
"""

import asyncio
import json
import re
import time as _time
from pathlib import Path

from fastapi import APIRouter, Body, HTTPException, Request
from fastapi.responses import StreamingResponse

from app_state import (
    _get_employees, get_employee, update_employee,
    get_personel_dir, get_agent_workdir, get_project_path_for_scoping,
    get_current_project,
    call_claude_api, stream_claude_api, stop_claude_api,
    save_chat_message,
    get_agent_timeout,
    running_tasks,
    subscribe_agent_stream, unsubscribe_agent_stream,
    _maybe_send_telegram_question,
    TAYFA_DIR_NAME,
    TAYFA_ROOT_WIN, SKILLS_DIR,
    CURSOR_CLI_PROMPT_FILE, CURSOR_CHATS_FILE,
    CURSOR_CLI_TIMEOUT, CURSOR_CLI_MODEL, CURSOR_CREATE_CHAT_TIMEOUT,
    _MODEL_RUNTIMES, _CURSOR_MODELS,
    _debug_log_ensure,
    logger,
)
from telegram_bot import get_bot

router = APIRouter(tags=["agents"])


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


def _cursor_cli_model_flag() -> str:
    """Always uses CURSOR_CLI_MODEL (Composer 1.5). Ignores any request override."""
    safe = CURSOR_CLI_MODEL.replace("'", "'\"'\"'")
    return f" --model '{safe}'"


async def run_cursor_cli(agent_name: str, user_prompt: str, use_chat: bool = True) -> dict:
    """
    Runs Cursor CLI in WSL in headless mode.
    If use_chat=True, ensures a chat exists for the agent (create-chat if needed)
    and sends a message with --resume <chat_id>. Otherwise — a one-time call without --resume.
    Model is always CURSOR_CLI_MODEL (Composer 1.5).
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
    model_part = _cursor_cli_model_flag()
    # Read prompt into variable with " escaping for bash, so quotes in text don't break the command
    wsl_script = (
        f"{base} && "
        "content=$(cat .cursor_cli_prompt.txt | sed 's/\"/\\\\\"/g') && "
        f"agent -p --force{resume_part}{model_part} --output-format json \"$content\""
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


# ── Prompt / skill management ─────────────────────────────────────────────────


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


# ── Agent registry helpers ─────────────────────────────────────────────────


def _get_agent_runtimes(agent_name: str) -> list[str]:
    """Returns runtimes for the agent: model-specific + cursor."""
    return _MODEL_RUNTIMES + ["cursor"]


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
                "default_runtime": emp_data.get("model", "sonnet"),
            }

    return result


def _notify_telegram_answer_from_web(agent_name: str, answer_text: str):
    """When user answers from the Web UI, mark agent as web-sourced and clean up pending."""
    try:
        bot = get_bot()
        if not bot:
            return
        # Mark that this agent's last message is from Web, not Telegram
        bot.mark_from_web(agent_name)
        # Clean up pending questions for this agent
        if bot._pending:
            keys_to_remove = [
                k for k, v in bot._pending.items()
                if v.get("agent") == agent_name
            ]
            for k in keys_to_remove:
                del bot._pending[k]
    except Exception as e:
        logger.warning(f"[Telegram] notify_answer_from_web error: {e}")


def _maybe_forward_reply_to_telegram(agent_name: str, reply_text: str):
    """If last message to this agent was from Telegram, forward the reply back."""
    if not reply_text:
        return
    try:
        bot = get_bot()
        if not bot:
            return
        is_tg = bot.is_from_telegram(agent_name)
        logger.info(f"[Telegram] forward check: agent={agent_name}, is_from_telegram={is_tg}, reply_len={len(reply_text)}")
        if is_tg:
            asyncio.create_task(bot.send_agent_reply(agent_name, reply_text))
    except Exception as e:
        logger.warning(f"[Telegram] forward reply error: {e}")


# ── Agent routes ──────────────────────────────────────────────────────────────


@router.get("/api/agents")
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
                cfg["default_runtime"] = employees[name].get("model", "sonnet")
                result[name] = cfg
    except HTTPException:
        for name in result:
            result[name]["runtimes"] = _get_agent_runtimes(name)
            result[name].setdefault("default_runtime", result[name].get("model", "sonnet"))
    except Exception:
        for name in result:
            result[name]["runtimes"] = _get_agent_runtimes(name)
            result[name].setdefault("default_runtime", result[name].get("model", "sonnet"))
    return result


@router.post("/api/create-agent")
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


@router.post("/api/send-prompt")
async def send_prompt(data: dict):
    """Send a prompt to an agent (Claude API). Saves history to chat_history.json."""
    agent_name = data.get("name") or data.get("agent")
    prompt_text = data.get("prompt", "")
    task_id = data.get("task_id")
    runtime = data.get("runtime", "claude")  # Use runtime from request, fallback to "claude" for backward compat

    # Resolve model from runtime (opus/sonnet/haiku) so claude_api uses correct per-model session
    if runtime in _MODEL_RUNTIMES:
        data["model"] = runtime
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
            runtime=runtime,  # Use resolved runtime instead of hardcoded "claude"
            cost_usd=api_result.get("cost_usd"),
            duration_sec=duration_sec,
            task_id=task_id,
            success=True,
            extra={"num_turns": api_result.get("num_turns")},
        )

    # Forward agent's reply to Telegram if the prompt came from Telegram
    _maybe_forward_reply_to_telegram(agent_name, api_result.get("result", ""))

    return api_result


@router.post("/api/send-prompt-stream")
async def send_prompt_stream(data: dict):
    """Send a prompt to an agent with SSE streaming. Saves history on completion."""
    agent_name = data.get("name") or data.get("agent")
    prompt_text = data.get("prompt", "")
    task_id = data.get("task_id")
    runtime = data.get("runtime", "claude")
    from_telegram = data.get("_from_telegram", False)

    if not agent_name or not prompt_text:
        raise HTTPException(400, "Fields 'name' and 'prompt' are required")

    # Only mark as "from web" if the request is NOT from Telegram callback
    if not from_telegram:
        _notify_telegram_answer_from_web(agent_name, prompt_text)

    # Resolve model from runtime (same as send_prompt)
    if runtime in _MODEL_RUNTIMES:
        data["model"] = runtime
    if "project_path" not in data:
        data["project_path"] = get_project_path_for_scoping()

    start_time = _time.time()

    # Metadata-only event types to suppress (contain model, usage, service_tier)
    _SKIP_TYPES = {"message_start", "message_delta", "message_stop", "system", "keep_alive"}

    async def sse_generator():
        full_result = ""
        cost_usd = 0
        num_turns = 0
        async for chunk in stream_claude_api("/run-stream", json_data=data):
            # Parse chunk and optionally filter before forwarding to browser
            try:
                event = json.loads(chunk)
            except (json.JSONDecodeError, ValueError):
                continue

            etype = event.get("type", "")

            # Unwrap stream_event wrapper (Claude CLI stream-json format)
            # {"type": "stream_event", "event": {"type": "content_block_delta", ...}}
            if etype == "stream_event" and isinstance(event.get("event"), dict):
                event = event["event"]
                etype = event.get("type", "")

            # Skip metadata-only lifecycle events
            if etype in _SKIP_TYPES:
                continue

            # Check for AskUserQuestion — forward to Telegram
            # (handles both streaming and non-streaming event formats)
            _maybe_send_telegram_question(agent_name, event)

            # For 'message' events: strip raw API metadata, keep only
            # fields the frontend needs for rendering.
            if etype == "message":
                content = event.get("content", [])
                # Skip empty messages (no content to show)
                if not content:
                    continue
                filtered = {
                    "type": "message",
                    "id": event.get("id", ""),
                    "role": event.get("role", ""),
                    "content": content,
                }
                if event.get("stop_reason"):
                    filtered["stop_reason"] = event["stop_reason"]
                yield f"data: {json.dumps(filtered)}\n\n"
                # Track full result for chat history
                for block in content:
                    if isinstance(block, dict) and block.get("type") == "text" and block.get("text"):
                        full_result = block["text"]
            else:
                yield f"data: {json.dumps(event, ensure_ascii=False)}\n\n"
                # Track result / cost for chat history
                try:
                    if etype == "result":
                        full_result = event.get("result", full_result)
                        cost_usd = event.get("cost_usd", 0)
                        num_turns = event.get("num_turns", 0)
                    elif etype == "assistant" and event.get("subtype") == "text":
                        full_result = event.get("text", full_result)
                    elif etype == "content_block_delta":
                        delta = event.get("delta", {})
                        if delta.get("type") == "text_delta" and delta.get("text"):
                            full_result += delta["text"]
                    elif etype == "streamlined_text":
                        # Claude CLI v2: final text content
                        full_result = event.get("text", full_result)
                except KeyError:
                    pass

        # Save chat history after stream completes
        duration_sec = _time.time() - start_time
        if agent_name and prompt_text:
            save_chat_message(
                agent_name=agent_name,
                prompt=prompt_text,
                result=full_result,
                runtime=runtime,
                cost_usd=cost_usd,
                duration_sec=duration_sec,
                task_id=task_id,
                success=True,
                extra={"num_turns": num_turns},
            )

        # Forward agent's reply to Telegram if the prompt came from Telegram
        _maybe_forward_reply_to_telegram(agent_name, full_result)

    return StreamingResponse(sse_generator(), media_type="text/event-stream")


@router.post("/api/send-prompt-cursor")
async def send_prompt_cursor(data: dict):
    """
    Send a prompt to Cursor CLI via WSL. Saves history to chat_history.json.
    Agent chat: from .cursor_chats.json (see GET /api/cursor-chats) or created via create-chat on first send.
    Model: from employees.json for this agent, or override via data.model. CLI: agent -p --force [--model <id>] [--resume <chat_id>] ...
    """
    name = data.get("name") or data.get("agent")
    prompt_text = data.get("prompt") or ""
    task_id = data.get("task_id")

    if not name or not prompt_text:
        raise HTTPException(status_code=400, detail="name and prompt are required")

    use_chat = data.get("use_chat", True)
    # Model always CURSOR_CLI_MODEL (Composer 1.5), request body model is ignored

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


@router.post("/api/cursor-create-chat")
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


@router.post("/api/cursor-create-chats")
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


@router.get("/api/cursor-chats")
async def list_cursor_chats():
    """List of agent -> chat_id bindings (from .cursor_chats.json)."""
    return {"chats": _load_cursor_chats()}


@router.post("/api/reset-agent")
async def reset_agent(data: dict):
    """Reset agent memory."""
    payload = {"name": data["name"], "reset": True, "project_path": get_project_path_for_scoping()}
    return await call_claude_api("POST", "/run", json_data=payload)


@router.delete("/api/agents/{name}")
async def delete_agent(name: str):
    """Delete agent."""
    pp = get_project_path_for_scoping()
    return await call_claude_api("DELETE", f"/agents/{name}", params={"project_path": pp} if pp else None)


@router.get("/api/agent-activity/{name}")
async def get_agent_activity(name: str):
    """Return current activity for an agent: running task info if busy, else idle."""
    now = _time.time()
    for tid, info in running_tasks.items():
        if info.get("agent") == name:
            return {
                "busy": True,
                "task_id": tid,
                "role": info.get("role", ""),
                "runtime": info.get("runtime", ""),
                "elapsed_seconds": round(now - info.get("started_at", now)),
            }
    return {"busy": False}


@router.get("/api/agent-stream/{name}")
async def get_agent_stream(name: str):
    """SSE endpoint: replay buffered stream events and follow live ones for an agent.
    Used by the frontend to show agent's live thoughts during task execution."""

    past_events, queue = subscribe_agent_stream(name)

    # Metadata-only event types to suppress (same filter as send_prompt_stream)
    _SKIP_TYPES = {"message_start", "message_delta", "message_stop", "system", "keep_alive"}

    async def sse_generator():
        try:
            # 1. Replay buffered past events
            for event in past_events:
                etype = event.get("type", "")
                if etype in _SKIP_TYPES:
                    continue
                yield f"data: {json.dumps(event, ensure_ascii=False)}\n\n"

            # 2. Follow live events if stream is still active
            if queue is not None:
                while True:
                    try:
                        event = await asyncio.wait_for(queue.get(), timeout=30.0)
                    except asyncio.TimeoutError:
                        # Send keep-alive to prevent connection drop
                        yield f"data: {json.dumps({'type': 'keep_alive'})}\n\n"
                        continue

                    if event is None:
                        # Stream finished sentinel
                        break

                    etype = event.get("type", "")
                    if etype in _SKIP_TYPES:
                        continue
                    yield f"data: {json.dumps(event, ensure_ascii=False)}\n\n"
        finally:
            if queue is not None:
                unsubscribe_agent_stream(name, queue)

    return StreamingResponse(sse_generator(), media_type="text/event-stream")


@router.get("/api/agent-config/{name}")
async def get_agent_config(name: str):
    """Get full agent configuration from claude_agents.json."""
    pp = get_project_path_for_scoping()
    agents = await call_claude_api("GET", "/agents", params={"project_path": pp} if pp else None)
    if name not in agents:
        raise HTTPException(404, f"Agent '{name}' not found")
    config = agents[name]
    config["name"] = name
    return config


@router.put("/api/agent-config/{name}")
async def update_agent_config(name: str, data: dict):
    """Update agent configuration. Accepts partial updates."""
    pp = get_project_path_for_scoping()
    # Build payload for claude_api /run (create/update mode — no prompt)
    payload = {"name": name}
    if pp:
        payload["project_path"] = pp

    # Forward config fields
    for field in ("system_prompt", "system_prompt_file", "workdir",
                  "allowed_tools", "permission_mode", "model", "budget_limit"):
        if field in data:
            payload[field] = data[field]

    # Sync model change to employees.json so the employee list shows the current model
    if "model" in data and data["model"]:
        update_employee(name, model=data["model"])

    result = await call_claude_api("POST", "/run", json_data=payload)
    return result


@router.post("/api/agent-config/{name}/reset-session")
async def reset_agent_session(name: str, data: dict = None):
    """Reset agent session. Optionally specify model to reset only that model's session."""
    pp = get_project_path_for_scoping()
    payload = {"name": name, "reset": True}
    if pp:
        payload["project_path"] = pp
    if data and data.get("model"):
        payload["model"] = data["model"]
    return await call_claude_api("POST", "/run", json_data=payload)


@router.post("/api/kill-agents")
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


@router.post("/api/refresh-agent-prompt/{name}")
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


@router.post("/api/ensure-agents")
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
                existing_model = (existing or {}).get("model") or ""
                emp_data = employees.get(emp_name, {})
                expected_model = emp_data.get("model", "sonnet")
                model_missing = not existing_model
                logger.info(f"[ensure_agents] {emp_name}: already exists, has_inline_prompt={has_inline}, system_prompt_file={spf!r}, model={existing_model!r}")

                # Migrate: if agent uses stale inline prompt, wrong file path, missing model,
                # or old-style session_id (string UUID from pre-S031) — update so prompt.md
                # edits take effect immediately, model is always set, and legacy sessions
                # are reset so the agent receives --system-prompt on the next run.
                legacy_session = isinstance((existing or {}).get("session_id"), str)
                if has_inline or spf != expected_spf or model_missing or legacy_session:
                    try:
                        fix_composed = compose_system_prompt(emp_name, personel_dir=personel_dir)
                        _fix_payload = {
                            "name": emp_name,
                            "system_prompt_file": expected_spf,
                            "model": expected_model,  # always sync model from employees.json
                            "project_path": project_path_str or "",
                        }
                        # Include inline prompt so agent knows role even on first run after reset
                        if fix_composed:
                            _fix_payload["system_prompt"] = fix_composed
                        if model_missing:
                            logger.info(f"[ensure_agents] {emp_name}: fixing missing model \u2192 {expected_model!r}")
                        if legacy_session:
                            logger.info(f"[ensure_agents] {emp_name}: legacy string session_id detected, will be reset by claude_api")
                        _debug_log_ensure("ensure_agents prompt_to_file payload", {"path": "prompt_to_file", "emp_name": emp_name, "had_inline": has_inline, "old_spf": spf, "new_spf": expected_spf, "model_missing": model_missing, "expected_model": expected_model, "legacy_session": legacy_session, "project_path": project_path_str or ""}, "Tayfa")
                        await call_claude_api("POST", "/run", json_data=_fix_payload)
                        logger.info(f"[ensure_agents] {emp_name}: switched to system_prompt_file={expected_spf!r} (had_inline={has_inline}, old_spf={spf!r}, model_fixed={model_missing}, legacy_session_reset={legacy_session})")
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
            # Pass system_prompt inline so the agent knows its role from the very first run,
            # regardless of which model is selected. system_prompt_file is also set so that
            # subsequent runs re-read prompt.md and pick up any edits automatically.
            # When claude_api.py receives BOTH, inline takes priority (see CREATE logic).
            if composed:
                payload["system_prompt"] = composed
            payload["system_prompt_file"] = f"{TAYFA_DIR_NAME}/{emp_name}/prompt.md"
            logger.info(
                f"[ensure_agents] {emp_name}: CREATE with system_prompt_file="
                f"{payload['system_prompt_file']!r}, system_prompt_len={len(composed) if composed else 0}, "
                f"workdir={agent_workdir!r}, model={model!r}"
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
