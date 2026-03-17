"""
T006: Tests for update check using configured GitHub repository.

Verifies that:
1. _get_configured_repo_url() reads githubOwner from settings + repoName from project
2. _find_tayfa_remote() prefers the configured repo URL over hardcoded name matching
3. _find_tayfa_remote() creates 'tayfa-updates' remote when no match found
4. _find_tayfa_remote() falls back to 'tayfa'-named remote then 'origin'
5. _find_tayfa_remote() updates stale 'tayfa-updates' URL on re-run
"""
import sys
from pathlib import Path
from unittest.mock import patch, MagicMock

import pytest

_KOK_DIR = Path(__file__).resolve().parents[1]
if str(_KOK_DIR) not in sys.path:
    sys.path.insert(0, str(_KOK_DIR))

from routers.server import _get_configured_repo_url, _find_tayfa_remote


# ---------------------------------------------------------------------------
# _get_configured_repo_url
# ---------------------------------------------------------------------------

class TestGetConfiguredRepoUrl:
    """Tests for building the GitHub URL from settings + project config."""

    def test_returns_url_when_both_owner_and_repo_set(self):
        mock_settings = {"git": {"githubOwner": "milgrig"}}
        with patch("settings_manager.load_public_settings", return_value=mock_settings), \
             patch("project_manager.get_project_repo_name", return_value="tayfa"):
            assert _get_configured_repo_url() == "https://github.com/milgrig/tayfa"

    def test_returns_none_when_owner_missing(self):
        mock_settings = {"git": {"githubOwner": ""}}
        with patch("settings_manager.load_public_settings", return_value=mock_settings), \
             patch("project_manager.get_project_repo_name", return_value="tayfa"):
            assert _get_configured_repo_url() is None

    def test_returns_none_when_repo_missing(self):
        mock_settings = {"git": {"githubOwner": "milgrig"}}
        with patch("settings_manager.load_public_settings", return_value=mock_settings), \
             patch("project_manager.get_project_repo_name", return_value=""):
            assert _get_configured_repo_url() is None

    def test_returns_none_when_git_section_missing(self):
        with patch("settings_manager.load_public_settings", return_value={}), \
             patch("project_manager.get_project_repo_name", return_value="tayfa"):
            assert _get_configured_repo_url() is None

    def test_strips_whitespace(self):
        mock_settings = {"git": {"githubOwner": " milgrig "}}
        with patch("settings_manager.load_public_settings", return_value=mock_settings), \
             patch("project_manager.get_project_repo_name", return_value=" tayfa "):
            assert _get_configured_repo_url() == "https://github.com/milgrig/tayfa"


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _fake_remote_v(lines: str):
    """Create a mock subprocess.run result for 'git remote -v'."""
    mock = MagicMock()
    mock.returncode = 0
    mock.stdout = lines
    mock.stderr = ""
    return mock


def _fake_run_git(returncode=0, stdout="", stderr=""):
    return {"returncode": returncode, "stdout": stdout, "stderr": stderr}


# ---------------------------------------------------------------------------
# _find_tayfa_remote
# ---------------------------------------------------------------------------

class TestFindTayfaRemote:
    """Tests for remote selection logic."""

    def test_matches_configured_url_exact(self):
        remote_v = (
            "origin\thttps://github.com/milgrig/tayfa.git (fetch)\n"
            "origin\thttps://github.com/milgrig/tayfa.git (push)\n"
        )
        with patch("routers.server._get_configured_repo_url",
                    return_value="https://github.com/milgrig/tayfa"), \
             patch("subprocess.run", return_value=_fake_remote_v(remote_v)):
            assert _find_tayfa_remote("/tmp") == "origin"

    def test_matches_configured_url_case_insensitive(self):
        remote_v = (
            "upstream\thttps://github.com/Milgrig/Tayfa.git (fetch)\n"
            "upstream\thttps://github.com/Milgrig/Tayfa.git (push)\n"
        )
        with patch("routers.server._get_configured_repo_url",
                    return_value="https://github.com/milgrig/tayfa"), \
             patch("subprocess.run", return_value=_fake_remote_v(remote_v)):
            assert _find_tayfa_remote("/tmp") == "upstream"

    def test_creates_remote_when_no_match(self):
        remote_v = (
            "origin\thttps://github.com/other/other-repo.git (fetch)\n"
            "origin\thttps://github.com/other/other-repo.git (push)\n"
        )
        with patch("routers.server._get_configured_repo_url",
                    return_value="https://github.com/milgrig/tayfa"), \
             patch("subprocess.run", return_value=_fake_remote_v(remote_v)), \
             patch("routers.server._run_git", return_value=_fake_run_git(0)) as mock_git:
            result = _find_tayfa_remote("/tmp")
            assert result == "tayfa-updates"
            mock_git.assert_called_once_with(
                ["remote", "add", "tayfa-updates", "https://github.com/milgrig/tayfa.git"],
                "/tmp",
            )

    def test_updates_stale_tayfa_updates_remote(self):
        remote_v = (
            "tayfa-updates\thttps://github.com/old/old-repo.git (fetch)\n"
            "tayfa-updates\thttps://github.com/old/old-repo.git (push)\n"
        )
        with patch("routers.server._get_configured_repo_url",
                    return_value="https://github.com/milgrig/tayfa"), \
             patch("subprocess.run", return_value=_fake_remote_v(remote_v)), \
             patch("routers.server._run_git", return_value=_fake_run_git(0)) as mock_git:
            result = _find_tayfa_remote("/tmp")
            assert result == "tayfa-updates"
            mock_git.assert_called_once_with(
                ["remote", "set-url", "tayfa-updates", "https://github.com/milgrig/tayfa.git"],
                "/tmp",
            )

    def test_fallback_to_tayfa_named_remote_without_config(self):
        remote_v = (
            "upstream\thttps://github.com/someone/tayfa.git (fetch)\n"
            "upstream\thttps://github.com/someone/tayfa.git (push)\n"
            "origin\thttps://github.com/fork/other.git (fetch)\n"
            "origin\thttps://github.com/fork/other.git (push)\n"
        )
        with patch("routers.server._get_configured_repo_url", return_value=None), \
             patch("subprocess.run", return_value=_fake_remote_v(remote_v)):
            assert _find_tayfa_remote("/tmp") == "upstream"

    def test_fallback_to_origin_when_nothing_matches(self):
        remote_v = (
            "origin\thttps://github.com/someone/other.git (fetch)\n"
            "origin\thttps://github.com/someone/other.git (push)\n"
        )
        with patch("routers.server._get_configured_repo_url", return_value=None), \
             patch("subprocess.run", return_value=_fake_remote_v(remote_v)):
            assert _find_tayfa_remote("/tmp") == "origin"

    def test_returns_origin_on_git_failure(self):
        mock = MagicMock()
        mock.returncode = 128
        mock.stdout = ""
        mock.stderr = "fatal: not a git repository"
        with patch("routers.server._get_configured_repo_url", return_value="https://github.com/milgrig/tayfa"), \
             patch("subprocess.run", return_value=mock):
            assert _find_tayfa_remote("/tmp") == "origin"

    def test_returns_origin_on_subprocess_exception(self):
        with patch("routers.server._get_configured_repo_url", return_value="https://github.com/milgrig/tayfa"), \
             patch("subprocess.run", side_effect=OSError("not found")):
            assert _find_tayfa_remote("/tmp") == "origin"
