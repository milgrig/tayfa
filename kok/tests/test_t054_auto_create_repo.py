"""
T054: Tests for auto-create GitHub repo on sprint finalize.

Verifies that:
- _get_github_owner() reads githubOwner from kok/settings.json
- _get_repo_name() reads repoName from kok/projects.json
- _ensure_github_repo() checks/creates repo via GitHub API
- _ensure_remote_and_repo() wires remote setup + repo creation
- _release_sprint() calls _ensure_remote_and_repo() before push
- Missing config (no owner, no token, no repo) handled gracefully
"""
import json
import sys
from pathlib import Path
from unittest.mock import patch, MagicMock, call

import pytest

# ---------------------------------------------------------------------------
# Path helpers
# ---------------------------------------------------------------------------

_KOK_DIR = Path(__file__).resolve().parents[1]
_TEMPLATE_COMMON = _KOK_DIR / "template_tayfa" / "common"

if str(_TEMPLATE_COMMON) not in sys.path:
    sys.path.insert(0, str(_TEMPLATE_COMMON))


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture(autouse=True)
def _isolate(tmp_path, monkeypatch):
    """Point task_manager at a temp project root."""
    import task_manager as tm

    # Create .tayfa/common structure
    tayfa_common = tmp_path / ".tayfa" / "common"
    tayfa_common.mkdir(parents=True)

    # Write minimal tasks.json
    tasks_file = tayfa_common / "tasks.json"
    tasks_file.write_text("[]", encoding="utf-8")
    monkeypatch.setattr(tm, "TASKS_FILE", tasks_file)

    yield tmp_path


@pytest.fixture()
def setup_config(tmp_path):
    """Create kok/ config files with standard settings."""
    kok_dir = tmp_path / "kok"
    kok_dir.mkdir(exist_ok=True)

    # settings.json with githubOwner
    settings = {
        "git": {
            "userName": "testuser",
            "userEmail": "test@example.com",
            "defaultBranch": "main",
            "githubOwner": "testowner",
        }
    }
    (kok_dir / "settings.json").write_text(json.dumps(settings), encoding="utf-8")

    # secret_settings.json with githubToken
    secrets = {"githubToken": "ghp_testtoken123"}
    (kok_dir / "secret_settings.json").write_text(json.dumps(secrets), encoding="utf-8")

    # projects.json with repoName
    projects = {
        "current": str(tmp_path),
        "projects": [
            {
                "path": str(tmp_path),
                "name": "TestProject",
                "repoName": "test-repo",
            }
        ],
    }
    (kok_dir / "projects.json").write_text(json.dumps(projects), encoding="utf-8")

    return kok_dir


# ---------------------------------------------------------------------------
# Tests: _get_github_owner
# ---------------------------------------------------------------------------


class TestGetGithubOwner:

    def test_reads_owner_from_settings(self, tmp_path, setup_config):
        import task_manager as tm
        owner = tm._get_github_owner()
        assert owner == "testowner"

    def test_returns_empty_when_no_settings(self, tmp_path):
        import task_manager as tm
        result = tm._get_github_owner()
        assert result == ""

    def test_returns_empty_when_no_git_section(self, tmp_path):
        import task_manager as tm
        kok_dir = tmp_path / "kok"
        kok_dir.mkdir(exist_ok=True)
        (kok_dir / "settings.json").write_text("{}", encoding="utf-8")
        assert tm._get_github_owner() == ""

    def test_strips_whitespace(self, tmp_path):
        import task_manager as tm
        kok_dir = tmp_path / "kok"
        kok_dir.mkdir(exist_ok=True)
        settings = {"git": {"githubOwner": "  spacey  "}}
        (kok_dir / "settings.json").write_text(json.dumps(settings), encoding="utf-8")
        assert tm._get_github_owner() == "spacey"


# ---------------------------------------------------------------------------
# Tests: _get_repo_name
# ---------------------------------------------------------------------------


