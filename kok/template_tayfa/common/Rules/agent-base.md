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
python .tayfa/common/task_manager.py list --status in_progress
python .tayfa/common/task_manager.py get T001

# Work with task
python .tayfa/common/task_manager.py result T001 "Description"
python .tayfa/common/task_manager.py status T001 <status>
```

### Task Statuses

| Status | Who works | What they do |
|--------|-----------|--------------|
| `new` | Customer | Details requirements |
| `in_progress` | Developer | Implements |
| `in_review` | Tester | Verifies |
| `done` | — | Done |

### Task Roles

| Role | Description |
|------|-------------|
| **Customer** | Details requirements, formulates acceptance criteria |
| **Developer** | Implements functionality |
| **Tester** | Verifies against requirements |

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

### No Questions!

**Strictly forbidden:**
- ❌ Writing "please clarify requirements" and waiting
- ❌ Stopping work due to ambiguity

**Instead:**
- ✅ Make a decision within your role
- ✅ Document the decision in discussions
- ✅ Complete the task and pass it on

If the decision is wrong — tester will return it.

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

### What you MUST do:

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

### For testers:

**First thing you do — run the code.**

If code doesn't run → immediately return to `in_progress`:
```bash
python .tayfa/common/task_manager.py result T001 "❌ Code doesn't run: [error]"
python .tayfa/common/task_manager.py status T001 in_progress
```

Don't waste time checking functionality if basic startup fails.

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
