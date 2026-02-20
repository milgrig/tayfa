"""Tests for T010: Launch-instance endpoint and Open in New Window frontend.

Tests that:
- POST /api/launch-instance validates path
- POST /api/launch-instance rejects missing path
- POST /api/launch-instance rejects non-existent path
- POST /api/launch-instance rejects non-directory path
- POST /api/launch-instance detects already running instance
- POST /api/launch-instance launches new instance and returns URL
- GET /api/status includes locked_project for document.title usage
- document.title is set to project name (frontend, verified via status field)
- Project switching is disabled when locked_project is set (tested via 403)
"""

import sys
import os
import tempfile
from pathlib import Path
from unittest.mock import patch, MagicMock, AsyncMock

import pytest

# Add kok/ to path
KOK_DIR = Path(__file__).resolve().parent.parent
TEMPLATE_COMMON = KOK_DIR / "template_tayfa" / "common"
sys.path.insert(0, str(TEMPLATE_COMMON))
sys.path.insert(0, str(KOK_DIR))


# ---------------------------------------------------------------------------
# Tests: POST /api/launch-instance — validation
# ---------------------------------------------------------------------------

class TestLaunchInstanceValidation:

    def test_launch_instance_requires_path(self):
        """POST /api/launch-instance must return 400 when path is missing."""
        from routers.server import router
        from fastapi import FastAPI
        from fastapi.testclient import TestClient

        test_app = FastAPI()
        test_app.include_router(router)

        with TestClient(test_app, raise_server_exceptions=False) as client:
            resp = client.post("/api/launch-instance", json={})
            assert resp.status_code == 400
            assert "path" in resp.json()["detail"].lower()

    def test_launch_instance_rejects_empty_path(self):
        """POST /api/launch-instance must return 400 when path is empty string."""
        from routers.server import router
        from fastapi import FastAPI
        from fastapi.testclient import TestClient

        test_app = FastAPI()
        test_app.include_router(router)

        with TestClient(test_app, raise_server_exceptions=False) as client:
            resp = client.post("/api/launch-instance", json={"path": ""})
            assert resp.status_code == 400

    def test_launch_instance_rejects_nonexistent_path(self):
        """POST /api/launch-instance must return 400 for a path that doesn't exist."""
        from routers.server import router
        from fastapi import FastAPI
        from fastapi.testclient import TestClient

        test_app = FastAPI()
        test_app.include_router(router)

        with TestClient(test_app, raise_server_exceptions=False) as client:
            resp = client.post("/api/launch-instance", json={"path": "C:\\NonExistent\\FakePath\\12345"})
            assert resp.status_code == 400
            assert "does not exist" in resp.json()["detail"]

    def test_launch_instance_rejects_file_path(self):
        """POST /api/launch-instance must return 400 when path is a file, not a directory."""
        from routers.server import router
        from fastapi import FastAPI
        from fastapi.testclient import TestClient

        test_app = FastAPI()
        test_app.include_router(router)

        # Create a temporary file
        with tempfile.NamedTemporaryFile(delete=False, suffix=".txt") as tmp:
            tmp_path = tmp.name

        try:
            with TestClient(test_app, raise_server_exceptions=False) as client:
                resp = client.post("/api/launch-instance", json={"path": tmp_path})
                assert resp.status_code == 400
                assert "not a directory" in resp.json()["detail"]
        finally:
            os.unlink(tmp_path)


# ---------------------------------------------------------------------------
# Tests: POST /api/launch-instance — already running detection
# ---------------------------------------------------------------------------

