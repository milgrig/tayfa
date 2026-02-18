"""Tests for T020: Agent error recovery and retry mechanism.

Tests failure logging, error classification, retry logic, failure API endpoints,
api_trigger_task retry behavior, cursor silent-success bug, and file resilience.
"""

import json
import sys
import time
from pathlib import Path
from unittest.mock import patch, MagicMock, AsyncMock
from datetime import datetime

import pytest

# Add kok/ and its dependencies to path
KOK_DIR = Path(__file__).resolve().parent.parent
TEMPLATE_COMMON = KOK_DIR / "template_tayfa" / "common"
sys.path.insert(0, str(TEMPLATE_COMMON))
sys.path.insert(0, str(KOK_DIR))


# ---------------------------------------------------------------------------
# Fixture: mock personel dir for failure log
# ---------------------------------------------------------------------------

@pytest.fixture
def tmp_failures(tmp_path, monkeypatch):
    """Redirect agent_failures.json to a temp directory."""
    common_dir = tmp_path / "common"
    common_dir.mkdir()
    # Patch get_personel_dir to return tmp_path (so common/ is under it)
    import app
    monkeypatch.setattr(app, "get_personel_dir", lambda: tmp_path)
    return common_dir / "agent_failures.json"


# ---------------------------------------------------------------------------
# Tests: log_agent_failure
# ---------------------------------------------------------------------------

class TestLogAgentFailure:

    def test_creates_failure_entry(self, tmp_failures):
        from app import log_agent_failure
        entry = log_agent_failure(
            task_id="T001", agent="dev_1", role="developer",
            runtime="claude", error_type="timeout",
            message="Read timed out", attempt=1,
        )
        assert entry["id"] == "F0001"
        assert entry["task_id"] == "T001"
        assert entry["agent"] == "dev_1"
        assert entry["error_type"] == "timeout"
        assert entry["resolved"] is False
        assert entry["attempt"] == 1
        # File should exist
        assert tmp_failures.exists()

    def test_multiple_failures_increment_id(self, tmp_failures):
        from app import log_agent_failure
        e1 = log_agent_failure("T001", "dev_1", "developer", "claude", "timeout", "err", 1)
        e2 = log_agent_failure("T001", "dev_1", "developer", "claude", "timeout", "err", 2)
        e3 = log_agent_failure("T002", "qa_1", "tester", "claude", "internal", "err", 1)
        assert e1["id"] == "F0001"
        assert e2["id"] == "F0002"
        assert e3["id"] == "F0003"

    def test_fifo_limit(self, tmp_failures, monkeypatch):
        import app
        monkeypatch.setattr(app, "MAX_FAILURE_LOG_ENTRIES", 5)
        from app import log_agent_failure, _load_failures
        for i in range(8):
            log_agent_failure(f"T{i:03d}", "dev", "developer", "claude", "timeout", "err", 1)
        failures = _load_failures()
        assert len(failures) == 5
        # Oldest entries should be trimmed
        assert failures[0]["task_id"] == "T003"

    def test_persisted_to_disk(self, tmp_failures):
        from app import log_agent_failure
        log_agent_failure("T001", "dev_1", "developer", "claude", "internal", "oops", 1)
        data = json.loads(tmp_failures.read_text(encoding="utf-8"))
        assert len(data) == 1
        assert data[0]["task_id"] == "T001"


# ---------------------------------------------------------------------------
# Tests: get_agent_failures
# ---------------------------------------------------------------------------

class TestGetAgentFailures:

    def test_filter_by_task_id(self, tmp_failures):
        from app import log_agent_failure, get_agent_failures
        log_agent_failure("T001", "d", "developer", "claude", "timeout", "e", 1)
        log_agent_failure("T002", "d", "developer", "claude", "internal", "e", 1)
        log_agent_failure("T001", "d", "developer", "claude", "timeout", "e", 2)
        result = get_agent_failures(task_id="T001")
        assert len(result) == 2
        assert all(f["task_id"] == "T001" for f in result)

    def test_filter_by_resolved(self, tmp_failures):
        from app import log_agent_failure, get_agent_failures, resolve_agent_failure
        e1 = log_agent_failure("T001", "d", "developer", "claude", "timeout", "e", 1)
        log_agent_failure("T002", "d", "developer", "claude", "internal", "e", 1)
        resolve_agent_failure(e1["id"])
        unresolved = get_agent_failures(resolved=False)
        assert len(unresolved) == 1
        assert unresolved[0]["task_id"] == "T002"

    def test_no_filters_returns_all(self, tmp_failures):
        from app import log_agent_failure, get_agent_failures
        log_agent_failure("T001", "d", "developer", "claude", "timeout", "e", 1)
        log_agent_failure("T002", "d", "developer", "claude", "internal", "e", 1)
        assert len(get_agent_failures()) == 2


