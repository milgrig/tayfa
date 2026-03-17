# project/kok/user_data.py
"""
Tayfa user data directory management.

All user-specific data (settings, secrets, projects list) is stored in
a **system-level** directory that persists across Tayfa updates.

The user can download a new version of Tayfa into a completely different
folder — all settings, projects, and secrets remain intact.

Location (resolved once on import):
    Windows:  %APPDATA%\\Tayfa          (e.g. C:\\Users\\<user>\\AppData\\Roaming\\Tayfa)
    Linux:    ~/.config/tayfa
    macOS:    ~/Library/Application Support/Tayfa

Override: set TAYFA_USER_DATA env var to use a custom path.

Layout inside the directory:
    Tayfa/
    ├── settings.json          # public settings (theme, port, git info)
    ├── secret_settings.json   # secrets (tokens, API keys)
    ├── projects.json          # project list and current project
    ├── claude_agents.json     # agent registry (sessions, config cache)
    ├── cursor_chats.json      # Cursor agent chat mappings
    └── logs/
        ├── tayfa_server.log
        └── claude_api.log
"""

import os
import platform
import shutil
from pathlib import Path

KOK_DIR = Path(__file__).resolve().parent
TAYFA_ROOT = KOK_DIR.parent


def _resolve_user_data_dir() -> Path:
    """Determine the system-level user data directory.

    Priority:
    1. TAYFA_USER_DATA environment variable (explicit override)
    2. Platform-specific standard location
    """
    env_override = os.environ.get("TAYFA_USER_DATA")
    if env_override:
        return Path(env_override)

    system = platform.system()
    if system == "Windows":
        base = os.environ.get("APPDATA")
        if base:
            return Path(base) / "Tayfa"
        return Path.home() / "AppData" / "Roaming" / "Tayfa"
    elif system == "Darwin":
        return Path.home() / "Library" / "Application Support" / "Tayfa"
    else:
        xdg = os.environ.get("XDG_CONFIG_HOME")
        if xdg:
            return Path(xdg) / "tayfa"
        return Path.home() / ".config" / "tayfa"


USER_DATA_DIR = _resolve_user_data_dir()
USER_DATA_LOGS_DIR = USER_DATA_DIR / "logs"

# Ensure directories exist on import
USER_DATA_DIR.mkdir(parents=True, exist_ok=True)
USER_DATA_LOGS_DIR.mkdir(parents=True, exist_ok=True)

# ── Canonical paths for user data files ──────────────────────────────────

SETTINGS_FILE = USER_DATA_DIR / "settings.json"
SECRET_SETTINGS_FILE = USER_DATA_DIR / "secret_settings.json"
PROJECTS_FILE = USER_DATA_DIR / "projects.json"
AGENTS_FILE = USER_DATA_DIR / "claude_agents.json"
CURSOR_CHATS_FILE = USER_DATA_DIR / "cursor_chats.json"
SERVER_LOG_FILE = USER_DATA_LOGS_DIR / "tayfa_server.log"
CLAUDE_API_LOG_FILE = USER_DATA_LOGS_DIR / "claude_api.log"

# Temp file — stays in repo (ephemeral, recreated on every CLI call)
CURSOR_CLI_PROMPT_FILE = TAYFA_ROOT / ".cursor_cli_prompt.txt"

# ── Migration from legacy locations ──────────────────────────────────────
# Old locations (inside kok/) → new system-level paths.

_MIGRATION_MAP = [
    # (old_path, new_path)
    (KOK_DIR / "settings.json",              SETTINGS_FILE),
    (KOK_DIR / "secret_settings.json",       SECRET_SETTINGS_FILE),
    (KOK_DIR / "projects.json",              PROJECTS_FILE),
    (TAYFA_ROOT / "claude_agents.json",      AGENTS_FILE),
    (TAYFA_ROOT / ".cursor_chats.json",      CURSOR_CHATS_FILE),
    (KOK_DIR / "tayfa_server.log",           SERVER_LOG_FILE),
    (KOK_DIR / "claude_api.log",             CLAUDE_API_LOG_FILE),
]

_migrated = False


def migrate_user_data() -> list[tuple[str, str]]:
    """Move legacy user data files to the system-level directory.

    Called once on startup. Skips files that already exist at the new
    location to avoid overwriting user edits. Returns a list of
    (old_path, new_path) for files that were actually moved.
    """
    global _migrated
    if _migrated:
        return []

    moved: list[tuple[str, str]] = []
    for old_path, new_path in _MIGRATION_MAP:
        if old_path == new_path:
            continue
        if old_path.exists() and not new_path.exists():
            try:
                new_path.parent.mkdir(parents=True, exist_ok=True)
                shutil.move(str(old_path), str(new_path))
                moved.append((str(old_path), str(new_path)))
            except Exception:
                pass

    _migrated = True
    return moved
