"""Tests for T019: Sprint analytics auto-report."""

import json
import sys
from pathlib import Path
from unittest.mock import patch, MagicMock

import pytest

# Add kok/ and its dependencies to path
KOK_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(KOK_DIR))
sys.path.insert(0, str(KOK_DIR / "template_tayfa" / "common"))


# ---------------------------------------------------------------------------
# TC-1: Duration formatting
# ---------------------------------------------------------------------------
@pytest.mark.unit
class TestFormatDuration:

    def test_zero(self):
        from task_manager import _format_duration
        assert _format_duration(0) == "0s"

    def test_seconds_only(self):
        from task_manager import _format_duration
        assert _format_duration(45) == "45s"

    def test_minutes_and_seconds(self):
        from task_manager import _format_duration
        assert _format_duration(150) == "2m 30s"

    def test_hours_minutes_seconds(self):
        from task_manager import _format_duration
        assert _format_duration(3723) == "1h 02m 03s"

    def test_exact_hour(self):
        from task_manager import _format_duration
        assert _format_duration(3600) == "1h 00m 00s"


# ---------------------------------------------------------------------------
# TC-2: Tester return count
# ---------------------------------------------------------------------------
@pytest.mark.unit
class TestTesterReturnCount:

    def test_no_tester_messages(self):
        from task_manager import _count_tester_returns
        msgs = [
            {"role": "developer", "task_id": "T001"},
        ]
        assert _count_tester_returns(msgs) == 0

    def test_one_tester_message_no_returns(self):
        from task_manager import _count_tester_returns
        msgs = [
            {"role": "developer", "task_id": "T001"},
            {"role": "tester", "task_id": "T001"},
        ]
        assert _count_tester_returns(msgs) == 0

    def test_two_tester_messages_one_return(self):
        from task_manager import _count_tester_returns
        msgs = [
            {"role": "developer", "task_id": "T001"},
            {"role": "tester", "task_id": "T001"},
            {"role": "developer", "task_id": "T001"},
            {"role": "tester", "task_id": "T001"},
        ]
        assert _count_tester_returns(msgs) == 1

    def test_russian_tester_role(self):
        from task_manager import _count_tester_returns
        msgs = [
            {"role": "разработчик", "task_id": "T001"},
            {"role": "тестер", "task_id": "T001"},
            {"role": "разработчик", "task_id": "T001"},
            {"role": "тестер", "task_id": "T001"},
            {"role": "разработчик", "task_id": "T001"},
            {"role": "тестер", "task_id": "T001"},
        ]
        assert _count_tester_returns(msgs) == 2

    def test_тестировщик_role(self):
        from task_manager import _count_tester_returns
        msgs = [
            {"role": "тестировщик", "task_id": "T001"},
        ]
        assert _count_tester_returns(msgs) == 0

    def test_empty_messages(self):
        from task_manager import _count_tester_returns
        assert _count_tester_returns([]) == 0


# ---------------------------------------------------------------------------
# TC-3: Error pattern extraction
# ---------------------------------------------------------------------------
@pytest.mark.unit
class TestErrorPatterns:

    def test_extracts_frequent_words(self):
        from task_manager import _extract_error_patterns
        tasks = [
            {"id": "T001", "result": "Tests failed because import missing. Tests crashed again."},
            {"id": "T002", "result": "Build failed, tests failed on module load."},
        ]
        returns_map = {"T001": 1, "T002": 1}
        patterns = _extract_error_patterns(tasks, returns_map)
        # "failed" appears 3 times, should be top
        words = [w for w, c in patterns]
        assert "failed" in words

    def test_skips_tasks_without_returns(self):
        from task_manager import _extract_error_patterns
        tasks = [
            {"id": "T001", "result": "Everything works perfectly fine"},
            {"id": "T002", "result": "Tests failed badly"},
        ]
        returns_map = {"T001": 0, "T002": 1}
        patterns = _extract_error_patterns(tasks, returns_map)
        words = [w for w, c in patterns]
        # "perfectly" and "everything" should NOT appear (T001 has 0 returns)
        assert "perfectly" not in words
        assert "everything" not in words

    def test_empty_results(self):
        from task_manager import _extract_error_patterns
        tasks = [{"id": "T001", "result": ""}]
        returns_map = {"T001": 1}
        assert _extract_error_patterns(tasks, returns_map) == []


