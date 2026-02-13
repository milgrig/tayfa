"""Общие fixtures для тестов Tayfa."""

import json
import shutil
import tempfile
from pathlib import Path
from typing import Any, Dict

import pytest


@pytest.fixture
def tmp_tayfa_dir(tmp_path: Path) -> Path:
    """
    Создаёт временную директорию .tayfa для тестов.

    Структура:
    .tayfa/
    ├── config.json
    ├── common/
    │   ├── backlog/
    │   ├── discussions/
    │   └── employees.json
    └── <agent_dirs>/

    После теста директория автоматически удаляется.
    """
    tayfa_dir = tmp_path / ".tayfa"
    tayfa_dir.mkdir()

    # Создаём базовую структуру
    common_dir = tayfa_dir / "common"
    common_dir.mkdir()
    (common_dir / "backlog").mkdir()
    (common_dir / "discussions").mkdir()

    # Создаём config.json
    config = {
        "project_name": "test_project",
        "version": "0.1.0"
    }
    (tayfa_dir / "config.json").write_text(json.dumps(config, indent=2))

    # Создаём employees.json
    employees = {
        "boss": {
            "name": "boss",
            "role": "менеджер",
            "skills": ["управление", "планирование"]
        },
        "developer": {
            "name": "developer",
            "role": "разработчик",
            "skills": ["python", "fastapi"]
        },
        "tester": {
            "name": "tester",
            "role": "тестировщик",
            "skills": ["pytest", "тестирование"]
        }
    }
    (common_dir / "employees.json").write_text(json.dumps(employees, indent=2, ensure_ascii=False))

    return tayfa_dir


@pytest.fixture
def mock_settings(tmp_path: Path) -> Dict[str, Any]:
    """
    Возвращает тестовые настройки для settings_manager.

    Включает как публичные, так и секретные настройки.
    """
    return {
        "theme": "dark",
        "port": 8008,
        "language": "ru",
        "autoOpenBrowser": False,  # Отключаем для тестов
        "maxConcurrentTasks": 3,
        "autoShutdown": {
            "enabled": False,  # Отключаем для тестов
            "timeout": 60,
        },
        "version": {
            "major": 0,
            "minor": 1,
            "patch": 0,
            "autoIncrement": "patch",
        },
        "git": {
            "userName": "test_user",
            "userEmail": "test@example.com",
            "defaultBranch": "main",
            "remoteUrl": "https://github.com/test/test.git",
        },
        "githubToken": "test_token_123",
        "apiKeys": {
            "claude": "test_api_key"
        },
    }


@pytest.fixture
def mock_employees() -> Dict[str, Dict[str, Any]]:
    """
    Возвращает тестовый список сотрудников.
    """
    return {
        "boss": {
            "name": "boss",
            "role": "менеджер",
            "skills": ["управление", "планирование", "координация"],
            "status": "активен"
        },
        "analyst": {
            "name": "analyst",
            "role": "аналитик",
            "skills": ["анализ требований", "документирование"],
            "status": "активен"
        },
        "developer": {
            "name": "developer",
            "role": "разработчик",
            "skills": ["python", "fastapi", "pytest"],
            "status": "активен"
        },
        "tester": {
            "name": "tester",
            "role": "тестировщик",
            "skills": ["pytest", "тестирование", "qa"],
            "status": "активен"
        }
    }


@pytest.fixture
def clean_json_files(tmp_path: Path):
    """
    Очищает временные JSON файлы после тестов.

    Использование:
        def test_something(clean_json_files, tmp_path):
            # Создаём файлы
            file = tmp_path / "test.json"
            file.write_text('{"key": "value"}')
            # После теста файл будет удалён автоматически
    """
    yield
    # Cleanup после теста
    if tmp_path.exists():
        for json_file in tmp_path.glob("**/*.json"):
            try:
                json_file.unlink()
            except Exception:
                pass  # Игнорируем ошибки при удалении


@pytest.fixture
def mock_backlog_task() -> Dict[str, Any]:
    """
    Возвращает тестовую задачу для backlog.
    """
    return {
        "id": "T001",
        "title": "Тестовая задача",
        "description": "Описание тестовой задачи",
        "status": "новая",
        "customer": "boss",
        "developer": None,
        "tester": None,
        "result": None,
        "sprint_id": "S001",
        "depends_on": [],
        "created_at": "2024-01-01T10:00:00",
        "updated_at": "2024-01-01T10:00:00"
    }


@pytest.fixture
def settings_files(tmp_path: Path) -> tuple[Path, Path]:
    """
    Создаёт временные файлы settings.json и secret_settings.json.

    Возвращает кортеж (settings_path, secret_settings_path).
    """
    settings_path = tmp_path / "settings.json"
    secret_settings_path = tmp_path / "secret_settings.json"

    # Публичные настройки
    public_settings = {
        "theme": "dark",
        "port": 8008,
        "language": "ru"
    }
    settings_path.write_text(json.dumps(public_settings, indent=2))

    # Секретные настройки
    secret_settings = {
        "githubToken": "secret_token",
        "apiKeys": {"claude": "secret_key"}
    }
    secret_settings_path.write_text(json.dumps(secret_settings, indent=2))

    return settings_path, secret_settings_path


@pytest.fixture
def mock_git_config() -> Dict[str, Any]:
    """
    Возвращает тестовую конфигурацию Git.
    """
    return {
        "userName": "Test User",
        "userEmail": "test@example.com",
        "defaultBranch": "main",
        "remoteUrl": "https://github.com/test/repo.git"
    }
