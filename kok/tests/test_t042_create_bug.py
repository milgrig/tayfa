"""
T042: Tests for create_bug() and CLI create-bug command.

Verifies that:
- next_bug_id backward compat in _load()
- create_bug() generates B001, B002, ... IDs
- Bug has task_type='bug' and related_task fields
- Bug is stored in data['tasks'] alongside regular tasks
- next_bug_id increments correctly
- Discussion file is created for bugs
- _update_finalize_depends is called when sprint_id is set
- CLI create-bug command works
- Bugs follow same status flow as tasks (new -> done)
"""
import json
import subprocess
import sys
from pathlib import Path

import pytest

# ---------------------------------------------------------------------------
# Path helpers
# ---------------------------------------------------------------------------

_KOK_DIR = Path(__file__).resolve().parents[1]
_TEMPLATE_COMMON = _KOK_DIR / "template_tayfa" / "common"

if str(_TEMPLATE_COMMON) not in sys.path:
    sys.path.insert(0, str(_TEMPLATE_COMMON))

import task_manager as tm  # noqa: E402


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture(autouse=True)
def tmp_tasks(tmp_path, monkeypatch):
    """Point task_manager at a temp directory for isolation."""
    tasks_file = tmp_path / "tasks.json"
    discussions_dir = tmp_path / "discussions"
    monkeypatch.setattr(tm, "TASKS_FILE", tasks_file)
    monkeypatch.setattr(tm, "DISCUSSIONS_DIR", discussions_dir)
    yield tmp_path


# ---------------------------------------------------------------------------
# _load() backward compatibility
# ---------------------------------------------------------------------------

def test_load_fresh_file_has_next_bug_id(tmp_tasks):
    """Fresh _load() returns next_bug_id=1."""
    data = tm._load()
    assert data["next_bug_id"] == 1


def test_load_existing_file_without_next_bug_id(tmp_tasks):
    """Existing tasks.json without next_bug_id gets it added as 1."""
    tasks_file = tmp_tasks / "tasks.json"
    tasks_file.write_text(json.dumps({
        "tasks": [], "sprints": [], "next_id": 5, "next_sprint_id": 2
    }), encoding="utf-8")
    data = tm._load()
    assert data["next_bug_id"] == 1
    assert data["next_id"] == 5  # other fields preserved


def test_load_existing_file_with_next_bug_id(tmp_tasks):
    """Existing tasks.json with next_bug_id preserves the value."""
    tasks_file = tmp_tasks / "tasks.json"
    tasks_file.write_text(json.dumps({
        "tasks": [], "sprints": [], "next_id": 5, "next_sprint_id": 2, "next_bug_id": 7
    }), encoding="utf-8")
    data = tm._load()
    assert data["next_bug_id"] == 7


# ---------------------------------------------------------------------------
# create_bug() function
# ---------------------------------------------------------------------------

def test_create_bug_basic(tmp_tasks):
    """Basic bug creation returns correct structure."""
    bug = tm.create_bug(
        title="Login button broken",
        description="Clicking login does nothing",
        author="tester",
        executor="developer",
    )
    assert bug["id"] == "B001"
    assert bug["title"] == "Login button broken"
    assert bug["description"] == "Clicking login does nothing"
    assert bug["status"] == "new"
    assert bug["author"] == "tester"
    assert bug["executor"] == "developer"
    assert bug["result"] == ""
    assert bug["task_type"] == "bug"
    assert bug["related_task"] == ""
    assert bug["sprint_id"] == ""
    assert bug["depends_on"] == []
    assert "created_at" in bug
    assert "updated_at" in bug


def test_create_bug_with_related_task(tmp_tasks):
    """Bug with related_task field."""
    bug = tm.create_bug(
        title="Test failure",
        description="Tests fail after T040 changes",
        author="tester",
        executor="developer",
        related_task="T040",
    )
    assert bug["related_task"] == "T040"


def test_create_bug_with_sprint(tmp_tasks):
    """Bug linked to a sprint."""
    bug = tm.create_bug(
        title="Sprint bug",
        description="Found during sprint",
        author="tester",
        executor="developer",
        sprint_id="S007",
    )
    assert bug["sprint_id"] == "S007"


def test_create_bug_id_sequence(tmp_tasks):
    """Bug IDs increment: B001, B002, B003."""
    b1 = tm.create_bug("Bug 1", "d1", "tester", "dev")
    b2 = tm.create_bug("Bug 2", "d2", "tester", "dev")
    b3 = tm.create_bug("Bug 3", "d3", "tester", "dev")
    assert b1["id"] == "B001"
    assert b2["id"] == "B002"
    assert b3["id"] == "B003"


def test_create_bug_increments_next_bug_id(tmp_tasks):
    """next_bug_id in data increments after each bug creation."""
    tm.create_bug("Bug 1", "d1", "tester", "dev")
    data = tm._load()
    assert data["next_bug_id"] == 2

    tm.create_bug("Bug 2", "d2", "tester", "dev")
    data = tm._load()
    assert data["next_bug_id"] == 3


def test_create_bug_does_not_affect_next_id(tmp_tasks):
    """Bug creation should NOT increment next_id (used for tasks)."""
    data_before = tm._load()
    next_id_before = data_before["next_id"]

    tm.create_bug("Bug", "desc", "tester", "dev")

    data_after = tm._load()
    assert data_after["next_id"] == next_id_before


