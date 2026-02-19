"""Tests for T056: Per-agent parallelization semaphore (max 1 task per agent).

Tests that agent_locks dict exists, get_agent_lock returns consistent Semaphore(1),
same-agent tasks run sequentially, different-agent tasks run in parallel,
and semaphore is released on error.
"""

import asyncio
import sys
import time
from pathlib import Path

import pytest

# Add kok/ and its dependencies to path
KOK_DIR = Path(__file__).resolve().parent.parent
TEMPLATE_COMMON = KOK_DIR / "template_tayfa" / "common"
sys.path.insert(0, str(TEMPLATE_COMMON))
sys.path.insert(0, str(KOK_DIR))


# ---------------------------------------------------------------------------
# Tests: agent_locks dict exists
# ---------------------------------------------------------------------------

class TestAgentLocksDict:

    def test_agent_locks_dict_exists(self):
        from app import agent_locks
        assert isinstance(agent_locks, dict)


# ---------------------------------------------------------------------------
# Tests: get_agent_lock returns Semaphore
# ---------------------------------------------------------------------------

class TestGetAgentLock:

    def test_returns_semaphore(self):
        from app import get_agent_lock, agent_locks
        # Clean up any stale state
        agent_locks.pop("test_agent_lock_1", None)
        lock = get_agent_lock("test_agent_lock_1")
        assert isinstance(lock, asyncio.Semaphore)
        # Clean up
        agent_locks.pop("test_agent_lock_1", None)

    def test_same_agent_returns_same_instance(self):
        from app import get_agent_lock, agent_locks
        agent_locks.pop("test_agent_lock_2", None)
        lock1 = get_agent_lock("test_agent_lock_2")
        lock2 = get_agent_lock("test_agent_lock_2")
        assert lock1 is lock2
        agent_locks.pop("test_agent_lock_2", None)

    def test_different_agents_return_different_instances(self):
        from app import get_agent_lock, agent_locks
        agent_locks.pop("test_agent_a", None)
        agent_locks.pop("test_agent_b", None)
        lock_a = get_agent_lock("test_agent_a")
        lock_b = get_agent_lock("test_agent_b")
        assert lock_a is not lock_b
        agent_locks.pop("test_agent_a", None)
        agent_locks.pop("test_agent_b", None)

    def test_initial_value_is_1(self):
        from app import get_agent_lock, agent_locks
        agent_locks.pop("test_agent_lock_3", None)
        lock = get_agent_lock("test_agent_lock_3")
        # asyncio.Semaphore stores internal value as _value
        assert lock._value == 1
        agent_locks.pop("test_agent_lock_3", None)


# ---------------------------------------------------------------------------
# Tests: same-agent tasks run sequentially
# ---------------------------------------------------------------------------

class TestSameAgentSequential:

    @pytest.mark.asyncio
    async def test_second_task_same_agent_waits(self):
        """Two coroutines for the same agent should run sequentially, not in parallel."""
        from app import get_agent_lock, agent_locks

        agent_name = "test_sequential_agent"
        agent_locks.pop(agent_name, None)

        execution_log: list[tuple[str, float]] = []

        async def fake_task(task_label: str):
            async with get_agent_lock(agent_name):
                execution_log.append((f"{task_label}_start", time.monotonic()))
                await asyncio.sleep(0.1)  # simulate work
                execution_log.append((f"{task_label}_end", time.monotonic()))

        await asyncio.gather(fake_task("A"), fake_task("B"))

        # Both tasks completed
        labels = [e[0] for e in execution_log]
        assert "A_start" in labels
        assert "A_end" in labels
        assert "B_start" in labels
        assert "B_end" in labels

        # They must be sequential: one must finish before the other starts
        times = {e[0]: e[1] for e in execution_log}

        # Either A finishes before B starts, or B finishes before A starts
        a_before_b = times["A_end"] <= times["B_start"]
        b_before_a = times["B_end"] <= times["A_start"]
        assert a_before_b or b_before_a, (
            f"Tasks overlapped! A: {times['A_start']:.4f}-{times['A_end']:.4f}, "
            f"B: {times['B_start']:.4f}-{times['B_end']:.4f}"
        )

        agent_locks.pop(agent_name, None)


# ---------------------------------------------------------------------------
# Tests: different agents run in parallel
# ---------------------------------------------------------------------------

class TestDifferentAgentsParallel:

    @pytest.mark.asyncio
    async def test_different_agents_run_parallel(self):
        """Two coroutines for different agents should overlap in time."""
        from app import get_agent_lock, agent_locks

        agent_a = "test_parallel_agent_a"
        agent_b = "test_parallel_agent_b"
        agent_locks.pop(agent_a, None)
        agent_locks.pop(agent_b, None)

        execution_log: list[tuple[str, float]] = []

        async def fake_task(agent_name: str, task_label: str):
            async with get_agent_lock(agent_name):
                execution_log.append((f"{task_label}_start", time.monotonic()))
                await asyncio.sleep(0.1)  # simulate work
                execution_log.append((f"{task_label}_end", time.monotonic()))

        await asyncio.gather(fake_task(agent_a, "A"), fake_task(agent_b, "B"))

        times = {e[0]: e[1] for e in execution_log}

        # Both tasks should overlap: A starts before B ends AND B starts before A ends
        a_overlaps_b = times["A_start"] < times["B_end"] and times["B_start"] < times["A_end"]
        assert a_overlaps_b, (
            f"Tasks did not overlap! A: {times['A_start']:.4f}-{times['A_end']:.4f}, "
            f"B: {times['B_start']:.4f}-{times['B_end']:.4f}"
        )

        agent_locks.pop(agent_a, None)
        agent_locks.pop(agent_b, None)


# ---------------------------------------------------------------------------
# Tests: semaphore released on error
# ---------------------------------------------------------------------------

class TestSemaphoreReleasedOnError:

    @pytest.mark.asyncio
    async def test_semaphore_released_on_error(self):
        """If execution raises, the semaphore must still be released."""
        from app import get_agent_lock, agent_locks

        agent_name = "test_error_agent"
        agent_locks.pop(agent_name, None)

        lock = get_agent_lock(agent_name)
        assert lock._value == 1

        with pytest.raises(RuntimeError, match="boom"):
            async with get_agent_lock(agent_name):
                raise RuntimeError("boom")

        # Semaphore should be released back to 1
        assert lock._value == 1

        agent_locks.pop(agent_name, None)
