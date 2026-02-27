"""
T040: Integration tests for the Agent Load Dashboard

Verifies that:
1. GET /api/agents/metrics endpoint returns correct data for all agents
2. Time windows filter correctly (60s, 10min)
3. is_busy and current_task_id reflect actual running state
4. Token estimation is reasonable for known costs
5. Widget handles edge cases (0 agents, multiple active agents)
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
from app_state import running_tasks, estimate_tokens  # noqa: E402


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


@pytest.fixture()
def mock_employees():
    """Mock employees.json with test agents."""
    return {
        "developer": {"role": "Developer", "model": "sonnet"},
        "qa": {"role": "QA Engineer", "model": "haiku"},
        "boss": {"role": "Project Manager", "model": "opus"},
    }


def _make_message(prompt: str, cost_usd: float, duration_sec: float,
                  timestamp: str | None = None, runtime: str = "opus") -> dict:
    """Build a chat_history message dict."""
    msg = {
        "id": f"msg_{hash(prompt) % 10000:04d}",
        "timestamp": timestamp or datetime.now().isoformat(timespec="seconds"),
        "direction": "to_agent",
        "prompt": prompt,
        "result": f"response to {prompt}",
        "runtime": runtime,
        "success": True,
        "cost_usd": cost_usd,
        "duration_sec": duration_sec,
    }
    return msg


def _write_history(tayfa: Path, agent: str, messages: list[dict]):
    """Write messages directly to an agent's chat_history.json."""
    agent_dir = tayfa / agent
    agent_dir.mkdir(parents=True, exist_ok=True)
    (agent_dir / "chat_history.json").write_text(
        json.dumps(messages, ensure_ascii=False, indent=2), encoding="utf-8"
    )


# ---------------------------------------------------------------------------
# Integration tests: /api/agents/metrics endpoint
# ---------------------------------------------------------------------------

def test_metrics_endpoint_data_structure(tmp_tayfa, mock_employees):
    """Test that the metrics endpoint returns the correct data structure."""
    from routers.agents import get_agents_metrics

    # Mock employees in the routers.agents module where it's actually imported
    with patch('routers.agents._get_employees', return_value=mock_employees):
        # Create some test data
        now = datetime.now()
        msgs = [
            _make_message("test1", 0.01, 1.0, timestamp=now.isoformat(timespec="seconds"), runtime="opus"),
            _make_message("test2", 0.02, 2.0, timestamp=(now - timedelta(minutes=5)).isoformat(timespec="seconds"), runtime="sonnet"),
        ]
        _write_history(tmp_tayfa, "developer", msgs)

        # Call endpoint
        import asyncio
        result = asyncio.run(get_agents_metrics(window=60))

        # Verify structure
        assert "agents" in result
        assert "window" in result
        assert result["window"] == 60

        agents = result["agents"]
        assert "developer" in agents

        dev = agents["developer"]
        # Check required fields
        assert "is_busy" in dev
        assert "current_task_id" in dev
        assert "last_60s" in dev
        assert "last_10m" in dev
        assert "total" in dev

        # Check bucket structure
        for bucket_key in ["last_60s", "last_10m", "total"]:
            bucket = dev[bucket_key]
            assert "request_count" in bucket
            assert "cost_usd" in bucket
            assert "duration_sec" in bucket
            assert "est_input_tokens" in bucket
            assert "est_output_tokens" in bucket
            assert isinstance(bucket["request_count"], int)
            assert isinstance(bucket["cost_usd"], (int, float))
            assert isinstance(bucket["duration_sec"], (int, float))
            assert isinstance(bucket["est_input_tokens"], int)
            assert isinstance(bucket["est_output_tokens"], int)


