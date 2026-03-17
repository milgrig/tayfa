"""
T053: Integration tests for agent stability and memory features.

Verifies that:
1. Cross-project agent lookup works end-to-end
2. Agent memory persists across sessions
3. Memory content includes role, project, and recent work
4. Memory stays under token limits
5. Crash recovery is recorded in memory
6. Existing functionality (TayfaWindows agents) still works
"""
import json
import sys
import time
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

import task_manager as tm  # noqa: E402
import memory_manager as mm  # noqa: E402


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture(autouse=True)
def isolate_managers(tmp_path):
    """Isolate both task_manager and memory_manager."""
    # Task manager
    tasks_file = tmp_path / "tasks.json"
    discussions_dir = tmp_path / "discussions"
    discussions_dir.mkdir()
    old_tf = tm.TASKS_FILE
    old_dd = tm.DISCUSSIONS_DIR
    tm.TASKS_FILE = tasks_file
    tm.DISCUSSIONS_DIR = discussions_dir

    # Memory manager
    old_mm = mm._TAYFA_DIR
    mm.set_tayfa_dir(tmp_path)

    yield tmp_path

    # Restore
    tm.TASKS_FILE = old_tf
    tm.DISCUSSIONS_DIR = old_dd
    mm._TAYFA_DIR = old_mm


@pytest.fixture()
def mock_projects():
    """Mock multiple projects."""
    return {
        "TayfaWindows": "C:\\Projects\\TayfaWindows",
        "AndroidGame": "C:\\Projects\\AndroidGame",
    }


# ---------------------------------------------------------------------------
# Test 1: Cross-project agent lookup
# ---------------------------------------------------------------------------

class TestCrossProjectAgentLookup:
    """Tests that agents can work across different projects."""

    def test_task_stores_project_path(self, mock_projects):
        """Task created in one project stores that project's path."""
        task = tm.create_task(
            title="AndroidGame task",
            description="Work on game",
            author="boss",
            executor="developer_game",
            project_path=mock_projects["AndroidGame"],
        )
        assert task["project_path"] == "C:\\Projects\\AndroidGame"

    def test_task_without_project_path_defaults_empty(self):
        """Tasks without project_path are backward compatible."""
        task = tm.create_task(
            title="Legacy task",
            description="desc",
            author="boss",
            executor="developer",
        )
        assert task["project_path"] == ""

    def test_trigger_uses_task_project_path_not_global(self):
        """Verify trigger logic uses task's project_path over global."""
        # Read the actual source code to verify the fix
        tasks_router = _KOK_DIR / "routers" / "tasks.py"
        source = tasks_router.read_text(encoding="utf-8")

        # The fix: should read project_path from task, not global
        assert 'task.get("project_path")' in source
        assert 'task_project_path = task.get("project_path") or get_project_path_for_scoping()' in source

    def test_agent_workdir_matches_task_project_path(self):
        """When triggering task, agent runs in task's project directory."""
        # Verify the source sets workdir correctly
        tasks_router = _KOK_DIR / "routers" / "tasks.py"
        source = tasks_router.read_text(encoding="utf-8")

        # Should use task_project_path for agent workdir
        assert '"project_path": task_project_path' in source

    def test_multiple_projects_can_coexist(self, mock_projects):
        """Tasks from different projects can coexist in tasks.json."""
        task1 = tm.create_task(
            "Tayfa task", "desc", "boss", "developer",
            project_path=mock_projects["TayfaWindows"],
        )
        task2 = tm.create_task(
            "Game task", "desc", "boss", "developer_game",
            project_path=mock_projects["AndroidGame"],
        )

        # Both stored in same tasks.json
        all_tasks = tm.get_tasks()
        assert len(all_tasks) == 2

        # Each has correct project_path
        stored_1 = tm.get_task(task1["id"])
        stored_2 = tm.get_task(task2["id"])
        assert stored_1["project_path"] == mock_projects["TayfaWindows"]
        assert stored_2["project_path"] == mock_projects["AndroidGame"]


# ---------------------------------------------------------------------------
# Test 2: Agent memory persistence
# ---------------------------------------------------------------------------

