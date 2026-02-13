"""
Тесты для settings_manager.py

Покрытие:
- load_settings() — загрузка и merge настроек
- save_settings() — сохранение с разделением на public/secret
- update_settings() — частичное обновление
- validate_setting() — валидация значений
- Вспомогательные функции (get_github_token, get_next_version и т.д.)
"""

import json
from pathlib import Path
from unittest.mock import patch

import pytest

# Импортируем модуль для тестирования
import sys
sys.path.insert(0, str(Path(__file__).parent.parent))

import settings_manager as sm


# ============================================================================
# Fixtures
# ============================================================================

@pytest.fixture
def isolated_settings(tmp_path: Path, monkeypatch):
    """
    Изолирует settings_manager от реальных файлов.
    Перенаправляет SETTINGS_FILE и SECRET_SETTINGS_FILE во временную директорию.
    """
    settings_file = tmp_path / "settings.json"
    secret_file = tmp_path / "secret_settings.json"

    monkeypatch.setattr(sm, "SETTINGS_FILE", settings_file)
    monkeypatch.setattr(sm, "SECRET_SETTINGS_FILE", secret_file)

    return settings_file, secret_file


@pytest.fixture
def default_settings_file(isolated_settings):
    """Создаёт файл настроек с дефолтными значениями."""
    settings_file, secret_file = isolated_settings
    settings_file.write_text(json.dumps(sm.DEFAULT_SETTINGS, indent=2))
    secret_file.write_text(json.dumps(sm.DEFAULT_SECRET_SETTINGS, indent=2))
    return settings_file, secret_file


# ============================================================================
# Tests: _load_json / _save_json
# ============================================================================

class TestLoadJson:
    """Тесты для _load_json."""

    def test_load_existing_file(self, tmp_path: Path):
        """Загрузка существующего JSON файла."""
        file = tmp_path / "test.json"
        data = {"key": "value", "number": 42}
        file.write_text(json.dumps(data))

        result = sm._load_json(file, {})
        assert result == data

    def test_load_nonexistent_file_returns_defaults(self, tmp_path: Path):
        """При отсутствии файла возвращает дефолтные значения."""
        file = tmp_path / "nonexistent.json"
        defaults = {"default_key": "default_value"}

        result = sm._load_json(file, defaults)
        assert result == defaults

    def test_load_merges_with_defaults(self, tmp_path: Path):
        """Загруженные данные мержатся с дефолтными."""
        file = tmp_path / "test.json"
        file.write_text(json.dumps({"custom": "value"}))
        defaults = {"default_key": "default_value", "custom": "old"}

        result = sm._load_json(file, defaults)
        assert result["default_key"] == "default_value"
        assert result["custom"] == "value"  # Перезаписано из файла

    def test_load_corrupted_json_returns_defaults(self, tmp_path: Path):
        """При битом JSON возвращает дефолтные значения."""
        file = tmp_path / "corrupted.json"
        file.write_text("{invalid json")
        defaults = {"safe": "defaults"}

        result = sm._load_json(file, defaults)
        assert result == defaults


class TestSaveJson:
    """Тесты для _save_json."""

    def test_save_creates_file(self, tmp_path: Path):
        """Сохранение создаёт файл."""
        file = tmp_path / "new.json"
        data = {"key": "value"}

        sm._save_json(file, data)

        assert file.exists()
        assert json.loads(file.read_text()) == data

    def test_save_overwrites_existing(self, tmp_path: Path):
        """Сохранение перезаписывает существующий файл."""
        file = tmp_path / "existing.json"
        file.write_text(json.dumps({"old": "data"}))

        sm._save_json(file, {"new": "data"})

        result = json.loads(file.read_text())
        assert "new" in result
        assert "old" not in result


# ============================================================================
# Tests: load_settings
# ============================================================================

