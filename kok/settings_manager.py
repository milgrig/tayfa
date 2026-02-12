# project/kok/settings_manager.py
"""
Модуль управления настройками Tayfa.

Загружает/сохраняет настройки из settings.json, валидирует значения.
"""

import json
from pathlib import Path
from typing import Any

SETTINGS_FILE = Path(__file__).parent / "settings.json"

DEFAULT_SETTINGS = {
    "theme": "dark",
    "port": 8008,
    "language": "ru",
    "autoOpenBrowser": True,
    "maxConcurrentTasks": 5,
    "version": {
        "major": 0,
        "minor": 1,
        "patch": 0,
        "autoIncrement": "minor",  # minor, patch, или none
    },
    "git": {
        "userName": "",
        "userEmail": "",
        "defaultBranch": "main",
        "remoteUrl": "",
        "githubToken": "",
    },
}

VALIDATORS = {
    "theme": lambda v: v in ("dark", "light", "blue"),
    "port": lambda v: isinstance(v, int) and 1024 <= v <= 65535,
    "language": lambda v: v in ("ru", "en"),
    "autoOpenBrowser": lambda v: isinstance(v, bool),
    "maxConcurrentTasks": lambda v: isinstance(v, int) and 1 <= v <= 50,
}


def load_settings() -> dict[str, Any]:
    """Загружает настройки из файла. Если файла нет — возвращает дефолтные."""
    if not SETTINGS_FILE.exists():
        return dict(DEFAULT_SETTINGS)
    try:
        data = json.loads(SETTINGS_FILE.read_text(encoding="utf-8"))
        # Мержим с дефолтами для отсутствующих полей
        return {**DEFAULT_SETTINGS, **data}
    except Exception:
        return dict(DEFAULT_SETTINGS)


def save_settings(settings: dict[str, Any]) -> None:
    """Сохраняет настройки в файл."""
    SETTINGS_FILE.write_text(
        json.dumps(settings, ensure_ascii=False, indent=2),
        encoding="utf-8"
    )


def validate_setting(key: str, value: Any) -> tuple[bool, str]:
    """Валидирует одну настройку. Возвращает (is_valid, error_message)."""
    if key not in VALIDATORS:
        return True, ""  # Неизвестные ключи пропускаем
    if not VALIDATORS[key](value):
        allowed = {
            "theme": "dark, light, blue",
            "port": "целое число 1024-65535",
            "language": "ru, en",
            "autoOpenBrowser": "true или false",
            "maxConcurrentTasks": "целое число 1-50",
        }
        return False, f"Недопустимое значение {key}. Допустимые: {allowed.get(key, '?')}"
    return True, ""


def update_settings(updates: dict[str, Any]) -> tuple[dict[str, Any], str | None]:
    """
    Обновляет настройки (partial update).
    Возвращает (новые_настройки, ошибка_или_None).
    """
    current = load_settings()

    for key, value in updates.items():
        is_valid, error = validate_setting(key, value)
        if not is_valid:
            return current, error

    current.update(updates)
    save_settings(current)
    return current, None


def get_orchestrator_port() -> int:
    """Получает порт из настроек."""
    settings = load_settings()
    return settings.get("port", 8008)


def get_current_version() -> str:
    """Получает текущую версию в формате vX.Y.Z."""
    settings = load_settings()
    v = settings.get("version", DEFAULT_SETTINGS["version"])
    return f"v{v['major']}.{v['minor']}.{v['patch']}"


def get_next_version(increment: str | None = None) -> str:
    """
    Вычисляет следующую версию.
    increment: 'major', 'minor', 'patch' или None (из настроек autoIncrement).
    Возвращает строку вида vX.Y.Z.
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
    # else: none — не инкрементируем

    return f"v{major}.{minor}.{patch}"


def save_version(version_str: str) -> dict:
    """
    Сохраняет версию из строки vX.Y.Z в настройки.
    Возвращает новую версию как dict.
    """
    # Парсим vX.Y.Z
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
