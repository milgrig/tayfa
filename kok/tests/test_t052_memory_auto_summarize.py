"""
T052: Tests for auto-summarize on session end.

Verifies that:
- update_memory is called on success path (from T051, verified here too)
- update_memory is called on crash/timeout with INTERRUPTED message
- Memory file persists across separate update_memory calls (simulating restart)
- Error path records error_type in memory
"""
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


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture(autouse=True)
def _isolate(tmp_path):
    """Point memory_manager at a temp directory."""
    import memory_manager as mm
    old = mm._TAYFA_DIR
    mm.set_tayfa_dir(tmp_path)
    yield tmp_path
    mm._TAYFA_DIR = old


# ---------------------------------------------------------------------------
# Tests: success path memory update
# ---------------------------------------------------------------------------


class TestSuccessPath:

    def test_update_memory_after_success(self, tmp_path):
        """Simulate success: update_memory called with task result."""
        import memory_manager as mm
        mm.update_memory("developer", "T042", "Implemented create_bug() function")
        content = (tmp_path / "developer" / "memory.md").read_text(encoding="utf-8")
        assert "T042" in content
        assert "Implemented create_bug()" in content

    def test_multiple_successes_build_log(self, tmp_path):
        """Multiple successful tasks build up the work log."""
        import memory_manager as mm
        mm.update_memory("developer", "T042", "Implemented create_bug()")
        mm.update_memory("developer", "T043", "Added POST /api/bugs endpoint")
        mm.update_memory("developer", "T045", "Bug card styling in board.js")
        content = (tmp_path / "developer" / "memory.md").read_text(encoding="utf-8")
        assert "T042" in content
        assert "T043" in content
        assert "T045" in content


# ---------------------------------------------------------------------------
# Tests: error/crash path memory update
# ---------------------------------------------------------------------------


class TestErrorPath:

    def test_interrupted_recorded_in_memory(self, tmp_path):
        """Simulate crash: update_memory called with INTERRUPTED message."""
        import memory_manager as mm
        mm.update_memory(
            "developer", "T050",
            "INTERRUPTED after 45s, error: timeout",
        )
        content = (tmp_path / "developer" / "memory.md").read_text(encoding="utf-8")
        assert "T050" in content
        assert "INTERRUPTED" in content
        assert "timeout" in content

    def test_interrupted_after_success_shows_both(self, tmp_path):
        """Success then crash: both appear in memory."""
        import memory_manager as mm
        mm.update_memory("developer", "T042", "Implemented create_bug()")
        mm.update_memory("developer", "T050", "INTERRUPTED after 30s, error: unavailable")
        content = (tmp_path / "developer" / "memory.md").read_text(encoding="utf-8")
        assert "T042" in content
        assert "T050" in content
        assert "INTERRUPTED" in content

    def test_different_error_types_recorded(self, tmp_path):
        """Different error types are preserved in memory."""
        import memory_manager as mm
        mm.update_memory("dev", "T001", "INTERRUPTED after 10s, error: context_overflow")
        content = (tmp_path / "dev" / "memory.md").read_text(encoding="utf-8")
        assert "context_overflow" in content


# ---------------------------------------------------------------------------
# Tests: persistence across restarts
# ---------------------------------------------------------------------------


class TestPersistence:

    def test_memory_survives_reinit(self, tmp_path):
        """Memory persists after set_tayfa_dir is called again (simulating restart)."""
        import memory_manager as mm
        mm.update_memory("developer", "T042", "Done before restart")
        # Simulate restart: re-set tayfa dir
        mm.set_tayfa_dir(tmp_path)
        content = mm.build_memory("developer")
        assert "T042" in content
        assert "Done before restart" in content

    def test_memory_available_for_system_prompt_after_restart(self, tmp_path):
        """After restart, build_memory returns previous work."""
        import memory_manager as mm
        mm.update_memory("tester", "T043", "Tested POST /api/bugs")
        # Simulate restart
        mm.set_tayfa_dir(tmp_path)
        memory = mm.build_memory("tester")
        assert "Agent Memory" in memory
        assert "T043" in memory


# ---------------------------------------------------------------------------
# Tests: source code integration checks
# ---------------------------------------------------------------------------


class TestSourceIntegration:

    def test_error_path_has_update_memory(self):
        """Verify tasks.py error path calls update_memory with INTERRUPTED."""
        source = (_KOK_DIR / "routers" / "tasks.py").read_text(encoding="utf-8")
        assert 'f"INTERRUPTED after {elapsed}s, error: {err_type}"' in source

    def test_success_paths_have_update_memory(self):
        """Verify both cursor and claude success paths call update_memory."""
        source = (_KOK_DIR / "routers" / "tasks.py").read_text(encoding="utf-8")
        # Count update_memory calls — should be at least 3:
        # cursor success, claude success, error path
        count = source.count("update_memory(")
        assert count >= 3, f"Expected >=3 update_memory calls, found {count}"

    def test_claude_api_reads_memory(self):
        """Verify claude_api.py reads memory into system_prompt."""
        source = (_KOK_DIR / "claude_api.py").read_text(encoding="utf-8")
        assert "_read_agent_memory(agent, req.name)" in source
        # Should appear twice (run + run-stream)
        count = source.count("_read_agent_memory(agent, req.name)")
        assert count == 2, f"Expected 2 _read_agent_memory calls, found {count}"
