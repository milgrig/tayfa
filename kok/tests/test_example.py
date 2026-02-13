"""Пример тестов для проверки работы pytest."""

import pytest


def test_basic():
    """Базовый тест для проверки работы pytest."""
    assert 1 + 1 == 2


def test_fixtures_tmp_tayfa_dir(tmp_tayfa_dir):
    """Тест fixture tmp_tayfa_dir."""
    assert tmp_tayfa_dir.exists()
    assert (tmp_tayfa_dir / "config.json").exists()
    assert (tmp_tayfa_dir / "common").exists()
    assert (tmp_tayfa_dir / "common" / "employees.json").exists()


def test_fixtures_mock_settings(mock_settings):
    """Тест fixture mock_settings."""
    assert "theme" in mock_settings
    assert mock_settings["theme"] == "dark"
    assert mock_settings["port"] == 8008
    assert "githubToken" in mock_settings


def test_fixtures_mock_employees(mock_employees):
    """Тест fixture mock_employees."""
    assert "boss" in mock_employees
    assert "developer" in mock_employees
    assert "tester" in mock_employees
    assert mock_employees["boss"]["role"] == "менеджер"


def test_fixtures_mock_backlog_task(mock_backlog_task):
    """Тест fixture mock_backlog_task."""
    assert mock_backlog_task["id"] == "T001"
    assert mock_backlog_task["title"] == "Тестовая задача"
    assert mock_backlog_task["status"] == "новая"


@pytest.mark.asyncio
async def test_async_example():
    """Пример async теста."""
    async def async_add(a, b):
        return a + b

    result = await async_add(2, 3)
    assert result == 5


def test_settings_files(settings_files):
    """Тест fixture settings_files."""
    settings_path, secret_settings_path = settings_files
    assert settings_path.exists()
    assert secret_settings_path.exists()


def test_mock_git_config(mock_git_config):
    """Тест fixture mock_git_config."""
    assert "userName" in mock_git_config
    assert mock_git_config["defaultBranch"] == "main"