def test_metrics_time_windows(tmp_tayfa, mock_employees):
    """Test that time windows filter correctly (60s, 10min)."""
    from routers.agents import get_agents_metrics

    with patch('routers.agents._get_employees', return_value=mock_employees):
        now = datetime.now()
        msgs = [
            # 2 hours ago — outside both 60s and 10m windows
            _make_message("old", 0.10, 5.0,
                         timestamp=(now - timedelta(hours=2)).isoformat(timespec="seconds")),
            # 5 minutes ago — inside 10m window, outside 60s window
            _make_message("recent", 0.20, 10.0,
                         timestamp=(now - timedelta(minutes=5)).isoformat(timespec="seconds")),
            # 30 seconds ago — inside both windows
            _make_message("now", 0.30, 15.0,
                         timestamp=(now - timedelta(seconds=30)).isoformat(timespec="seconds")),
        ]
        _write_history(tmp_tayfa, "developer", msgs)

        import asyncio
        result = asyncio.run(get_agents_metrics(window=60))

        dev = result["agents"]["developer"]

        # Total: all 3
        assert dev["total"]["request_count"] == 3
        assert abs(dev["total"]["cost_usd"] - 0.60) < 0.001

        # Last 10m: 2 (5min ago + 30s ago)
        assert dev["last_10m"]["request_count"] == 2
        assert abs(dev["last_10m"]["cost_usd"] - 0.50) < 0.001

        # Last 60s: 1 (only "now")
        assert dev["last_60s"]["request_count"] == 1
        assert abs(dev["last_60s"]["cost_usd"] - 0.30) < 0.001


def test_metrics_is_busy_and_current_task(tmp_tayfa, mock_employees):
    """Test that is_busy and current_task_id reflect actual running state."""
    from routers.agents import get_agents_metrics

    with patch('routers.agents._get_employees', return_value=mock_employees):
        # Simulate a running task for developer
        running_tasks["T999"] = {
            "agent": "developer",
            "role": "Developer",
            "runtime": "opus",
            "started_at": time.time(),
        }

        try:
            import asyncio
            result = asyncio.run(get_agents_metrics(window=60))

            # Developer should be busy
            dev = result["agents"]["developer"]
            assert dev["is_busy"] is True
            assert dev["current_task_id"] == "T999"

            # QA should not be busy
            qa = result["agents"]["qa"]
            assert qa["is_busy"] is False
            assert qa["current_task_id"] is None
        finally:
            # Cleanup
            running_tasks.pop("T999", None)


def test_metrics_token_estimation(tmp_tayfa, mock_employees):
    """Test that token estimation is reasonable for known costs."""
    from routers.agents import get_agents_metrics

    with patch('routers.agents._get_employees', return_value=mock_employees):
        now = datetime.now()
        # Known costs for different models
        msgs = [
            _make_message("opus_msg", 0.075, 5.0, timestamp=now.isoformat(timespec="seconds"), runtime="opus"),
            _make_message("sonnet_msg", 0.015, 3.0, timestamp=now.isoformat(timespec="seconds"), runtime="sonnet"),
            _make_message("haiku_msg", 0.001, 2.0, timestamp=now.isoformat(timespec="seconds"), runtime="haiku"),
        ]
        _write_history(tmp_tayfa, "developer", msgs)

        import asyncio
        result = asyncio.run(get_agents_metrics(window=60))

        dev = result["agents"]["developer"]

        # Check that tokens are estimated (non-zero for non-zero cost)
        assert dev["last_60s"]["est_input_tokens"] > 0
        assert dev["last_60s"]["est_output_tokens"] > 0

        # Verify token estimation logic (from app_state.estimate_tokens)
        # Opus: $15/1M input, $75/1M output (60-40 split)
        # For $0.075 total cost with 60-40 split: ~$0.045 output, $0.03 input
        # Output: 0.045 / (75/1M) = 600 tokens
        # Input: 0.03 / (15/1M) = 2000 tokens

        # Let's verify actual calculation
        opus_est = estimate_tokens(0.075, "opus")
        sonnet_est = estimate_tokens(0.015, "sonnet")
        haiku_est = estimate_tokens(0.001, "haiku")

        # Verify the estimates are reasonable (not zero, not absurdly large)
        assert 0 < opus_est["est_input_tokens"] < 100000
        assert 0 < opus_est["est_output_tokens"] < 100000
        assert 0 < sonnet_est["est_input_tokens"] < 100000
        assert 0 < sonnet_est["est_output_tokens"] < 100000
        assert 0 < haiku_est["est_input_tokens"] < 100000
        assert 0 < haiku_est["est_output_tokens"] < 100000


