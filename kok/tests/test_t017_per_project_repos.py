"""Tests for T017: Separate Git repos per project with auto-creation."""

import json
import sys
from pathlib import Path
from unittest.mock import patch, MagicMock

import pytest

# Add kok/ and its dependencies to path
KOK_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(KOK_DIR))
sys.path.insert(0, str(KOK_DIR.parent / ".tayfa" / "common"))


# ---------------------------------------------------------------------------
# TC-1: Repo name sanitization
# ---------------------------------------------------------------------------
@pytest.mark.unit
class TestRepoNameSanitize:

    def test_spaces_to_hyphens(self):
        from project_manager import sanitize_repo_name
        assert sanitize_repo_name("My App") == "my-app"

    def test_underscores_to_hyphens(self):
        from project_manager import sanitize_repo_name
        assert sanitize_repo_name("my_project") == "my-project"

    def test_special_chars_stripped(self):
        from project_manager import sanitize_repo_name
        assert sanitize_repo_name("Hello World!") == "hello-world"

    def test_numeric_prefix(self):
        from project_manager import sanitize_repo_name
        assert sanitize_repo_name("123-test") == "123-test"

    def test_empty_string(self):
        from project_manager import sanitize_repo_name
        assert sanitize_repo_name("") == "unnamed-project"

    def test_multiple_hyphens_collapsed(self):
        from project_manager import sanitize_repo_name
        assert sanitize_repo_name("my---project") == "my-project"

    def test_dots_preserved(self):
        from project_manager import sanitize_repo_name
        assert sanitize_repo_name("my.project") == "my.project"


# ---------------------------------------------------------------------------
# TC-2: Computed remote URL
# ---------------------------------------------------------------------------
@pytest.mark.unit
class TestComputedRemoteUrl:

    def test_url_from_owner_and_repo(self):
        with patch("git_manager._get_git_settings", return_value={"githubOwner": "testuser"}), \
             patch("git_manager.get_project_repo_name", return_value="my-app"):
            from git_manager import _get_computed_remote_url
            assert _get_computed_remote_url() == "https://github.com/testuser/my-app.git"

    def test_empty_owner_returns_empty(self):
        with patch("git_manager._get_git_settings", return_value={"githubOwner": ""}), \
             patch("git_manager.get_project_repo_name", return_value="my-app"):
            from git_manager import _get_computed_remote_url
            assert _get_computed_remote_url() == ""

    def test_empty_repo_returns_empty(self):
        with patch("git_manager._get_git_settings", return_value={"githubOwner": "testuser"}), \
             patch("git_manager.get_project_repo_name", return_value=""):
            from git_manager import _get_computed_remote_url
            assert _get_computed_remote_url() == ""


# ---------------------------------------------------------------------------
# TC-3: GitHub API mock — ensure_github_repo_exists
# ---------------------------------------------------------------------------
@pytest.mark.unit
class TestEnsureGithubRepoExists:

    def test_repo_exists_returns_existed(self):
        from git_manager import _ensure_github_repo_exists
        import urllib.request

        mock_response = MagicMock()
        mock_response.status = 200
        mock_response.read.return_value = b'{}'

        with patch.object(urllib.request, "urlopen", return_value=mock_response):
            result = _ensure_github_repo_exists("owner", "repo", "token123")
            assert result["existed"] is True
            assert result["created"] is False
            assert result["error"] is None

    def test_repo_not_found_creates(self):
        from git_manager import _ensure_github_repo_exists
        import urllib.request
        import urllib.error

        call_count = [0]

        def mock_urlopen(req, timeout=None):
            call_count[0] += 1
            if call_count[0] == 1:
                # First call: check repo -> 404
                raise urllib.error.HTTPError(
                    req.full_url, 404, "Not Found", {}, None
                )
            # Second call: create repo -> success
            resp = MagicMock()
            resp.status = 201
            resp.read.return_value = b'{"name": "repo"}'
            return resp

        with patch.object(urllib.request, "urlopen", side_effect=mock_urlopen):
            result = _ensure_github_repo_exists("owner", "repo", "token123")
            assert result["created"] is True
            assert result["existed"] is False
            assert result["error"] is None

    def test_api_error_returns_error(self):
        from git_manager import _ensure_github_repo_exists
        import urllib.request
        import urllib.error

        def mock_urlopen(req, timeout=None):
            raise urllib.error.HTTPError(
                req.full_url, 500, "Server Error", {}, None
            )

        with patch.object(urllib.request, "urlopen", side_effect=mock_urlopen):
            result = _ensure_github_repo_exists("owner", "repo", "token123")
            assert result["error"] is not None
            assert "500" in result["error"]


