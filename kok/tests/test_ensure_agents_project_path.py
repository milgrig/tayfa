"""Tests for T010: ensure_agents accepts project_path from request body."""

import json
import sys
from pathlib import Path
from unittest.mock import AsyncMock, patch, MagicMock

import pytest
from httpx import AsyncClient, ASGITransport

# Add kok/ and its dependencies to path
KOK_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(KOK_DIR))
sys.path.insert(0, str(KOK_DIR.parent / ".tayfa" / "common"))


@pytest.fixture
def _patch_app():
    """Patch heavy dependencies so app.py can be imported without side-effects."""
    with patch.dict("os.environ", {"TAYFA_SKIP_INIT": "1"}):
        yield


def _build_client():
    from app import app
    transport = ASGITransport(app=app)
    return AsyncClient(transport=transport, base_url="http://test")


# ---------------------------------------------------------------------------
# TC-1: CLI with correct project_path
# ---------------------------------------------------------------------------
@pytest.mark.api
class TestEnsureAgentsWithProjectPath:

    @pytest.mark.asyncio
    async def test_tc1_project_path_used_for_personel_dir(self):
        """POST with project_path uses it instead of get_current_project()."""
        fake_project = "C:\\Cursor\\TayfaWindows"

        with patch("routers.agents._get_employees", return_value={}), \
             patch("routers.agents.call_claude_api", new_callable=AsyncMock, return_value={}), \
             patch("routers.agents.get_personel_dir") as mock_gpd, \
             patch("routers.agents.get_agent_workdir") as mock_gaw:

            async with _build_client() as client:
                resp = await client.post(
                    "/api/ensure-agents",
                    json={"project_path": fake_project},
                )

            assert resp.status_code == 200
            # get_personel_dir / get_agent_workdir should NOT have been called
            mock_gpd.assert_not_called()
            mock_gaw.assert_not_called()

    @pytest.mark.asyncio
    async def test_tc1_agent_created_with_correct_workdir(self):
        """Agent is created with workdir matching the provided project_path."""
        fake_project = "C:\\Cursor\\TayfaWindows"
        tayfa_dir = Path(fake_project) / ".tayfa"
        emp_name = "developer"

        # Create a temporary prompt.md so it "exists"
        with patch("routers.agents._get_employees", return_value={emp_name: {"model": "sonnet"}}), \
             patch("routers.agents.call_claude_api", new_callable=AsyncMock) as mock_api, \
             patch("routers.agents.compose_system_prompt", return_value="system prompt"), \
             patch.object(Path, "exists", return_value=True):

            mock_api.return_value = {}

            async with _build_client() as client:
                resp = await client.post(
                    "/api/ensure-agents",
                    json={"project_path": fake_project},
                )

            assert resp.status_code == 200
            data = resp.json()
            # Should have a result for the employee
            assert len(data["results"]) == 1
            result = data["results"][0]
            assert result["agent"] == emp_name
            assert result["status"] == "created"

            # Check the CREATE call used correct workdir
            create_call = None
            for call in mock_api.call_args_list:
                if call[0][0] == "POST" and call[0][1] == "/run":
                    payload = call[1].get("json_data") or call[0][2] if len(call[0]) > 2 else call[1].get("json_data")
                    if payload and payload.get("name") == emp_name and "workdir" in payload:
                        create_call = payload
                        break

            assert create_call is not None, "Expected a POST /run call with workdir"
            if sys.platform == "win32":
                assert create_call["workdir"] == fake_project


# ---------------------------------------------------------------------------
# TC-2: UI without project_path
# ---------------------------------------------------------------------------
class TestEnsureAgentsWithoutProjectPath:

    @pytest.mark.asyncio
    async def test_tc2_empty_body_uses_current_project(self):
        """POST with empty JSON body {} falls back to get_current_project()."""
        with patch("routers.agents._get_employees", return_value={}), \
             patch("routers.agents.call_claude_api", new_callable=AsyncMock, return_value={}), \
             patch("routers.agents.get_personel_dir") as mock_gpd, \
             patch("routers.agents.get_agent_workdir") as mock_gaw:

            mock_gpd.return_value = Path("C:/fallback/.tayfa")
            mock_gaw.return_value = "C:\\fallback"

            async with _build_client() as client:
                resp = await client.post(
                    "/api/ensure-agents",
                    json={},
                )

            assert resp.status_code == 200
            mock_gpd.assert_called_once()
            mock_gaw.assert_called_once()


# ---------------------------------------------------------------------------
# TC-3: Empty body (legacy clients)
# ---------------------------------------------------------------------------
class TestEnsureAgentsEmptyBody:

    @pytest.mark.asyncio
    async def test_tc3_empty_bytes_no_error(self):
        """POST with empty body (b'') does not cause 422/500."""
        with patch("routers.agents._get_employees", return_value={}), \
             patch("routers.agents.call_claude_api", new_callable=AsyncMock, return_value={}), \
             patch("routers.agents.get_personel_dir", return_value=Path("C:/x/.tayfa")), \
             patch("routers.agents.get_agent_workdir", return_value="C:\\x"):

            async with _build_client() as client:
                resp = await client.post(
                    "/api/ensure-agents",
                    content=b"",
                    headers={"Content-Type": "application/json"},
                )

            assert resp.status_code == 200


# ---------------------------------------------------------------------------
# TC-4: Nonexistent path
# ---------------------------------------------------------------------------
class TestEnsureAgentsNonexistentPath:

    @pytest.mark.asyncio
    async def test_tc4_nonexistent_path_returns_empty_results(self):
        """POST with nonexistent project_path returns results=[], no exceptions."""
        with patch("routers.agents._get_employees", return_value={"dev": {"model": "sonnet"}}), \
             patch("routers.agents.call_claude_api", new_callable=AsyncMock, return_value={}), \
             patch("routers.agents.compose_system_prompt", return_value=None):

            async with _build_client() as client:
                resp = await client.post(
                    "/api/ensure-agents",
                    json={"project_path": "C:\\nonexistent"},
                )

            assert resp.status_code == 200
            data = resp.json()
            # The employee has no prompt.md at the nonexistent path → skipped
            results = data["results"]
            assert len(results) == 1
            assert results[0]["status"] == "skipped"


# ---------------------------------------------------------------------------
# Test: create_employee.py sends project_path
# ---------------------------------------------------------------------------
class TestCreateEmployeeNotifyOrchestrator:

    def test_notify_orchestrator_sends_project_path(self):
        """notify_orchestrator() sends project_path in request body."""
        import importlib
        hr_dir = KOK_DIR.parent / ".tayfa" / "hr"
        sys.path.insert(0, str(hr_dir))
        sys.path.insert(0, str(KOK_DIR.parent / ".tayfa" / "common"))

        with patch("urllib.request.urlopen") as mock_urlopen:
            mock_resp = MagicMock()
            mock_resp.status = 200
            mock_resp.__enter__ = lambda s: s
            mock_resp.__exit__ = MagicMock(return_value=False)
            mock_urlopen.return_value = mock_resp

            # Import and call
            import create_employee
            create_employee.notify_orchestrator()

            # Check the request was made with project_path in body
            call_args = mock_urlopen.call_args
            req = call_args[0][0]
            body = json.loads(req.data.decode())
            assert "project_path" in body
            assert body["project_path"] == str(create_employee.PROJECT_DIR)
