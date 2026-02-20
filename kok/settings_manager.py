# project/kok/settings_manager.py
"""
Tayfa settings management module.

Settings are split into two files:
- settings.json — public settings (theme, port, language, etc.), stored in git
- secret_settings.json — secret data (tokens, API keys), NOT stored in git

On load, settings are merged: public + secret.
On save, secret fields are automatically placed into secret_settings.json.
"""

import json
from pathlib import Path
from typing import Any

from file_lock import locked_read_json, locked_write_json

SETTINGS_FILE = Path(__file__).parent / "settings.json"
SECRET_SETTINGS_FILE = Path(__file__).parent / "secret_settings.json"

# List of secret fields (these fields are stored in secret_settings.json)
SECRET_FIELDS = {"githubToken", "apiKeys", "secrets", "telegramBotToken", "telegramChatId"}

DEFAULT_SETTINGS = {
    "theme": "dark",
    "port": 8008,
    "language": "ru",
    "autoOpenBrowser": True,
    "maxConcurrentTasks": 5,
    "autoLaunchSprints": False,
    "autoShutdown": {
        "enabled": True,  # Enable/disable automatic shutdown
        "timeout": 120,   # Timeout in seconds (default 120)
    },
    "version": {
        "major": 0,
        "minor": 1,
        "patch": 0,
        "autoIncrement": "minor",  # minor, patch, or none
    },
    "git": {
        "userName": "",
        "userEmail": "",
        "defaultBranch": "main",
        "githubOwner": "",
        "remoteUrl": "",  # deprecated: kept for backward compat migration only
    },
}

DEFAULT_SECRET_SETTINGS = {
    "githubToken": "",
    "apiKeys": {},
    "telegramBotToken": "",
    "telegramChatId": "",
}

VALIDATORS = {
    "theme": lambda v: v in ("dark", "light", "blue", "girly"),
    "port": lambda v: isinstance(v, int) and 1024 <= v <= 65535,
    "language": lambda v: v in ("ru", "en"),
    "autoOpenBrowser": lambda v: isinstance(v, bool),
    "maxConcurrentTasks": lambda v: isinstance(v, int) and 1 <= v <= 50,
    "autoLaunchSprints": lambda v: isinstance(v, bool),
    "autoShutdown": lambda v: isinstance(v, dict) and "enabled" in v and "timeout" in v,
}


def _load_json(path: Path, defaults: dict) -> dict:
    """Loads a JSON file with cross-process file locking.
    If the file does not exist, returns default values."""
    data = locked_read_json(str(path), default=dict(defaults))
    return {**defaults, **data} if isinstance(data, dict) else dict(defaults)


def _save_json(path: Path, data: dict) -> None:
    """Saves data to a JSON file with cross-process file locking."""
    locked_write_json(str(path), data)


def _migrate_secrets_from_settings() -> None:
    """
    Migration: if settings.json contains secret fields (e.g. githubToken in git),
    move them to secret_settings.json and remove them from settings.json.
    """
    if not SETTINGS_FILE.exists():
        return

    try:
        settings = json.loads(SETTINGS_FILE.read_text(encoding="utf-8"))
    except Exception:
        return

    secrets_to_migrate = {}
    settings_modified = False

    # Check git.githubToken
    if "git" in settings and isinstance(settings["git"], dict):
        if "githubToken" in settings["git"] and settings["git"]["githubToken"]:
            secrets_to_migrate["githubToken"] = settings["git"]["githubToken"]
            del settings["git"]["githubToken"]
            settings_modified = True

    # Check secret fields at the top level
    for field in SECRET_FIELDS:
        if field in settings and settings[field]:
            secrets_to_migrate[field] = settings[field]
            del settings[field]
            settings_modified = True

    # Save the migration
    if secrets_to_migrate:
        # Load existing secrets and merge
        existing_secrets = _load_json(SECRET_SETTINGS_FILE, DEFAULT_SECRET_SETTINGS)
        existing_secrets.update(secrets_to_migrate)
        _save_json(SECRET_SETTINGS_FILE, existing_secrets)

    if settings_modified:
        _save_json(SETTINGS_FILE, settings)