class TestLaunchInstanceAlreadyRunning:

    def test_launch_instance_detects_already_running(self):
        """POST /api/launch-instance should return already_running when an instance exists."""
        from routers.server import router
        from fastapi import FastAPI
        from fastapi.testclient import TestClient
        import httpx

        test_app = FastAPI()
        test_app.include_router(router)

        # Create a temporary directory to use as project path
        with tempfile.TemporaryDirectory() as tmpdir:
            resolved = str(Path(tmpdir).resolve())

            # Mock is_port_in_use to return True for port 8010
            # Mock httpx to return a status response with locked_project
            mock_response = MagicMock()
            mock_response.status_code = 200
            mock_response.json.return_value = {
                "locked_project": resolved,
                "has_project": True,
            }

            async def mock_get(url, *args, **kwargs):
                if "/api/status" in url:
                    return mock_response
                raise httpx.ConnectError("Not found")

            mock_client = AsyncMock()
            mock_client.get = mock_get
            mock_client.__aenter__ = AsyncMock(return_value=mock_client)
            mock_client.__aexit__ = AsyncMock(return_value=False)

            with patch("routers.server.is_port_in_use", side_effect=lambda p: p == 8010), \
                 patch("routers.server.httpx.AsyncClient", return_value=mock_client):
                with TestClient(test_app, raise_server_exceptions=False) as client:
                    resp = client.post("/api/launch-instance", json={"path": tmpdir})
                    assert resp.status_code == 200
                    body = resp.json()
                    assert body["status"] == "already_running"
                    assert body["port"] == 8010
                    assert "url" in body


# ---------------------------------------------------------------------------
# Tests: POST /api/launch-instance — successful launch
# ---------------------------------------------------------------------------

class TestLaunchInstanceSpawn:

    def test_launch_instance_spawns_process(self):
        """POST /api/launch-instance should spawn a subprocess and return URL."""
        from routers.server import router
        from fastapi import FastAPI
        from fastapi.testclient import TestClient
        import httpx

        test_app = FastAPI()
        test_app.include_router(router)

        with tempfile.TemporaryDirectory() as tmpdir:
            resolved = str(Path(tmpdir).resolve())

            # Track call number to simulate: first scan = no instances, second scan = found
            call_count = {"n": 0}

            # Mock is_port_in_use: initially no ports in use, then port 8009 appears
            def mock_port_in_use(port):
                if call_count["n"] >= 1 and port == 8009:
                    return True
                return False

            mock_response = MagicMock()
            mock_response.status_code = 200
            mock_response.json.return_value = {
                "locked_project": resolved,
                "has_project": True,
            }

            async def mock_get(url, *args, **kwargs):
                if "/api/status" in url and "8009" in url:
                    call_count["n"] += 1
                    return mock_response
                raise httpx.ConnectError("Not found")

            mock_client = AsyncMock()
            mock_client.get = mock_get
            mock_client.__aenter__ = AsyncMock(return_value=mock_client)
            mock_client.__aexit__ = AsyncMock(return_value=False)

            mock_proc = MagicMock()
            mock_proc.poll.return_value = None  # Process is running
            mock_proc.pid = 12345

            # Make asyncio.sleep instant for test speed
            async def instant_sleep(t):
                call_count["n"] += 1
                return

            with patch("routers.server.is_port_in_use", side_effect=mock_port_in_use), \
                 patch("routers.server.httpx.AsyncClient", return_value=mock_client), \
                 patch("routers.server.subprocess.Popen", return_value=mock_proc) as mock_popen, \
                 patch("routers.server.asyncio.sleep", side_effect=instant_sleep):
                with TestClient(test_app, raise_server_exceptions=False) as client:
                    resp = client.post("/api/launch-instance", json={"path": tmpdir})
                    assert resp.status_code == 200
                    body = resp.json()
                    assert body["status"] == "launched"
                    assert body["port"] == 8009
                    assert body["pid"] == 12345
                    assert "url" in body

                    # Verify subprocess.Popen was called with --project flag
                    mock_popen.assert_called_once()
                    call_args = mock_popen.call_args
                    cmd = call_args[0][0]
                    assert "--project" in cmd
                    assert resolved in cmd


# ---------------------------------------------------------------------------
# Tests: GET /api/status — locked_project field for frontend title
# ---------------------------------------------------------------------------