class TestLoadSettings:
    """Тесты для load_settings."""

    def test_load_creates_defaults_if_no_files(self, isolated_settings):
        """Если файлов нет, возвращает дефолтные настройки."""
        result = sm.load_settings()

        assert result["theme"] == sm.DEFAULT_SETTINGS["theme"]
        assert result["port"] == sm.DEFAULT_SETTINGS["port"]
        assert "git" in result

    def test_load_existing_settings(self, isolated_settings):
        """Загрузка существующих настроек."""
        settings_file, secret_file = isolated_settings

        settings_file.write_text(json.dumps({
            "theme": "light",
            "port": 9000,
        }))
        secret_file.write_text(json.dumps({
            "githubToken": "my_token_123"
        }))

        result = sm.load_settings()

        assert result["theme"] == "light"
        assert result["port"] == 9000
        assert result["git"]["githubToken"] == "my_token_123"

    def test_load_merges_secrets_into_git(self, isolated_settings):
        """githubToken из secret_settings попадает в git.githubToken."""
        settings_file, secret_file = isolated_settings

        settings_file.write_text(json.dumps({"git": {"userName": "test"}}))
        secret_file.write_text(json.dumps({"githubToken": "secret_token"}))

        result = sm.load_settings()

        assert result["git"]["githubToken"] == "secret_token"
        assert result["git"]["userName"] == "test"

    def test_load_handles_corrupted_settings(self, isolated_settings):
        """При битом settings.json возвращает дефолты."""
        settings_file, _ = isolated_settings
        settings_file.write_text("{corrupted")

        result = sm.load_settings()

        assert result["theme"] == sm.DEFAULT_SETTINGS["theme"]


# ============================================================================
# Tests: save_settings
# ============================================================================

class TestSaveSettings:
    """Тесты для save_settings."""

    def test_save_creates_both_files(self, isolated_settings):
        """Сохранение создаёт оба файла (public и secret)."""
        settings_file, secret_file = isolated_settings

        settings = {
            "theme": "dark",
            "git": {"githubToken": "my_secret_token"},
        }
        sm.save_settings(settings)

        assert settings_file.exists()
        assert secret_file.exists()

    def test_save_separates_secrets(self, isolated_settings):
        """Секретные поля сохраняются в secret_settings.json."""
        settings_file, secret_file = isolated_settings

        settings = {
            "theme": "light",
            "git": {
                "userName": "test",
                "githubToken": "secret_123",
            },
            "apiKeys": {"claude": "api_key_456"},
        }
        sm.save_settings(settings)

        # Проверяем публичный файл
        public = json.loads(settings_file.read_text())
        assert public["theme"] == "light"
        assert "githubToken" not in public.get("git", {})
        assert "apiKeys" not in public

        # Проверяем секретный файл
        secrets = json.loads(secret_file.read_text())
        assert secrets["githubToken"] == "secret_123"
        assert secrets["apiKeys"]["claude"] == "api_key_456"

    def test_save_preserves_existing_secrets(self, isolated_settings):
        """Сохранение не теряет существующие секреты."""
        settings_file, secret_file = isolated_settings

        # Сначала сохраняем с одним токеном
        secret_file.write_text(json.dumps({
            "githubToken": "old_token",
            "apiKeys": {"old_key": "value"}
        }))

        # Сохраняем новые настройки без apiKeys
        sm.save_settings({"theme": "dark", "git": {"githubToken": "new_token"}})

        secrets = json.loads(secret_file.read_text())
        assert secrets["githubToken"] == "new_token"
        # apiKeys должны сохраниться от предыдущего
        assert "apiKeys" in secrets


# ============================================================================
# Tests: update_settings
# ============================================================================

class TestUpdateSettings:
    """Тесты для update_settings."""

    def test_partial_update_theme(self, default_settings_file):
        """Частичное обновление — только theme."""
        result, error = sm.update_settings({"theme": "light"})

        assert error is None
        assert result["theme"] == "light"
        # Остальные настройки не изменились
        assert result["port"] == sm.DEFAULT_SETTINGS["port"]

    def test_update_multiple_fields(self, default_settings_file):
        """Обновление нескольких полей одновременно."""
        result, error = sm.update_settings({
            "theme": "blue",
            "language": "en",
            "maxConcurrentTasks": 10,
        })

        assert error is None
        assert result["theme"] == "blue"
        assert result["language"] == "en"
        assert result["maxConcurrentTasks"] == 10

    def test_update_nested_git_settings(self, default_settings_file):
        """Обновление вложенных настроек git."""
        result, error = sm.update_settings({
            "git": {"userName": "new_user"}
        })

        assert error is None
        assert result["git"]["userName"] == "new_user"
        # defaultBranch не должен потеряться
        assert result["git"]["defaultBranch"] == sm.DEFAULT_SETTINGS["git"]["defaultBranch"]

    def test_update_invalid_value_returns_error(self, default_settings_file):
        """Невалидное значение возвращает ошибку."""
        result, error = sm.update_settings({"theme": "invalid_theme"})

        assert error is not None
        assert "theme" in error.lower() or "недопустимое" in error.lower()


# ============================================================================
# Tests: validate_setting
# ============================================================================

