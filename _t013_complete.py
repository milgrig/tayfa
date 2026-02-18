#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""One-shot script: set T013 result + status. Run from project root."""
import sys
import os

sys.path.insert(0, r"C:\Cursor\TayfaWindows\.tayfa\common")
sys.stdout.reconfigure(encoding="utf-8")

import task_manager as tm

RESULT = (
    "Requirements detailed in .tayfa/common/discussions/T013.md. "
    "Scope - 4 groups: "
    "(1) Python 14 files - translate all comments/docstrings/print/error messages; "
    "task status enum migration: pending/in_progress/in_review/done/cancelled; "
    "sprint statuses: active/completed/released. "
    "(2) JSON - employees.json role names (Project Manager/HR Manager/Developer), "
    "backlog.json titles, tasks.json status values migration. "
    "(3) Markdown - Rules/*.md, boss+hr profile.md, docs/product/**/*.md; "
    "EXCLUDE: all prompt.md files and discussions history text. "
    "(4) scripts/ dir. "
    "Recommended order: task_manager.py statuses first -> tasks.json migration -> "
    "Python files -> JSON -> Markdown. "
    "Acceptance: grep finds no Cyrillic in kok/ and .tayfa/common/*.py; "
    "task_manager list works; app.py starts without errors."
)

r1 = tm.set_task_result("T013", RESULT)
print("result:", r1)

r2 = tm.update_task_status("T013", "\u0432_\u0440\u0430\u0431\u043e\u0442\u0435")
print("status:", r2)
