"""
Создать чат Cursor CLI для одного агента (через WSL) и сохранить в .cursor_chats.json.
Запуск: python cursor_create_chat.py boss
"""
import asyncio
import json
import sys
from pathlib import Path

# Корень Tayfa
TAYFA_ROOT_WIN = Path(__file__).resolve().parent.parent
CURSOR_CHATS_FILE = TAYFA_ROOT_WIN / ".cursor_chats.json"
def _to_wsl_path(path) -> str:
    """Конвертирует путь в WSL-формат. Работает и из Windows, и из WSL."""
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
CURSOR_CREATE_CHAT_TIMEOUT = 30.0


def load_chats():
    if not CURSOR_CHATS_FILE.exists():
        return {}
    try:
        return json.loads(CURSOR_CHATS_FILE.read_text(encoding="utf-8"))
    except Exception:
        return {}


def save_chats(chats):
    CURSOR_CHATS_FILE.write_text(json.dumps(chats, ensure_ascii=False, indent=2), encoding="utf-8")


async def create_chat():
    # Не используем $PATH в WSL — может содержать Windows-пути с (x86), ломающие bash
    wsl_script = (
        'export PATH="$HOME/.local/bin:/usr/local/bin:/usr/bin:/bin" && '
        f'cd "{TAYFA_ROOT_WSL}" && '
        "agent --print --output-format json create-chat"
    )
    proc = await asyncio.create_subprocess_exec(
        "wsl", "bash",
        stdin=asyncio.subprocess.PIPE,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
        cwd=str(TAYFA_ROOT_WIN),
    )
    try:
        stdout, stderr = await asyncio.wait_for(
            proc.communicate(input=wsl_script.encode("utf-8")),
            timeout=CURSOR_CREATE_CHAT_TIMEOUT,
        )
    except asyncio.TimeoutError:
        print("Timeout create-chat", file=sys.stderr)
        return None, None
    out_text = (stdout or b"").decode("utf-8", errors="replace").strip()
    err_text = (stderr or b"").decode("utf-8", errors="replace").strip()
    if err_text:
        print("stderr:", err_text, file=sys.stderr)
    chat_id = None
    if out_text and proc.returncode == 0:
        try:
            obj = json.loads(out_text)
            chat_id = obj.get("chat_id") or obj.get("session_id") or obj.get("id")
            if isinstance(chat_id, dict):
                chat_id = chat_id.get("id") or chat_id.get("chat_id")
        except Exception:
            pass
        # Иногда create-chat возвращает только UUID строкой (не JSON)
        if not chat_id and out_text.strip():
            line = out_text.strip().splitlines()[0].strip()
            if len(line) == 36 and line.count("-") == 4:
                chat_id = line
    return str(chat_id) if chat_id else None, out_text


def main():
    agent = (sys.argv[1] if len(sys.argv) > 1 else "").strip() or "boss"
    chats = load_chats()
    if agent in chats and chats[agent]:
        print(f"Chat for '{agent}' already exists: {chats[agent]}")
        return 0
    print(f"Creating Cursor chat for '{agent}' via WSL...")
    chat_id, raw = asyncio.run(create_chat())
    if not chat_id:
        print("Failed to get chat_id. Output:", raw or "(empty)", file=sys.stderr)
        return 1
    chats[agent] = chat_id
    save_chats(chats)
    print(f"Done. {agent} -> {chat_id}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