def test_metrics_zero_agents(tmp_tayfa):
    """Test widget handles correctly with 0 active agents."""
    from routers.agents import get_agents_metrics

    # Empty employees
    with patch('routers.agents._get_employees', return_value={}):
        import asyncio
        result = asyncio.run(get_agents_metrics(window=60))

        assert "agents" in result
        # Should return empty dict when no employees configured
        assert len(result["agents"]) == 0
        assert result["window"] == 60


def test_metrics_multiple_active_agents(tmp_tayfa, mock_employees):
    """Test widget displays correctly with multiple active agents."""
    from routers.agents import get_agents_metrics

    with patch('routers.agents._get_employees', return_value=mock_employees):
        now = datetime.now()

        # Create history for multiple agents
        dev_msgs = [_make_message("dev1", 0.01, 1.0, timestamp=now.isoformat(timespec="seconds"))]
        qa_msgs = [_make_message("qa1", 0.02, 2.0, timestamp=now.isoformat(timespec="seconds"))]
        boss_msgs = [_make_message("boss1", 0.03, 3.0, timestamp=now.isoformat(timespec="seconds"))]

        _write_history(tmp_tayfa, "developer", dev_msgs)
        _write_history(tmp_tayfa, "qa", qa_msgs)
        _write_history(tmp_tayfa, "boss", boss_msgs)

        # Simulate multiple running tasks
        running_tasks["T001"] = {"agent": "developer", "started_at": time.time()}
        running_tasks["T002"] = {"agent": "qa", "started_at": time.time()}

        try:
            import asyncio
            result = asyncio.run(get_agents_metrics(window=60))

            agents = result["agents"]

            # All three agents should be present
            assert len(agents) == 3
            assert "developer" in agents
            assert "qa" in agents
            assert "boss" in agents

            # Two should be busy
            assert agents["developer"]["is_busy"] is True
            assert agents["qa"]["is_busy"] is True
            assert agents["boss"]["is_busy"] is False

            # Each should have correct metrics
            assert agents["developer"]["last_60s"]["request_count"] == 1
            assert agents["qa"]["last_60s"]["request_count"] == 1
            assert agents["boss"]["last_60s"]["request_count"] == 1
        finally:
            # Cleanup
            running_tasks.pop("T001", None)
            running_tasks.pop("T002", None)


def test_metrics_custom_window_parameter(tmp_tayfa, mock_employees):
    """Test that custom window parameter is respected."""
    from routers.agents import get_agents_metrics

    with patch('routers.agents._get_employees', return_value=mock_employees):
        now = datetime.now()
        msgs = [
            _make_message("msg1", 0.10, 5.0,
                         timestamp=(now - timedelta(seconds=90)).isoformat(timespec="seconds")),
            _make_message("msg2", 0.20, 10.0,
                         timestamp=(now - timedelta(seconds=30)).isoformat(timespec="seconds")),
        ]
        _write_history(tmp_tayfa, "developer", msgs)

        import asyncio

        # Test with window=120 — both messages should be included
        result_120 = asyncio.run(get_agents_metrics(window=120))
        assert result_120["window"] == 120
        assert "last_120s" in result_120["agents"]["developer"]
        assert result_120["agents"]["developer"]["last_120s"]["request_count"] == 2

        # Test with window=60 — only one message should be included
        result_60 = asyncio.run(get_agents_metrics(window=60))
        assert result_60["window"] == 60
        assert "last_60s" in result_60["agents"]["developer"]
        assert result_60["agents"]["developer"]["last_60s"]["request_count"] == 1