def test_bug_stored_alongside_tasks(tmp_tasks):
    """Bugs are stored in the same data['tasks'] array as regular tasks."""
    task = tm.create_task("Task 1", "d1", "boss", "dev")
    bug = tm.create_bug("Bug 1", "d1", "tester", "dev")

    data = tm._load()
    assert len(data["tasks"]) == 2
    ids = [t["id"] for t in data["tasks"]]
    assert task["id"] in ids
    assert bug["id"] in ids


def test_bug_found_by_get_task(tmp_tasks):
    """Bugs can be retrieved using get_task()."""
    bug = tm.create_bug("Bug 1", "d1", "tester", "dev")
    found = tm.get_task(bug["id"])
    assert found is not None
    assert found["id"] == bug["id"]
    assert found["task_type"] == "bug"


def test_bug_found_by_get_tasks(tmp_tasks):
    """Bugs appear in get_tasks() results."""
    tm.create_task("Task 1", "d1", "boss", "dev")
    tm.create_bug("Bug 1", "d1", "tester", "dev")

    all_tasks = tm.get_tasks()
    assert len(all_tasks) == 2

    new_tasks = tm.get_tasks(status="new")
    assert len(new_tasks) == 2


def test_bug_status_update(tmp_tasks):
    """Bug status can be updated like a regular task."""
    bug = tm.create_bug("Bug 1", "d1", "tester", "dev")
    result = tm.update_task_status(bug["id"], "done")
    assert result["status"] == "done"
    assert result["old_status"] == "new"


def test_bug_result_update(tmp_tasks):
    """Bug result can be set like a regular task."""
    bug = tm.create_bug("Bug 1", "d1", "tester", "dev")
    result = tm.set_task_result(bug["id"], "Fixed the login button")
    assert result["result"] == "Fixed the login button"


def test_create_bug_creates_discussion_file(tmp_tasks):
    """Discussion file is created for the bug."""
    bug = tm.create_bug("Bug 1", "desc1", "tester", "dev")
    discussion_file = tmp_tasks / "discussions" / f"{bug['id']}.md"
    assert discussion_file.exists()
    content = discussion_file.read_text(encoding="utf-8")
    assert bug["id"] in content
    assert "Bug 1" in content


def test_create_bug_updates_finalize_depends(tmp_tasks):
    """When sprint_id is set, finalize task depends_on is updated to include the bug."""
    # Create a sprint first (manually to avoid git branch issues)
    data = tm._load()
    sprint_id = "S001"
    finalize_id = f"T{data['next_id']:03d}"
    data["sprints"].append({
        "id": sprint_id, "title": "Test Sprint", "status": "active",
        "finalize_task_id": finalize_id,
        "created_at": tm._now(), "updated_at": tm._now(),
    })
    data["tasks"].append({
        "id": finalize_id, "title": "Finalize sprint", "status": "new",
        "author": "boss", "executor": "boss", "result": "",
        "sprint_id": sprint_id, "depends_on": [], "is_finalize": True,
        "created_at": tm._now(), "updated_at": tm._now(),
    })
    data["next_id"] += 1
    tm._save(data)

    # Create a regular task in the sprint
    task = tm.create_task("Task 1", "d1", "boss", "dev", sprint_id=sprint_id)

    # Create a bug in the same sprint
    bug = tm.create_bug("Bug 1", "d1", "tester", "dev", sprint_id=sprint_id)

    # Check finalize task depends_on
    data = tm._load()
    finalize = None
    for t in data["tasks"]:
        if t["id"] == finalize_id:
            finalize = t
            break

    assert finalize is not None
    assert task["id"] in finalize["depends_on"]
    assert bug["id"] in finalize["depends_on"]


def test_bug_get_next_agent(tmp_tasks):
    """get_next_agent works for bugs just like tasks."""
    bug = tm.create_bug("Bug 1", "d1", "tester", "developer")
    result = tm.get_next_agent(bug["id"])
    assert result is not None
    assert result["agent"] == "developer"
    assert result["role"] == "executor"


# ---------------------------------------------------------------------------
# CLI create-bug command
# ---------------------------------------------------------------------------

def test_cli_create_bug(tmp_tasks):
    """CLI create-bug command creates a bug and outputs JSON."""
    result = subprocess.run(
        [
            sys.executable, str(_TEMPLATE_COMMON / "task_manager.py"),
            "create-bug", "CLI Bug Title", "CLI Bug Description",
            "--author", "tester",
            "--executor", "developer",
        ],
        capture_output=True,
        text=True,
        encoding="utf-8",
        env={**__import__("os").environ, "PYTHONIOENCODING": "utf-8"},
        cwd=str(tmp_tasks),
    )
    assert result.returncode == 0, f"stderr: {result.stderr}"
    output = json.loads(result.stdout)
    assert output["id"] == "B001"
    assert output["title"] == "CLI Bug Title"
    assert output["description"] == "CLI Bug Description"
    assert output["task_type"] == "bug"
    assert output["author"] == "tester"
    assert output["executor"] == "developer"


def test_cli_create_bug_with_sprint_and_related(tmp_tasks):
    """CLI create-bug with --sprint and --related-task flags."""
    result = subprocess.run(
        [
            sys.executable, str(_TEMPLATE_COMMON / "task_manager.py"),
            "create-bug", "Sprint Bug", "Found in T040",
            "--author", "tester",
            "--executor", "developer",
            "--sprint", "S007",
            "--related-task", "T040",
        ],
        capture_output=True,
        text=True,
        encoding="utf-8",
        env={**__import__("os").environ, "PYTHONIOENCODING": "utf-8"},
        cwd=str(tmp_tasks),
    )
    assert result.returncode == 0, f"stderr: {result.stderr}"
    output = json.loads(result.stdout)
    assert output["sprint_id"] == "S007"
    assert output["related_task"] == "T040"
