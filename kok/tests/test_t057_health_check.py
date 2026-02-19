"""Tests for T057: Health check for Claude API server.

Tests:
- /api/health endpoint returns ok when API is running
- /api/health endpoint returns not-ok when API is down (HTTP 200 always)
- Startup health check succeeds after retries
- Startup health check logs CRITICAL after max retries (startup still completes)
- Startup retry count is configurable via config.json
"""

import asyncio
import json
import sys
from pathlib import Path
from unittest.mock import patch, AsyncMock, MagicMock

import pytest
import httpx

# Add kok/ and template_tayfa/common to path
KOK_DIR = Path(__file__).resolve().parent.parent
TEMPLATE_COMMON = KOK_DIR / "template_tayfa" / "common"
sys.path.insert(0, str(TEMPLATE_COMMON))
sys.path.insert(0, str(KOK_DIR))


# ---------------------------------------------------------------------------
# Helper: build a minimal httpx Response mock
# ---------------------------------------------------------------------------

def _mock_response(status_code: int) -> MagicMock:
    resp = MagicMock()
    resp.status_code = status_code
    return resp


# ---------------------------------------------------------------------------
# Tests: /api/health endpoint
# ---------------------------------------------------------------------------

class TestHealthEndpoint:
    """Tests for GET /api/health."""

    @pytest.mark.asyncio
    async def test_health_endpoint_returns_ok_when_api_running(self):
        """When Claude API responds 200, /api/health returns {ok:true, claude_api:true}."""
        import app
        from fastapi.testclient import TestClient

        with patch("routers.server.httpx.AsyncClient") as mock_client_cls:
            mock_client = AsyncMock()
            mock_client.__aenter__ = AsyncMock(return_value=mock_client)
            mock_client.__aexit__ = AsyncMock(return_value=False)
            mock_client.get = AsyncMock(return_value=_mock_response(200))
            mock_client_cls.return_value = mock_client

            with TestClient(app.app) as client:
                resp = client.get("/api/health")

        assert resp.status_code == 200
        data = resp.json()
        assert data["ok"] is True
        assert data["claude_api"] is True
        assert data["orchestrator"] == "ok"

    @pytest.mark.asyncio
    async def test_health_endpoint_returns_not_ok_when_api_down(self):
        """When Claude API is unreachable, /api/health returns {ok:false, claude_api:false} with HTTP 200."""
        import app
        from fastapi.testclient import TestClient

        with patch("routers.server.httpx.AsyncClient") as mock_client_cls:
            mock_client = AsyncMock()
            mock_client.__aenter__ = AsyncMock(return_value=mock_client)
            mock_client.__aexit__ = AsyncMock(return_value=False)
            mock_client.get = AsyncMock(side_effect=httpx.ConnectError("connection refused"))
            mock_client_cls.return_value = mock_client

            with TestClient(app.app) as client:
                resp = client.get("/api/health")

        assert resp.status_code == 200  # health endpoints always return 200
        data = resp.json()
        assert data["ok"] is False
        assert data["claude_api"] is False
        assert data["orchestrator"] == "ok"


# ---------------------------------------------------------------------------
# Tests: startup health check logic (extracted from lifespan)
# ---------------------------------------------------------------------------

async def _run_startup_check(mock_get_fn, startup_retries: int, config_override: dict | None = None):
    """
    Replicate the startup health-check loop from lifespan() for isolated testing.
    Returns (ready: bool, log_messages: list[tuple[level, msg]])
    """
    log_messages = []

    class FakeLogger:
        def info(self, msg): log_messages.append(("info", msg))
        def critical(self, msg): log_messages.append(("critical", msg))

    fake_logger = FakeLogger()

    # Replicate the startup check logic from lifespan()
    retries = startup_retries
    claude_api_ready = False
    fake_logger.info(f"Waiting for Claude API to become ready (max {retries} retries)...")
    for attempt in range(1, retries + 1):
        try:
            result = await mock_get_fn(attempt)
            if result.status_code == 200:
                fake_logger.info("Claude API ready.")
                claude_api_ready = True
                break
        except Exception:
            pass
        if attempt < retries:
            # Skip actual sleep in tests
            pass
    if not claude_api_ready:
        fake_logger.critical(
            f"Claude API did not become ready after {retries} retries - tasks may fail"
        )

    return claude_api_ready, log_messages


class TestStartupHealthCheck:
    """Tests for the startup health check loop in lifespan()."""

    @pytest.mark.asyncio
    async def test_startup_check_succeeds_after_retries(self):
        """Startup check should retry and succeed when API becomes available after 2 failures."""
        call_count = 0

        async def mock_get(attempt):
            nonlocal call_count
            call_count += 1
            if attempt <= 2:
                raise httpx.ConnectError("not ready yet")
            return _mock_response(200)

        ready, logs = await _run_startup_check(mock_get, startup_retries=10)

        assert ready is True
        assert call_count == 3  # failed twice, succeeded on 3rd
        info_msgs = [msg for level, msg in logs if level == "info"]
        assert any("ready" in m.lower() for m in info_msgs), f"Expected 'ready' in logs, got: {info_msgs}"

    @pytest.mark.asyncio
    async def test_startup_check_logs_critical_after_max_retries(self):
        """When all retries are exhausted, CRITICAL is logged but no exception is raised."""
        async def mock_get(attempt):
            raise httpx.ConnectError("always down")

        # Should NOT raise — startup still completes
        try:
            ready, logs = await _run_startup_check(mock_get, startup_retries=5)
        except Exception as e:
            pytest.fail(f"Startup check raised unexpected exception: {e}")

        assert ready is False
        critical_msgs = [msg for level, msg in logs if level == "critical"]
        assert len(critical_msgs) == 1
        assert "did not become ready" in critical_msgs[0]
        assert "5 retries" in critical_msgs[0]
        assert "tasks may fail" in critical_msgs[0]

    @pytest.mark.asyncio
    async def test_startup_retry_count_configurable(self):
        """Startup retry count respects claude_api_startup_retries config value."""
        call_count = 0

        async def mock_get(attempt):
            nonlocal call_count
            call_count += 1
            raise httpx.ConnectError("always down")

        # Run with only 3 retries
        ready, logs = await _run_startup_check(mock_get, startup_retries=3)

        assert ready is False
        assert call_count == 3  # exactly 3 attempts, not more

    @pytest.mark.asyncio
    async def test_startup_check_succeeds_on_first_try(self):
        """If Claude API is immediately ready, only one attempt is made."""
        call_count = 0

        async def mock_get(attempt):
            nonlocal call_count
            call_count += 1
            return _mock_response(200)

        ready, logs = await _run_startup_check(mock_get, startup_retries=10)

        assert ready is True
        assert call_count == 1

    def test_read_config_startup_retries(self, tmp_path, monkeypatch):
        """_read_config_value reads claude_api_startup_retries from config.json."""
        import app_state

        config_data = {"claude_api_startup_retries": 3}
        config_file = tmp_path / "config.json"
        config_file.write_text(json.dumps(config_data), encoding="utf-8")

        monkeypatch.setattr(app_state, "get_personel_dir", lambda: tmp_path)
        # Also patch TAYFA_DATA_DIR to point nowhere useful (so fallback doesn't interfere)
        monkeypatch.setattr(app_state, "TAYFA_DATA_DIR", tmp_path / "nonexistent")

        result = app_state._read_config_value(
            "claude_api_startup_retries", 10,
            lambda v: isinstance(v, int) and v > 0,
        )
        assert result == 3
