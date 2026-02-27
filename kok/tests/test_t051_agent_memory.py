"""
T051: Tests for agent memory system (memory_manager.py).

Verifies that:
- build_memory() reads memory.md and formats it for system prompt
- update_memory() appends work log entries
- trim_memory() keeps only last N entries
- Auto-trim on update works
- Empty/missing memory files handled gracefully
- Memory survives across calls (persistent file)
- Integration: claude_api.py reads memory from workdir
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


@pytest.fixture()
def agent_dir(tmp_path):
    """Create agent directory."""
    d = tmp_path / "developer"
    d.mkdir()
    return d


# ---------------------------------------------------------------------------
# Tests: build_memory
# ---------------------------------------------------------------------------


class TestBuildMemory:

    def test_empty_when_no_file(self):
        import memory_manager as mm
        assert mm.build_memory("developer") == ""

    def test_reads_existing_file(self, agent_dir):
        import memory_manager as mm
        (agent_dir / "memory.md").write_text("Some context here", encoding="utf-8")
        result = mm.build_memory("developer")
        assert "Agent Memory" in result
        assert "Some context here" in result

    def test_wraps_with_header(self, agent_dir):
        import memory_manager as mm
        (agent_dir / "memory.md").write_text("test content", encoding="utf-8")
        result = mm.build_memory("developer")
        assert result.startswith("\n\n---\n\n# Agent Memory")
        assert "test content" in result


# ---------------------------------------------------------------------------
# Tests: update_memory
# ---------------------------------------------------------------------------


class TestUpdateMemory:

    def test_creates_file_if_missing(self, tmp_path):
        import memory_manager as mm
        assert mm.update_memory("developer", "T001", "Did something")
        path = tmp_path / "developer" / "memory.md"
        assert path.exists()
        content = path.read_text(encoding="utf-8")
        assert "T001" in content
        assert "Did something" in content

    def test_appends_entry(self, agent_dir):
        import memory_manager as mm
        mm.update_memory("developer", "T001", "First task")
        mm.update_memory("developer", "T002", "Second task")
        content = (agent_dir / "memory.md").read_text(encoding="utf-8")
        assert "T001" in content
        assert "T002" in content

    def test_preserves_preamble(self, agent_dir):
        import memory_manager as mm
        (agent_dir / "memory.md").write_text(
            "# Context\n\nThis is the project context.\n", encoding="utf-8"
        )
        mm.update_memory("developer", "T001", "Did work")
        content = (agent_dir / "memory.md").read_text(encoding="utf-8")
        assert "This is the project context." in content
        assert "T001" in content

    def test_truncates_long_summary(self, agent_dir):
        import memory_manager as mm
        long_text = "x" * 300
        mm.update_memory("developer", "T001", long_text)
        content = (agent_dir / "memory.md").read_text(encoding="utf-8")
        assert "..." in content
        # Should be truncated to ~200 chars
        lines = [l for l in content.splitlines() if "T001" in l]
        assert len(lines) == 1
        # The entry after "- [timestamp] **T001**: " should be <=200
        entry_text = lines[0].split("**: ", 1)[1]
        assert len(entry_text) <= 200

    def test_auto_trims_to_max_items(self, agent_dir):
        import memory_manager as mm
        for i in range(8):
            mm.update_memory("developer", f"T{i:03d}", f"Task {i}")
        content = (agent_dir / "memory.md").read_text(encoding="utf-8")
        # Default max is 5, so T000-T002 should be trimmed
        assert "T000" not in content
        assert "T001" not in content
        assert "T002" not in content
        assert "T003" in content
        assert "T007" in content

    def test_newlines_in_summary_replaced(self, agent_dir):
        import memory_manager as mm
        mm.update_memory("developer", "T001", "line1\nline2\nline3")
        content = (agent_dir / "memory.md").read_text(encoding="utf-8")
        # Summary should be single line
        entry_lines = [l for l in content.splitlines() if "T001" in l]
        assert len(entry_lines) == 1
        assert "\n" not in entry_lines[0].split("T001")[1]


# ---------------------------------------------------------------------------
# Tests: trim_memory
# ---------------------------------------------------------------------------


class TestTrimMemory:

    def test_trim_noop_when_under_limit(self, agent_dir):
        import memory_manager as mm
        mm.update_memory("developer", "T001", "Task 1")
        mm.update_memory("developer", "T002", "Task 2")
        assert mm.trim_memory("developer", max_items=5)
        content = (agent_dir / "memory.md").read_text(encoding="utf-8")
        assert "T001" in content
        assert "T002" in content

    def test_trim_removes_oldest(self, agent_dir):
        import memory_manager as mm
        for i in range(6):
            mm.update_memory("developer", f"T{i:03d}", f"Task {i}")
        # Now trim to 3
        assert mm.trim_memory("developer", max_items=3)
        content = (agent_dir / "memory.md").read_text(encoding="utf-8")
        assert "T000" not in content
        assert "T001" not in content
        assert "T002" not in content
        assert "T003" in content
        assert "T005" in content

    def test_trim_empty_file(self):
        import memory_manager as mm
        assert mm.trim_memory("nonexistent", max_items=5)


# ---------------------------------------------------------------------------
# Tests: work log parsing round-trip
# ---------------------------------------------------------------------------


class TestWorkLogParsing:

    def test_roundtrip(self, agent_dir):
        import memory_manager as mm
        preamble = "# Project\n\nSome context."
        (agent_dir / "memory.md").write_text(preamble, encoding="utf-8")
        mm.update_memory("developer", "T001", "First task done")
        mm.update_memory("developer", "T002", "Second task done")
        content = (agent_dir / "memory.md").read_text(encoding="utf-8")
        # Preamble preserved
        assert content.startswith("# Project\n\nSome context.")
        # Work log present
        assert "## Recent Work Log" in content
        assert "**T001**" in content
        assert "**T002**" in content


# ---------------------------------------------------------------------------
# Tests: integration with claude_api.py
# ---------------------------------------------------------------------------


class TestClaudeApiIntegration:

    def test_read_agent_memory_in_source(self):
        """Verify claude_api.py has _read_agent_memory integration."""
        source = (_KOK_DIR / "claude_api.py").read_text(encoding="utf-8")
        assert "def _read_agent_memory" in source
        assert "_read_agent_memory(agent, req.name)" in source

    def test_update_memory_in_tasks_router(self):
        """Verify routers/tasks.py calls update_memory after save_chat_message."""
        source = (_KOK_DIR / "routers" / "tasks.py").read_text(encoding="utf-8")
        assert "update_memory(" in source
        # Should appear twice (cursor path + claude path)
        assert source.count("update_memory(agent_name,") >= 2
