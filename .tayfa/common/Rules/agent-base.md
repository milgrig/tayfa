# Base Rules for All Agents

This document contains mandatory rules for all employees.

---

## 0. Language Policy

**All internal communication is in ENGLISH:**
- Task descriptions
- Discussions in `discussions/{task_id}.md`
- Backlog items
- Handoff documents
- Code comments

**Exception:** When a human user writes in Russian in chat — respond in Russian. But all artifacts (tasks, discussions, proposals) must be in English.

---

## 1. Task System

### Central Storage

All tasks are in **`.tayfa/common/tasks.json`**, managed via **`.tayfa/common/task_manager.py`**.

**Do NOT edit `tasks.json` manually** — use `task_manager.py`.

### Main Commands

```bash
# View
python .tayfa/common/task_manager.py list
python .tayfa/common/task_manager.py list --status new
python .tayfa/common/task_manager.py get T001

# Work with task
python .tayfa/common/task_manager.py result T001 "Description"
python .tayfa/common/task_manager.py status T001 <status>
```

### Task Statuses

| Status | Meaning |
|--------|---------|
| `new` | Task created, ready for execution |
| `done` | Task completed |
| `questions` | Agent blocked — needs clarification. Write detailed comment in discussion file, then set status to `questions` |
| `cancelled` | Task cancelled |

### Task Fields

| Field | Description |
|-------|-------------|
| **author** | Who created the task (boss or agent name) |
| **executor** | Who executes the task (agent name) |

### Completing a task

When you finish your work:
```bash
python .tayfa/common/task_manager.py result T001 "Description of what was done"
python .tayfa/common/task_manager.py status T001 done
```

If you CANNOT complete the task (missing permissions, unclear requirements, blocked):
```bash
python .tayfa/common/task_manager.py result T001 "Detailed explanation of what is needed"
python .tayfa/common/task_manager.py status T001 questions
```

---

## 2. Task Communication

### Discussion Files

All task messages go in:

```
.tayfa/common/discussions/{task_id}.md
```

**Rules:**
- **Read** the file before starting — it has context from previous participants
- **Append** to the end, don't delete previous content
- **Header format**: `## [YYYY-MM-DD HH:MM] agent_name (role)`

---

## 3. Working Directories

| Directory | Purpose |
|-----------|---------|
| **Project root** | Code, frontend/backend, product documentation |
| **`.tayfa/`** | Communication: tasks, employees, rules |
| **`.tayfa/<name>/`** | Agent's personal folder |
| **`.tayfa/common/discussions/`** | Task discussions |
| **`.tayfa/common/Rules/`** | Team rules (English) |

---

## 4. Git

**Do NOT run git commands** — the orchestrator does this automatically on status change.

---

## 5. Required Documents

Before starting work, study:
- `.tayfa/common/Rules/teamwork.md` — workflow and handoff formats
- `.tayfa/common/Rules/employees.md` — employee list
- `.tayfa/common/known_bugs.md` — known bug patterns and lessons learned

---

## 5.1. Known Bugs & Lessons Learned

The file **`.tayfa/common/known_bugs.md`** contains recurring bug patterns discovered across sprints.

### Before every task:
- **Read** `known_bugs.md` — check your work against every KB-* entry
- Do NOT repeat listed bugs — they have already been fixed before

### When you fix a bug:
1. Check if the bug pattern is already in `known_bugs.md`
2. If **NOT** — **add a new entry** following the KB-XXX format:
   ```markdown
   ## KB-XXX: Short Title

   **Symptom:** What the user sees
   **Root Cause:** Why it happens
   **Prevention:** Steps to avoid it
   **Recurred:** How many times / which sprints
   ```
3. Use the next available KB number (e.g., if last is KB-005, add KB-006)

### This is mandatory — not optional. The goal is to prevent the same bug from happening twice.

---

## 6. MANDATORY: Code Execution and Testing

### ⚠️ CRITICAL for developers and testers

**YOU MUST PHYSICALLY RUN THE CODE before passing the task.**

This is not a recommendation — it's a requirement. Task without running = incomplete task.

### For developers — what you MUST do:

**1. INSTALL ALL DEPENDENCIES**
```bash
pip install -r requirements.txt
# or
npm install
```
If you added a new library — add it to requirements.txt/package.json AND install it.

**2. RUN THE CODE AND VERIFY IT WORKS**
```bash
python kok/app.py
# or
npm start
```
Open in browser, check functionality manually. Don't guess — verify.

**3. RUN TESTS**
```bash
# Fast tests (unit + integration)
bash ./run_tests.sh unit
# or: pytest tests/ -m "not e2e" -v

# E2E tests (Playwright) — mandatory for UI changes
bash ./run_tests.sh e2e
# or: pytest tests/e2e/ -m e2e -v

# All tests at once
bash ./run_tests.sh
```
All tests must pass. If they fail — fix them.

**For UI changes:** You MUST add/update E2E tests in `tests/e2e/`. Use centralized selectors from `tests/e2e/helpers/selectors.py` and reusable actions from `tests/e2e/helpers/actions.py`. See `.tayfa/common/Rules/testing.md` for E2E guidelines.

