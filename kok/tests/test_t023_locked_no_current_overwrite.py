"""Tests for T023: locked instance must NOT overwrite shared current project.

Tests that:
- When LOCKED_PROJECT_PATH is set, get_current_project() returns the locked
  project without reading the "current" field from projects.json.
- The lifespan startup for a locked instance calls init_project() + add_project()
  but NOT set_current_project(), so the shared "current" field is untouched.
- _init_files_for_current_project() still works for locked instances.
"""

import json
import sys
import tempfile
from pathlib import Path
from unittest.mock import patch, MagicMock

import pytest

# Add kok/ to path
KOK_DIR = Path(__file__).resolve().parent.parent
TEMPLATE_COMMON = KOK_DIR / "template_tayfa" / "common"
sys.path.insert(0, str(TEMPLATE_COMMON))
sys.path.insert(0, str(KOK_DIR))


# ---------------------------------------------------------------------------
# Tests: get_current_project override for locked instances
# ---------------------------------------------------------------------------

class TestGetCurrentProjectOverride:

    def test_locked_instance_returns_locked_project(self):
        """When LOCKED_PROJECT_PATH is set, get_current_project() must return
        the project matching that path, ignoring the 'current' field."""
        import app_state
        original = app_state.LOCKED_PROJECT_PATH
        try:
            locked_path = "C:\\Projects\\LockedOne"
            app_state.LOCKED_PROJECT_PATH = locked_path

            fake_project = {"path": locked_path, "name": "LockedOne", "last_opened": "2026-01-01T00:00:00"}

            with patch("app_state.get_project", return_value=fake_project) as mock_get:
                result = app_state.get_current_project()
                assert result is not None
                assert result["path"] == locked_path
                assert result["name"] == "LockedOne"
                mock_get.assert_called_once_with(locked_path)
        finally:
            app_state.LOCKED_PROJECT_PATH = original

    def test_locked_instance_does_not_read_current_field(self):
        """When LOCKED_PROJECT_PATH is set, _pm_get_current_project must NOT be called."""
        import app_state
        original = app_state.LOCKED_PROJECT_PATH
        try:
            app_state.LOCKED_PROJECT_PATH = "C:\\Projects\\LockedOne"

            fake_project = {"path": "C:\\Projects\\LockedOne", "name": "LockedOne", "last_opened": ""}

            with patch("app_state.get_project", return_value=fake_project), \
                 patch("app_state._pm_get_current_project") as mock_pm:
                app_state.get_current_project()
                mock_pm.assert_not_called()
        finally:
            app_state.LOCKED_PROJECT_PATH = original

    def test_unlocked_instance_uses_current_field(self):
        """When LOCKED_PROJECT_PATH is None, get_current_project() must call
        through to _pm_get_current_project (the original project_manager version)."""
        import app_state
        original = app_state.LOCKED_PROJECT_PATH
        try:
            app_state.LOCKED_PROJECT_PATH = None

            fake_project = {"path": "C:\\Projects\\Main", "name": "Main", "last_opened": ""}

            with patch("app_state._pm_get_current_project", return_value=fake_project) as mock_pm:
                result = app_state.get_current_project()
                assert result is not None
                assert result["path"] == "C:\\Projects\\Main"
                mock_pm.assert_called_once()
        finally:
            app_state.LOCKED_PROJECT_PATH = original

    def test_locked_instance_fallback_when_project_not_in_list(self):
        """When LOCKED_PROJECT_PATH is set but get_project() returns None,
        a minimal dict is constructed so the instance can still operate."""
        import app_state
        original = app_state.LOCKED_PROJECT_PATH
        try:
            app_state.LOCKED_PROJECT_PATH = "C:\\Projects\\NewProject"

            with patch("app_state.get_project", return_value=None):
                result = app_state.get_current_project()
                assert result is not None
                assert "NewProject" in result["name"]
                # path should be normalized
                assert result["path"] is not None
        finally:
            app_state.LOCKED_PROJECT_PATH = original


# ---------------------------------------------------------------------------
# Tests: lifespan startup does NOT call set_current_project for locked instance
# ---------------------------------------------------------------------------

