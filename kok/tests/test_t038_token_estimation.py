"""
T038: Tests for token estimation from cost_usd.

Verifies that:
- estimate_tokens correctly calculates tokens for opus, sonnet, haiku models
- Zero/negative cost returns zero tokens
- Unknown model returns zero tokens
- Token estimates are properly integrated into metrics buckets
- Multi-model cost aggregation produces correct per-model token estimates
"""
import json
import sys
import time
from datetime import datetime, timedelta
from pathlib import Path

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

from app_state import estimate_tokens  # noqa: E402
import chat_history_manager as chm  # noqa: E402


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture(autouse=True)
def reset_tayfa_dir():
    chm.set_tayfa_dir(None)
    yield
    chm.set_tayfa_dir(None)


@pytest.fixture()
def tmp_tayfa(tmp_path):
    tayfa = tmp_path / ".tayfa"
    tayfa.mkdir()
    chm.set_tayfa_dir(tayfa)
    return tayfa


def _write_history(tayfa: Path, agent: str, messages: list[dict]):
    agent_dir = tayfa / agent
    agent_dir.mkdir(parents=True, exist_ok=True)
    (agent_dir / "chat_history.json").write_text(
        json.dumps(messages, ensure_ascii=False, indent=2), encoding="utf-8"
    )


# ---------------------------------------------------------------------------
# estimate_tokens() unit tests
# ---------------------------------------------------------------------------


class TestEstimateTokensOpus:
    """Opus pricing: $15/1M input, $75/1M output."""

    def test_basic_opus_input(self):
        """$0.015 at opus input rate = 1000 tokens."""
        result = estimate_tokens(0.015, "opus")
        assert result["est_input_tokens"] == 1000

    def test_basic_opus_output(self):
        """$0.075 at opus output rate = 1000 tokens."""
        result = estimate_tokens(0.075, "opus")
        assert result["est_output_tokens"] == 1000

    def test_opus_1_dollar(self):
        """$1.00 at opus rates."""
        result = estimate_tokens(1.0, "opus")
        # input: 1.0 / (15/1M) = 66667 tokens
        assert result["est_input_tokens"] == round(1_000_000 / 15)
        # output: 1.0 / (75/1M) = 13333 tokens
        assert result["est_output_tokens"] == round(1_000_000 / 75)


class TestEstimateTokensSonnet:
    """Sonnet pricing: $3/1M input, $15/1M output."""

    def test_basic_sonnet_input(self):
        """$0.003 at sonnet input rate = 1000 tokens."""
        result = estimate_tokens(0.003, "sonnet")
        assert result["est_input_tokens"] == 1000

    def test_basic_sonnet_output(self):
        """$0.015 at sonnet output rate = 1000 tokens."""
        result = estimate_tokens(0.015, "sonnet")
        assert result["est_output_tokens"] == 1000

    def test_sonnet_1_dollar(self):
        """$1.00 at sonnet rates."""
        result = estimate_tokens(1.0, "sonnet")
        assert result["est_input_tokens"] == round(1_000_000 / 3)
        assert result["est_output_tokens"] == round(1_000_000 / 15)


class TestEstimateTokensHaiku:
    """Haiku pricing: $0.25/1M input, $1.25/1M output."""

    def test_basic_haiku_input(self):
        """$0.00025 at haiku input rate = 1000 tokens."""
        result = estimate_tokens(0.00025, "haiku")
        assert result["est_input_tokens"] == 1000

    def test_basic_haiku_output(self):
        """$0.00125 at haiku output rate = 1000 tokens."""
        result = estimate_tokens(0.00125, "haiku")
        assert result["est_output_tokens"] == 1000

    def test_haiku_1_dollar(self):
        """$1.00 at haiku rates."""
        result = estimate_tokens(1.0, "haiku")
        assert result["est_input_tokens"] == round(1_000_000 / 0.25)
        assert result["est_output_tokens"] == round(1_000_000 / 1.25)


class TestEstimateTokensEdgeCases:

    def test_zero_cost(self):
        result = estimate_tokens(0.0, "opus")
        assert result == {"est_input_tokens": 0, "est_output_tokens": 0}

    def test_negative_cost(self):
        result = estimate_tokens(-1.0, "sonnet")
        assert result == {"est_input_tokens": 0, "est_output_tokens": 0}

    def test_unknown_model(self):
        result = estimate_tokens(0.50, "gpt-4")
        assert result == {"est_input_tokens": 0, "est_output_tokens": 0}

    def test_cursor_model_returns_zero(self):
        """Cursor (non-Claude) model should return zero tokens."""
        result = estimate_tokens(0.50, "cursor")
        assert result == {"est_input_tokens": 0, "est_output_tokens": 0}

    def test_empty_model_string(self):
        result = estimate_tokens(0.50, "")
        assert result == {"est_input_tokens": 0, "est_output_tokens": 0}

    def test_return_type_is_int(self):
        """Token counts must be integers."""
        result = estimate_tokens(0.01, "opus")
        assert isinstance(result["est_input_tokens"], int)
        assert isinstance(result["est_output_tokens"], int)

    def test_input_always_gte_output(self):
        """Input rate is always cheaper, so est_input_tokens >= est_output_tokens."""
        for model in ("opus", "sonnet", "haiku"):
            result = estimate_tokens(0.50, model)
            assert result["est_input_tokens"] >= result["est_output_tokens"], (
                f"For model={model}: input={result['est_input_tokens']} < output={result['est_output_tokens']}"
            )


