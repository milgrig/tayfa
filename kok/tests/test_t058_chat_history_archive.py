"""
T058: Tests for chat history TTL archiving.

Verifies that:
- max_history_items config option is respected
- Overflow messages are archived (not dropped)
- Archive files are date-based (archive_YYYY-MM-DD.json)
- Appends to existing archive file for the same date
- No data loss across multiple overflow cycles
"""
import json
import re
import sys
from datetime import datetime
from pathlib import Path

import pytest

# ---------------------------------------------------------------------------
# Path helpers – import chat_history_manager from the live .tayfa/common/
# ---------------------------------------------------------------------------

_REPO_ROOT = Path(__file__).resolve().parents[2]  # C:\Cursor\TayfaWindows
_CHM_DIR = _REPO_ROOT / ".tayfa" / "common"

if str(_CHM_DIR) not in sys.path:
    sys.path.insert(0, str(_CHM_DIR))

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


def _save(tayfa, agent="agent", limit=5, n=1, start=1):
    """Helper: write config with given limit, then save n messages."""
    config = tayfa / "config.json"
    config.write_text(json.dumps({"max_history_items": limit}), encoding="utf-8")
    for i in range(start, start + n):
        chm.save_message(agent, prompt=f"prompt_{i}", result=f"result_{i}")


def _history_count(tayfa, agent="agent"):
    hist = tayfa / agent / "chat_history.json"
    if not hist.exists():
        return 0
    return len(json.loads(hist.read_text(encoding="utf-8")))


def _archive_dir(tayfa, agent="agent"):
    return tayfa / agent / "chat_history_archive"


def _all_archive_messages(tayfa, agent="agent"):
    ad = _archive_dir(tayfa, agent)
    if not ad.exists():
        return []
    msgs = []
    for f in ad.glob("archive_*.json"):
        data = json.loads(f.read_text(encoding="utf-8"))
        if isinstance(data, list):
            msgs.extend(data)
    return msgs


# ---------------------------------------------------------------------------
# AC1: max_history_items config option
# ---------------------------------------------------------------------------

def test_max_history_items_default_is_100(tmp_path):
    """When no config.json exists, get_max_history_items returns 100."""
    empty_tayfa = tmp_path / "no_config"
    empty_tayfa.mkdir()
    assert chm.get_max_history_items(empty_tayfa) == 100


def test_max_history_items_reads_from_config(tmp_path):
    """get_max_history_items reads 'max_history_items' key from config.json."""
    tayfa = tmp_path / "cfg"
    tayfa.mkdir()
    (tayfa / "config.json").write_text(
        json.dumps({"max_history_items": 5}), encoding="utf-8"
    )
    assert chm.get_max_history_items(tayfa) == 5


def test_max_history_items_invalid_value_falls_back_to_default(tmp_path):
    """Non-integer or non-positive value falls back to 100."""
    tayfa = tmp_path / "cfg"
    tayfa.mkdir()
    (tayfa / "config.json").write_text(
        json.dumps({"max_history_items": "bad"}), encoding="utf-8"
    )
    assert chm.get_max_history_items(tayfa) == 100


def test_max_history_items_missing_key_falls_back_to_default(tmp_path):
    """Missing key falls back to 100."""
    tayfa = tmp_path / "cfg"
    tayfa.mkdir()
    (tayfa / "config.json").write_text(json.dumps({}), encoding="utf-8")
    assert chm.get_max_history_items(tayfa) == 100


# ---------------------------------------------------------------------------
# AC2 / AC3: Auto-archive when limit exceeded; archive files in archive dir
# ---------------------------------------------------------------------------

def test_no_archive_when_under_limit(tmp_tayfa):
    """Saving 3 messages with limit=5 does NOT create the archive directory."""
    _save(tmp_tayfa, limit=5, n=3)
    assert not _archive_dir(tmp_tayfa).exists()


def test_archive_created_when_limit_exceeded(tmp_tayfa):
    """Save 6 messages with limit=5: chat_history.json=5, archive has 1 message."""
    _save(tmp_tayfa, limit=5, n=6)
    assert _history_count(tmp_tayfa) == 5
    assert _archive_dir(tmp_tayfa).exists()
    archive_messages = _all_archive_messages(tmp_tayfa)
    assert len(archive_messages) == 1


