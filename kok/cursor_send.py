"""
Send a message to a Cursor CLI chat for an agent (WSL).
Uses .cursor_chats.json for --resume.
Usage: python cursor_send.py boss "task text"
"""
import asyncio
import json
import sys
from pathlib import Path

TAYFA_ROOT_WIN = Path(__file__).resolve().parent.parent
def _to_wsl_path(path) -> str:
    """Converts a path to WSL format. Works from both Windows and WSL."""
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

TAYFA_ROOT_WSL = _to_wsl_path(TAYFA_ROOT_WIN)
CURSOR_CHATS_FILE = TAYFA_ROOT_WIN / ".cursor_chats.json"
CURSOR_CLI_PROMPT_FILE = TAYFA_ROOT_WIN / ".cursor_cli_prompt.txt"
CURSOR_CLI_TIMEOUT = 600.0


def load_chats():
    if not CURSOR_CHATS_FILE.exists():
        return {}
    try:
        return json.loads(CURSOR_CHATS_FILE.read_text(encoding="utf-8"))
    except Exception:
        return {}


def build_prompt(agent_name: str, user_prompt: str) -> str:
    return (
        f"Role: {agent_name}. Project dir: Tayfa (Personel - rules/tasks, project - code). "
        f"Use context from Personel/{agent_name}/prompt.md and Personel/Rules/. Task: {user_prompt}"
    )


async def send(agent_name: str, user_prompt: str) -> dict:
    chats = load_chats()
    chat_id = (chats or {}).get(agent_name)
    if not chat_id:
        print(f"No chat_id for '{agent_name}'. Run: python cursor_create_chat.py {agent_name}", file=sys.stderr)
        return {"success": False, "result": "", "stderr": "No chat_id"}

    full_prompt = build_prompt(agent_name, user_prompt)
    CURSOR_CLI_PROMPT_FILE.write_text(full_prompt, encoding="utf-8")

    safe_id = (chat_id or "").replace("'", "'\"'\"'")
    # Do not use $PATH in WSL — it may contain Windows paths with (x86) that break bash
    wsl_script = (
        'export PATH="$HOME/.local/bin:/usr/local/bin:/usr/bin:/bin" && '
        f'cd "{TAYFA_ROOT_WSL}" && '
        f"agent -p --force --resume '{safe_id}' --output-format json \"$(cat .cursor_cli_prompt.txt)\""
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
    except asyncio.TimeoutError:
        CURSOR_CLI_PROMPT_FILE.unlink(missing_ok=True)
        return {"success": False, "result": "", "stderr": f"Timeout {CURSOR_CLI_TIMEOUT}s"}
    except Exception as e:
        CURSOR_CLI_PROMPT_FILE.unlink(missing_ok=True)
        return {"success": False, "result": "", "stderr": str(e)}

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
    if len(sys.argv) < 3:
        print("Usage: python cursor_send.py <agent> <message>", file=sys.stderr)
        sys.exit(1)
    agent = sys.argv[1].strip()
    message = " ".join(sys.argv[2:]).strip()
    if not message:
        print("Empty message", file=sys.stderr)
        sys.exit(1)
    print(f"Sending to {agent} in Cursor CLI: {message[:60]}...")
    r = asyncio.run(send(agent, message))
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
