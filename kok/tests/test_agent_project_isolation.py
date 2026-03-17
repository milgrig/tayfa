"""Tests for T016: Agent isolation per project.

Agents in claude_api.py must be scoped by project_path so that
switching projects doesn't reuse/overwrite agents from another project.
"""

import json
import os
import sys
import tempfile
from pathlib import Path

import pytest

# Add kok/ to path so we can import claude_api helpers directly
KOK_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(KOK_DIR))


# ---------------------------------------------------------------------------
# Unit tests for scoping helpers
# ---------------------------------------------------------------------------


class TestProjectKey:
    """_project_key derives a folder name from project_path."""

    def test_windows_path(self):
        from claude_api import _project_key
        assert _project_key("C:\\Projects\\MyApp") == "MyApp"

    def test_unix_path(self):
        from claude_api import _project_key
        assert _project_key("/home/user/projects/MyApp") == "MyApp"

    def test_trailing_slash(self):
        from claude_api import _project_key
        assert _project_key("C:\\Projects\\MyApp\\") == "MyApp"

    def test_empty(self):
        from claude_api import _project_key
        assert _project_key("") == ""

    def test_none(self):
        from claude_api import _project_key
        assert _project_key(None) == ""

    def test_single_name(self):
        from claude_api import _project_key
        assert _project_key("MyApp") == "MyApp"


class TestScopedName:
    """_scoped_name builds internal key '{project_key}:{name}'."""

    def test_with_project(self):
        from claude_api import _scoped_name
        assert _scoped_name("developer", "C:\\Projects\\MyApp") == "MyApp:developer"

    def test_without_project(self):
        from claude_api import _scoped_name
        assert _scoped_name("developer", "") == "developer"

    def test_none_project(self):
        from claude_api import _scoped_name
        assert _scoped_name("developer", None) == "developer"


class TestUnscopedName:
    """_unscoped_name extracts plain name from internal key."""

    def test_scoped(self):
        from claude_api import _unscoped_name
        assert _unscoped_name("MyApp:developer") == "developer"

    def test_unscoped(self):
        from claude_api import _unscoped_name
        assert _unscoped_name("developer") == "developer"


class TestAgentsForProject:
    """_agents_for_project filters agents by project."""

    def test_filters_by_project(self):
        from claude_api import _agents_for_project
        agents = {
            "ProjectA:developer": {"workdir": "A"},
            "ProjectA:tester": {"workdir": "A"},
            "ProjectB:developer": {"workdir": "B"},
            "legacy_agent": {"workdir": "old"},
        }
        result = _agents_for_project(agents, "C:\\Projects\\ProjectA")
        assert set(result.keys()) == {"developer", "tester"}
        assert result["developer"]["workdir"] == "A"

    def test_no_project_returns_legacy(self):
        from claude_api import _agents_for_project
        agents = {
            "ProjectA:developer": {"workdir": "A"},
            "legacy_agent": {"workdir": "old"},
        }
        result = _agents_for_project(agents, "")
        assert set(result.keys()) == {"legacy_agent"}

    def test_empty_agents(self):
        from claude_api import _agents_for_project
        result = _agents_for_project({}, "C:\\Projects\\X")
        assert result == {}


# ---------------------------------------------------------------------------
# Integration tests: API endpoint isolation
# ---------------------------------------------------------------------------


@pytest.fixture
def _tmp_agents_file(tmp_path, monkeypatch):
    """Redirect AGENTS_FILE to a temp file so tests don't pollute real data."""
    agents_file = str(tmp_path / "claude_agents.json")
    import claude_api
    monkeypatch.setattr(claude_api, "AGENTS_FILE", agents_file)
    return agents_file