# ---------------------------------------------------------------------------
# Tests: resolve_agent_failure
# ---------------------------------------------------------------------------

class TestResolveAgentFailure:

    def test_resolves_failure(self, tmp_failures):
        from app import log_agent_failure, resolve_agent_failure
        entry = log_agent_failure("T001", "d", "developer", "claude", "timeout", "e", 1)
        resolved = resolve_agent_failure(entry["id"])
        assert resolved is not None
        assert resolved["resolved"] is True

    def test_nonexistent_returns_none(self, tmp_failures):
        from app import resolve_agent_failure
        assert resolve_agent_failure("F9999") is None

    def test_resolve_persisted(self, tmp_failures):
        from app import log_agent_failure, resolve_agent_failure, _load_failures
        entry = log_agent_failure("T001", "d", "developer", "claude", "timeout", "e", 1)
        resolve_agent_failure(entry["id"])
        failures = _load_failures()
        assert failures[0]["resolved"] is True


# ---------------------------------------------------------------------------
# Tests: _classify_error
# ---------------------------------------------------------------------------

class TestClassifyError:

    def test_timeout_from_status_code(self, tmp_failures):
        from app import _classify_error
        from fastapi import HTTPException
        assert _classify_error(HTTPException(status_code=504, detail="Gateway Timeout")) == "timeout"

    def test_timeout_from_detail(self, tmp_failures):
        from app import _classify_error
        from fastapi import HTTPException
        assert _classify_error(HTTPException(status_code=500, detail="request timeout exceeded")) == "timeout"

    def test_unavailable(self, tmp_failures):
        from app import _classify_error
        from fastapi import HTTPException
        assert _classify_error(HTTPException(status_code=503, detail="Service unavailable")) == "unavailable"

    def test_context_overflow(self, tmp_failures):
        from app import _classify_error
        from fastapi import HTTPException
        assert _classify_error(HTTPException(status_code=400, detail="context length exceeded")) == "context_overflow"

    def test_budget(self, tmp_failures):
        from app import _classify_error
        from fastapi import HTTPException
        assert _classify_error(HTTPException(status_code=429, detail="billing limit reached")) == "budget"

    def test_config(self, tmp_failures):
        from app import _classify_error
        from fastapi import HTTPException
        assert _classify_error(HTTPException(status_code=400, detail="Agent not registered")) == "config"

    def test_internal_fallback(self, tmp_failures):
        from app import _classify_error
        from fastapi import HTTPException
        assert _classify_error(HTTPException(status_code=500, detail="Something broke")) == "internal"

    def test_generic_exception(self, tmp_failures):
        from app import _classify_error
        assert _classify_error(RuntimeError("random crash")) == "internal"

    def test_httpx_read_timeout(self, tmp_failures):
        from app import _classify_error
        import httpx
        assert _classify_error(httpx.ReadTimeout("timed out")) == "timeout"

    def test_httpx_connect_error(self, tmp_failures):
        from app import _classify_error
        import httpx
        assert _classify_error(httpx.ConnectError("connection refused")) == "unavailable"


# ---------------------------------------------------------------------------
# Tests: retry logic constants
# ---------------------------------------------------------------------------

class TestRetryConfig:

    def test_retryable_errors(self, tmp_failures):
        from app import _RETRYABLE_ERRORS
        assert "timeout" in _RETRYABLE_ERRORS
        assert "unavailable" in _RETRYABLE_ERRORS
        assert "context_overflow" not in _RETRYABLE_ERRORS
        assert "budget" not in _RETRYABLE_ERRORS
        assert "config" not in _RETRYABLE_ERRORS

    def test_max_retry_attempts(self, tmp_failures):
        from app import _MAX_RETRY_ATTEMPTS
        assert _MAX_RETRY_ATTEMPTS == 3

    def test_retry_delay(self, tmp_failures):
        from app import _RETRY_DELAY_SEC
        assert _RETRY_DELAY_SEC == 5


# ---------------------------------------------------------------------------
# Tests: API endpoints (GET/DELETE /api/agent-failures)
# ---------------------------------------------------------------------------

@pytest.fixture
def client(tmp_failures):
    from fastapi.testclient import TestClient
    from app import app
    return TestClient(app, raise_server_exceptions=False)