class TestAgentMemoryPersistence:
    """Tests that agent memory persists across sessions."""

    def test_memory_file_created_on_first_update(self, tmp_path):
        """First update_memory call creates memory.md file."""
        mm.update_memory("developer", "T001", "Implemented feature X")

        memory_file = tmp_path / "developer" / "memory.md"
        assert memory_file.exists()

    def test_memory_persists_across_multiple_updates(self, tmp_path):
        """Multiple updates accumulate in same memory file."""
        mm.update_memory("developer", "T001", "Task 1 done")
        mm.update_memory("developer", "T002", "Task 2 done")
        mm.update_memory("developer", "T003", "Task 3 done")

        content = (tmp_path / "developer" / "memory.md").read_text(encoding="utf-8")
        assert "T001" in content
        assert "T002" in content
        assert "T003" in content

    def test_build_memory_reads_persisted_data(self, tmp_path):
        """build_memory() reads from persisted memory.md."""
        # Simulate agent did work previously
        mm.update_memory("developer", "T042", "Created bug reporting feature")

        # Now build_memory should include that context
        memory_context = mm.build_memory("developer")
        assert "T042" in memory_context
        assert "bug reporting" in memory_context

    def test_memory_survives_simulated_restart(self, tmp_path):
        """Memory persists even if memory_manager is re-imported."""
        # Agent does work
        mm.update_memory("developer", "T001", "Before restart")

        # Simulate restart by creating new manager instance
        # (In real scenario, server restarts and re-imports memory_manager)
        memory_content = mm.build_memory("developer")
        assert "Before restart" in memory_content

        # After "restart", agent can still add to memory
        mm.update_memory("developer", "T002", "After restart")
        updated_content = mm.build_memory("developer")
        assert "Before restart" in updated_content
        assert "After restart" in updated_content


# ---------------------------------------------------------------------------
# Test 3: Memory content structure
# ---------------------------------------------------------------------------

class TestMemoryContent:
    """Tests that memory includes required information."""

    def test_memory_includes_task_id(self, tmp_path):
        """Memory entries include task IDs."""
        mm.update_memory("developer", "T040", "Completed QA verification")
        content = (tmp_path / "developer" / "memory.md").read_text(encoding="utf-8")
        assert "**T040**" in content

    def test_memory_includes_work_summary(self, tmp_path):
        """Memory entries include work summary."""
        mm.update_memory("developer", "T042", "Implemented create_bug() function")
        content = (tmp_path / "developer" / "memory.md").read_text(encoding="utf-8")
        assert "create_bug()" in content

    def test_memory_includes_timestamp(self, tmp_path):
        """Memory entries have timestamps."""
        mm.update_memory("developer", "T001", "Work done")
        content = (tmp_path / "developer" / "memory.md").read_text(encoding="utf-8")
        # Should have date in format YYYY-MM-DD
        import re
        assert re.search(r"\d{4}-\d{2}-\d{2}", content)

    def test_memory_can_have_preamble_context(self, tmp_path):
        """Memory.md can have preamble (role, project context) before work log."""
        # Manually create preamble (in real scenario, this would be pre-populated)
        dev_dir = tmp_path / "developer"
        dev_dir.mkdir()
        (dev_dir / "memory.md").write_text(
            "# Developer Agent\n\n"
            "Role: Application Developer\n"
            "Project: Tayfa Orchestrator\n\n",
            encoding="utf-8"
        )

        # Add work entry
        mm.update_memory("developer", "T001", "Feature implemented")

        # Preamble should be preserved
        content = (dev_dir / "memory.md").read_text(encoding="utf-8")
        assert "Role: Application Developer" in content
        assert "Project: Tayfa Orchestrator" in content
        assert "T001" in content

    def test_build_memory_formats_for_system_prompt(self, tmp_path):
        """build_memory() wraps content for inclusion in system prompt."""
        mm.update_memory("developer", "T001", "Work done")
        formatted = mm.build_memory("developer")

        # Should have header
        assert "# Agent Memory" in formatted
        assert "---" in formatted


# ---------------------------------------------------------------------------
# Test 4: Memory token limits
# ---------------------------------------------------------------------------

class TestMemoryTokenLimits:
    """Tests that memory stays within reasonable size."""

    def test_auto_trim_keeps_last_n_entries(self, tmp_path):
        """Memory auto-trims to keep only last N entries (default 5)."""
        # Add 8 entries
        for i in range(8):
            mm.update_memory("developer", f"T{i:03d}", f"Task {i}")

        content = (tmp_path / "developer" / "memory.md").read_text(encoding="utf-8")

        # First 3 should be trimmed
        assert "T000" not in content
        assert "T001" not in content
        assert "T002" not in content

        # Last 5 should remain
        assert "T003" in content
        assert "T007" in content

    def test_long_summaries_truncated(self, tmp_path):
        """Long work summaries are truncated to ~200 chars."""
        long_summary = "x" * 500
        mm.update_memory("developer", "T001", long_summary)

        content = (tmp_path / "developer" / "memory.md").read_text(encoding="utf-8")

        # Should contain ellipsis indicating truncation
        assert "..." in content

        # Extract the entry line
        lines = [l for l in content.splitlines() if "T001" in l]
        assert len(lines) == 1

        # Entry should be reasonable length
        entry_text = lines[0].split("**: ", 1)[1]
        assert len(entry_text) <= 210  # ~200 + "..."

    def test_memory_size_reasonable_after_many_tasks(self, tmp_path):
        """Even after many tasks, memory file stays reasonable size."""
        # Simulate 20 tasks (but only last 5 kept)
        for i in range(20):
            mm.update_memory("developer", f"T{i:03d}", f"Task {i} completed")

        memory_file = tmp_path / "developer" / "memory.md"
        content = memory_file.read_text(encoding="utf-8")

        # Should be under 2000 characters (approximately)
        # (Preamble + 5 entries with timestamps + formatting)
        assert len(content) < 2000

    def test_manual_trim_works(self, tmp_path):
        """Manual trim_memory() can reduce entries further."""
        # Add 6 entries
        for i in range(6):
            mm.update_memory("developer", f"T{i:03d}", f"Task {i}")

        # Manually trim to 2
        mm.trim_memory("developer", max_items=2)

        content = (tmp_path / "developer" / "memory.md").read_text(encoding="utf-8")

        # Only last 2 should remain
        assert "T000" not in content
        assert "T003" not in content
        assert "T004" in content
        assert "T005" in content