class TestRunEndpointIsolation:
    """POST /run with project_path scopes agents correctly."""

    def _client(self):
        from claude_api import app
        from starlette.testclient import TestClient
        return TestClient(app)

    def test_create_agent_scoped(self, _tmp_agents_file):
        """Creating agent with project_path stores it under scoped key."""
        client = self._client()
        resp = client.post("/run", json={
            "name": "developer",
            "workdir": "C:\\ProjectA",
            "system_prompt": "You are dev for A",
            "project_path": "C:\\ProjectA",
        })
        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "created"
        assert data["agent"] == "developer"

        # Verify internal storage uses scoped key
        with open(_tmp_agents_file, encoding="utf-8") as f:
            raw = json.load(f)
        assert "ProjectA:developer" in raw
        assert "developer" not in raw

    def test_two_projects_isolated(self, _tmp_agents_file):
        """Same agent name in different projects creates separate entries."""
        client = self._client()

        # Create for project A
        resp_a = client.post("/run", json={
            "name": "developer",
            "workdir": "C:\\ProjectA",
            "system_prompt": "Dev for A",
            "project_path": "C:\\ProjectA",
        })
        assert resp_a.status_code == 200

        # Create for project B
        resp_b = client.post("/run", json={
            "name": "developer",
            "workdir": "C:\\ProjectB",
            "system_prompt": "Dev for B",
            "project_path": "C:\\ProjectB",
        })
        assert resp_b.status_code == 200

        # Verify both exist separately
        with open(_tmp_agents_file, encoding="utf-8") as f:
            raw = json.load(f)
        assert "ProjectA:developer" in raw
        assert "ProjectB:developer" in raw
        assert raw["ProjectA:developer"]["system_prompt"] == "Dev for A"
        assert raw["ProjectB:developer"]["system_prompt"] == "Dev for B"

    def test_update_scoped_agent(self, _tmp_agents_file):
        """Updating an agent uses scoped key, doesn't affect other projects."""
        client = self._client()

        # Create for both projects
        client.post("/run", json={
            "name": "developer",
            "workdir": "C:\\ProjectA",
            "system_prompt": "Original A",
            "project_path": "C:\\ProjectA",
        })
        client.post("/run", json={
            "name": "developer",
            "workdir": "C:\\ProjectB",
            "system_prompt": "Original B",
            "project_path": "C:\\ProjectB",
        })

        # Update A only
        resp = client.post("/run", json={
            "name": "developer",
            "system_prompt": "Updated A",
            "project_path": "C:\\ProjectA",
        })
        assert resp.json()["status"] == "updated"

        # Verify B unchanged
        with open(_tmp_agents_file, encoding="utf-8") as f:
            raw = json.load(f)
        assert raw["ProjectA:developer"]["system_prompt"] == "Updated A"
        assert raw["ProjectB:developer"]["system_prompt"] == "Original B"

    def test_reset_scoped_agent(self, _tmp_agents_file):
        """Reset uses scoped key."""
        client = self._client()
        client.post("/run", json={
            "name": "developer",
            "workdir": "C:\\ProjectA",
            "system_prompt": "Dev A",
            "project_path": "C:\\ProjectA",
        })

        resp = client.post("/run", json={
            "name": "developer",
            "reset": True,
            "project_path": "C:\\ProjectA",
        })
        assert resp.status_code == 200
        assert resp.json()["status"] == "reset"

    def test_reset_nonexistent_returns_404(self, _tmp_agents_file):
        """Reset for agent that doesn't exist in this project returns 404."""
        client = self._client()
        # Create only in A
        client.post("/run", json={
            "name": "developer",
            "workdir": "C:\\ProjectA",
            "system_prompt": "Dev A",
            "project_path": "C:\\ProjectA",
        })

        # Try reset in B — should fail
        resp = client.post("/run", json={
            "name": "developer",
            "reset": True,
            "project_path": "C:\\ProjectB",
        })
        assert resp.status_code == 404


