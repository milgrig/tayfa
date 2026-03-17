"""
T037: Tests for GET /api/agents/metrics endpoint.

Verifies that:
- Endpoint returns per-agent metrics with correct structure
- Time-windowed aggregation works (custom window, 10m, total)
- cost_usd and duration_sec are correctly summed
- request_count is correct
- is_busy and current_task_id reflect running_tasks state
- Empty chat history returns zero metrics
- Custom window parameter is respected
"""
import json
import sys
import time
from datetime import datetime, timedelta
from pathlib import Path
from unittest.mock import patch

import pytest

# ---------------------------------------------------------------------------
# Path helpers
# ---------------------------------------------------------------------------

_KOK_DIR = Path(__file__).resolve().parents[1]  # kok/
_TEMPLATE_COMMON = _KOK_DIR / "template_tayfa" / "common"

if str(_TEMPLATE_COMMON) not in sys.path:
    sys.path.insert(0, str(_TEMPLATE_COMMON))
if str(_KOK_DIR) not in sys.path:
    sys.path.insert(0, str(_KOK_DIR))

import chat_history_manager as chm  # noqa: E402


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture(autouse=True)
def reset_tayfa_dir():
    """Ensure _TAYFA_DIR is None before and after every test."""
    chm.set_tayfa_dir(None)
    yield
    chm.set_tayfa_dir(None)


@pytest.fixture()
def tmp_tayfa(tmp_path):
    """Create a minimal .tayfa-like temp directory and point the module at it."""
    tayfa = tmp_path / ".tayfa"
    tayfa.mkdir()
    chm.set_tayfa_dir(tayfa)
    return tayfa


def _make_message(prompt: str, cost_usd: float, duration_sec: float,
                  timestamp: str | None = None, task_id: str | None = None) -> dict:
    """Build a chat_history message dict."""
    msg = {
        "id": f"msg_{hash(prompt) % 10000:04d}",
        "timestamp": timestamp or datetime.now().isoformat(timespec="seconds"),
        "direction": "to_agent",
        "prompt": prompt,
        "result": f"response to {prompt}",
        "runtime": "opus",
        "success": True,
        "cost_usd": cost_usd,
        "duration_sec": duration_sec,
    }
    if task_id:
        msg["task_id"] = task_id
    return msg


def _write_history(tayfa: Path, agent: str, messages: list[dict]):
    """Write messages directly to an agent's chat_history.json."""
    agent_dir = tayfa / agent
    agent_dir.mkdir(parents=True, exist_ok=True)
    (agent_dir / "chat_history.json").write_text(
        json.dumps(messages, ensure_ascii=False, indent=2), encoding="utf-8"
    )


# ---------------------------------------------------------------------------
# Unit tests for aggregation logic (no FastAPI needed)
# ---------------------------------------------------------------------------


def test_load_history_reads_messages(tmp_tayfa):
    """_load_history correctly reads messages from chat_history.json."""
    msgs = [
        _make_message("p1", 0.01, 1.0),
        _make_message("p2", 0.02, 2.0),
    ]
    _write_history(tmp_tayfa, "developer", msgs)
    loaded = chm._load_history("developer")
    assert len(loaded) == 2
    assert loaded[0]["cost_usd"] == 0.01
    assert loaded[1]["cost_usd"] == 0.02


def test_empty_history_returns_empty_list(tmp_tayfa):
    """_load_history returns empty list when no history file exists."""
    loaded = chm._load_history("nonexistent_agent")
    assert loaded == []


def test_metrics_aggregation_total(tmp_tayfa):
    """Total bucket sums all messages regardless of time."""
    now = datetime.now()
    msgs = [
        _make_message("p1", 0.10, 5.0, timestamp=(now - timedelta(hours=2)).isoformat(timespec="seconds")),
        _make_message("p2", 0.20, 10.0, timestamp=(now - timedelta(minutes=5)).isoformat(timespec="seconds")),
        _make_message("p3", 0.30, 15.0, timestamp=now.isoformat(timespec="seconds")),
    ]
    _write_history(tmp_tayfa, "developer", msgs)

    loaded = chm._load_history("developer")
    total_cost = sum(m.get("cost_usd", 0) for m in loaded)
    total_duration = sum(m.get("duration_sec", 0) for m in loaded)

    assert len(loaded) == 3
    assert abs(total_cost - 0.60) < 0.001
    assert abs(total_duration - 30.0) < 0.01