class TestAgentFailuresAPI:

    def test_get_empty(self, client, tmp_failures):
        resp = client.get("/api/agent-failures")
        assert resp.status_code == 200
        data = resp.json()
        assert data["failures"] == []
        assert data["count"] == 0

    def test_get_with_entries(self, client, tmp_failures):
        from app import log_agent_failure
        log_agent_failure("T001", "dev1", "developer", "claude", "timeout", "msg1")
        log_agent_failure("T002", "dev2", "developer", "cursor", "internal", "msg2")
        resp = client.get("/api/agent-failures")
        assert resp.status_code == 200
        assert resp.json()["count"] == 2

    def test_get_filter_task_id(self, client, tmp_failures):
        from app import log_agent_failure
        log_agent_failure("T001", "d", "developer", "claude", "timeout", "e")
        log_agent_failure("T002", "d", "developer", "claude", "internal", "e")
        resp = client.get("/api/agent-failures?task_id=T001")
        assert resp.status_code == 200
        data = resp.json()
        assert data["count"] == 1
        assert data["failures"][0]["task_id"] == "T001"

    def test_get_filter_resolved(self, client, tmp_failures):
        from app import log_agent_failure, resolve_agent_failure
        e1 = log_agent_failure("T001", "d", "developer", "claude", "timeout", "e")
        log_agent_failure("T002", "d", "developer", "claude", "internal", "e")
        resolve_agent_failure(e1["id"])
        resp = client.get("/api/agent-failures?resolved=false")
        assert resp.status_code == 200
        data = resp.json()
        assert data["count"] == 1
        assert data["failures"][0]["task_id"] == "T002"

    def test_delete_resolves(self, client, tmp_failures):
        from app import log_agent_failure
        entry = log_agent_failure("T001", "d", "developer", "claude", "timeout", "e")
        resp = client.delete(f"/api/agent-failures/{entry['id']}")
        assert resp.status_code == 200
        assert resp.json()["resolved"] is True

    def test_delete_not_found(self, client, tmp_failures):
        resp = client.delete("/api/agent-failures/F9999")
        assert resp.status_code == 404


# ---------------------------------------------------------------------------
# Tests: api_trigger_task retry behavior
# ---------------------------------------------------------------------------

@pytest.fixture
def mock_task_env(tmp_failures, monkeypatch):
    """Mock out dependencies of api_trigger_task for isolated testing."""
    import app
    # Reset loop-detection counters so tests don't leak state
    app.task_trigger_counts.pop("T001", None)
    mock_task = {
        "id": "T001", "title": "Test task", "description": "desc",
        "status": "in_progress", "result": "",
    }
    monkeypatch.setattr(app, "get_next_agent", lambda tid: {
        "agent": "dev1", "role": "developer", "task": mock_task,
    })
    monkeypatch.setattr(app, "get_employee", lambda name: {"name": name})
    monkeypatch.setattr(app, "save_chat_message", lambda **kw: None)
    monkeypatch.setattr(app, "get_project_path_for_scoping", lambda: "/mock")
    return mock_task