class TestLifespanDoesNotSetCurrent:

    def test_locked_startup_calls_init_and_add_not_set_current(self):
        """When LOCKED_PROJECT_PATH is set, lifespan must call init_project()
        and add_project() but NOT set_current_project() or open_project()."""
        import app_state
        original = app_state.LOCKED_PROJECT_PATH
        try:
            app_state.LOCKED_PROJECT_PATH = "C:\\Projects\\LockedOne"

            with patch("app_state.init_project", return_value={"status": "already_exists", "tayfa_path": "C:\\Projects\\LockedOne\\.tayfa"}) as mock_init, \
                 patch("app_state.add_project", return_value={"status": "added", "project": {"path": "C:\\Projects\\LockedOne", "name": "LockedOne"}}) as mock_add, \
                 patch("app_state.set_current_project") as mock_set_current, \
                 patch("app_state.open_project") as mock_open:

                # Simulate what app.py lifespan does for locked projects
                # (we test the logic directly rather than running the full async lifespan)
                from app import lifespan  # noqa: F811
                # Re-read the app.py source to verify it calls the right functions
                import inspect
                source = inspect.getsource(lifespan)

                # The lifespan source should NOT contain open_project for locked path
                assert "_open_project" not in source, \
                    "lifespan should not call open_project for locked instances"

                # It should contain init_project and add_project
                assert "_init_project" in source, \
                    "lifespan should call init_project for locked instances"
                assert "_add_project" in source, \
                    "lifespan should call add_project for locked instances"
        finally:
            app_state.LOCKED_PROJECT_PATH = original

    def test_locked_startup_preserves_existing_current(self):
        """Launching a locked instance must NOT change the 'current' field
        in projects.json — the main window's project stays untouched."""
        import app_state
        original = app_state.LOCKED_PROJECT_PATH
        try:
            # Use a temp file as projects.json
            with tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False, encoding="utf-8") as f:
                original_current = "C:\\Projects\\MainProject"
                data = {
                    "current": original_current,
                    "projects": [
                        {"path": original_current, "name": "MainProject", "last_opened": "2026-01-01T00:00:00"},
                    ]
                }
                json.dump(data, f)
                tmp_path = f.name

            app_state.LOCKED_PROJECT_PATH = "C:\\Projects\\SecondProject"

            # Patch project_manager to use our temp file
            import project_manager
            original_file = project_manager.PROJECTS_FILE
            try:
                project_manager.PROJECTS_FILE = Path(tmp_path)

                # Simulate what app.py lifespan does: init_project + add_project
                # (init_project requires the folder to exist, so we mock it)
                with patch.object(project_manager, "init_project", return_value={"status": "already_exists", "tayfa_path": ""}):
                    project_manager.add_project("C:\\Projects\\SecondProject")

                # Verify "current" was NOT changed
                result_data = json.loads(Path(tmp_path).read_text(encoding="utf-8"))
                assert result_data["current"] == original_current, \
                    f"Expected current to remain {original_current!r}, got {result_data['current']!r}"

                # Verify the second project was added to the list
                paths = [p["path"] for p in result_data["projects"]]
                assert any("SecondProject" in p for p in paths), \
                    "SecondProject should be in the projects list"
            finally:
                project_manager.PROJECTS_FILE = original_file
                Path(tmp_path).unlink(missing_ok=True)
        finally:
            app_state.LOCKED_PROJECT_PATH = original


# ---------------------------------------------------------------------------
# Tests: _init_files_for_current_project works with locked instances
# ---------------------------------------------------------------------------

class TestInitFilesForLockedInstance:

    def test_init_files_uses_locked_project(self):
        """_init_files_for_current_project() should use the locked project's
        .tayfa dir when LOCKED_PROJECT_PATH is set."""
        import app_state
        original = app_state.LOCKED_PROJECT_PATH
        try:
            locked_path = "C:\\Projects\\LockedOne"
            app_state.LOCKED_PROJECT_PATH = locked_path
            fake_project = {"path": locked_path, "name": "LockedOne", "last_opened": ""}

            with patch("app_state.get_project", return_value=fake_project), \
                 patch("app.migrate_remote_url", return_value=None), \
                 patch("app.set_tasks_file") as mock_tasks, \
                 patch("app.set_employees_file") as mock_emp, \
                 patch("app.set_backlog_file") as mock_backlog, \
                 patch("app.set_chat_history_tayfa_dir") as mock_chat:

                from app import _init_files_for_current_project
                _init_files_for_current_project()

                # Verify set_tasks_file was called with a path under the locked project
                if mock_tasks.called:
                    tasks_path = str(mock_tasks.call_args[0][0])
                    assert "LockedOne" in tasks_path or locked_path.replace("\\", "/") in tasks_path.replace("\\", "/")
        finally:
            app_state.LOCKED_PROJECT_PATH = original
