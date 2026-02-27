#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Agent memory manager — persistent context that survives restarts.

Each agent has a ``memory.md`` file in ``.tayfa/{agent_name}/`` that is
auto-included in the system prompt on every call.

Sections:
  - RECENT WORK LOG: last N task results (auto-updated after each call)

Usage:
    from memory_manager import build_memory, update_memory, trim_memory

    text = build_memory("developer")          # read memory for system prompt
    update_memory("developer", "T042", "Implemented create_bug()...")
    trim_memory("developer", max_items=5)     # keep last 5 entries
"""
from __future__ import annotations

import re
from datetime import datetime
from pathlib import Path

# ── Module-level state ────────────────────────────────────────────────────

_TAYFA_DIR: Path | None = None

_MAX_WORK_LOG_ITEMS = 5
_MEMORY_FILENAME = "memory.md"


def set_tayfa_dir(path: str | Path) -> None:
    """Set the path to .tayfa of the current project."""
    global _TAYFA_DIR
    _TAYFA_DIR = Path(path) if path else None


def get_tayfa_dir() -> Path | None:
    return _TAYFA_DIR


# ── Helpers ───────────────────────────────────────────────────────────────

def _memory_path(agent_name: str) -> Path | None:
    if _TAYFA_DIR is None:
        return None
    return _TAYFA_DIR / agent_name / _MEMORY_FILENAME


def _read_memory(agent_name: str) -> str:
    """Read raw memory.md content. Returns empty string if missing."""
    path = _memory_path(agent_name)
    if path is None or not path.exists():
        return ""
    try:
        return path.read_text(encoding="utf-8")
    except Exception:
        return ""


def _write_memory(agent_name: str, content: str) -> bool:
    """Write memory.md content. Creates parent dirs if needed."""
    path = _memory_path(agent_name)
    if path is None:
        return False
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content, encoding="utf-8")
        return True
    except Exception:
        return False


# ── Work log parsing ──────────────────────────────────────────────────────

_WORK_LOG_HEADER = "## Recent Work Log"
_ENTRY_RE = re.compile(r"^- \[(.+?)\] \*\*(.+?)\*\*: (.+)$")


def _parse_work_log(text: str) -> tuple[str, list[dict]]:
    """Split memory into (preamble, work_log_entries).

    preamble: everything before ``## Recent Work Log``
    entries: list of {"timestamp", "task_id", "summary"}
    """
    idx = text.find(_WORK_LOG_HEADER)
    if idx == -1:
        return text.rstrip(), []

    preamble = text[:idx].rstrip()
    log_section = text[idx + len(_WORK_LOG_HEADER):]

    entries: list[dict] = []
    for line in log_section.strip().splitlines():
        line = line.strip()
        m = _ENTRY_RE.match(line)
        if m:
            entries.append({
                "timestamp": m.group(1),
                "task_id": m.group(2),
                "summary": m.group(3),
            })
    return preamble, entries


def _format_work_log(entries: list[dict]) -> str:
    """Format work log entries into markdown lines."""
    lines = [_WORK_LOG_HEADER, ""]
    for e in entries:
        lines.append(f"- [{e['timestamp']}] **{e['task_id']}**: {e['summary']}")
    return "\n".join(lines)


def _now_short() -> str:
    return datetime.now().strftime("%Y-%m-%d %H:%M")


# ── Public API ────────────────────────────────────────────────────────────

def build_memory(agent_name: str) -> str:
    """Read memory.md and return formatted text for system prompt injection.

    Returns empty string if no memory file exists (agent starts fresh).
    """
    content = _read_memory(agent_name)
    if not content.strip():
        return ""
    return f"\n\n---\n\n# Agent Memory\n\n{content.strip()}\n"


def update_memory(agent_name: str, task_id: str, result_summary: str) -> bool:
    """Append a work log entry and auto-trim to max items.

    Args:
        agent_name: Agent name (e.g. "developer")
        task_id: Task ID (e.g. "T042")
        result_summary: One-line summary of what was done

    Returns True on success.
    """
    content = _read_memory(agent_name)

    # Truncate long summaries to keep memory lean
    summary = result_summary.strip().replace("\n", " ")
    if len(summary) > 200:
        summary = summary[:197] + "..."

    preamble, entries = _parse_work_log(content)
    entries.append({
        "timestamp": _now_short(),
        "task_id": task_id,
        "summary": summary,
    })

    # Auto-trim
    if len(entries) > _MAX_WORK_LOG_ITEMS:
        entries = entries[-_MAX_WORK_LOG_ITEMS:]

    new_content = preamble + "\n\n" + _format_work_log(entries) + "\n"
    return _write_memory(agent_name, new_content)


def trim_memory(agent_name: str, max_items: int = _MAX_WORK_LOG_ITEMS) -> bool:
    """Keep only the last *max_items* entries in the work log.

    Returns True on success.
    """
    content = _read_memory(agent_name)
    if not content.strip():
        return True  # nothing to trim

    preamble, entries = _parse_work_log(content)
    if len(entries) <= max_items:
        return True  # already within limit

    entries = entries[-max_items:]
    new_content = preamble + "\n\n" + _format_work_log(entries) + "\n"
    return _write_memory(agent_name, new_content)