class TestValidateSetting:
    """Тесты для validate_setting."""

    @pytest.mark.parametrize("theme", ["dark", "light", "blue", "girly"])
    def test_valid_themes(self, theme):
        """Все допустимые темы проходят валидацию."""
        is_valid, error = sm.validate_setting("theme", theme)
        assert is_valid
        assert error == ""

    def test_invalid_theme(self):
        """Недопустимая тема не проходит валидацию."""
        is_valid, error = sm.validate_setting("theme", "rainbow")
        assert not is_valid
        assert "theme" in error.lower() or "недопустимое" in error.lower()

    @pytest.mark.parametrize("port", [1024, 8000, 8008, 65535])
    def test_valid_ports(self, port):
        """Допустимые порты проходят валидацию."""
        is_valid, _ = sm.validate_setting("port", port)
        assert is_valid

    @pytest.mark.parametrize("port", [0, 1023, 65536, -1, "8000"])
    def test_invalid_ports(self, port):
        """Недопустимые порты не проходят валидацию."""
        is_valid, _ = sm.validate_setting("port", port)
        assert not is_valid

    def test_valid_max_concurrent_tasks(self):
        """Допустимое значение maxConcurrentTasks."""
        is_valid, _ = sm.validate_setting("maxConcurrentTasks", 25)
        assert is_valid

    @pytest.mark.parametrize("value", [0, 51, -5, "10"])
    def test_invalid_max_concurrent_tasks(self, value):
        """Недопустимые значения maxConcurrentTasks."""
        is_valid, _ = sm.validate_setting("maxConcurrentTasks", value)
        assert not is_valid

    def test_unknown_key_passes(self):
        """Неизвестные ключи пропускаются (считаются валидными)."""
        is_valid, _ = sm.validate_setting("unknown_key", "any_value")
        assert is_valid


# ============================================================================
# Tests: _migrate_secrets_from_settings
# ============================================================================

class TestMigrateSecrets:
    """Тесты для _migrate_secrets_from_settings."""

    def test_migrate_github_token_from_git(self, isolated_settings):
        """Миграция githubToken из git в secret_settings."""
        settings_file, secret_file = isolated_settings

        # Старый формат с токеном в git
        settings_file.write_text(json.dumps({
            "theme": "dark",
            "git": {
                "userName": "test",
                "githubToken": "old_location_token"
            }
        }))

        sm._migrate_secrets_from_settings()

        # Проверяем что токен перенесён
        secrets = json.loads(secret_file.read_text())
        assert secrets["githubToken"] == "old_location_token"

        # Проверяем что токен удалён из settings
        settings = json.loads(settings_file.read_text())
        assert "githubToken" not in settings.get("git", {})

    def test_migrate_top_level_secrets(self, isolated_settings):
        """Миграция секретных полей с верхнего уровня."""
        settings_file, secret_file = isolated_settings

        settings_file.write_text(json.dumps({
            "theme": "dark",
            "apiKeys": {"claude": "secret_api_key"}
        }))

        sm._migrate_secrets_from_settings()

        secrets = json.loads(secret_file.read_text())
        assert secrets["apiKeys"]["claude"] == "secret_api_key"

        settings = json.loads(settings_file.read_text())
        assert "apiKeys" not in settings

    def test_migrate_does_nothing_if_no_secrets(self, isolated_settings):
        """Миграция ничего не делает если секретов нет."""
        settings_file, secret_file = isolated_settings

        original = {"theme": "dark", "port": 8008}
        settings_file.write_text(json.dumps(original))

        sm._migrate_secrets_from_settings()

        settings = json.loads(settings_file.read_text())
        assert settings == original
        assert not secret_file.exists()


# ============================================================================
# Tests: Helper functions
# ============================================================================

class TestGetGithubToken:
    """Тесты для get_github_token."""

    def test_get_existing_token(self, isolated_settings):
        """Получение существующего токена."""
        _, secret_file = isolated_settings
        secret_file.write_text(json.dumps({"githubToken": "my_token"}))

        token = sm.get_github_token()
        assert token == "my_token"

    def test_get_empty_token_if_not_set(self, isolated_settings):
        """Пустая строка если токен не установлен."""
        _, secret_file = isolated_settings
        secret_file.write_text(json.dumps({}))

        token = sm.get_github_token()
        assert token == ""