def load_settings() -> dict[str, Any]:
    """
    Loads settings from both files and merges them.
    Secret fields (githubToken, etc.) are taken from secret_settings.json.
    """
    # Automatic migration on first load
    _migrate_secrets_from_settings()

    # Load public settings
    settings = _load_json(SETTINGS_FILE, DEFAULT_SETTINGS)

    # Load secret settings
    secrets = _load_json(SECRET_SETTINGS_FILE, DEFAULT_SECRET_SETTINGS)

    # Merge secrets into settings
    # githubToken goes into git.githubToken for compatibility
    if "git" not in settings:
        settings["git"] = {}
    settings["git"]["githubToken"] = secrets.get("githubToken", "")

    # Other secret fields at the top level
    for field in SECRET_FIELDS:
        if field != "githubToken" and field in secrets:
            settings[field] = secrets[field]

    return settings


def load_public_settings() -> dict[str, Any]:
    """Loads only public settings (without secrets)."""
    return _load_json(SETTINGS_FILE, DEFAULT_SETTINGS)


def load_secret_settings() -> dict[str, Any]:
    """Loads only secret settings."""
    return _load_json(SECRET_SETTINGS_FILE, DEFAULT_SECRET_SETTINGS)


def save_settings(settings: dict[str, Any]) -> None:
    """
    Saves settings, splitting them into public and secret.
    Secret fields are automatically placed into secret_settings.json.
    """
    # Copy to avoid modifying the original
    public = dict(settings)
    secrets = _load_json(SECRET_SETTINGS_FILE, DEFAULT_SECRET_SETTINGS)

    # Extract githubToken from git
    if "git" in public and isinstance(public["git"], dict):
        if "githubToken" in public["git"]:
            secrets["githubToken"] = public["git"]["githubToken"]
            # Remove from public (create a new dict without githubToken)
            public["git"] = {k: v for k, v in public["git"].items() if k != "githubToken"}

    # Extract secret fields from the top level
    for field in SECRET_FIELDS:
        if field in public:
            secrets[field] = public[field]
            del public[field]

    # Save both files
    _save_json(SETTINGS_FILE, public)
    _save_json(SECRET_SETTINGS_FILE, secrets)


def validate_setting(key: str, value: Any) -> tuple[bool, str]:
    """Validates a single setting. Returns (is_valid, error_message)."""
    if key not in VALIDATORS:
        return True, ""  # Unknown keys are skipped
    if not VALIDATORS[key](value):
        allowed = {
            "theme": "dark, light, blue, girly",
            "port": "integer 1024-65535",
            "language": "ru, en",
            "autoOpenBrowser": "true or false",
            "maxConcurrentTasks": "integer 1-50",
            "autoLaunchSprints": "true or false",
        }
        return False, f"Invalid value for {key}. Allowed: {allowed.get(key, '?')}"
    return True, ""


def update_settings(updates: dict[str, Any]) -> tuple[dict[str, Any], str | None]:
    """
    Updates settings (partial update).
    Returns (new_settings, error_or_None).
    """
    current = load_settings()

    for key, value in updates.items():
        is_valid, error = validate_setting(key, value)
        if not is_valid:
            return current, error

    # Deep update for nested objects (e.g. git)
    for key, value in updates.items():
        if isinstance(value, dict) and key in current and isinstance(current[key], dict):
            current[key] = {**current[key], **value}
        else:
            current[key] = value

    save_settings(current)
    return current, None


def get_orchestrator_port() -> int:
    """Gets the port from settings."""
    settings = load_settings()
    return settings.get("port", 8008)


def get_github_token() -> str:
    """Gets the GitHub token from secret settings."""
    secrets = load_secret_settings()
    return secrets.get("githubToken", "")


def set_github_token(token: str) -> None:
    """Saves the GitHub token to secret settings."""
    secrets = load_secret_settings()
    secrets["githubToken"] = token
    _save_json(SECRET_SETTINGS_FILE, secrets)