class TestListAgentsIsolation:
    """GET /agents with project_path returns only scoped agents."""

    def _client(self):
        from claude_api import app
        from starlette.testclient import TestClient
        return TestClient(app)

    def test_list_scoped(self, _tmp_agents_file):
        """GET /agents?project_path=... returns only agents for that project."""
        client = self._client()

        # Create agents in two projects
        client.post("/run", json={
            "name": "developer",
            "workdir": "C:\\ProjectA",
            "system_prompt": "A dev",
            "project_path": "C:\\ProjectA",
        })
        client.post("/run", json={
            "name": "tester",
            "workdir": "C:\\ProjectA",
            "system_prompt": "A tester",
            "project_path": "C:\\ProjectA",
        })
        client.post("/run", json={
            "name": "developer",
            "workdir": "C:\\ProjectB",
            "system_prompt": "B dev",
            "project_path": "C:\\ProjectB",
        })

        # List for project A
        resp = client.get("/agents", params={"project_path": "C:\\ProjectA"})
        assert resp.status_code == 200
        agents = resp.json()
        assert set(agents.keys()) == {"developer", "tester"}

        # List for project B
        resp = client.get("/agents", params={"project_path": "C:\\ProjectB"})
        agents = resp.json()
        assert set(agents.keys()) == {"developer"}

    def test_list_without_scope_returns_all(self, _tmp_agents_file):
        """GET /agents without project_path returns all agents (raw keys)."""
        client = self._client()
        client.post("/run", json={
            "name": "developer",
            "workdir": "C:\\ProjectA",
            "system_prompt": "A dev",
            "project_path": "C:\\ProjectA",
        })
        resp = client.get("/agents")
        agents = resp.json()
        # Should contain the internal key
        assert "ProjectA:developer" in agents


class TestDeleteAgentIsolation:
    """DELETE /agents/{name} with project_path deletes only scoped agent."""

    def _client(self):
        from claude_api import app
        from starlette.testclient import TestClient
        return TestClient(app)

    def test_delete_scoped(self, _tmp_agents_file):
        """Delete only affects the scoped project."""
        client = self._client()

        # Create in both projects
        client.post("/run", json={
            "name": "developer",
            "workdir": "C:\\ProjectA",
            "system_prompt": "A dev",
            "project_path": "C:\\ProjectA",
        })
        client.post("/run", json={
            "name": "developer",
            "workdir": "C:\\ProjectB",
            "system_prompt": "B dev",
            "project_path": "C:\\ProjectB",
        })

        # Delete from A
        resp = client.delete("/agents/developer", params={"project_path": "C:\\ProjectA"})
        assert resp.status_code == 200

        # Verify: A gone, B still exists
        with open(_tmp_agents_file, encoding="utf-8") as f:
            raw = json.load(f)
        assert "ProjectA:developer" not in raw
        assert "ProjectB:developer" in raw

    def test_delete_wrong_project_404(self, _tmp_agents_file):
        """Delete from a project where agent doesn't exist returns 404."""
        client = self._client()
        client.post("/run", json={
            "name": "developer",
            "workdir": "C:\\ProjectA",
            "system_prompt": "A dev",
            "project_path": "C:\\ProjectA",
        })

        resp = client.delete("/agents/developer", params={"project_path": "C:\\ProjectB"})
        assert resp.status_code == 404


class TestBackwardCompatibility:
    """Legacy agents (no project_path) still work."""

    def _client(self):
        from claude_api import app
        from starlette.testclient import TestClient
        return TestClient(app)

    def test_create_without_project_path(self, _tmp_agents_file):
        """Agent created without project_path uses plain name."""
        client = self._client()
        resp = client.post("/run", json={
            "name": "developer",
            "workdir": "C:\\Legacy",
            "system_prompt": "Legacy dev",
        })
        assert resp.status_code == 200

        with open(_tmp_agents_file, encoding="utf-8") as f:
            raw = json.load(f)
        assert "developer" in raw
        assert not any(":" in k for k in raw)

    def test_legacy_and_scoped_coexist(self, _tmp_agents_file):
        """Legacy agent and scoped agent with same name don't collide."""
        client = self._client()

        # Create legacy
        client.post("/run", json={
            "name": "developer",
            "workdir": "C:\\Legacy",
            "system_prompt": "Legacy dev",
        })

        # Create scoped
        client.post("/run", json={
            "name": "developer",
            "workdir": "C:\\ProjectA",
            "system_prompt": "A dev",
            "project_path": "C:\\ProjectA",
        })

        with open(_tmp_agents_file, encoding="utf-8") as f:
            raw = json.load(f)
        assert "developer" in raw
        assert "ProjectA:developer" in raw
        assert raw["developer"]["system_prompt"] == "Legacy dev"
        assert raw["ProjectA:developer"]["system_prompt"] == "A dev"