def test_archive_appends_to_existing_date_file(tmp_tayfa):
    """Pre-create archive file for today with 2 messages; trigger overflow of 1 more.
    Archive file must contain 3 messages in total."""
    # Pre-create archive with 2 messages
    archive_dir = _archive_dir(tmp_tayfa)
    archive_dir.mkdir(parents=True)
    date_str = datetime.utcnow().strftime("%Y-%m-%d")
    archive_file = archive_dir / f"archive_{date_str}.json"
    existing = [{"id": "old_1", "prompt": "old1"}, {"id": "old_2", "prompt": "old2"}]
    archive_file.write_text(json.dumps(existing), encoding="utf-8")

    # Now trigger overflow of 1 message (save 6 with limit=5 → 1 overflow)
    _save(tmp_tayfa, limit=5, n=6)

    data = json.loads(archive_file.read_text(encoding="utf-8"))
    assert len(data) == 3  # 2 pre-existing + 1 new overflow


# ---------------------------------------------------------------------------
# AC3: Archive filename format
# ---------------------------------------------------------------------------

def test_archive_filename_is_date_based(tmp_tayfa):
    """Archive filename matches archive_YYYY-MM-DD.json pattern for today (UTC)."""
    _save(tmp_tayfa, limit=5, n=6)
    ad = _archive_dir(tmp_tayfa)
    assert ad.exists()
    files = list(ad.glob("archive_*.json"))
    assert len(files) == 1
    name = files[0].name
    assert re.match(r"^archive_\d{4}-\d{2}-\d{2}\.json$", name), f"Bad filename: {name}"
    expected_date = datetime.utcnow().strftime("%Y-%m-%d")
    assert name == f"archive_{expected_date}.json"


# ---------------------------------------------------------------------------
# AC4: No data loss
# ---------------------------------------------------------------------------

def test_no_data_loss(tmp_tayfa):
    """Save N messages exceeding limit multiple times.
    Total across chat_history.json + all archive files must equal N."""
    total_n = 25
    limit = 5
    _save(tmp_tayfa, limit=limit, n=total_n)

    in_history = _history_count(tmp_tayfa)
    in_archive = len(_all_archive_messages(tmp_tayfa))
    assert in_history + in_archive == total_n, (
        f"Data loss: {in_history} in history + {in_archive} in archive = "
        f"{in_history + in_archive}, expected {total_n}"
    )


def test_no_data_loss_multiple_overflow_cycles(tmp_tayfa):
    """Multiple separate save bursts all preserve data."""
    limit = 3
    # Save in 3 separate bursts to trigger multiple overflow events
    _save(tmp_tayfa, limit=limit, n=4, start=1)   # 1 overflow
    _save(tmp_tayfa, limit=limit, n=4, start=5)   # more overflow
    _save(tmp_tayfa, limit=limit, n=4, start=9)   # more overflow

    total_saved = 12
    in_history = _history_count(tmp_tayfa)
    in_archive = len(_all_archive_messages(tmp_tayfa))
    assert in_history + in_archive == total_saved


# ---------------------------------------------------------------------------
# AC5: Existing tests still pass (smoke-run via subprocess is done in pytest
#       session — here we just verify save_message still returns the message)
# ---------------------------------------------------------------------------

def test_save_message_still_returns_message(tmp_tayfa):
    """save_message returns the saved message dict (basic smoke test)."""
    (tmp_tayfa / "config.json").write_text(
        json.dumps({"max_history_items": 10}), encoding="utf-8"
    )
    msg = chm.save_message("agent", prompt="hello", result="world")
    assert msg is not None
    assert msg["prompt"] == "hello"
    assert msg["result"] == "world"


def test_history_stays_within_limit(tmp_tayfa):
    """chat_history.json never exceeds max_history_items."""
    limit = 7
    _save(tmp_tayfa, limit=limit, n=20)
    assert _history_count(tmp_tayfa) == limit


def test_history_content_is_newest_messages(tmp_tayfa):
    """After overflow, chat_history.json contains the NEWEST messages (FIFO)."""
    limit = 3
    _save(tmp_tayfa, limit=limit, n=5)  # prompts 1..5, limit=3 → keep 3,4,5
    hist = json.loads(
        (tmp_tayfa / "agent" / "chat_history.json").read_text(encoding="utf-8")
    )
    prompts = [m["prompt"] for m in hist]
    assert prompts == ["prompt_3", "prompt_4", "prompt_5"]
