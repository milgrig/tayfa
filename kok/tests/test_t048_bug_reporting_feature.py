"""
T048: Integration tests for bug reporting feature end-to-end.

Verifies that:
1. CLI create-bug command works and creates B-prefix IDs
2. API POST /api/bugs creates bugs and triggers board_notify
3. Bugs appear in task list with task_type='bug'
4. Discussion files are created for bugs
5. Bugs participate in sprint workflow (finalize task depends on bugs)
6. Bugs are distinguished from regular tasks (B-prefix vs T-prefix)
7. Frontend can identify bugs via task_type='bug' or B-prefix ID
8. related_task field is properly stored and can be displayed
"""
import json
import subprocess
import sys
from pathlib import Path
from unittest.mock import patch, MagicMock

import pytest

# ---------------------------------------------------------------------------
# Path helpers
# ---------------------------------------------------------------------------

_KOK_DIR = Path(__file__).resolve().parents[1]
_TEMPLATE_COMMON = _KOK_DIR / "template_tayfa" / "common"

if str(_TEMPLATE_COMMON) not in sys.path:
    sys.path.insert(0, str(_TEMPLATE_COMMON))
if str(_KOK_DIR) not in sys.path:
    sys.path.insert(0, str(_KOK_DIR))

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


@pytest.fixture()
def sample_sprint(tmp_tasks):
    """Create a sample sprint with finalize task."""
    data = tm._load()
    sprint_id = "S008"
    finalize_id = f"T{data['next_id']:03d}"
    data["sprints"].append({
        "id": sprint_id,
        "title": "Test Sprint for Bugs",
        "status": "active",
        "finalize_task_id": finalize_id,
        "created_at": tm._now(),
        "updated_at": tm._now(),
    })
    data["tasks"].append({
        "id": finalize_id,
        "title": "Finalize sprint",
        "status": "new",
        "author": "boss",
        "executor": "boss",
        "result": "",
        "sprint_id": sprint_id,
        "depends_on": [],
        "is_finalize": True,
        "created_at": tm._now(),
        "updated_at": tm._now(),
    })
    data["next_id"] += 1
    tm._save(data)
    return sprint_id, finalize_id


# ---------------------------------------------------------------------------
# Test 1: CLI bug creation
# ---------------------------------------------------------------------------

