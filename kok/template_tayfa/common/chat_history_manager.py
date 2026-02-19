#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Chat history management for agents.

Each agent has its own chat_history.json file in the .tayfa/{agent_name}/ folder.
The file contains a list of messages (maximum max_history_items most recent) with metadata.
Older messages are automatically archived to .tayfa/{agent_name}/chat_history_archive/
when the limit is exceeded (no data loss).

Message format:
{
    "id": "msg_001",
    "timestamp": "2026-02-12T10:45:00",
    "direction": "to_agent",
    "prompt": "Text of the sent prompt",
    "result": "Agent response",
    "runtime": "claude",
    "cost_usd": 0.05,
    "duration_sec": 12.5,
    "task_id": "T002",
    "success": true
}

Usage:
    from chat_history_manager import save_message, get_history, clear_history

    # Save a message
    msg = save_message(
        agent_name="developer_backend",
        prompt="Create a function...",
        result="Done, created...",
        runtime="claude",
        cost_usd=0.03,
        duration_sec=5.2,
        task_id="T001",
        success=True
    )

    # Get history with pagination
    history = get_history("developer_backend", limit=50, offset=0)

    # Clear history
    clear_history("developer_backend")
"""

import json
import os
import tempfile
from datetime import datetime
from pathlib import Path
from typing import Any

# Path to .tayfa of the current project (set externally)
_TAYFA_DIR: Path | None = None

# Default maximum number of messages in history
_DEFAULT_MAX_HISTORY_ITEMS = 100


def set_tayfa_dir(path: str | Path) -> None:
    """Set the path to .tayfa of the current project."""
    global _TAYFA_DIR
    _TAYFA_DIR = Path(path) if path else None


def get_tayfa_dir() -> Path | None:
    """Get the path to .tayfa of the current project."""
    return _TAYFA_DIR


def get_max_history_items(tayfa_dir: Path | None = None) -> int:
    """Read max_history_items from .tayfa/config.json. Fresh on every call.
    Falls back to _DEFAULT_MAX_HISTORY_ITEMS (100) if not configured or invalid."""
    base = tayfa_dir if tayfa_dir is not None else _TAYFA_DIR
    if base is None:
        return _DEFAULT_MAX_HISTORY_ITEMS
    try:
        config_path = base / "config.json"
        if not config_path.exists():
            return _DEFAULT_MAX_HISTORY_ITEMS
        data = json.loads(config_path.read_text(encoding="utf-8"))
        v = data.get("max_history_items")
        if isinstance(v, int) and v > 0:
            return v
    except Exception:
        pass
    return _DEFAULT_MAX_HISTORY_ITEMS


def _get_history_file(agent_name: str) -> Path | None:
    """Get the path to the agent's history file."""
    if _TAYFA_DIR is None:
        return None
    return _TAYFA_DIR / agent_name / "chat_history.json"


def _load_history(agent_name: str) -> list[dict]:
    """Load history from file. Returns an empty list if the file does not exist."""
    history_file = _get_history_file(agent_name)
    if history_file is None or not history_file.exists():
        return []
    try:
        data = json.loads(history_file.read_text(encoding="utf-8"))
        if isinstance(data, list):
            return data
        elif isinstance(data, dict) and "messages" in data:
            return data["messages"]
        return []
    except Exception:
        return []


def _save_history(agent_name: str, messages: list[dict]) -> bool:
    """
    Save history to file. Uses atomic write (temp + rename).
    Returns True on success.
    """
    history_file = _get_history_file(agent_name)
    if history_file is None:
        return False

    # Create the agent directory if it does not exist
    history_file.parent.mkdir(parents=True, exist_ok=True)

    # Atomic write: write to a temporary file, then rename
    try:
        fd, temp_path = tempfile.mkstemp(
            suffix=".json",
            prefix="chat_history_",
            dir=str(history_file.parent)
        )
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as f:
                json.dump(messages, f, ensure_ascii=False, indent=2)
            # Rename (atomic on most file systems)
            os.replace(temp_path, history_file)
            return True
        except Exception:
            # Delete the temporary file on error
            try:
                os.unlink(temp_path)
            except Exception:
                pass
            raise
    except Exception:
        return False


def _archive_messages(
    agent_name: str,
    messages_to_archive: list[dict],
    tayfa_dir: Path,
) -> None:
    """
    Append overflow messages to a date-based archive file.

    Archive location: .tayfa/{agent_name}/chat_history_archive/archive_YYYY-MM-DD.json
    If the archive file for today already exists, extend it; otherwise create it.
    Uses atomic write (temp file + os.replace).
    """
    archive_dir = tayfa_dir / agent_name / "chat_history_archive"
    archive_dir.mkdir(parents=True, exist_ok=True)

    date_str = datetime.utcnow().strftime("%Y-%m-%d")
    archive_file = archive_dir / f"archive_{date_str}.json"

    # Load existing archive for today (if any)
    existing: list[dict] = []
    if archive_file.exists():
        try:
            data = json.loads(archive_file.read_text(encoding="utf-8"))
            if isinstance(data, list):
                existing = data
        except Exception:
            existing = []

    existing.extend(messages_to_archive)

    # Atomic write
    fd, temp_path = tempfile.mkstemp(
        suffix=".json",
        prefix="archive_tmp_",
        dir=str(archive_dir),
    )
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            json.dump(existing, f, ensure_ascii=False, indent=2)
        os.replace(temp_path, archive_file)
    except Exception:
        try:
            os.unlink(temp_path)
        except Exception:
            pass
        raise


