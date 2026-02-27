"""
T043: Tests for POST /api/bugs endpoint.

Verifies that:
- POST /api/bugs creates a bug via create_bug()
- title is required (400 if missing)
- board_notify() is called after creation
- All optional fields are forwarded correctly
- Returns created bug dict
"""
import sys
from pathlib import Path
from unittest.mock import patch, MagicMock, ANY

import pytest

# ---------------------------------------------------------------------------
# Path helpers — add kok/ to sys.path so routers/app_state can be imported
# ---------------------------------------------------------------------------

_KOK_DIR = Path(__file__).resolve().parents[1]
if str(_KOK_DIR) not in sys.path:
    sys.path.insert(0, str(_KOK_DIR))


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture()
def client():
    """Create a TestClient with only the tasks router mounted."""
    from fastapi import FastAPI
    from fastapi.testclient import TestClient

    # We need to patch imports before importing the router
    # to avoid heavy app_state initialization
    mock_app_state = MagicMock()
    mock_app_state.board_notify = MagicMock()
    mock_app_state.TASK_STATUSES = ["new", "in_progress", "review", "done", "cancelled"]
    mock_app_state.TASKS_FILE = Path("/tmp/fake_tasks.md")
    mock_app_state.MAX_FAILURE_LOG_ENTRIES = 100
    mock_app_state.logger = MagicMock()
    mock_app_state._MODEL_RUNTIMES = {"opus", "sonnet", "haiku"}
    mock_app_state._CURSOR_MODELS = {"composer"}
    mock_app_state._RETRYABLE_ERRORS = {"timeout", "unavailable"}
    mock_app_state._MAX_RETRY_ATTEMPTS = 3
    mock_app_state._RETRY_DELAY_SEC = 5

    with patch.dict(sys.modules, {"app_state": mock_app_state}):
        # Force re-import of tasks router with mocked app_state
        if "routers.tasks" in sys.modules:
            del sys.modules["routers.tasks"]

        from routers.tasks import router

        app = FastAPI()
        app.include_router(router)
        yield TestClient(app)

        # Clean up
        if "routers.tasks" in sys.modules:
            del sys.modules["routers.tasks"]


@pytest.fixture()
def mock_create_bug():
    """Patch create_bug in the tasks router module."""
    fake_bug = {
        "id": "B001",
        "title": "Test bug",
        "description": "desc",
        "status": "new",
        "author": "tester",
        "executor": "developer",
        "result": "",
        "sprint_id": "",
        "depends_on": [],
        "task_type": "bug",
        "related_task": "",
        "created_at": "2026-02-27T12:00:00",
        "updated_at": "2026-02-27T12:00:00",
    }
    with patch("routers.tasks.create_bug", return_value=fake_bug) as m:
        yield m, fake_bug


@pytest.fixture()
def mock_board_notify():
    """Patch board_notify in the tasks router module."""
    with patch("routers.tasks.board_notify") as m:
        yield m


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


class TestPostApiBugs:
    """Tests for POST /api/bugs endpoint."""

    def test_create_bug_basic(self, client, mock_create_bug, mock_board_notify):
        """Basic bug creation with title only."""
        mock_fn, fake_bug = mock_create_bug
        resp = client.post("/api/bugs", json={"title": "Test bug"})
        assert resp.status_code == 200
        body = resp.json()
        assert body["id"] == "B001"
        assert body["task_type"] == "bug"
        mock_fn.assert_called_once()
        mock_board_notify.assert_called_once()

    def test_create_bug_all_fields(self, client, mock_create_bug, mock_board_notify):
        """Bug creation with all optional fields."""
        mock_fn, fake_bug = mock_create_bug
        payload = {
            "title": "Crash on login",
            "description": "App crashes when logging in",
            "author": "tester",
            "executor": "developer",
            "sprint_id": "S008",
            "related_task": "T040",
        }
        resp = client.post("/api/bugs", json=payload)
        assert resp.status_code == 200
        mock_fn.assert_called_once_with(
            title="Crash on login",
            description="App crashes when logging in",
            author="tester",
            executor="developer",
            sprint_id="S008",
            related_task="T040",
            project_path=ANY,
        )

    def test_create_bug_missing_title_returns_400(self, client, mock_create_bug, mock_board_notify):
        """Missing title should return 400."""
        mock_fn, _ = mock_create_bug
        resp = client.post("/api/bugs", json={"description": "no title"})
        assert resp.status_code == 400
        assert "title" in resp.json()["detail"].lower()
        mock_fn.assert_not_called()
        mock_board_notify.assert_not_called()

    def test_create_bug_empty_title_returns_400(self, client, mock_create_bug, mock_board_notify):
        """Empty title should return 400."""
        mock_fn, _ = mock_create_bug
        resp = client.post("/api/bugs", json={"title": ""})
        assert resp.status_code == 400
        mock_fn.assert_not_called()

    def test_create_bug_no_body_returns_422(self, client, mock_create_bug, mock_board_notify):
        """No JSON body should return 422 (validation error)."""
        resp = client.post("/api/bugs")
        assert resp.status_code == 422

    def test_create_bug_defaults_optional_fields(self, client, mock_create_bug, mock_board_notify):
        """Optional fields default to empty strings."""
        mock_fn, _ = mock_create_bug
        resp = client.post("/api/bugs", json={"title": "Bug title"})
        assert resp.status_code == 200
        mock_fn.assert_called_once_with(
            title="Bug title",
            description="",
            author="",
            executor="",
            sprint_id="",
            related_task="",
            project_path=ANY,
        )

    def test_create_bug_calls_board_notify(self, client, mock_create_bug, mock_board_notify):
        """board_notify() must be called after bug creation."""
        resp = client.post("/api/bugs", json={"title": "Notify bug"})
        assert resp.status_code == 200
        mock_board_notify.assert_called_once()

    def test_create_bug_returns_bug_dict(self, client, mock_create_bug, mock_board_notify):
        """Response should contain the full bug dict from create_bug()."""
        _, fake_bug = mock_create_bug
        resp = client.post("/api/bugs", json={"title": "Test bug"})
        body = resp.json()
        assert body["id"] == fake_bug["id"]
        assert body["title"] == fake_bug["title"]
        assert body["task_type"] == fake_bug["task_type"]
        assert body["related_task"] == fake_bug["related_task"]
        assert body["status"] == "new"
