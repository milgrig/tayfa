# Plan: Fix 3 Auto-Run Problems

## Problem 1: FAILED badge on already-done tasks

**Root cause**: When `api_trigger_task()` encounters an error (e.g. 502 from Claude API), `log_agent_failure()` writes a failure record **without checking if the task is already done**. The 502 error may happen during the tail end of an agent's stream — after the agent already ran `task_manager.py status T030 done` but before the HTTP response finishes.

**Fix** — `kok/routers/tasks.py`, in the `except` block (lines 691-718):

Before logging a failure, re-read the task's current status from disk. If the task is already `done` or `cancelled`, **do not log a failure** — the task completed successfully, the error is just a post-completion stream artifact. Return success instead.

```python
# Line ~691, inside except Exception as exc:
    last_error = exc
    error_type = _classify_error(exc)
    error_msg = str(getattr(exc, "detail", None) or exc)

    # NEW: Don't log failure if task already completed
    fresh_task = get_task(task_id)
    if fresh_task and fresh_task.get("status") in ("done", "cancelled"):
        logger.info(
            f"[Trigger] {task_id}: error after task already "
            f"{fresh_task['status']}, suppressing ({error_type}: {error_msg})"
        )
        return {
            "task_id": task_id,
            "agent": agent_name,
            "role": role_label,
            "runtime": resolved_model if runtime != "cursor" else "cursor",
            "success": True,
            "result": fresh_task.get("result", ""),
            "note": f"Completed despite stream error ({error_type})",
        }

    # Original failure logging continues below for tasks NOT yet done...
    log_agent_failure(...)
```

---

## Problem 2: Task "hanging" in done status with spinner

**Root cause**: The agent calls `task_manager.py status T030 done` mid-stream, changing status in `tasks.json` to `done`. But the HTTP trigger request is still running (stream not finished). The frontend sees `status=done` from API AND `runningTasks[T030]` still in memory → card shows as done + spinner.

**Fix** — `kok/static/js/board.js`, in `renderTaskCard()` (line ~250):

If a task has `status === 'done'` or `'cancelled'` but is still in `runningTasks`, clean it up:

```javascript
// Change const to let:
let isRunning = !!runningTasks[t.id];

// Clear stale running state for already-completed tasks
if (isRunning && (t.status === 'done' || t.status === 'cancelled')) {
    delete runningTasks[t.id];
    isRunning = false;
}
```

---

## Problem 3: Board flickers "Loading..." during auto-run

**Root cause**: `refreshTasksBoardNew()` line 102:
```javascript
wrap.innerHTML = '<div class="empty-state">Loading...</div>';
```
This destroys the entire DOM before fetching data. During auto-run, `refreshTasksBoardNew()` is called 5+ times per loop iteration (lines 195, 289, 298, 314 in sprints.js, plus triggerTask calls, plus boardAutoRefreshTimer every 5s). Each call causes a visible "Loading..." flash.

**Fix** — `kok/static/js/board.js`, in `refreshTasksBoardNew()`:

Don't clear the board before fetching. Show "Loading..." only on the **first render** (when board has no content). After data is ready, replace `innerHTML` in one shot.

```javascript
async function refreshTasksBoardNew() {
    const wrap = document.getElementById('tasksBoardWrap');

    // Show loading only on first render
    if (!wrap.children.length || wrap.querySelector('.empty-state')) {
        wrap.innerHTML = '<div class="empty-state">Loading...</div>';
    }

    try {
        // ... fetch data (unchanged) ...

        wrap.innerHTML = html;  // Replace in one shot — no flash
        // ... rest unchanged ...
    } catch (e) {
        wrap.innerHTML = '...error...';
    }
}
```

---

## Summary of Changes

| File | Change | Problem |
|------|--------|---------|
| `kok/routers/tasks.py` ~15 lines | Re-check task status before logging failure; return success if done | #1: FAILED on done tasks |
| `kok/static/js/board.js` ~5 lines | Clear stale `runningTasks` for done/cancelled tasks in `renderTaskCard()` | #2: spinner on done tasks |
| `kok/static/js/board.js` ~3 lines | Show "Loading..." only on first render in `refreshTasksBoardNew()` | #3: board flickering |

Total: ~23 lines changed across 2 files. No architectural changes, no new dependencies.
