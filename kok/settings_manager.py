# project/kok/settings_manager.py
"""
Модуль управления настройками Tayfa.

Настройки разделены на два файла:
- settings.json — публичные настройки (тема, порт, язык и т.д.), хранятся в git
- secret_settings.json — секретные данные (токены, API ключи), НЕ хранятся в git

При загрузке настройки мержатся: публичные + секретные.
При сохранении секретные поля автоматически попадают в secret_settings.json.
"""

import json
from pathlib import Path
from typing import Any

SETTINGS_FILE = Path(__file__).parent / "settings.json"
SECRET_SETTINGS_FILE = Path(__file__).parent / "secret_settings.json"

# Список секретных полей (эти поля хранятся в secret_settings.json)
SECRET_FIELDS = {"githubToken", "apiKeys", "secrets"}

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
    },
}

DEFAULT_SECRET_SETTINGS = {
    "githubToken": "",
    "apiKeys": {},
}

VALIDATORS = {
    "theme": lambda v: v in ("dark", "light", "blue", "girly"),
    "port": lambda v: isinstance(v, int) and 1024 <= v <= 65535,
    "language": lambda v: v in ("ru", "en"),
    "autoOpenBrowser": lambda v: isinstance(v, bool),
    "maxConcurrentTasks": lambda v: isinstance(v, int) and 1 <= v <= 50,
}


def _load_json(path: Path, defaults: dict) -> dict:
    """Загружает JSON-файл. Если файла нет — возвращает дефолтные значения."""
    if not path.exists():
        return dict(defaults)
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        return {**defaults, **data}
    except Exception:
        return dict(defaults)


def _save_json(path: Path, data: dict) -> None:
    """Сохраняет данные в JSON-файл."""
    path.write_text(
        json.dumps(data, ensure_ascii=False, indent=2),
        encoding="utf-8"
    )


def _migrate_secrets_from_settings() -> None:
    """
    Миграция: если в settings.json есть секретные поля (например githubToken в git),
    переносим их в secret_settings.json и удаляем из settings.json.
    """
    if not SETTINGS_FILE.exists():
        return

    try:
        settings = json.loads(SETTINGS_FILE.read_text(encoding="utf-8"))
    except Exception:
        return

    secrets_to_migrate = {}
    settings_modified = False

    # Проверяем git.githubToken
    if "git" in settings and isinstance(settings["git"], dict):
        if "githubToken" in settings["git"] and settings["git"]["githubToken"]:
            secrets_to_migrate["githubToken"] = settings["git"]["githubToken"]
            del settings["git"]["githubToken"]
            settings_modified = True

    # Проверяем секретные поля на верхнем уровне
    for field in SECRET_FIELDS:
        if field in settings and settings[field]:
            secrets_to_migrate[field] = settings[field]
            del settings[field]
            settings_modified = True

    # Сохраняем миграцию
    if secrets_to_migrate:
        # Загружаем существующие секреты и мержим
        existing_secrets = _load_json(SECRET_SETTINGS_FILE, DEFAULT_SECRET_SETTINGS)
        existing_secrets.update(secrets_to_migrate)
        _save_json(SECRET_SETTINGS_FILE, existing_secrets)

    if settings_modified:
        _save_json(SETTINGS_FILE, settings)


def load_settings() -> dict[str, Any]:
    """
    Загружает настройки из обоих файлов и мержит их.
    Секретные поля (githubToken и т.д.) берутся из secret_settings.json.
    """
    # Автоматическая миграция при первой загрузке
    _migrate_secrets_from_settings()

    # Загружаем публичные настройки
    settings = _load_json(SETTINGS_FILE, DEFAULT_SETTINGS)

    # Загружаем секретные настройки
    secrets = _load_json(SECRET_SETTINGS_FILE, DEFAULT_SECRET_SETTINGS)

    # Мержим секреты в настройки
    # githubToken идёт в git.githubToken для совместимости
    if "git" not in settings:
        settings["git"] = {}
    settings["git"]["githubToken"] = secrets.get("githubToken", "")

    # Остальные секретные поля на верхнем уровне
    for field in SECRET_FIELDS:
        if field != "githubToken" and field in secrets:
            settings[field] = secrets[field]

    return settings


def load_public_settings() -> dict[str, Any]:
    """Загружает только публичные настройки (без секретов)."""
    return _load_json(SETTINGS_FILE, DEFAULT_SETTINGS)


def load_secret_settings() -> dict[str, Any]:
    """Загружает только секретные настройки."""
    return _load_json(SECRET_SETTINGS_FILE, DEFAULT_SECRET_SETTINGS)


def save_settings(settings: dict[str, Any]) -> None:
    """
    Сохраняет настройки, разделяя на публичные и секретные.
    Секретные поля автоматически попадают в secret_settings.json.
    """
    # Копируем, чтобы не изменять оригинал
    public = dict(settings)
    secrets = _load_json(SECRET_SETTINGS_FILE, DEFAULT_SECRET_SETTINGS)

    # Извлекаем githubToken из git
    if "git" in public and isinstance(public["git"], dict):
        if "githubToken" in public["git"]:
            secrets["githubToken"] = public["git"]["githubToken"]
            # Удаляем из публичных (создаём новый dict без githubToken)
            public["git"] = {k: v for k, v in public["git"].items() if k != "githubToken"}

    # Извлекаем секретные поля с верхнего уровня
    for field in SECRET_FIELDS:
        if field in public:
            secrets[field] = public[field]
            del public[field]

    # Сохраняем оба файла
    _save_json(SETTINGS_FILE, public)
    _save_json(SECRET_SETTINGS_FILE, secrets)


def validate_setting(key: str, value: Any) -> tuple[bool, str]:
    """Валидирует одну настройку. Возвращает (is_valid, error_message)."""
    if key not in VALIDATORS:
        return True, ""  # Неизвестные ключи пропускаем
    if not VALIDATORS[key](value):
        allowed = {
            "theme": "dark, light, blue, girly",
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

    # Глубокое обновление для вложенных объектов (например git)
    for key, value in updates.items():
        if isinstance(value, dict) and key in current and isinstance(current[key], dict):
            current[key] = {**current[key], **value}
        else:
            current[key] = value

    save_settings(current)
    return current, None


def get_orchestrator_port() -> int:
    """Получает порт из настроек."""
    settings = load_settings()
    return settings.get("port", 8008)


def get_github_token() -> str:
    """Получает GitHub токен из секретных настроек."""
    secrets = load_secret_settings()
    return secrets.get("githubToken", "")


def set_github_token(token: str) -> None:
    """Сохраняет GitHub токен в секретные настройки."""
    secrets = load_secret_settings()
    secrets["githubToken"] = token
    _save_json(SECRET_SETTINGS_FILE, secrets)


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