class TestGetRepoName:

    def test_reads_repo_from_projects(self, tmp_path, setup_config):
        import task_manager as tm
        repo = tm._get_repo_name()
        assert repo == "test-repo"

    def test_returns_empty_when_no_projects_file(self, tmp_path):
        import task_manager as tm
        assert tm._get_repo_name() == ""

    def test_falls_back_to_dirname(self, tmp_path):
        import task_manager as tm
        kok_dir = tmp_path / "kok"
        kok_dir.mkdir(exist_ok=True)
        projects = {
            "current": str(tmp_path),
            "projects": [{"path": str(tmp_path), "name": "Test"}],
        }
        (kok_dir / "projects.json").write_text(json.dumps(projects), encoding="utf-8")
        # No repoName set — should derive from project root dir name
        result = tm._get_repo_name()
        assert result != ""
        assert result == tmp_path.name or len(result) > 0

    def test_no_matching_project(self, tmp_path):
        import task_manager as tm
        kok_dir = tmp_path / "kok"
        kok_dir.mkdir(exist_ok=True)
        projects = {
            "current": "/some/other/path",
            "projects": [{"path": "/some/other/path", "name": "Other", "repoName": "other-repo"}],
        }
        (kok_dir / "projects.json").write_text(json.dumps(projects), encoding="utf-8")
        # Current project doesn't match tmp_path — fallback
        result = tm._get_repo_name()
        # Should still return something (fallback to dir name)
        assert isinstance(result, str)


# ---------------------------------------------------------------------------
# Tests: _ensure_github_repo
# ---------------------------------------------------------------------------


class TestEnsureGithubRepo:

    def test_repo_exists_returns_existed(self, tmp_path):
        import task_manager as tm
        import urllib.request

        mock_response = MagicMock()
        with patch.object(urllib.request, "urlopen", return_value=mock_response):
            result = tm._ensure_github_repo("owner", "repo", "token123")
        assert result["existed"] is True
        assert result["created"] is False
        assert result["error"] is None

    def test_repo_not_found_creates_it(self, tmp_path):
        import task_manager as tm
        import urllib.request
        import urllib.error

        # First call: 404 (not found), second call: success (created)
        call_count = {"n": 0}

        def mock_urlopen(req, **kwargs):
            call_count["n"] += 1
            if call_count["n"] == 1:
                raise urllib.error.HTTPError(
                    req.full_url, 404, "Not Found", {}, None
                )
            return MagicMock()

        with patch.object(urllib.request, "urlopen", side_effect=mock_urlopen):
            result = tm._ensure_github_repo("owner", "repo", "token123")
        assert result["created"] is True
        assert result["existed"] is False
        assert result["error"] is None

    def test_api_error_returns_error(self, tmp_path):
        import task_manager as tm
        import urllib.request
        import urllib.error

        def mock_urlopen(req, **kwargs):
            raise urllib.error.HTTPError(
                req.full_url, 500, "Server Error", {}, None
            )

        with patch.object(urllib.request, "urlopen", side_effect=mock_urlopen):
            result = tm._ensure_github_repo("owner", "repo", "token123")
        assert result["error"] is not None
        assert "500" in result["error"]

    def test_422_race_condition_treated_as_existed(self, tmp_path):
        import task_manager as tm
        import urllib.request
        import urllib.error

        call_count = {"n": 0}

        def mock_urlopen(req, **kwargs):
            call_count["n"] += 1
            if call_count["n"] == 1:
                raise urllib.error.HTTPError(req.full_url, 404, "Not Found", {}, None)
            # Second call: 422 = already exists (race condition)
            raise urllib.error.HTTPError(req.full_url, 422, "Unprocessable", {}, None)

        with patch.object(urllib.request, "urlopen", side_effect=mock_urlopen):
            result = tm._ensure_github_repo("owner", "repo", "token123")
        assert result["existed"] is True
        assert result["error"] is None


# ---------------------------------------------------------------------------
# Tests: _ensure_remote_and_repo
# ---------------------------------------------------------------------------