class TestStatusForFrontend:

    def test_status_includes_current_project_name(self):
        """GET /api/status must include current_project with name for document.title."""
        import app_state
        original = app_state.LOCKED_PROJECT_PATH

        try:
            app_state.LOCKED_PROJECT_PATH = None

            from routers.server import router
            from fastapi import FastAPI
            from fastapi.testclient import TestClient

            test_app = FastAPI()
            test_app.include_router(router)

            with patch.object(app_state, "claude_api_process", None), \
                 patch("routers.server.get_current_project", return_value={"path": "C:\\Test", "name": "TestProject"}):
                with TestClient(test_app, raise_server_exceptions=False) as client:
                    resp = client.get("/api/status")
                    assert resp.status_code == 200
                    body = resp.json()
                    assert body["current_project"]["name"] == "TestProject"
                    assert body["has_project"] is True
        finally:
            app_state.LOCKED_PROJECT_PATH = original

    def test_status_locked_project_for_ui_lock(self):
        """GET /api/status with locked_project enables frontend project switching lock."""
        import app_state
        original = app_state.LOCKED_PROJECT_PATH

        try:
            app_state.LOCKED_PROJECT_PATH = "C:\\Locked\\Project"

            from routers.server import router
            from fastapi import FastAPI
            from fastapi.testclient import TestClient

            test_app = FastAPI()
            test_app.include_router(router)

            with patch.object(app_state, "claude_api_process", None):
                with TestClient(test_app, raise_server_exceptions=False) as client:
                    resp = client.get("/api/status")
                    assert resp.status_code == 200
                    body = resp.json()
                    assert body["locked_project"] == "C:\\Locked\\Project"
        finally:
            app_state.LOCKED_PROJECT_PATH = original


# ---------------------------------------------------------------------------
# Tests: Project switching disabled when locked (via 403 on /api/projects/open)
# ---------------------------------------------------------------------------

class TestProjectSwitchingLocked:

    def test_project_switching_blocked_when_locked(self):
        """POST /api/projects/open returns 403 when LOCKED_PROJECT_PATH is set — UI should use this."""
        import app_state
        original = app_state.LOCKED_PROJECT_PATH

        try:
            app_state.LOCKED_PROJECT_PATH = "C:\\Locked\\Instance"

            from routers.projects import router
            from fastapi import FastAPI
            from fastapi.testclient import TestClient

            test_app = FastAPI()
            test_app.include_router(router)

            with TestClient(test_app, raise_server_exceptions=False) as client:
                resp = client.post("/api/projects/open", json={"path": "C:\\Other"})
                assert resp.status_code == 403
        finally:
            app_state.LOCKED_PROJECT_PATH = original

    def test_project_switching_allowed_when_not_locked(self):
        """POST /api/projects/open is allowed when LOCKED_PROJECT_PATH is None."""
        import app_state
        original = app_state.LOCKED_PROJECT_PATH

        try:
            app_state.LOCKED_PROJECT_PATH = None

            from routers.projects import router
            from fastapi import FastAPI
            from fastapi.testclient import TestClient

            test_app = FastAPI()
            test_app.include_router(router)

            with patch("routers.projects.open_project") as mock_open:
                mock_open.return_value = {
                    "status": "opened",
                    "project": {"path": "C:\\Test", "name": "Test"},
                    "tayfa_path": None,
                    "init": None,
                }
                with TestClient(test_app, raise_server_exceptions=False) as client:
                    resp = client.post("/api/projects/open", json={"path": "C:\\Test"})
                    assert resp.status_code != 403
        finally:
            app_state.LOCKED_PROJECT_PATH = original


# ---------------------------------------------------------------------------
# Tests: Port range constants
# ---------------------------------------------------------------------------

class TestPortRangeConstants:

    def test_instance_port_range(self):
        """Instance port range should be 8008-8017."""
        from routers.server import _INSTANCE_PORT_MIN, _INSTANCE_PORT_MAX
        assert _INSTANCE_PORT_MIN == 8008
        assert _INSTANCE_PORT_MAX == 8017
        assert _INSTANCE_PORT_MAX - _INSTANCE_PORT_MIN + 1 == 10

    def test_launch_instance_endpoint_exists(self):
        """Router must have /api/launch-instance POST route."""
        from routers.server import router
        routes = [r.path for r in router.routes if hasattr(r, 'path')]
        assert "/api/launch-instance" in routes
