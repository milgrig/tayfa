"""
T050: Tests for cross-project agent lookup fix.

Verifies that:
- create_task() stores project_path in the task dict
- create_bug() stores project_path in the task dict
- Tasks without project_path default to empty string (backward compat)
- api_trigger_task() uses task's own project_path, not global current project
"""
import json
import sys
from pathlib import Path
from unittest.mock import patch, MagicMock, AsyncMock

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
def _isolate_task_manager(tmp_path):
    """Point task_manager at a temp directory so tests don't touch real data."""
    import task_manager as tm
    tasks_file = tmp_path / "tasks.json"
    discussions_dir = tmp_path / "discussions"
    discussions_dir.mkdir()
    old_tf = tm.TASKS_FILE
    old_dd = tm.DISCUSSIONS_DIR
    tm.TASKS_FILE = tasks_file
    tm.DISCUSSIONS_DIR = discussions_dir
    yield
    tm.TASKS_FILE = old_tf
    tm.DISCUSSIONS_DIR = old_dd


# ---------------------------------------------------------------------------
# Tests: create_task with project_path
# ---------------------------------------------------------------------------


class TestCreateTaskProjectPath:
    """Tests for project_path field in create_task()."""

    def test_create_task_stores_project_path(self):
        import task_manager as tm
        task = tm.create_task(
            title="Test",
            description="desc",
            author="boss",
            executor="dev",
            project_path="/projects/AndroidGame",
        )
        assert task["project_path"] == "/projects/AndroidGame"

    def test_create_task_default_project_path_empty(self):
        import task_manager as tm
        task = tm.create_task(
            title="Test",
            description="desc",
            author="boss",
            executor="dev",
        )
        assert task["project_path"] == ""

    def test_create_task_project_path_persisted(self, tmp_path):
        import task_manager as tm
        task = tm.create_task(
            title="Test",
            description="desc",
            author="boss",
            executor="dev",
            project_path="C:\\Projects\\MyApp",
        )
        # Reload from disk
        data = json.loads(tm.TASKS_FILE.read_text(encoding="utf-8"))
        stored = [t for t in data["tasks"] if t["id"] == task["id"]]
        assert len(stored) == 1
        assert stored[0]["project_path"] == "C:\\Projects\\MyApp"


class TestCreateBugProjectPath:
    """Tests for project_path field in create_bug()."""

    def test_create_bug_stores_project_path(self):
        import task_manager as tm
        bug = tm.create_bug(
            title="Crash",
            description="desc",
            author="tester",
            executor="dev",
            project_path="/projects/AndroidGame",
        )
        assert bug["project_path"] == "/projects/AndroidGame"

    def test_create_bug_default_project_path_empty(self):
        import task_manager as tm
        bug = tm.create_bug(
            title="Crash",
            description="desc",
            author="tester",
            executor="dev",
        )
        assert bug["project_path"] == ""


class TestBackwardCompat:
    """Tests that tasks without project_path still work (backward compat)."""

    def test_old_task_without_project_path_field(self, tmp_path):
        """Simulate loading a task created before T050 (no project_path field)."""
        import task_manager as tm
        # Create a tasks.json with an old-style task (no project_path)
        old_data = {
            "next_id": 2,
            "next_sprint_id": 1,
            "next_bug_id": 1,
            "sprints": [],
            "tasks": [
                {
                    "id": "T001",
                    "title": "Old task",
                    "description": "",
                    "status": "new",
                    "author": "boss",
                    "executor": "dev",
                    "result": "",
                    "sprint_id": "",
                    "depends_on": [],
                    "created_at": "2025-01-01T00:00:00",
                    "updated_at": "2025-01-01T00:00:00",
                }
            ],
        }
        tm.TASKS_FILE.write_text(json.dumps(old_data), encoding="utf-8")

        task = tm.get_task("T001")
        assert task is not None
        # Old tasks have no project_path key — .get() returns None
        assert task.get("project_path") is None or task.get("project_path") == ""


class TestCreateBacklogProjectPath:
    """Tests that create_backlog passes project_path through."""

    def test_backlog_passes_project_path(self):
        import task_manager as tm
        tasks = tm.create_backlog([
            {
                "title": "Task A",
                "description": "",
                "author": "boss",
                "executor": "dev",
                "project_path": "/projects/GameProject",
            },
            {
                "title": "Task B",
                "description": "",
                "author": "boss",
                "executor": "dev",
            },
        ])
        assert tasks[0]["project_path"] == "/projects/GameProject"
        assert tasks[1]["project_path"] == ""


class TestTriggerTaskProjectPath:
    """Tests that api_trigger_task uses the task's own project_path."""

    def test_task_project_path_used_over_global(self):
        """Verify that the task's project_path is preferred over get_project_path_for_scoping()."""
        # Read the source code of api_trigger_task to verify the fix
        tasks_py = _KOK_DIR / "routers" / "tasks.py"
        source = tasks_py.read_text(encoding="utf-8")

        # The fix: task_project_path should be derived from task, not from global
        assert 'task.get("project_path")' in source, \
            "api_trigger_task should read project_path from the task dict"
        assert 'task_project_path = task.get("project_path") or get_project_path_for_scoping()' in source, \
            "Should fallback to get_project_path_for_scoping() when task has no project_path"

    def test_stream_uses_task_project_path(self):
        """Verify that stream_claude_api call uses task_project_path, not get_project_path_for_scoping()."""
        tasks_py = _KOK_DIR / "routers" / "tasks.py"
        source = tasks_py.read_text(encoding="utf-8")

        # The stream call should use task_project_path
        assert '"project_path": task_project_path,' in source, \
            "stream_claude_api should receive task_project_path, not get_project_path_for_scoping()"

    def test_create_task_endpoint_stamps_project_path(self):
        """Verify that api_create_tasks passes project_path to create_task."""
        tasks_py = _KOK_DIR / "routers" / "tasks.py"
        source = tasks_py.read_text(encoding="utf-8")

        assert 'project_path=get_project_path_for_scoping()' in source, \
            "create_task call should stamp project_path from current project at creation time"

    def test_create_bug_endpoint_stamps_project_path(self):
        """Verify that api_create_bug passes project_path to create_bug."""
        tasks_py = _KOK_DIR / "routers" / "tasks.py"
        source = tasks_py.read_text(encoding="utf-8")

        # Check it appears at least twice (once for create_task, once for create_bug)
        count = source.count('project_path=get_project_path_for_scoping()')
        assert count >= 2, \
            f"Expected project_path stamped in both create_task and create_bug calls, found {count}"