**4. CHECK TYPES (for Python)**
```bash
mypy kok/
```

### What to do if something is missing:

- Need a library? → `pip install X` + add to requirements.txt
- Need a system utility? → Install and note in handoff
- Need a config? → Create and document

### Task is NOT ready for handoff if:

- ❌ You did NOT run the code
- ❌ Code crashes on startup
- ❌ Tests fail
- ❌ Dependencies not installed

---

### For testers: EXECUTION-ONLY verification

**⛔ FORBIDDEN: Reading source code as primary verification.**

Testers MUST NOT:
- ❌ Read source files to "check the code"
- ❌ Review implementation by reading files
- ❌ Write "code looks correct" or "reviewed the source"
- ❌ Base PASS/FAIL verdict on code reading alone

**✅ REQUIRED: Run the test suite script.**

The main commands testers execute:
```bash
# Run unit tests
bash ./run_tests.sh unit

# Run E2E tests (Playwright — auto-starts server, opens browser)
bash ./run_tests.sh e2e

# Run everything
bash ./run_tests.sh
```

`run_tests.sh` runs all mandatory checks and reports PASS/FAIL with exit code (0 = success, non-zero = failure).

### Tester mandatory steps:

**Step 1 — Run the unit test suite**
```bash
bash ./run_tests.sh unit
```
If exits with non-zero → log bugs as new backlog tasks, but still close/pass the current task.

**Step 2 — Run E2E tests (for UI tasks)**
```bash
bash ./run_tests.sh e2e
```
E2E tests auto-start the server on a free port — no manual server launch needed. For debugging, use `--headed` to see the browser.

**Step 3 — Verify endpoint behavior**

After tests pass, manually hit at least one real endpoint to confirm the feature works:
```bash
curl -sf http://localhost:8008/api/status
# or use httpx:
python -c "import httpx; print(httpx.get('http://localhost:8008/api/status').status_code)"
```

**Step 3 — Fill in the tester checklist**

Copy the checklist template from `.tayfa/common/tester_checklist.md` into the task discussion file and fill in every checkbox. The checklist is MANDATORY evidence — a task cannot be marked `done` without it.

**Step 4 — Record verdict**

Post the completed checklist and verdict (PASS or FAIL) in the discussion file, then update task status accordingly.

---

## 7. Change Proposals

To propose changes to infrastructure (task_manager.py, rules, orchestrator):

```bash
python .tayfa/common/backlog_manager.py add "Proposal description" \
  --description "What, why, how" \
  --priority medium \
  --created-by <your_name>
```

Boss will review during sprint planning.

---

## 8. Bug Reporting Rules

When creating a bug report:

1. **Before creating a new bug**, list all existing bugs in the sprint:
   ```bash
   python .tayfa/common/task_manager.py list --sprint SXXX
   ```
2. Review all entries starting with **B** (B001, B002, etc.) — both open and closed
3. If an existing bug describes the same or very similar issue, do **NOT** create a duplicate
4. Instead, add a comment to the existing bug's discussion file:
   ```
   .tayfa/common/discussions/{bug_id}.md
   ```
5. Only create a new bug if no similar issue exists
6. When creating a bug, use:
   ```bash
   python .tayfa/common/task_manager.py create-bug 'Title' 'Description' \
     --author <your_name> --executor <developer> --sprint SXXX --related-task TXXX
   ```

---

## 9. Output Size Limit

Your output for a single task **MUST NOT exceed 300 lines** of changes.

If you estimate the implementation will produce more than 300 lines of changes, **STOP** and request task decomposition:
- Set task result to: `DECOMPOSE: output exceeds 300-line limit. Suggest splitting into: [list sub-tasks]`
- Set status to `questions` (so the orchestrator can re-plan)

Do **NOT** attempt to produce oversized output. Break the task into smaller pieces instead.

---

## 10. Agent Memory

Your memory file is **`.tayfa/<your_name>/memory.md`**. It is automatically loaded into your context on every call.

### When to save to memory

Save to memory **only important information** — things you would need to remember after a restart:

- **Key architectural decisions** (e.g. "We chose WebSockets over SSE for real-time updates")
- **User preferences and agreements** (e.g. "User wants all UI text in Russian")
- **Critical context** (e.g. "Project uses Godot 4.3, NOT Godot 3.x")
- **Current state** (e.g. "Sprint S012 is in progress, working on multi-instance support")

### How to save

```bash
python .tayfa/common/memory_manager.py save <your_name> "<one-line summary>"
```

### What NOT to save

- ❌ Every chat message (that's what `chat_history.json` is for)
- ❌ Task results (saved automatically on sprint finalization)
- ❌ Obvious things from your prompt.md
- ❌ Long text — keep each entry under 200 characters

### When memory is updated automatically

- **Sprint finalization** — your completed tasks are recorded
- **App shutdown** — last session info is saved
- You do NOT need to duplicate these