@pytest.mark.asyncio
class TestApiTriggerTaskRetry:

    async def test_success_no_retry(self, mock_task_env, tmp_failures, monkeypatch):
        import app
        monkeypatch.setattr(app, "call_claude_api", AsyncMock(return_value={
            "result": "Done", "cost_usd": 0.01, "num_turns": 5,
        }))
        from app import api_trigger_task
        result = await api_trigger_task("T001", {"runtime": "claude"})
        assert result["success"] is True
        from app import get_agent_failures
        assert len(get_agent_failures()) == 0

    async def test_non_retryable_no_retry(self, mock_task_env, tmp_failures, monkeypatch):
        import app
        from fastapi import HTTPException
        call_count = 0
        async def mock_call(*a, **kw):
            nonlocal call_count
            call_count += 1
            raise HTTPException(status_code=400, detail="Context length overflow")
        monkeypatch.setattr(app, "call_claude_api", mock_call)
        from app import api_trigger_task
        with pytest.raises(HTTPException):
            await api_trigger_task("T001", {"runtime": "claude"})
        assert call_count == 1
        from app import get_agent_failures
        failures = get_agent_failures()
        assert len(failures) == 1
        assert failures[0]["error_type"] == "context_overflow"

    async def test_timeout_retries_3_times(self, mock_task_env, tmp_failures, monkeypatch):
        import app
        from fastapi import HTTPException
        call_count = 0
        async def mock_call(*a, **kw):
            nonlocal call_count
            call_count += 1
            raise HTTPException(status_code=504, detail="Timeout")
        monkeypatch.setattr(app, "call_claude_api", mock_call)
        monkeypatch.setattr(app, "_RETRY_DELAY_SEC", 0)
        from app import api_trigger_task
        with pytest.raises(HTTPException):
            await api_trigger_task("T001", {"runtime": "claude"})
        assert call_count == 3
        from app import get_agent_failures
        failures = get_agent_failures()
        assert len(failures) == 3
        for i, f in enumerate(failures, 1):
            assert f["attempt"] == i

    async def test_retry_succeeds_on_second(self, mock_task_env, tmp_failures, monkeypatch):
        import app
        from fastapi import HTTPException
        call_count = 0
        async def mock_call(*a, **kw):
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                raise HTTPException(status_code=503, detail="Unavailable")
            return {"result": "OK", "cost_usd": 0.02, "num_turns": 3}
        monkeypatch.setattr(app, "call_claude_api", mock_call)
        monkeypatch.setattr(app, "_RETRY_DELAY_SEC", 0)
        from app import api_trigger_task
        result = await api_trigger_task("T001", {"runtime": "claude"})
        assert result["success"] is True
        from app import get_agent_failures
        assert len(get_agent_failures()) == 1

    async def test_running_tasks_cleared_on_error(self, mock_task_env, tmp_failures, monkeypatch):
        import app
        from fastapi import HTTPException
        async def mock_call(*a, **kw):
            raise HTTPException(status_code=500, detail="Internal")
        monkeypatch.setattr(app, "call_claude_api", mock_call)
        from app import api_trigger_task
        with pytest.raises(HTTPException):
            await api_trigger_task("T001", {"runtime": "claude"})
        assert "T001" not in app.running_tasks

    async def test_duplicate_task_rejected(self, mock_task_env, tmp_failures, monkeypatch):
        import app
        from fastapi import HTTPException
        app.running_tasks["T001"] = {"agent": "dev1", "role": "developer",
                                      "runtime": "claude", "started_at": time.time()}
        try:
            from app import api_trigger_task
            with pytest.raises(HTTPException) as exc_info:
                await api_trigger_task("T001", {"runtime": "claude"})
            assert exc_info.value.status_code == 409
        finally:
            app.running_tasks.pop("T001", None)

    async def test_budget_error_no_retry(self, mock_task_env, tmp_failures, monkeypatch):
        import app
        from fastapi import HTTPException
        call_count = 0
        async def mock_call(*a, **kw):
            nonlocal call_count
            call_count += 1
            raise HTTPException(status_code=400, detail="Budget exceeded")
        monkeypatch.setattr(app, "call_claude_api", mock_call)
        from app import api_trigger_task
        with pytest.raises(HTTPException):
            await api_trigger_task("T001", {"runtime": "claude"})
        assert call_count == 1
        from app import get_agent_failures
        assert get_agent_failures()[0]["error_type"] == "budget"


# ---------------------------------------------------------------------------
# Tests: Cursor CLI silent-success bug fix
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
class TestCursorSilentSuccessBug:

    async def test_cursor_failure_detected(self, mock_task_env, tmp_failures, monkeypatch):
        import app
        from fastapi import HTTPException
        async def mock_cursor(agent, prompt):
            return {"success": False, "stderr": "Cursor timed out", "result": ""}
        monkeypatch.setattr(app, "run_cursor_cli", mock_cursor)
        monkeypatch.setattr(app, "_RETRY_DELAY_SEC", 0)
        from app import api_trigger_task
        with pytest.raises(HTTPException) as exc_info:
            await api_trigger_task("T001", {"runtime": "cursor"})
        assert exc_info.value.status_code == 502
        from app import get_agent_failures
        assert len(get_agent_failures()) >= 1

    async def test_cursor_success_passes(self, mock_task_env, tmp_failures, monkeypatch):
        import app
        async def mock_cursor(agent, prompt):
            return {"success": True, "result": "All done", "stderr": ""}
        monkeypatch.setattr(app, "run_cursor_cli", mock_cursor)
        from app import api_trigger_task
        result = await api_trigger_task("T001", {"runtime": "cursor"})
        assert result["success"] is True
        assert result["runtime"] == "cursor"


# ---------------------------------------------------------------------------
# Tests: Failure file resilience
# ---------------------------------------------------------------------------

class TestFailureFileResilience:

    def test_corrupted_json(self, tmp_failures):
        tmp_failures.write_text("not valid json!!!", encoding="utf-8")
        from app import _load_failures
        assert _load_failures() == []

    def test_non_list_json(self, tmp_failures):
        tmp_failures.write_text('{"key": "value"}', encoding="utf-8")
        from app import _load_failures
        assert _load_failures() == []

    def test_missing_file(self, tmp_failures):
        from app import _load_failures
        assert _load_failures() == []