# ---------------------------------------------------------------------------
# Integration: token estimates in metrics aggregation
# ---------------------------------------------------------------------------


def test_token_estimates_in_metrics_aggregation(tmp_tayfa):
    """Token estimates are correctly summed across messages in a bucket."""
    now = datetime.now()
    msgs = [
        {
            "id": "msg_001",
            "timestamp": now.isoformat(timespec="seconds"),
            "direction": "to_agent",
            "prompt": "task1",
            "result": "done1",
            "runtime": "opus",
            "success": True,
            "cost_usd": 0.15,   # opus: 10000 input tokens, 2000 output tokens
            "duration_sec": 5.0,
        },
        {
            "id": "msg_002",
            "timestamp": now.isoformat(timespec="seconds"),
            "direction": "to_agent",
            "prompt": "task2",
            "result": "done2",
            "runtime": "opus",
            "success": True,
            "cost_usd": 0.075,  # opus: 5000 input tokens, 1000 output tokens
            "duration_sec": 3.0,
        },
    ]
    _write_history(tmp_tayfa, "developer", msgs)

    loaded = chm._load_history("developer")

    # Simulate aggregation logic from the endpoint
    cost_by_model: dict[str, float] = {}
    for msg in loaded:
        model = msg.get("runtime", "")
        cost = msg.get("cost_usd") or 0
        if cost > 0 and model:
            cost_by_model[model] = cost_by_model.get(model, 0.0) + cost

    est_input_total = 0
    est_output_total = 0
    for model, model_cost in cost_by_model.items():
        tok = estimate_tokens(model_cost, model)
        est_input_total += tok["est_input_tokens"]
        est_output_total += tok["est_output_tokens"]

    # Total cost: 0.15 + 0.075 = 0.225
    # Opus input: 0.225 / (15/1M) = 15000 tokens
    # Opus output: 0.225 / (75/1M) = 3000 tokens
    assert est_input_total == 15000
    assert est_output_total == 3000


def test_multi_model_token_aggregation(tmp_tayfa):
    """Token estimates aggregate correctly when messages use different models."""
    now = datetime.now()
    msgs = [
        {
            "id": "msg_001",
            "timestamp": now.isoformat(timespec="seconds"),
            "direction": "to_agent",
            "prompt": "fast task",
            "result": "done",
            "runtime": "haiku",
            "success": True,
            "cost_usd": 0.00025,  # haiku: 1000 input tokens
            "duration_sec": 1.0,
        },
        {
            "id": "msg_002",
            "timestamp": now.isoformat(timespec="seconds"),
            "direction": "to_agent",
            "prompt": "hard task",
            "result": "done",
            "runtime": "opus",
            "success": True,
            "cost_usd": 0.015,  # opus: 1000 input tokens
            "duration_sec": 10.0,
        },
    ]
    _write_history(tmp_tayfa, "developer", msgs)

    loaded = chm._load_history("developer")

    cost_by_model: dict[str, float] = {}
    for msg in loaded:
        model = msg.get("runtime", "")
        cost = msg.get("cost_usd") or 0
        if cost > 0 and model:
            cost_by_model[model] = cost_by_model.get(model, 0.0) + cost

    est_input_total = 0
    est_output_total = 0
    for model, model_cost in cost_by_model.items():
        tok = estimate_tokens(model_cost, model)
        est_input_total += tok["est_input_tokens"]
        est_output_total += tok["est_output_tokens"]

    # haiku input: 0.00025 / (0.25/1M) = 1000
    # opus input: 0.015 / (15/1M) = 1000
    # Total input: 2000
    assert est_input_total == 2000

    # haiku output: 0.00025 / (1.25/1M) = 200
    # opus output: 0.015 / (75/1M) = 200
    # Total output: 400
    assert est_output_total == 400


def test_cursor_messages_excluded_from_token_estimation(tmp_tayfa):
    """Messages with runtime='cursor' should produce zero token estimates."""
    now = datetime.now()
    msgs = [
        {
            "id": "msg_001",
            "timestamp": now.isoformat(timespec="seconds"),
            "direction": "to_agent",
            "prompt": "cursor task",
            "result": "done",
            "runtime": "cursor",
            "success": True,
            "cost_usd": 0.50,
            "duration_sec": 5.0,
        },
    ]
    _write_history(tmp_tayfa, "developer", msgs)

    loaded = chm._load_history("developer")

    cost_by_model: dict[str, float] = {}
    for msg in loaded:
        model = msg.get("runtime", "")
        cost = msg.get("cost_usd") or 0
        if cost > 0 and model:
            cost_by_model[model] = cost_by_model.get(model, 0.0) + cost

    est_input_total = 0
    est_output_total = 0
    for model, model_cost in cost_by_model.items():
        tok = estimate_tokens(model_cost, model)
        est_input_total += tok["est_input_tokens"]
        est_output_total += tok["est_output_tokens"]

    # cursor is not a known model → zero tokens
    assert est_input_total == 0
    assert est_output_total == 0