# ---------------------------------------------------------------------------
# TC-4: Project repoName helpers
# ---------------------------------------------------------------------------
@pytest.mark.unit
class TestProjectRepoNameHelpers:

    def test_get_repo_name_from_project(self):
        from project_manager import get_project_repo_name
        project = {"path": "C:\\Test\\MyApp", "name": "MyApp", "repoName": "custom-repo"}
        with patch("project_manager.get_current_project", return_value=project):
            assert get_project_repo_name() == "custom-repo"

    def test_get_repo_name_fallback_to_name(self):
        from project_manager import get_project_repo_name
        project = {"path": "C:\\Test\\MyApp", "name": "My App"}
        with patch("project_manager.get_current_project", return_value=project), \
             patch("project_manager.set_project_repo_name"):
            assert get_project_repo_name() == "my-app"

    def test_get_repo_name_no_project(self):
        from project_manager import get_project_repo_name
        with patch("project_manager.get_current_project", return_value=None):
            assert get_project_repo_name() == ""


# ---------------------------------------------------------------------------
# TC-5: githubOwner in settings defaults
# ---------------------------------------------------------------------------
@pytest.mark.unit
class TestSettingsGithubOwner:

    def test_default_settings_has_github_owner(self):
        from settings_manager import DEFAULT_SETTINGS
        assert "githubOwner" in DEFAULT_SETTINGS["git"]
        assert DEFAULT_SETTINGS["git"]["githubOwner"] == ""


# ---------------------------------------------------------------------------
# TC-6: Backward compat — migrate_remote_url
# ---------------------------------------------------------------------------
@pytest.mark.unit
class TestMigrateRemoteUrl:

    def test_extracts_repo_name_from_url(self, tmp_path):
        from settings_manager import migrate_remote_url, SETTINGS_FILE, _save_json
        settings_data = {
            "git": {
                "userName": "user",
                "remoteUrl": "https://github.com/user/old-repo.git",
            }
        }
        settings_file = tmp_path / "settings.json"
        settings_file.write_text(json.dumps(settings_data), encoding="utf-8")

        with patch("settings_manager.SETTINGS_FILE", settings_file):
            repo_name = migrate_remote_url()

        assert repo_name == "old-repo"

        # Check settings file was updated
        updated = json.loads(settings_file.read_text(encoding="utf-8"))
        assert "remoteUrl" not in updated["git"]
        assert updated["git"]["githubOwner"] == "user"

    def test_preserves_existing_github_owner(self, tmp_path):
        from settings_manager import migrate_remote_url
        settings_data = {
            "git": {
                "githubOwner": "existing-owner",
                "remoteUrl": "https://github.com/url-owner/repo.git",
            }
        }
        settings_file = tmp_path / "settings.json"
        settings_file.write_text(json.dumps(settings_data), encoding="utf-8")

        with patch("settings_manager.SETTINGS_FILE", settings_file):
            repo_name = migrate_remote_url()

        assert repo_name == "repo"
        updated = json.loads(settings_file.read_text(encoding="utf-8"))
        # Should NOT overwrite existing owner
        assert updated["git"]["githubOwner"] == "existing-owner"

    def test_no_remote_url_returns_none(self, tmp_path):
        from settings_manager import migrate_remote_url
        settings_data = {"git": {"userName": "user"}}
        settings_file = tmp_path / "settings.json"
        settings_file.write_text(json.dumps(settings_data), encoding="utf-8")

        with patch("settings_manager.SETTINGS_FILE", settings_file):
            assert migrate_remote_url() is None

    def test_non_github_url_returns_none(self, tmp_path):
        from settings_manager import migrate_remote_url
        settings_data = {
            "git": {"remoteUrl": "https://gitlab.com/user/repo.git"}
        }
        settings_file = tmp_path / "settings.json"
        settings_file.write_text(json.dumps(settings_data), encoding="utf-8")

        with patch("settings_manager.SETTINGS_FILE", settings_file):
            assert migrate_remote_url() is None