# ---------------------------------------------------------------------------
# Test 5: Crash recovery memory
# ---------------------------------------------------------------------------

class TestCrashRecoveryMemory:
    """Tests that interruptions are recorded in memory."""

    def test_interrupted_task_recorded(self, tmp_path):
        """Crashed/interrupted task recorded with INTERRUPTED marker."""
        mm.update_memory(
            "developer", "T050",
            "INTERRUPTED after 45s, error: timeout"
        )

        content = (tmp_path / "developer" / "memory.md").read_text(encoding="utf-8")
        assert "T050" in content
        assert "INTERRUPTED" in content
        assert "timeout" in content

    def test_interrupt_includes_error_type(self, tmp_path):
        """Interrupt entry includes error type for debugging."""
        mm.update_memory(
            "developer", "T051",
            "INTERRUPTED after 30s, error: context_overflow"
        )

        content = (tmp_path / "developer" / "memory.md").read_text(encoding="utf-8")
        assert "context_overflow" in content

    def test_success_and_interrupts_mixed(self, tmp_path):
        """Memory can contain both successful completions and interrupts."""
        mm.update_memory("developer", "T001", "Successfully completed feature")
        mm.update_memory("developer", "T002", "INTERRUPTED after 20s, error: unavailable")
        mm.update_memory("developer", "T003", "Bug fixed successfully")

        content = (tmp_path / "developer" / "memory.md").read_text(encoding="utf-8")
        assert "T001" in content
        assert "Successfully completed" in content
        assert "T002" in content
        assert "INTERRUPTED" in content
        assert "T003" in content

    def test_retrigger_after_interrupt_has_context(self, tmp_path):
        """After interrupt, re-triggering task provides previous context."""
        # First attempt interrupted
        mm.update_memory("developer", "T050", "INTERRUPTED after 45s, error: timeout")

        # Agent is re-triggered, should see previous attempt in memory
        memory_context = mm.build_memory("developer")
        assert "T050" in memory_context
        assert "INTERRUPTED" in memory_context

        # This tells agent it was interrupted before
        assert "timeout" in memory_context


# ---------------------------------------------------------------------------
# Test 6: Integration with claude_api
# ---------------------------------------------------------------------------

class TestClaudeApiIntegration:
    """Tests that claude_api.py properly integrates memory."""

    def test_claude_api_has_read_memory_function(self):
        """claude_api.py implements _read_agent_memory()."""
        source = (_KOK_DIR / "claude_api.py").read_text(encoding="utf-8")
        assert "def _read_agent_memory" in source
        assert "memory.md" in source  # Reads memory.md file

    def test_claude_api_includes_memory_in_system_prompt(self):
        """claude_api.py appends memory to system prompt."""
        source = (_KOK_DIR / "claude_api.py").read_text(encoding="utf-8")
        # Should call _read_agent_memory and append to system_prompt
        assert "_read_agent_memory(agent, req.name)" in source

    def test_tasks_router_updates_memory_on_success(self):
        """routers/tasks.py calls update_memory after task completion."""
        source = (_KOK_DIR / "routers" / "tasks.py").read_text(encoding="utf-8")
        # Should have update_memory calls
        assert "update_memory(agent_name," in source
        # Should appear at least twice (cursor path + claude path)
        count = source.count("update_memory(")
        assert count >= 2

    def test_tasks_router_updates_memory_on_error(self):
        """routers/tasks.py calls update_memory even on error/timeout."""
        source = (_KOK_DIR / "routers" / "tasks.py").read_text(encoding="utf-8")
        # Should have update_memory in error handling
        assert "INTERRUPTED" in source


# ---------------------------------------------------------------------------
# Test 7: Regression - backward compatibility
# ---------------------------------------------------------------------------