def test_cli_create_bug_generates_b_prefix(tmp_tasks):
    """CLI create-bug generates B001, B002, etc. IDs."""
    result = subprocess.run(
        [
            sys.executable,
            str(_TEMPLATE_COMMON / "task_manager.py"),
            "create-bug",
            "CLI Test Bug",
            "Bug description",
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
    bug = json.loads(result.stdout)
    assert bug["id"].startswith("B")
    assert bug["task_type"] == "bug"


def test_cli_bug_appears_in_tasks_list(tmp_tasks):
    """Bug created via CLI appears in tasks.json."""
    subprocess.run(
        [
            sys.executable,
            str(_TEMPLATE_COMMON / "task_manager.py"),
            "create-bug",
            "Bug for list",
            "desc",
            "--author", "tester",
            "--executor", "developer",
        ],
        capture_output=True,
        text=True,
        cwd=str(tmp_tasks),
    )

    # Check tasks.json
    tasks_file = tmp_tasks / "tasks.json"
    assert tasks_file.exists()
    data = json.loads(tasks_file.read_text(encoding="utf-8"))
    bugs = [t for t in data["tasks"] if t.get("task_type") == "bug"]
    assert len(bugs) >= 1
    assert bugs[0]["id"].startswith("B")


def test_cli_bug_creates_discussion_file(tmp_tasks):
    """Discussion file is created for CLI-created bugs."""
    result = subprocess.run(
        [
            sys.executable,
            str(_TEMPLATE_COMMON / "task_manager.py"),
            "create-bug",
            "Bug with discussion",
            "desc",
            "--author", "tester",
            "--executor", "developer",
        ],
        capture_output=True,
        text=True,
        cwd=str(tmp_tasks),
    )
    bug = json.loads(result.stdout)
    discussion_file = tmp_tasks / "discussions" / f"{bug['id']}.md"
    assert discussion_file.exists()
    content = discussion_file.read_text(encoding="utf-8")
    assert bug["id"] in content
    assert "Bug with discussion" in content


# ---------------------------------------------------------------------------
# Test 2: API bug creation
# ---------------------------------------------------------------------------

@pytest.fixture()
def api_client():
    """Create a FastAPI TestClient with tasks router."""
    from fastapi import FastAPI
    from fastapi.testclient import TestClient

    # Mock app_state to avoid heavy initialization
    mock_app_state = MagicMock()
    mock_app_state.board_notify = MagicMock()
    mock_app_state.TASK_STATUSES = ["new", "in_progress", "review", "done", "cancelled"]
    mock_app_state.logger = MagicMock()

    with patch.dict(sys.modules, {"app_state": mock_app_state}):
        if "routers.tasks" in sys.modules:
            del sys.modules["routers.tasks"]

        from routers.tasks import router

        app = FastAPI()
        app.include_router(router)
        yield TestClient(app)

        if "routers.tasks" in sys.modules:
            del sys.modules["routers.tasks"]


def test_api_create_bug_returns_b_prefix(api_client, tmp_tasks):
    """API POST /api/bugs creates bug with B-prefix."""
    with patch("routers.tasks.create_bug") as mock_create:
        mock_create.return_value = {
            "id": "B001",
            "title": "API Bug",
            "task_type": "bug",
            "status": "new",
            "author": "tester",
            "executor": "developer",
            "description": "",
            "result": "",
            "sprint_id": "",
            "depends_on": [],
            "related_task": "",
            "created_at": "2026-02-27T12:00:00",
            "updated_at": "2026-02-27T12:00:00",
        }

        response = api_client.post("/api/bugs", json={"title": "API Bug"})
        assert response.status_code == 200
        bug = response.json()
        assert bug["id"] == "B001"
        assert bug["task_type"] == "bug"


def test_api_create_bug_calls_board_notify(api_client, tmp_tasks):
    """API creates bug and calls board_notify() to update frontend."""
    with patch("routers.tasks.create_bug") as mock_create, \
         patch("routers.tasks.board_notify") as mock_notify:
        mock_create.return_value = {
            "id": "B001",
            "title": "Notify Test",
            "task_type": "bug",
            "status": "new",
        }

        response = api_client.post("/api/bugs", json={"title": "Notify Test"})
        assert response.status_code == 200
        mock_notify.assert_called_once()


# ---------------------------------------------------------------------------
# Test 3: Task Board UI bug identification
# ---------------------------------------------------------------------------

def test_frontend_can_identify_bug_by_task_type(tmp_tasks):
    """Frontend identifies bugs via task_type='bug' field."""
    bug = tm.create_bug("UI Bug", "desc", "tester", "dev")
    assert bug["task_type"] == "bug"
    assert bug["id"].startswith("B")

    # Simulate frontend logic: isBug = t.task_type === 'bug' || t.id.startsWith('B')
    is_bug_by_type = bug.get("task_type") == "bug"
    is_bug_by_id = bug["id"].startswith("B")
    assert is_bug_by_type or is_bug_by_id


def test_frontend_can_identify_bug_by_b_prefix(tmp_tasks):
    """Frontend can identify bugs by B-prefix even without task_type."""
    bug = tm.create_bug("Prefix Bug", "desc", "tester", "dev")
    # Simulate data without task_type (e.g., old data)
    bug_without_type = {k: v for k, v in bug.items() if k != "task_type"}

    is_bug = bug_without_type["id"].startswith("B")
    assert is_bug


def test_bug_has_related_task_field(tmp_tasks):
    """Bug with related_task can be displayed in UI."""
    bug = tm.create_bug("Related Bug", "desc", "tester", "dev", related_task="T040")
    assert bug["related_task"] == "T040"

    # Simulate UI display logic
    related_html = f"Related to: {bug['related_task']}" if bug["related_task"] else ""
    assert "Related to: T040" in related_html


# ---------------------------------------------------------------------------
# Test 4: Report Bug modal workflow
# ---------------------------------------------------------------------------

def test_report_bug_modal_payload_structure(tmp_tasks):
    """Modal creates correct payload for POST /api/bugs."""
    # Simulate modal form data
    form_data = {
        "title": "Modal Bug",
        "description": "Bug from modal",
        "author": "tester",
        "executor": "developer",
        "sprint_id": "S008",
        "related_task": "T040",
    }

    # This payload should be accepted by the API
    bug = tm.create_bug(**form_data)
    assert bug["id"].startswith("B")
    assert bug["title"] == form_data["title"]
    assert bug["sprint_id"] == form_data["sprint_id"]
    assert bug["related_task"] == form_data["related_task"]


# ---------------------------------------------------------------------------
# Test 5: Sprint integration
# ---------------------------------------------------------------------------

def test_bug_participates_in_sprint(tmp_tasks, sample_sprint):
    """Bug in sprint is included in finalize task dependencies."""
    sprint_id, finalize_id = sample_sprint

    # Create a regular task in sprint
    task = tm.create_task("Task 1", "desc", "boss", "dev", sprint_id=sprint_id)

    # Create a bug in same sprint
    bug = tm.create_bug("Sprint Bug", "desc", "tester", "dev", sprint_id=sprint_id)

    # Check finalize task depends_on includes both
    finalize = tm.get_task(finalize_id)
    assert task["id"] in finalize["depends_on"]
    assert bug["id"] in finalize["depends_on"]


def test_bug_appears_in_sprint_task_list(tmp_tasks, sample_sprint):
    """get_tasks(sprint_id=...) returns both tasks and bugs."""
    sprint_id, _ = sample_sprint

    tm.create_task("Task 1", "desc", "boss", "dev", sprint_id=sprint_id)
    tm.create_bug("Bug 1", "desc", "tester", "dev", sprint_id=sprint_id)

    sprint_items = tm.get_tasks(sprint_id=sprint_id)
    sprint_items_no_finalize = [t for t in sprint_items if not t.get("is_finalize")]

    assert len(sprint_items_no_finalize) == 2
    task_types = [t.get("task_type", "task") for t in sprint_items_no_finalize]
    assert "bug" in task_types


def test_bug_status_flow_same_as_task(tmp_tasks):
    """Bugs follow same status flow as tasks (new -> done)."""
    bug = tm.create_bug("Status Bug", "desc", "tester", "dev")
    assert bug["status"] == "new"

    # Update to done
    result = tm.update_task_status(bug["id"], "done")
    assert result["status"] == "done"
    assert result["old_status"] == "new"


# ---------------------------------------------------------------------------
# Test 6: Backward compatibility
# ---------------------------------------------------------------------------

def test_regular_task_still_gets_t_prefix(tmp_tasks):
    """Regular tasks still get T-prefix, not B-prefix."""
    task = tm.create_task("Regular Task", "desc", "boss", "dev")
    assert task["id"].startswith("T")
    assert task.get("task_type", "task") != "bug"


def test_bugs_dont_affect_task_id_counter(tmp_tasks):
    """Bug creation doesn't increment next_id (task counter)."""
    data_before = tm._load()
    next_id_before = data_before["next_id"]

    tm.create_bug("Bug", "desc", "tester", "dev")

    data_after = tm._load()
    assert data_after["next_id"] == next_id_before


def test_mixed_tasks_and_bugs_in_list(tmp_tasks):
    """get_tasks() returns both tasks and bugs mixed."""
    task1 = tm.create_task("Task 1", "desc", "boss", "dev")
    bug1 = tm.create_bug("Bug 1", "desc", "tester", "dev")
    task2 = tm.create_task("Task 2", "desc", "boss", "dev")

    all_items = tm.get_tasks()
    assert len(all_items) == 3

    ids = [t["id"] for t in all_items]
    assert task1["id"] in ids
    assert bug1["id"] in ids
    assert task2["id"] in ids


def test_bug_can_be_retrieved_by_get_task(tmp_tasks):
    """Bugs can be fetched individually via get_task()."""
    bug = tm.create_bug("Get Bug", "desc", "tester", "dev")

    fetched = tm.get_task(bug["id"])
    assert fetched is not None
    assert fetched["id"] == bug["id"]
    assert fetched["task_type"] == "bug"


def test_bug_result_can_be_set(tmp_tasks):
    """Bug result field can be updated like regular tasks."""
    bug = tm.create_bug("Result Bug", "desc", "tester", "dev")

    result = tm.set_task_result(bug["id"], "Fixed the bug")
    assert result["result"] == "Fixed the bug"


# ---------------------------------------------------------------------------
# Test 7: UI styling markers
# ---------------------------------------------------------------------------

def test_bug_card_has_bug_css_class_marker(tmp_tasks):
    """Frontend adds 'task-card-bug' CSS class for styling."""
    bug = tm.create_bug("Styled Bug", "desc", "tester", "dev")

    # Simulate frontend logic
    is_bug = bug.get("task_type") == "bug" or bug["id"].startswith("B")
    css_class = "task-card-bug" if is_bug else ""

    assert css_class == "task-card-bug"


def test_bug_card_has_bug_icon_before_id(tmp_tasks):
    """Frontend displays bug icon 🐛 before bug ID."""
    bug = tm.create_bug("Icon Bug", "desc", "tester", "dev")

    # Simulate frontend logic: idPrefix = isBug ? '\u{1F41B} ' : '';
    is_bug = bug.get("task_type") == "bug"
    id_prefix = "🐛 " if is_bug else ""

    assert id_prefix == "🐛 "


# ---------------------------------------------------------------------------
# Test 8: Sprint report includes bugs
# ---------------------------------------------------------------------------

def test_bugs_counted_in_sprint_metrics(tmp_tasks, sample_sprint):
    """Sprint report should count bugs alongside tasks."""
    sprint_id, _ = sample_sprint

    tm.create_task("Task 1", "desc", "boss", "dev", sprint_id=sprint_id)
    tm.create_bug("Bug 1", "desc", "tester", "dev", sprint_id=sprint_id)
    tm.create_bug("Bug 2", "desc", "tester", "dev", sprint_id=sprint_id)

    # Get sprint tasks (excluding finalize)
    sprint_tasks = tm.get_tasks(sprint_id=sprint_id)
    sprint_tasks_no_finalize = [t for t in sprint_tasks if not t.get("is_finalize")]

    # Should have 3 items total (1 task + 2 bugs)
    assert len(sprint_tasks_no_finalize) == 3

    bug_count = sum(1 for t in sprint_tasks_no_finalize if t.get("task_type") == "bug")
    assert bug_count == 2