# ---------------------------------------------------------------------------
# TC-4: Report generation with mock data
# ---------------------------------------------------------------------------
@pytest.mark.unit
class TestGenerateSprintReport:

    def test_report_created_with_correct_content(self, tmp_path):
        from task_manager import generate_sprint_report, set_tasks_file

        # Setup mock project structure
        common_dir = tmp_path / ".tayfa" / "common"
        common_dir.mkdir(parents=True)

        tasks_data = {
            "tasks": [
                {
                    "id": "T_a", "title": "Task A", "status": "done",
                    "developer": "dev", "tester": "qa", "customer": "boss",
                    "result": "", "sprint_id": "S_test", "depends_on": [],
                    "created_at": "2026-01-01T00:00:00", "updated_at": "2026-01-01T01:00:00",
                },
                {
                    "id": "T_b", "title": "Task B", "status": "done",
                    "developer": "dev", "tester": "qa", "customer": "boss",
                    "result": "Fixed tests after tester feedback",
                    "sprint_id": "S_test", "depends_on": [],
                    "created_at": "2026-01-01T00:00:00", "updated_at": "2026-01-01T02:00:00",
                },
                {
                    "id": "T_fin", "title": "Finalize sprint", "status": "done",
                    "developer": "boss", "tester": "boss", "customer": "boss",
                    "result": "", "sprint_id": "S_test", "depends_on": ["T_a", "T_b"],
                    "is_finalize": True,
                    "created_at": "2026-01-01T00:00:00", "updated_at": "2026-01-01T03:00:00",
                },
            ],
            "sprints": [
                {
                    "id": "S_test", "title": "Test Sprint", "status": "released",
                    "version": "v1.0.0", "created_by": "boss",
                    "created_at": "2026-01-01T00:00:00", "updated_at": "2026-01-01T03:00:00",
                },
            ],
            "next_id": 4,
            "next_sprint_id": 2,
        }
        tasks_file = common_dir / "tasks.json"
        tasks_file.write_text(json.dumps(tasks_data), encoding="utf-8")

        # Create chat history for dev agent
        dev_dir = tmp_path / ".tayfa" / "dev"
        dev_dir.mkdir(parents=True)
        dev_history = [
            {"task_id": "T_a", "role": "developer", "duration_sec": 120, "cost_usd": 0.10},
            {"task_id": "T_b", "role": "developer", "duration_sec": 300, "cost_usd": 0.50},
            {"task_id": "T_b", "role": "developer", "duration_sec": 60, "cost_usd": 0.05},
        ]
        (dev_dir / "chat_history.json").write_text(json.dumps(dev_history), encoding="utf-8")

        # Create chat history for qa agent
        qa_dir = tmp_path / ".tayfa" / "qa"
        qa_dir.mkdir(parents=True)
        qa_history = [
            {"task_id": "T_a", "role": "tester", "duration_sec": 30, "cost_usd": 0.02},
            {"task_id": "T_b", "role": "tester", "duration_sec": 45, "cost_usd": 0.03},
            {"task_id": "T_b", "role": "tester", "duration_sec": 50, "cost_usd": 0.04},
        ]
        (qa_dir / "chat_history.json").write_text(json.dumps(qa_history), encoding="utf-8")

        # Set tasks file path
        set_tasks_file(tasks_file)

        # Generate report
        result = generate_sprint_report("S_test")

        assert result["generated"] is True
        assert result["error"] is None

        # Check file exists
        report_path = Path(result["path"])
        assert report_path.exists()

        content = report_path.read_text(encoding="utf-8")

        # Verify key sections
        assert "# Sprint S_test Report: Test Sprint" in content
        assert "## Summary" in content
        assert "Total tasks: 2" in content  # excludes finalize
        assert "## Tasks" in content
        assert "T_a" in content
        assert "T_b" in content
        assert "## Slowest Tasks" in content
        assert "## Most Returned Tasks" in content
        assert "## Cost Breakdown" in content

    def test_report_no_chat_history_graceful(self, tmp_path):
        from task_manager import generate_sprint_report, set_tasks_file

        common_dir = tmp_path / ".tayfa" / "common"
        common_dir.mkdir(parents=True)

        tasks_data = {
            "tasks": [
                {
                    "id": "T_x", "title": "Task X", "status": "done",
                    "developer": "dev", "tester": "qa", "customer": "boss",
                    "result": "", "sprint_id": "S_empty",
                    "created_at": "2026-01-01T00:00:00", "updated_at": "2026-01-01T01:00:00",
                },
            ],
            "sprints": [
                {
                    "id": "S_empty", "title": "Empty Sprint", "status": "completed",
                    "created_by": "boss",
                    "created_at": "2026-01-01T00:00:00", "updated_at": "2026-01-01T01:00:00",
                },
            ],
            "next_id": 2,
            "next_sprint_id": 2,
        }
        tasks_file = common_dir / "tasks.json"
        tasks_file.write_text(json.dumps(tasks_data), encoding="utf-8")
        set_tasks_file(tasks_file)

        # Generate report — no chat history at all
        result = generate_sprint_report("S_empty")

        assert result["generated"] is True
        assert result["error"] is None

        content = Path(result["path"]).read_text(encoding="utf-8")
        assert "N/A" in content  # Duration/cost shown as N/A
        assert "No tester returns" in content

    def test_report_sprint_not_found(self, tmp_path):
        from task_manager import generate_sprint_report, set_tasks_file

        common_dir = tmp_path / ".tayfa" / "common"
        common_dir.mkdir(parents=True)
        tasks_data = {"tasks": [], "sprints": [], "next_id": 1, "next_sprint_id": 1}
        tasks_file = common_dir / "tasks.json"
        tasks_file.write_text(json.dumps(tasks_data), encoding="utf-8")
        set_tasks_file(tasks_file)

        result = generate_sprint_report("S_nonexistent")
        assert result["generated"] is False
        assert "not found" in result["error"]

    def test_tester_returns_counted_correctly(self, tmp_path):
        """T_b has 2 tester messages -> 1 return."""
        from task_manager import generate_sprint_report, set_tasks_file

        common_dir = tmp_path / ".tayfa" / "common"
        common_dir.mkdir(parents=True)

        tasks_data = {
            "tasks": [
                {
                    "id": "T_b", "title": "Task B", "status": "done",
                    "developer": "dev", "tester": "qa", "customer": "boss",
                    "result": "", "sprint_id": "S_ret",
                    "created_at": "2026-01-01T00:00:00", "updated_at": "2026-01-01T01:00:00",
                },
            ],
            "sprints": [
                {
                    "id": "S_ret", "title": "Return Sprint", "status": "released",
                    "version": "v1.0.0", "created_by": "boss",
                    "created_at": "2026-01-01T00:00:00", "updated_at": "2026-01-01T01:00:00",
                },
            ],
            "next_id": 2,
            "next_sprint_id": 2,
        }
        tasks_file = common_dir / "tasks.json"
        tasks_file.write_text(json.dumps(tasks_data), encoding="utf-8")

        qa_dir = tmp_path / ".tayfa" / "qa"
        qa_dir.mkdir(parents=True)
        qa_history = [
            {"task_id": "T_b", "role": "tester", "duration_sec": 30, "cost_usd": 0.02},
            {"task_id": "T_b", "role": "tester", "duration_sec": 40, "cost_usd": 0.03},
        ]
        (qa_dir / "chat_history.json").write_text(json.dumps(qa_history), encoding="utf-8")
        set_tasks_file(tasks_file)

        result = generate_sprint_report("S_ret")
        assert result["generated"] is True

        content = Path(result["path"]).read_text(encoding="utf-8")
        assert "Tester returns (total): 1" in content
        assert "tasks sent back at least once: 1" in content