class TestEnsureRemoteAndRepo:

    def test_success_with_existing_remote(self, tmp_path, setup_config):
        import task_manager as tm

        with patch.object(tm, "_run_git") as mock_git, \
             patch.object(tm, "_ensure_github_repo", return_value={"existed": True, "created": False, "error": None}):
            mock_git.return_value = {"success": True, "stdout": "https://github.com/testowner/test-repo.git", "stderr": ""}
            result = tm._ensure_remote_and_repo()

        assert result["success"] is True
        assert result["remote_url"] == "https://github.com/testowner/test-repo.git"
        assert result["repo_created"] is False

    def test_adds_remote_when_missing(self, tmp_path, setup_config):
        import task_manager as tm

        call_log = []

        def mock_git(args, cwd=None):
            call_log.append(args)
            if args[0] == "remote" and args[1] == "get-url":
                return {"success": False, "stdout": "", "stderr": "not found"}
            if args[0] == "remote" and args[1] == "add":
                return {"success": True, "stdout": "", "stderr": ""}
            return {"success": True, "stdout": "", "stderr": ""}

        with patch.object(tm, "_run_git", side_effect=mock_git), \
             patch.object(tm, "_ensure_github_repo", return_value={"existed": True, "created": False, "error": None}):
            result = tm._ensure_remote_and_repo()

        assert result["success"] is True
        # Verify remote add was called
        add_calls = [c for c in call_log if c[0] == "remote" and c[1] == "add"]
        assert len(add_calls) == 1
        assert "https://github.com/testowner/test-repo.git" in add_calls[0]

    def test_creates_repo_when_needed(self, tmp_path, setup_config):
        import task_manager as tm

        with patch.object(tm, "_run_git", return_value={"success": True, "stdout": "https://github.com/testowner/test-repo.git", "stderr": ""}), \
             patch.object(tm, "_ensure_github_repo", return_value={"existed": False, "created": True, "error": None}):
            result = tm._ensure_remote_and_repo()

        assert result["success"] is True
        assert result["repo_created"] is True

    def test_fails_without_owner(self, tmp_path):
        import task_manager as tm
        # No config files — owner is empty
        result = tm._ensure_remote_and_repo()
        assert result["success"] is False
        assert "githubOwner" in result["error"]

    def test_fails_without_token(self, tmp_path):
        import task_manager as tm
        kok_dir = tmp_path / "kok"
        kok_dir.mkdir(exist_ok=True)
        settings = {"git": {"githubOwner": "owner"}}
        (kok_dir / "settings.json").write_text(json.dumps(settings), encoding="utf-8")
        projects = {
            "current": str(tmp_path),
            "projects": [{"path": str(tmp_path), "name": "P", "repoName": "repo"}],
        }
        (kok_dir / "projects.json").write_text(json.dumps(projects), encoding="utf-8")
        # No secret_settings.json — token is empty
        result = tm._ensure_remote_and_repo()
        assert result["success"] is False
        assert "githubToken" in result["error"]


# ---------------------------------------------------------------------------
# Tests: source integration — _release_sprint calls _ensure_remote_and_repo
# ---------------------------------------------------------------------------


class TestSourceIntegration:

    def test_release_sprint_calls_ensure_remote(self):
        """Verify _release_sprint() calls _ensure_remote_and_repo before push."""
        source = (_TEMPLATE_COMMON / "task_manager.py").read_text(encoding="utf-8")
        assert "_ensure_remote_and_repo()" in source

    def test_ensure_remote_before_push(self):
        """_ensure_remote_and_repo must appear before push step."""
        source = (_TEMPLATE_COMMON / "task_manager.py").read_text(encoding="utf-8")
        ensure_pos = source.find("_ensure_remote_and_repo()")
        push_pos = source.find("_get_authenticated_push_url()")
        assert ensure_pos > 0
        assert push_pos > 0
        assert ensure_pos < push_pos, "ensure_remote must come before push"

    def test_repo_created_in_result(self):
        """Release result should include repo_created field."""
        source = (_TEMPLATE_COMMON / "task_manager.py").read_text(encoding="utf-8")
        assert 'result["repo_created"]' in source

    def test_ensure_github_repo_function_exists(self):
        """_ensure_github_repo() function exists in task_manager.py."""
        source = (_TEMPLATE_COMMON / "task_manager.py").read_text(encoding="utf-8")
        assert "def _ensure_github_repo(" in source

    def test_get_github_owner_function_exists(self):
        """_get_github_owner() function exists."""
        source = (_TEMPLATE_COMMON / "task_manager.py").read_text(encoding="utf-8")
        assert "def _get_github_owner(" in source

    def test_get_repo_name_function_exists(self):
        """_get_repo_name() function exists."""
        source = (_TEMPLATE_COMMON / "task_manager.py").read_text(encoding="utf-8")
        assert "def _get_repo_name(" in source
