"""Tests for T018: Sprint readiness flag and auto-launch.

Tests create_sprint with ready_to_execute, update_sprint, and
the autoLaunchSprints setting.
"""

import json
import sys
from pathlib import Path

import pytest

# Add template_tayfa/common to path (same as app.py does)
KOK_DIR = Path(__file__).resolve().parent.parent
TEMPLATE_COMMON = KOK_DIR / "template_tayfa" / "common"
sys.path.insert(0, str(TEMPLATE_COMMON))
sys.path.insert(0, str(KOK_DIR))


# ---------------------------------------------------------------------------
# Fixture: temp tasks.json
# ---------------------------------------------------------------------------

@pytest.fixture
def tmp_tasks(tmp_path, monkeypatch):
    """Redirect TASKS_FILE to a temp file."""
    import task_manager
    tasks_file = tmp_path / "tasks.json"
    monkeypatch.setattr(task_manager, "TASKS_FILE", tasks_file)
    # Disable git branch creation during tests
    monkeypatch.setattr(task_manager, "_create_sprint_branch",
                        lambda sid: {"success": True, "branch": f"sprint/{sid}"})
    # Disable discussion file creation
    monkeypatch.setattr(task_manager, "DISCUSSIONS_DIR", tmp_path / "discussions")
    return tasks_file


# ---------------------------------------------------------------------------
# Tests: create_sprint with ready_to_execute
# ---------------------------------------------------------------------------

class TestCreateSprintReadyToExecute:

    def test_default_ready_to_execute_is_false(self, tmp_tasks):
        from task_manager import create_sprint
        sprint = create_sprint(title="Test Sprint")
        assert sprint["ready_to_execute"] is False

    def test_ready_to_execute_true(self, tmp_tasks):
        from task_manager import create_sprint
        sprint = create_sprint(title="Ready Sprint", ready_to_execute=True)
        assert sprint["ready_to_execute"] is True

    def test_ready_to_execute_persisted(self, tmp_tasks):
        from task_manager import create_sprint, get_sprint
        sprint = create_sprint(title="Persisted Sprint", ready_to_execute=True)
        loaded = get_sprint(sprint["id"])
        assert loaded is not None
        assert loaded["ready_to_execute"] is True

    def test_backward_compat_missing_field(self, tmp_tasks):
        """Sprints without ready_to_execute field are treated as false."""
        from task_manager import create_sprint, get_sprint
        sprint = create_sprint(title="Old Sprint")
        # Simulate a legacy sprint by removing the field from disk
        data = json.loads(tmp_tasks.read_text(encoding="utf-8"))
        for s in data["sprints"]:
            if s["id"] == sprint["id"]:
                del s["ready_to_execute"]
        tmp_tasks.write_text(json.dumps(data), encoding="utf-8")
        loaded = get_sprint(sprint["id"])
        # Missing field → treated as False by consumers
        assert loaded.get("ready_to_execute", False) is False


# ---------------------------------------------------------------------------
# Tests: update_sprint
# ---------------------------------------------------------------------------

class TestUpdateSprint:

    def test_update_ready_to_execute(self, tmp_tasks):
        from task_manager import create_sprint, update_sprint
        sprint = create_sprint(title="S1")
        assert sprint["ready_to_execute"] is False
        result = update_sprint(sprint["id"], {"ready_to_execute": True})
        assert result["ready_to_execute"] is True

    def test_update_title(self, tmp_tasks):
        from task_manager import create_sprint, update_sprint
        sprint = create_sprint(title="Old Title")
        result = update_sprint(sprint["id"], {"title": "New Title"})
        assert result["title"] == "New Title"

    def test_update_description(self, tmp_tasks):
        from task_manager import create_sprint, update_sprint
        sprint = create_sprint(title="S2")
        result = update_sprint(sprint["id"], {"description": "Updated desc"})
        assert result["description"] == "Updated desc"

    def test_update_does_not_change_status(self, tmp_tasks):
        """Status cannot be changed via update_sprint."""
        from task_manager import create_sprint, update_sprint
        sprint = create_sprint(title="S3")
        result = update_sprint(sprint["id"], {"status": "completed"})
        assert "error" in result

    def test_update_nonexistent_sprint(self, tmp_tasks):
        from task_manager import update_sprint
        result = update_sprint("S999", {"title": "X"})
        assert "error" in result

    def test_update_no_valid_fields(self, tmp_tasks):
        from task_manager import create_sprint, update_sprint
        sprint = create_sprint(title="S4")
        result = update_sprint(sprint["id"], {"invalid_field": 123})
        assert "error" in result

    def test_update_updates_timestamp(self, tmp_tasks):
        from task_manager import create_sprint, update_sprint
        sprint = create_sprint(title="S5")
        old_ts = sprint["updated_at"]
        import time
        time.sleep(0.01)
        result = update_sprint(sprint["id"], {"ready_to_execute": True})
        assert result["updated_at"] >= old_ts


# ---------------------------------------------------------------------------
# Tests: autoLaunchSprints setting
# ---------------------------------------------------------------------------

class TestAutoLaunchSetting:

    @pytest.fixture
    def tmp_settings(self, tmp_path, monkeypatch):
        import settings_manager
        settings_file = tmp_path / "settings.json"
        secret_file = tmp_path / "secret_settings.json"
        monkeypatch.setattr(settings_manager, "SETTINGS_FILE", settings_file)
        monkeypatch.setattr(settings_manager, "SECRET_SETTINGS_FILE", secret_file)
        return settings_file

    def test_default_is_false(self, tmp_settings):
        from settings_manager import load_settings
        settings = load_settings()
        assert settings["autoLaunchSprints"] is False

    def test_save_and_load(self, tmp_settings):
        from settings_manager import update_settings, load_settings
        update_settings({"autoLaunchSprints": True})
        settings = load_settings()
        assert settings["autoLaunchSprints"] is True

    def test_validation_rejects_non_bool(self, tmp_settings):
        from settings_manager import validate_setting
        is_valid, error = validate_setting("autoLaunchSprints", "yes")
        assert is_valid is False
        assert "autoLaunchSprints" in error

    def test_validation_accepts_bool(self, tmp_settings):
        from settings_manager import validate_setting
        is_valid, _ = validate_setting("autoLaunchSprints", True)
        assert is_valid is True
        is_valid, _ = validate_setting("autoLaunchSprints", False)
        assert is_valid is True
