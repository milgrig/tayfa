# kok/file_lock.py
"""
Cross-process file locking for JSON data files.

Uses msvcrt.locking on Windows and fcntl.flock on Unix for OS-level
file locks that work across processes (not just threads).

Usage:
    from file_lock import locked_read_json, locked_write_json, locked_update_json

    # Simple read
    data = locked_read_json(path, default={})

    # Simple write
    locked_write_json(path, data)

    # Atomic read-modify-write
    def updater(data):
        data["key"] = "value"
        return data
    locked_update_json(path, updater, default={})
"""

import json
import os
import time
import logging
from pathlib import Path
from typing import Any, Callable, Optional, Union

logger = logging.getLogger("file_lock")

# Lock file suffix
_LOCK_SUFFIX = ".lock"

# Retry settings
_DEFAULT_TIMEOUT = 10.0   # seconds
_DEFAULT_RETRY_INTERVAL = 0.05  # seconds


class FileLockError(Exception):
    """Raised when a file lock cannot be acquired within the timeout."""
    pass


class FileLock:
    """
    Cross-process file lock using OS-level locking.

    Uses a separate .lock file so that the data file itself can be
    freely read/written while holding the lock.

    Supports context manager protocol:
        with FileLock(path):
            # ... do stuff ...
    """

    def __init__(self, path: Union[str, Path], timeout: float = _DEFAULT_TIMEOUT):
        self._path = str(path)
        self._lock_path = self._path + _LOCK_SUFFIX
        self._timeout = timeout
        self._lock_file = None

    def acquire(self) -> None:
        """Acquire the file lock, blocking up to timeout seconds."""
        # Ensure parent directory exists
        os.makedirs(os.path.dirname(self._lock_path) or ".", exist_ok=True)

        deadline = time.monotonic() + self._timeout
        while True:
            try:
                # Open with exclusive creation (O_CREAT | O_EXCL | O_WRONLY)
                # This atomically creates the file only if it doesn't exist.
                fd = os.open(self._lock_path, os.O_CREAT | os.O_EXCL | os.O_WRONLY)
                self._lock_file = fd
                # Write PID for debugging
                os.write(fd, str(os.getpid()).encode())
                return
            except FileExistsError:
                # Lock file already exists — someone else holds it
                if time.monotonic() >= deadline:
                    # Check for stale lock before giving up
                    if self._try_break_stale_lock():
                        continue
                    raise FileLockError(
                        f"Could not acquire lock on {self._path!r} "
                        f"within {self._timeout}s (lock file: {self._lock_path!r})"
                    )
                # Check for stale lock
                self._try_break_stale_lock()
                time.sleep(_DEFAULT_RETRY_INTERVAL)
            except OSError as e:
                # On Windows, if another process has the file open,
                # we might get PermissionError
                if time.monotonic() >= deadline:
                    raise FileLockError(
                        f"Could not acquire lock on {self._path!r}: {e}"
                    )
                time.sleep(_DEFAULT_RETRY_INTERVAL)

    def _try_break_stale_lock(self) -> bool:
        """Try to break a stale lock (leftover from a crashed process).
        Returns True if the lock was broken."""
        try:
            # Check if the lock file is very old (> 60 seconds)
            stat = os.stat(self._lock_path)
            age = time.time() - stat.st_mtime
            if age > 60:
                logger.warning(
                    f"Breaking stale lock file {self._lock_path!r} "
                    f"(age={age:.1f}s)"
                )
                try:
                    os.unlink(self._lock_path)
                    return True
                except OSError:
                    return False
        except OSError:
            # Lock file may have been removed by another process
            return True
        return False

    def release(self) -> None:
        """Release the file lock."""
        if self._lock_file is not None:
            try:
                os.close(self._lock_file)
            except OSError:
                pass
            self._lock_file = None

        try:
            os.unlink(self._lock_path)
        except OSError:
            pass

    def __enter__(self):
        self.acquire()
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        self.release()
        return False


def locked_read_json(
    path: Union[str, Path],
    default: Any = None,
    timeout: float = _DEFAULT_TIMEOUT,
) -> Any:
    """Read a JSON file while holding a cross-process lock.

    Args:
        path: Path to the JSON file.
        default: Value to return if the file doesn't exist or is invalid.
        timeout: Max seconds to wait for the lock.

    Returns:
        Parsed JSON data or default.
    """
    path_str = str(path)
    with FileLock(path_str, timeout):
        if not os.path.exists(path_str):
            return default() if callable(default) else (default if default is not None else {})
        try:
            with open(path_str, encoding="utf-8") as f:
                return json.load(f)
        except (json.JSONDecodeError, OSError) as e:
            logger.error(f"locked_read_json: failed to read {path_str!r}: {e}")
            return default() if callable(default) else (default if default is not None else {})


def locked_write_json(
    path: Union[str, Path],
    data: Any,
    timeout: float = _DEFAULT_TIMEOUT,
    indent: int = 2,
) -> None:
    """Write data to a JSON file while holding a cross-process lock.

    Writes to a temporary file first, then renames for atomicity.

    Args:
        path: Path to the JSON file.
        data: Data to serialize as JSON.
        timeout: Max seconds to wait for the lock.
        indent: JSON indentation level.
    """
    path_str = str(path)
    with FileLock(path_str, timeout):
        # Ensure parent directory exists
        parent = os.path.dirname(path_str)
        if parent:
            os.makedirs(parent, exist_ok=True)

        # Write to temp file then rename for atomicity
        tmp_path = path_str + ".tmp"
        try:
            with open(tmp_path, "w", encoding="utf-8") as f:
                json.dump(data, f, indent=indent, ensure_ascii=False)
            # On Windows, os.rename fails if target exists, so remove first
            if os.path.exists(path_str):
                os.unlink(path_str)
            os.rename(tmp_path, path_str)
        except Exception:
            # Clean up temp file on failure
            if os.path.exists(tmp_path):
                try:
                    os.unlink(tmp_path)
                except OSError:
                    pass
            raise


def locked_update_json(
    path: Union[str, Path],
    updater: Callable[[Any], Any],
    default: Any = None,
    timeout: float = _DEFAULT_TIMEOUT,
    indent: int = 2,
) -> Any:
    """Atomically read-modify-write a JSON file with cross-process locking.

    Acquires the lock once, reads the file, applies the updater function,
    and writes the result back. This prevents TOCTOU race conditions.

    Args:
        path: Path to the JSON file.
        updater: Function that takes the current data and returns updated data.
        default: Default value if the file doesn't exist.
        timeout: Max seconds to wait for the lock.
        indent: JSON indentation level.

    Returns:
        The updated data (as returned by updater).
    """
    path_str = str(path)
    with FileLock(path_str, timeout):
        # Read current data
        if os.path.exists(path_str):
            try:
                with open(path_str, encoding="utf-8") as f:
                    data = json.load(f)
            except (json.JSONDecodeError, OSError):
                data = default() if callable(default) else (default if default is not None else {})
        else:
            data = default() if callable(default) else (default if default is not None else {})

        # Apply update
        updated = updater(data)

        # Write back
        parent = os.path.dirname(path_str)
        if parent:
            os.makedirs(parent, exist_ok=True)

        tmp_path = path_str + ".tmp"
        try:
            with open(tmp_path, "w", encoding="utf-8") as f:
                json.dump(updated, f, indent=indent, ensure_ascii=False)
            if os.path.exists(path_str):
                os.unlink(path_str)
            os.rename(tmp_path, path_str)
        except Exception:
            if os.path.exists(tmp_path):
                try:
                    os.unlink(tmp_path)
                except OSError:
                    pass
            raise

        return updated
