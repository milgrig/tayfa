"""Tests for T003: Cross-process file locking (file_lock.py).

Tests that FileLock acquires/releases correctly, locked_read_json / locked_write_json
work as expected, locked_update_json does atomic read-modify-write, stale locks are
broken, concurrent access is serialized, and edge cases are handled.
"""

import json
import os
import sys
import time
import threading
from pathlib import Path

import pytest

# Add kok/ to path
KOK_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(KOK_DIR))

from file_lock import (
    FileLock,
    FileLockError,
    locked_read_json,
    locked_write_json,
    locked_update_json,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

@pytest.fixture
def tmp_json(tmp_path):
    """Return a path to a temporary JSON file (not yet created)."""
    return str(tmp_path / "data.json")


@pytest.fixture
def tmp_json_with_data(tmp_path):
    """Return a path to a temporary JSON file pre-populated with data."""
    p = str(tmp_path / "data.json")
    with open(p, "w", encoding="utf-8") as f:
        json.dump({"key": "value", "count": 0}, f)
    return p


# ---------------------------------------------------------------------------
# Tests: FileLock basics
# ---------------------------------------------------------------------------

class TestFileLockBasics:

    def test_acquire_release(self, tmp_json):
        """Lock can be acquired and released."""
        lock = FileLock(tmp_json)
        lock.acquire()
        # Lock file should exist
        assert os.path.exists(tmp_json + ".lock")
        lock.release()
        # Lock file should be removed
        assert not os.path.exists(tmp_json + ".lock")

    def test_context_manager(self, tmp_json):
        """Lock works as context manager."""
        with FileLock(tmp_json):
            assert os.path.exists(tmp_json + ".lock")
        assert not os.path.exists(tmp_json + ".lock")

    def test_double_release_safe(self, tmp_json):
        """Releasing a lock twice should not raise."""
        lock = FileLock(tmp_json)
        lock.acquire()
        lock.release()
        lock.release()  # should not raise

    def test_lock_creates_parent_dirs(self, tmp_path):
        """Lock creates parent directories if needed."""
        p = str(tmp_path / "nested" / "dir" / "data.json")
        with FileLock(p):
            assert os.path.exists(p + ".lock")
        assert not os.path.exists(p + ".lock")


# ---------------------------------------------------------------------------
# Tests: FileLock contention
# ---------------------------------------------------------------------------

class TestFileLockContention:

    def test_lock_blocks_concurrent_thread(self, tmp_json):
        """A second thread must wait for the lock."""
        results = []
        barrier = threading.Event()

        def hold_lock():
            with FileLock(tmp_json, timeout=5):
                barrier.set()
                time.sleep(0.3)
                results.append("first")

        def wait_for_lock():
            barrier.wait()
            time.sleep(0.05)  # ensure we try to acquire after first thread
            with FileLock(tmp_json, timeout=5):
                results.append("second")

        t1 = threading.Thread(target=hold_lock)
        t2 = threading.Thread(target=wait_for_lock)
        t1.start()
        t2.start()
        t1.join(timeout=10)
        t2.join(timeout=10)

        assert results == ["first", "second"]

    def test_timeout_raises_error(self, tmp_json):
        """Lock raises FileLockError on timeout."""
        # Create a lock file manually to simulate a held lock
        os.makedirs(os.path.dirname(tmp_json) or ".", exist_ok=True)
        lock_path = tmp_json + ".lock"
        # Touch the lock file with current timestamp so it's not stale
        fd = os.open(lock_path, os.O_CREAT | os.O_EXCL | os.O_WRONLY)
        os.write(fd, b"99999")
        os.close(fd)
        # Keep touching it so it doesn't go stale
        os.utime(lock_path, None)

        with pytest.raises(FileLockError):
            FileLock(tmp_json, timeout=0.3).acquire()

        # Cleanup
        os.unlink(lock_path)


# ---------------------------------------------------------------------------
# Tests: Stale lock breaking
# ---------------------------------------------------------------------------

class TestStaleLockBreaking:

    def test_stale_lock_is_broken(self, tmp_json):
        """A lock file older than 60s is considered stale and broken."""
        os.makedirs(os.path.dirname(tmp_json) or ".", exist_ok=True)
        lock_path = tmp_json + ".lock"
        fd = os.open(lock_path, os.O_CREAT | os.O_EXCL | os.O_WRONLY)
        os.write(fd, b"99999")
        os.close(fd)
        # Make it old
        old_time = time.time() - 120
        os.utime(lock_path, (old_time, old_time))

        # Should succeed by breaking the stale lock
        lock = FileLock(tmp_json, timeout=2)
        lock.acquire()
        lock.release()


# ---------------------------------------------------------------------------
# Tests: locked_read_json
# ---------------------------------------------------------------------------

class TestLockedReadJson:

    def test_read_existing_file(self, tmp_json_with_data):
        """Read an existing JSON file."""
        data = locked_read_json(tmp_json_with_data)
        assert data == {"key": "value", "count": 0}

    def test_read_missing_file_returns_default(self, tmp_json):
        """Read a missing file returns the default."""
        data = locked_read_json(tmp_json, default={"empty": True})
        assert data == {"empty": True}

    def test_read_missing_file_returns_empty_dict(self, tmp_json):
        """Read a missing file with no default returns {}."""
        data = locked_read_json(tmp_json)
        assert data == {}

    def test_read_callable_default(self, tmp_json):
        """Read a missing file with callable default calls the factory."""
        data = locked_read_json(tmp_json, default=lambda: {"factory": True})
        assert data == {"factory": True}

    def test_read_invalid_json_returns_default(self, tmp_path):
        """Read a file with invalid JSON returns the default."""
        p = str(tmp_path / "bad.json")
        with open(p, "w") as f:
            f.write("not json {{{")
        data = locked_read_json(p, default={"fallback": True})
        assert data == {"fallback": True}


# ---------------------------------------------------------------------------
# Tests: locked_write_json
# ---------------------------------------------------------------------------

class TestLockedWriteJson:

    def test_write_new_file(self, tmp_json):
        """Write to a new file creates it."""
        locked_write_json(tmp_json, {"hello": "world"})
        with open(tmp_json, encoding="utf-8") as f:
            data = json.load(f)
        assert data == {"hello": "world"}

    def test_write_overwrite(self, tmp_json_with_data):
        """Write overwrites existing data."""
        locked_write_json(tmp_json_with_data, {"new": True})
        with open(tmp_json_with_data, encoding="utf-8") as f:
            data = json.load(f)
        assert data == {"new": True}

    def test_write_preserves_unicode(self, tmp_json):
        """Write preserves unicode characters."""
        locked_write_json(tmp_json, {"name": "Тест"})
        with open(tmp_json, encoding="utf-8") as f:
            data = json.load(f)
        assert data["name"] == "Тест"

    def test_no_temp_file_left(self, tmp_json):
        """No .tmp file should remain after write."""
        locked_write_json(tmp_json, {"clean": True})
        assert not os.path.exists(tmp_json + ".tmp")

    def test_no_lock_file_left(self, tmp_json):
        """No .lock file should remain after write."""
        locked_write_json(tmp_json, {"clean": True})
        assert not os.path.exists(tmp_json + ".lock")


# ---------------------------------------------------------------------------
# Tests: locked_update_json
# ---------------------------------------------------------------------------

class TestLockedUpdateJson:

    def test_update_existing(self, tmp_json_with_data):
        """Update an existing file atomically."""

        def updater(data):
            data["count"] += 1
            return data

        result = locked_update_json(tmp_json_with_data, updater)
        assert result["count"] == 1

        # Verify file on disk
        with open(tmp_json_with_data, encoding="utf-8") as f:
            on_disk = json.load(f)
        assert on_disk["count"] == 1

    def test_update_missing_creates(self, tmp_json):
        """Update on a missing file uses default and creates file."""

        def updater(data):
            data["created"] = True
            return data

        result = locked_update_json(tmp_json, updater, default=dict)
        assert result == {"created": True}
        assert os.path.exists(tmp_json)

    def test_concurrent_updates(self, tmp_json):
        """Multiple concurrent updates should all be applied (no lost updates)."""
        # Initialize with count=0
        locked_write_json(tmp_json, {"count": 0})

        n_threads = 10
        n_increments = 20
        errors = []

        def increment():
            try:
                for _ in range(n_increments):
                    def updater(data):
                        data["count"] += 1
                        return data
                    locked_update_json(tmp_json, updater, default=lambda: {"count": 0})
            except Exception as e:
                errors.append(e)

        threads = [threading.Thread(target=increment) for _ in range(n_threads)]
        for t in threads:
            t.start()
        for t in threads:
            t.join(timeout=60)

        assert not errors, f"Errors occurred: {errors}"

        with open(tmp_json, encoding="utf-8") as f:
            data = json.load(f)
        assert data["count"] == n_threads * n_increments

    def test_update_no_lock_leak(self, tmp_json_with_data):
        """Lock file should not be left after update."""

        def updater(data):
            return data

        locked_update_json(tmp_json_with_data, updater)
        assert not os.path.exists(tmp_json_with_data + ".lock")

    def test_update_error_in_updater_no_data_loss(self, tmp_json_with_data):
        """If updater raises, original data is preserved."""
        original_data = locked_read_json(tmp_json_with_data)

        def bad_updater(data):
            raise ValueError("test error")

        with pytest.raises(ValueError, match="test error"):
            locked_update_json(tmp_json_with_data, bad_updater)

        # Original data should be untouched
        data = locked_read_json(tmp_json_with_data)
        assert data == original_data


# ---------------------------------------------------------------------------
# Tests: Integration — usage patterns from claude_api / project_manager / settings_manager
# ---------------------------------------------------------------------------

class TestIntegrationPatterns:

    def test_load_save_agents_pattern(self, tmp_json):
        """Simulates the load_agents/save_agents pattern from claude_api.py."""
        # Create initial agents file
        locked_write_json(tmp_json, {})

        # Create agent
        def create_agent(agents):
            agents["test_agent"] = {
                "system_prompt": "You are a test agent",
                "workdir": "/tmp",
                "session_id": {},
            }
            return agents

        locked_update_json(tmp_json, create_agent, default=dict)

        # Verify
        agents = locked_read_json(tmp_json, default={})
        assert "test_agent" in agents
        assert agents["test_agent"]["system_prompt"] == "You are a test agent"

        # Update agent
        def update_agent(agents):
            agents["test_agent"]["session_id"] = {"opus": {"bypass": "sid123"}}
            return agents

        locked_update_json(tmp_json, update_agent, default=dict)

        # Verify
        agents = locked_read_json(tmp_json, default={})
        assert agents["test_agent"]["session_id"]["opus"]["bypass"] == "sid123"

        # Delete agent
        def delete_agent(agents):
            del agents["test_agent"]
            return agents

        locked_update_json(tmp_json, delete_agent, default=dict)

        agents = locked_read_json(tmp_json, default={})
        assert "test_agent" not in agents

    def test_projects_load_save_pattern(self, tmp_json):
        """Simulates the _load_data/_save_data pattern from project_manager.py."""
        default_data = {"current": None, "projects": []}

        # First load — file doesn't exist
        data = locked_read_json(tmp_json, default=default_data)
        assert data == default_data

        # Add a project
        data["projects"].append({"path": "/my/project", "name": "test"})
        data["current"] = "/my/project"
        locked_write_json(tmp_json, data)

        # Reload and verify
        data = locked_read_json(tmp_json, default=default_data)
        assert len(data["projects"]) == 1
        assert data["current"] == "/my/project"

    def test_settings_load_save_pattern(self, tmp_json):
        """Simulates the _load_json/_save_json pattern from settings_manager.py."""
        defaults = {"theme": "dark", "port": 8008, "language": "ru"}

        # First load — file doesn't exist
        data = locked_read_json(tmp_json, default=dict(defaults))
        merged = {**defaults, **data}
        assert merged["theme"] == "dark"

        # Modify and save
        merged["theme"] = "light"
        locked_write_json(tmp_json, merged)

        # Reload and verify
        data = locked_read_json(tmp_json, default=dict(defaults))
        merged = {**defaults, **data}
        assert merged["theme"] == "light"
