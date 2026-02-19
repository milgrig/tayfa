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

### Task Roles

Boss assigns roles freely when creating tasks. Any combination is possible.

| Role | Description |
|------|-------------|
| **Customer** | Details requirements, formulates acceptance criteria |
| **Developer** | Implements functionality |
| **Tester** | Verifies against requirements |

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
pytest kok/tests/
# or
npm test
```
All tests must pass. If they fail — fix them.

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

The single command testers execute:
```bash
bash ./run_tests.sh
```

This script automatically performs all mandatory checks:
1. Installs dependencies
2. Runs `pytest kok/tests/`
3. Starts the server and performs a health check via HTTP
4. Reports PASS/FAIL with exit code (0 = success, non-zero = failure)

### Tester mandatory steps:

**Step 1 — Run the test suite**
```bash
bash ./run_tests.sh
```
If `run_tests.sh` exits with non-zero → log bugs as new backlog tasks, but still close/pass the current task:
```bash
python .tayfa/common/task_manager.py result T001 "❌ run_tests.sh failed: [paste output]. Logged as backlog item."
python .tayfa/common/task_manager.py status T001 done
```

**Step 2 — Verify endpoint behavior**

After `run_tests.sh` passes, manually hit at least one real endpoint to confirm the feature works:
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

## 8. Output Size Limit

Your output for a single task **MUST NOT exceed 300 lines** of changes.

If you estimate the implementation will produce more than 300 lines of changes, **STOP** and request task decomposition:
- Set task result to: `DECOMPOSE: output exceeds 300-line limit. Suggest splitting into: [list sub-tasks]`
- Set status to `questions` (so the orchestrator can re-plan)

Do **NOT** attempt to produce oversized output. Break the task into smaller pieces instead.