class TestSetGithubToken:
    """Тесты для set_github_token."""

    def test_set_new_token(self, isolated_settings):
        """Установка нового токена."""
        _, secret_file = isolated_settings

        sm.set_github_token("new_token_123")

        secrets = json.loads(secret_file.read_text())
        assert secrets["githubToken"] == "new_token_123"

    def test_set_overwrites_existing_token(self, isolated_settings):
        """Перезапись существующего токена."""
        _, secret_file = isolated_settings
        secret_file.write_text(json.dumps({"githubToken": "old_token"}))

        sm.set_github_token("updated_token")

        secrets = json.loads(secret_file.read_text())
        assert secrets["githubToken"] == "updated_token"


class TestVersionFunctions:
    """Тесты для функций работы с версиями."""

    def test_get_current_version(self, default_settings_file):
        """Получение текущей версии."""
        version = sm.get_current_version()
        assert version.startswith("v")
        assert "." in version

    def test_get_next_version_minor(self, isolated_settings):
        """Инкремент minor версии."""
        settings_file, secret_file = isolated_settings
        settings_file.write_text(json.dumps({
            "version": {"major": 1, "minor": 2, "patch": 3, "autoIncrement": "minor"}
        }))
        secret_file.write_text(json.dumps({}))

        next_ver = sm.get_next_version()
        assert next_ver == "v1.3.0"

    def test_get_next_version_major(self, isolated_settings):
        """Инкремент major версии."""
        settings_file, secret_file = isolated_settings
        settings_file.write_text(json.dumps({
            "version": {"major": 1, "minor": 2, "patch": 3, "autoIncrement": "major"}
        }))
        secret_file.write_text(json.dumps({}))

        next_ver = sm.get_next_version("major")
        assert next_ver == "v2.0.0"

    def test_get_next_version_patch(self, isolated_settings):
        """Инкремент patch версии."""
        settings_file, secret_file = isolated_settings
        settings_file.write_text(json.dumps({
            "version": {"major": 1, "minor": 2, "patch": 3, "autoIncrement": "patch"}
        }))
        secret_file.write_text(json.dumps({}))

        next_ver = sm.get_next_version("patch")
        assert next_ver == "v1.2.4"

    def test_save_version(self, default_settings_file):
        """Сохранение версии."""
        result = sm.save_version("v2.5.10")

        assert result["major"] == 2
        assert result["minor"] == 5
        assert result["patch"] == 10


class TestAutoShutdownSettings:
    """Тесты для get_auto_shutdown_settings."""

    def test_get_default_auto_shutdown(self, default_settings_file):
        """Получение дефолтных настроек автовыключения."""
        enabled, timeout = sm.get_auto_shutdown_settings()

        assert isinstance(enabled, bool)
        assert isinstance(timeout, int)
        assert timeout > 0

    def test_get_custom_auto_shutdown(self, isolated_settings):
        """Получение кастомных настроек автовыключения."""
        settings_file, secret_file = isolated_settings
        settings_file.write_text(json.dumps({
            "autoShutdown": {"enabled": False, "timeout": 300}
        }))
        secret_file.write_text(json.dumps({}))

        enabled, timeout = sm.get_auto_shutdown_settings()

        assert enabled is False
        assert timeout == 300


class TestOrchestratorPort:
    """Тесты для get_orchestrator_port."""

    def test_get_default_port(self, isolated_settings):
        """Получение дефолтного порта."""
        port = sm.get_orchestrator_port()
        assert port == 8008

    def test_get_custom_port(self, isolated_settings):
        """Получение кастомного порта."""
        settings_file, secret_file = isolated_settings
        settings_file.write_text(json.dumps({"port": 9000}))
        secret_file.write_text(json.dumps({}))

        port = sm.get_orchestrator_port()
        assert port == 9000


class TestLoadPublicAndSecret:
    """Тесты для load_public_settings и load_secret_settings."""

    def test_load_public_excludes_secrets(self, isolated_settings):
        """load_public_settings не включает значения секретов из secret_settings."""
        settings_file, secret_file = isolated_settings
        settings_file.write_text(json.dumps({"theme": "dark"}))
        secret_file.write_text(json.dumps({"githubToken": "my_secret_value"}))

        public = sm.load_public_settings()

        assert public["theme"] == "dark"
        # Публичные настройки не содержат значение секрета
        assert "my_secret_value" not in str(public)

    def test_load_secret_only_secrets(self, isolated_settings):
        """load_secret_settings возвращает только секреты."""
        settings_file, secret_file = isolated_settings
        settings_file.write_text(json.dumps({"theme": "dark"}))
        secret_file.write_text(json.dumps({"githubToken": "my_secret"}))

        secrets = sm.load_secret_settings()

        assert secrets["githubToken"] == "my_secret"
        assert "theme" not in secrets