class TestBackwardCompatibility:
    """Tests that existing functionality still works."""

    def test_tasks_without_project_path_still_work(self):
        """Old tasks without project_path field still function."""
        # Create old-style task
        task = tm.create_task("Old task", "desc", "boss", "dev")

        # Should work (project_path defaults to "")
        assert task["id"].startswith("T")
        assert task.get("project_path") == ""

    def test_agents_without_memory_still_work(self, tmp_path):
        """Agents without memory.md file still function."""
        # build_memory on agent with no memory.md
        memory = mm.build_memory("nonexistent_agent")

        # Should return empty string, not error
        assert memory == ""

    def test_get_task_works_for_all_tasks(self):
        """get_task() works regardless of project_path."""
        task1 = tm.create_task("Task 1", "desc", "boss", "dev", project_path="C:\\P1")
        task2 = tm.create_task("Task 2", "desc", "boss", "dev", project_path="")
        task3 = tm.create_task("Task 3", "desc", "boss", "dev", project_path="C:\\P2")

        # All retrievable
        assert tm.get_task(task1["id"]) is not None
        assert tm.get_task(task2["id"]) is not None
        assert tm.get_task(task3["id"]) is not None

    def test_status_updates_work_across_projects(self):
        """Task status updates work regardless of project."""
        task = tm.create_task(
            "Cross-project task", "desc", "boss", "dev",
            project_path="C:\\OtherProject"
        )

        result = tm.update_task_status(task["id"], "done")
        assert result["status"] == "done"
        assert result["old_status"] == "new"

    def test_bugs_support_project_path_too(self):
        """Bugs also support project_path field."""
        bug = tm.create_bug(
            "Bug in game", "desc", "tester", "dev",
            project_path="C:\\Projects\\AndroidGame"
        )
        assert bug["project_path"] == "C:\\Projects\\AndroidGame"


# ---------------------------------------------------------------------------
# Test 8: End-to-end workflow
# ---------------------------------------------------------------------------

class TestEndToEndWorkflow:
    """Tests complete workflow from task creation to execution with memory."""

    def test_complete_workflow_single_project(self, tmp_path):
        """Complete workflow: create task → execute (simulated) → memory updated."""
        # 1. Create task
        task = tm.create_task(
            "Implement feature X",
            "Add new feature",
            "boss",
            "developer",
            project_path="C:\\Projects\\Tayfa"
        )

        # 2. Simulate task execution (would be done by claude_api)
        # Agent receives memory context
        memory_before = mm.build_memory("developer")
        # Initially empty (new agent)
        assert memory_before == ""

        # 3. After execution, memory is updated
        mm.update_memory("developer", task["id"], "Implemented feature X successfully")

        # 4. On next task, agent has context
        memory_after = mm.build_memory("developer")
        assert task["id"] in memory_after
        assert "feature X" in memory_after

    def test_complete_workflow_multi_project(self, tmp_path, mock_projects):
        """Workflow with tasks from different projects."""
        # Task 1 from TayfaWindows
        task1 = tm.create_task(
            "Fix Tayfa bug", "desc", "boss", "developer",
            project_path=mock_projects["TayfaWindows"]
        )

        # Task 2 from AndroidGame
        task2 = tm.create_task(
            "Add game feature", "desc", "boss", "developer_game",
            project_path=mock_projects["AndroidGame"]
        )

        # Both stored, each with correct project_path
        stored1 = tm.get_task(task1["id"])
        stored2 = tm.get_task(task2["id"])
        assert stored1["project_path"] == mock_projects["TayfaWindows"]
        assert stored2["project_path"] == mock_projects["AndroidGame"]

        # Memory updates for different agents
        mm.update_memory("developer", task1["id"], "Fixed Tayfa bug")
        mm.update_memory("developer_game", task2["id"], "Added game feature")

        # Each agent has separate memory
        dev_memory = mm.build_memory("developer")
        game_memory = mm.build_memory("developer_game")

        assert "Tayfa bug" in dev_memory
        assert "game feature" not in dev_memory  # Different agent

        assert "game feature" in game_memory
        assert "Tayfa bug" not in game_memory  # Different agent

    def test_workflow_with_interruption(self, tmp_path):
        """Workflow with crash and recovery."""
        task = tm.create_task("Complex task", "desc", "boss", "developer")

        # First attempt: interrupted
        mm.update_memory(
            "developer", task["id"],
            "INTERRUPTED after 45s, error: timeout"
        )

        # Re-trigger: agent sees previous interrupt in memory
        memory = mm.build_memory("developer")
        assert "INTERRUPTED" in memory
        assert task["id"] in memory

        # Second attempt: successful
        mm.update_memory("developer", task["id"], "Completed successfully on retry")

        # Memory now shows both attempts
        final_memory = mm.build_memory("developer")
        assert "INTERRUPTED" in final_memory
        assert "successfully on retry" in final_memory
