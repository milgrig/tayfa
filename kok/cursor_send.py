"""
Send a message to a Cursor CLI chat for an agent.
Uses native Windows agent when available, falls back to WSL.
Usage: python cursor_send.py <agent> <message> [--project <path>]
"""
import asyncio
import json
import os
import shutil
import sys
from pathlib import Path

TAYFA_ROOT_WIN = Path(__file__).resolve().parent.parent

from user_data import CURSOR_CHATS_FILE

CURSOR_CLI_PROMPT_FILE = TAYFA_ROOT_WIN / ".cursor_cli_prompt.txt"
CURSOR_CLI_TIMEOUT = 600.0


def _find_native_agent() -> str | None:
    localappdata = os.environ.get("LOCALAPPDATA", "")
    if localappdata:
        for name in ("agent.cmd", "cursor-agent.cmd"):
            p = os.path.join(localappdata, "cursor-agent", name)
            if os.path.isfile(p):
                return p
    return shutil.which("agent") or shutil.which("cursor-agent")


_NATIVE_AGENT: str | None = _find_native_agent()


def _to_wsl_path(path) -> str:
    p = str(path).replace("\\", "/")
    if "/mnt//nt/" in p:
        p = p.replace("/mnt//nt/", "/mnt/")
    if p.startswith("/mnt/"):
        return p
    if len(p) >= 2 and p[1] == ":":
        return "/mnt/" + p[0].lower() + p[2:]
    import re
    m = re.match(r"^/{1,2}nt/([a-zA-Z])/(.*)", p)
    if m:
        return "/mnt/" + m.group(1).lower() + "/" + m.group(2)
    return p


_WSL_PROMPT_FILE = _to_wsl_path(CURSOR_CLI_PROMPT_FILE)


def _cursor_chat_key(agent_name: str, project_path: str = "", model: str = "") -> str:
    parts = []
    if project_path:
        p = project_path.replace("\\", "/").rstrip("/")
        parts.append(p.rsplit("/", 1)[-1] if "/" in p else p)
    parts.append(agent_name)
    if model:
        parts.append(model)
    return ":".join(parts)


def load_chats():
    if not CURSOR_CHATS_FILE.exists():
        return {}
    try:
        return json.loads(CURSOR_CHATS_FILE.read_text(encoding="utf-8"))
    except Exception:
        return {}


def build_prompt(agent_name: str, user_prompt: str, project_path: str = "") -> str:
    if project_path:
        p = project_path.replace("\\", "/").rstrip("/")
        project_name = p.rsplit("/", 1)[-1] if "/" in p else p
        return (
            f"Role: {agent_name}. Project: '{project_name}' (root: {project_path}). "
            f"Working directory: project root (code is here). "
            f".tayfa/ contains team files (.tayfa/common/Rules/ — rules, "
            f".tayfa/{agent_name}/prompt.md — your role prompt). "
            f"Task: {user_prompt}"
        )
    return (
        f"Role: {agent_name}. Working directory: project root. "
        f".tayfa/ contains team files (.tayfa/common/Rules/ — rules, "
        f".tayfa/{agent_name}/prompt.md — your role prompt). "
        f"Task: {user_prompt}"
    )


async def send(agent_name: str, user_prompt: str, project_path: str = "", model: str = "") -> dict:
    chats = load_chats()
    key = _cursor_chat_key(agent_name, project_path, model)
    chat_id = (chats or {}).get(key)
    if not chat_id:
        chat_id = (chats or {}).get(agent_name)
    if not chat_id:
        print(f"No chat_id for '{agent_name}' (key={key}). Run: python cursor_create_chat.py {agent_name}", file=sys.stderr)
        return {"success": False, "result": "", "stderr": "No chat_id"}

    full_prompt = build_prompt(agent_name, user_prompt, project_path)
    workdir = project_path or str(TAYFA_ROOT_WIN)

    try:
        if _NATIVE_AGENT:
            cmd = [_NATIVE_AGENT, "-p", "--force", "--output-format", "json",
                   "--resume", chat_id]
            if model:
                cmd.extend(["--model", model])
            cmd.append(full_prompt)
            proc = await asyncio.create_subprocess_exec(
                *cmd,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
                cwd=workdir,
            )
            stdout, stderr = await asyncio.wait_for(
                proc.communicate(),
                timeout=CURSOR_CLI_TIMEOUT,
            )
        else:
            CURSOR_CLI_PROMPT_FILE.write_text(full_prompt, encoding="utf-8")
            wsl_workdir = _to_wsl_path(workdir)
            safe_id = (chat_id or "").replace("'", "'\"'\"'")
            wsl_script = (
                'export PATH="$HOME/.local/bin:/usr/local/bin:/usr/bin:/bin" && '
                f'cd "{wsl_workdir}" && '
                f"agent -p --force --resume '{safe_id}' --output-format json \"$(cat '{_WSL_PROMPT_FILE}')\""
            )
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
    except asyncio.TimeoutError:
        return {"success": False, "result": "", "stderr": f"Timeout {CURSOR_CLI_TIMEOUT}s"}
    except Exception as e:
        return {"success": False, "result": "", "stderr": str(e)}
    finally:
        if not _NATIVE_AGENT:
            CURSOR_CLI_PROMPT_FILE.unlink(missing_ok=True)

    out_text = (stdout or b"").decode("utf-8", errors="replace").strip()
    err_text = (stderr or b"").decode("utf-8", errors="replace").strip()

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


def main():
    args = sys.argv[1:]
    project_path = ""
    if "--project" in args:
        idx = args.index("--project")
        if idx + 1 < len(args):
            project_path = args[idx + 1]
            args = args[:idx] + args[idx + 2:]

    if len(args) < 2:
        print("Usage: python cursor_send.py <agent> <message> [--project <path>]", file=sys.stderr)
        sys.exit(1)
    agent = args[0].strip()
    message = " ".join(args[1:]).strip()
    if not message:
        print("Empty message", file=sys.stderr)
        sys.exit(1)
    print(f"Sending to {agent} in Cursor CLI: {message[:60]}...")
    r = asyncio.run(send(agent, message, project_path=project_path))
    if r["stderr"]:
        print("stderr:", r["stderr"], file=sys.stderr)
    out = r["result"] or "(no output)"
    try:
        print(out)
    except UnicodeEncodeError:
        print(out.encode("utf-8", errors="replace").decode("utf-8"))
    sys.exit(0 if r["success"] else 1)


if __name__ == "__main__":
    main()