# ---------------------------------------------------------------------------
# TC-5: Chat history collection
# ---------------------------------------------------------------------------
@pytest.mark.unit
class TestCollectChatHistory:

    def test_collects_from_multiple_agents(self, tmp_path):
        from task_manager import _collect_chat_history_for_sprint

        # Agent 1
        a1 = tmp_path / "agent1"
        a1.mkdir()
        (a1 / "chat_history.json").write_text(json.dumps([
            {"task_id": "T001", "role": "developer", "duration_sec": 100},
        ]), encoding="utf-8")

        # Agent 2
        a2 = tmp_path / "agent2"
        a2.mkdir()
        (a2 / "chat_history.json").write_text(json.dumps([
            {"task_id": "T001", "role": "tester", "duration_sec": 50},
            {"task_id": "T002", "role": "tester", "duration_sec": 30},
        ]), encoding="utf-8")

        result = _collect_chat_history_for_sprint(tmp_path, {"T001", "T002"})
        assert len(result["T001"]) == 2
        assert len(result["T002"]) == 1

    def test_empty_tayfa_dir(self, tmp_path):
        from task_manager import _collect_chat_history_for_sprint
        result = _collect_chat_history_for_sprint(tmp_path, {"T001"})
        assert result["T001"] == []

    def test_nonexistent_dir(self):
        from task_manager import _collect_chat_history_for_sprint
        result = _collect_chat_history_for_sprint(Path("/nonexistent"), {"T001"})
        assert result["T001"] == []