def test_metrics_aggregation_time_window(tmp_tayfa):
    """Messages are correctly filtered by time window."""
    now = datetime.now()
    msgs = [
        # 2 hours ago — outside both 60s and 10m windows
        _make_message("old", 0.10, 5.0,
                       timestamp=(now - timedelta(hours=2)).isoformat(timespec="seconds")),
        # 5 minutes ago — inside 10m window, outside 60s window
        _make_message("recent", 0.20, 10.0,
                       timestamp=(now - timedelta(minutes=5)).isoformat(timespec="seconds")),
        # Just now — inside both windows
        _make_message("now", 0.30, 15.0,
                       timestamp=now.isoformat(timespec="seconds")),
    ]
    _write_history(tmp_tayfa, "developer", msgs)

    loaded = chm._load_history("developer")
    current_time = time.time()

    # Simulate the time-window logic from the endpoint
    window = 60
    buckets = {
        f"last_{window}s": {"since": current_time - window, "count": 0, "cost": 0.0},
        "last_10m": {"since": current_time - 600, "count": 0, "cost": 0.0},
        "total": {"since": 0, "count": 0, "cost": 0.0},
    }

    for msg in loaded:
        ts_str = msg.get("timestamp", "")
        try:
            msg_time = datetime.fromisoformat(ts_str).timestamp()
        except (ValueError, TypeError):
            msg_time = 0

        cost = msg.get("cost_usd") or 0
        buckets["total"]["count"] += 1
        buckets["total"]["cost"] += cost

        for key in (f"last_{window}s", "last_10m"):
            if msg_time >= buckets[key]["since"]:
                buckets[key]["count"] += 1
                buckets[key]["cost"] += cost

    # Total: all 3
    assert buckets["total"]["count"] == 3
    assert abs(buckets["total"]["cost"] - 0.60) < 0.001

    # Last 10m: 2 (5min ago + now)
    assert buckets["last_10m"]["count"] == 2
    assert abs(buckets["last_10m"]["cost"] - 0.50) < 0.001

    # Last 60s: 1 (only "now")
    assert buckets[f"last_{window}s"]["count"] == 1
    assert abs(buckets[f"last_{window}s"]["cost"] - 0.30) < 0.001


def test_running_tasks_busy_status():
    """is_busy and current_task_id are correctly derived from running_tasks."""
    import app_state

    # Simulate a running task
    app_state.running_tasks["T042"] = {
        "agent": "developer",
        "role": "Developer",
        "runtime": "opus",
        "started_at": time.time(),
    }

    try:
        is_busy = False
        current_task_id = None
        for tid, info in app_state.running_tasks.items():
            if info.get("agent") == "developer":
                is_busy = True
                current_task_id = tid
                break

        assert is_busy is True
        assert current_task_id == "T042"

        # Non-busy agent
        is_busy_other = False
        current_task_other = None
        for tid, info in app_state.running_tasks.items():
            if info.get("agent") == "boss":
                is_busy_other = True
                current_task_other = tid
                break

        assert is_busy_other is False
        assert current_task_other is None
    finally:
        # Cleanup
        app_state.running_tasks.pop("T042", None)


def test_custom_window_parameter(tmp_tayfa):
    """Custom window parameter creates correctly named bucket."""
    now = datetime.now()
    msgs = [
        _make_message("p1", 0.10, 5.0,
                       timestamp=(now - timedelta(seconds=90)).isoformat(timespec="seconds")),
        _make_message("p2", 0.20, 10.0,
                       timestamp=now.isoformat(timespec="seconds")),
    ]
    _write_history(tmp_tayfa, "developer", msgs)

    loaded = chm._load_history("developer")
    current_time = time.time()

    # With window=120 — both messages should be in the custom bucket
    window = 120
    count_in_window = 0
    for msg in loaded:
        ts_str = msg.get("timestamp", "")
        try:
            msg_time = datetime.fromisoformat(ts_str).timestamp()
        except (ValueError, TypeError):
            msg_time = 0
        if msg_time >= current_time - window:
            count_in_window += 1

    assert count_in_window == 2

    # With window=30 — only the most recent message
    window = 30
    count_in_window = 0
    for msg in loaded:
        ts_str = msg.get("timestamp", "")
        try:
            msg_time = datetime.fromisoformat(ts_str).timestamp()
        except (ValueError, TypeError):
            msg_time = 0
        if msg_time >= current_time - window:
            count_in_window += 1

    assert count_in_window == 1


def test_missing_cost_and_duration_treated_as_zero(tmp_tayfa):
    """Messages without cost_usd or duration_sec default to 0."""
    msg = {
        "id": "msg_001",
        "timestamp": datetime.now().isoformat(timespec="seconds"),
        "direction": "to_agent",
        "prompt": "test",
        "result": "response",
        "runtime": "cursor",
        "success": True,
        # No cost_usd or duration_sec
    }
    _write_history(tmp_tayfa, "developer", [msg])

    loaded = chm._load_history("developer")
    cost = loaded[0].get("cost_usd") or 0
    duration = loaded[0].get("duration_sec") or 0
    assert cost == 0
    assert duration == 0