def get_current_version() -> str:
    """Gets the current version in vX.Y.Z format."""
    settings = load_settings()
    v = settings.get("version", DEFAULT_SETTINGS["version"])
    return f"v{v['major']}.{v['minor']}.{v['patch']}"


def get_next_version(increment: str | None = None) -> str:
    """
    Calculates the next version.
    increment: 'major', 'minor', 'patch' or None (from autoIncrement setting).
    Returns a string in vX.Y.Z format.
    """
    settings = load_settings()
    v = settings.get("version", DEFAULT_SETTINGS["version"])
    major, minor, patch = v["major"], v["minor"], v["patch"]

    inc = increment or v.get("autoIncrement", "minor")

    if inc == "major":
        major += 1
        minor = 0
        patch = 0
    elif inc == "minor":
        minor += 1
        patch = 0
    elif inc == "patch":
        patch += 1
    # else: none — do not increment

    return f"v{major}.{minor}.{patch}"


def save_version(version_str: str) -> dict:
    """
    Saves a version from a vX.Y.Z string to settings.
    Returns the new version as a dict.
    """
    # Parse vX.Y.Z
    if version_str.startswith("v"):
        version_str = version_str[1:]
    parts = version_str.split(".")
    major = int(parts[0]) if len(parts) > 0 else 0
    minor = int(parts[1]) if len(parts) > 1 else 0
    patch = int(parts[2]) if len(parts) > 2 else 0

    settings = load_settings()
    settings["version"] = {
        **settings.get("version", {}),
        "major": major,
        "minor": minor,
        "patch": patch,
    }
    save_settings(settings)
    return settings["version"]


def get_telegram_settings() -> tuple[str, str]:
    """
    Gets Telegram bot settings.
    Returns (bot_token: str, chat_id: str).
    """
    secrets = load_secret_settings()
    return secrets.get("telegramBotToken", ""), secrets.get("telegramChatId", "")


def set_telegram_settings(bot_token: str, chat_id: str) -> None:
    """Saves Telegram bot settings to secret settings."""
    secrets = load_secret_settings()
    secrets["telegramBotToken"] = bot_token
    secrets["telegramChatId"] = chat_id
    _save_json(SECRET_SETTINGS_FILE, secrets)


def get_auto_shutdown_settings() -> tuple[bool, int]:
    """
    Gets auto-shutdown settings.
    Returns (enabled: bool, timeout: int).
    """
    settings = load_settings()
    auto_shutdown = settings.get("autoShutdown", DEFAULT_SETTINGS["autoShutdown"])
    enabled = auto_shutdown.get("enabled", True)
    timeout = auto_shutdown.get("timeout", 120)
    return enabled, timeout


def migrate_remote_url() -> str | None:
    """
    One-time migration: extract githubOwner and repoName from legacy remoteUrl.

    If settings.json has git.remoteUrl set (e.g. "https://github.com/user/repo.git"):
    1. Extract githubOwner from URL (set in settings if not already present)
    2. Extract repoName from URL (returned to caller for per-project storage)
    3. Clear remoteUrl from settings.json

    Returns the extracted repoName, or None if no migration was needed.
    """
    import re

    if not SETTINGS_FILE.exists():
        return None

    try:
        settings = json.loads(SETTINGS_FILE.read_text(encoding="utf-8"))
    except Exception:
        return None

    git = settings.get("git", {})
    remote_url = git.get("remoteUrl", "").strip()

    if not remote_url:
        return None

    # Parse GitHub URL: https://github.com/{owner}/{repo}.git
    match = re.match(
        r"https?://(?:[^@]+@)?github\.com/([^/]+)/([^/]+?)(?:\.git)?/?$",
        remote_url,
    )
    if not match:
        return None

    owner = match.group(1)
    repo_name = match.group(2)

    # Set githubOwner if not already set
    if not git.get("githubOwner", "").strip():
        git["githubOwner"] = owner

    # Clear remoteUrl
    del git["remoteUrl"]
    settings["git"] = git

    _save_json(SETTINGS_FILE, settings)

    return repo_name