def _generate_message_id(messages: list[dict]) -> str:
    """Generate a unique message ID."""
    if not messages:
        return "msg_001"

    # Find the maximum number
    max_num = 0
    for msg in messages:
        msg_id = msg.get("id", "")
        if msg_id.startswith("msg_"):
            try:
                num = int(msg_id[4:])
                max_num = max(max_num, num)
            except ValueError:
                pass

    return f"msg_{max_num + 1:03d}"


def _now_iso() -> str:
    """Current time in ISO 8601 format."""
    return datetime.now().isoformat(timespec="seconds")


def save_message(
    agent_name: str,
    prompt: str,
    result: str = "",
    runtime: str = "claude",
    cost_usd: float | None = None,
    duration_sec: float | None = None,
    task_id: str | None = None,
    success: bool = True,
    extra: dict[str, Any] | None = None,
) -> dict | None:
    """
    Save a message to the chat history with an agent.

    Args:
        agent_name: Agent name (e.g., "developer_backend")
        prompt: Text of the sent prompt
        result: Agent response
        runtime: "claude" or "cursor"
        cost_usd: Request cost in USD (if available)
        duration_sec: Execution time in seconds
        task_id: Task ID (if the message is part of a task)
        success: True if the request was successful
        extra: Additional fields to save

    Returns:
        Saved message or None on error
    """
    if _TAYFA_DIR is None:
        return None

    messages = _load_history(agent_name)

    message = {
        "id": _generate_message_id(messages),
        "timestamp": _now_iso(),
        "direction": "to_agent",  # Request is always "to agent", result contains the response
        "prompt": prompt,
        "result": result,
        "runtime": runtime,
        "success": success,
    }

    # Add optional fields only if they are set
    if cost_usd is not None:
        message["cost_usd"] = cost_usd
    if duration_sec is not None:
        message["duration_sec"] = round(duration_sec, 2)
    if task_id:
        message["task_id"] = task_id
    if extra:
        message.update(extra)

    messages.append(message)

    # Archive overflow: move oldest messages to date-based archive file
    max_items = get_max_history_items()
    if len(messages) > max_items:
        overflow = messages[:-max_items]  # oldest messages that exceed the limit
        messages = messages[-max_items:]
        try:
            _archive_messages(agent_name, overflow, _TAYFA_DIR)
        except Exception:
            pass  # archiving failure must not block saving current history

    if _save_history(agent_name, messages):
        return message
    return None


def get_history(
    agent_name: str,
    limit: int = 50,
    offset: int = 0,
) -> dict:
    """
    Get the chat history with an agent.

    Args:
        agent_name: Agent name
        limit: Maximum number of messages (default 50)
        offset: Offset from the beginning (for pagination)

    Returns:
        {"messages": [...], "total": int, "limit": int, "offset": int}
    """
    messages = _load_history(agent_name)
    total = len(messages)

    # Return messages in chronological order (from oldest to newest)
    # Pagination works from the end (newest messages are last)
    if offset > 0:
        messages = messages[:-offset] if offset < len(messages) else []

    if limit > 0:
        messages = messages[-limit:] if limit < len(messages) else messages

    return {
        "messages": messages,
        "total": total,
        "limit": limit,
        "offset": offset,
    }


def clear_history(agent_name: str) -> dict:
    """
    Clear the chat history with an agent.

    Returns:
        {"status": "cleared", "deleted_count": int}
    """
    messages = _load_history(agent_name)
    deleted_count = len(messages)

    if _save_history(agent_name, []):
        return {"status": "cleared", "deleted_count": deleted_count}
    return {"status": "error", "deleted_count": 0, "error": "Failed to save empty history"}


def get_last_messages(agent_name: str, count: int = 5) -> list[dict]:
    """
    Get the last N messages (for context).

    Args:
        agent_name: Agent name
        count: Number of messages

    Returns:
        List of the last messages
    """
    messages = _load_history(agent_name)
    return messages[-count:] if count < len(messages) else messages


def search_history(
    agent_name: str,
    query: str,
    limit: int = 20,
) -> list[dict]:
    """
    Search history by prompt or result text.

    Args:
        agent_name: Agent name
        query: Search string (case-insensitive)
        limit: Maximum number of results

    Returns:
        List of found messages
    """
    messages = _load_history(agent_name)
    query_lower = query.lower()

    results = []
    for msg in reversed(messages):  # From newest to oldest
        prompt = msg.get("prompt", "").lower()
        result = msg.get("result", "").lower()
        if query_lower in prompt or query_lower in result:
            results.append(msg)
            if len(results) >= limit:
                break

    return results