# ---------------------------------------------------------------------------
# TC-6: Duration aggregation per task
# ---------------------------------------------------------------------------
@pytest.mark.unit
class TestDurationAggregation:

    def test_sums_across_messages(self, tmp_path):
        from task_manager import generate_sprint_report, set_tasks_file

        common_dir = tmp_path / ".tayfa" / "common"
        common_dir.mkdir(parents=True)

        tasks_data = {
            "tasks": [
                {
                    "id": "T_d", "title": "Duration Task", "status": "done",
                    "developer": "dev", "tester": "qa", "customer": "boss",
                    "result": "", "sprint_id": "S_dur",
                    "created_at": "2026-01-01T00:00:00", "updated_at": "2026-01-01T01:00:00",
                },
            ],
            "sprints": [
                {
                    "id": "S_dur", "title": "Dur Sprint", "status": "completed",
                    "created_by": "boss",
                    "created_at": "2026-01-01T00:00:00", "updated_at": "2026-01-01T01:00:00",
                },
            ],
            "next_id": 2,
            "next_sprint_id": 2,
        }
        tasks_file = common_dir / "tasks.json"
        tasks_file.write_text(json.dumps(tasks_data), encoding="utf-8")

        dev_dir = tmp_path / ".tayfa" / "dev"
        dev_dir.mkdir(parents=True)
        (dev_dir / "chat_history.json").write_text(json.dumps([
            {"task_id": "T_d", "role": "developer", "duration_sec": 120, "cost_usd": 0.10},
            {"task_id": "T_d", "role": "tester", "duration_sec": 30, "cost_usd": 0.02},
        ]), encoding="utf-8")
        set_tasks_file(tasks_file)

        result = generate_sprint_report("S_dur")
        assert result["generated"] is True
        content = Path(result["path"]).read_text(encoding="utf-8")
        # 120 + 30 = 150s = 2m 30s
        assert "2m 30s" in content
