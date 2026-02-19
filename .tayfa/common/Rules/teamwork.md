# Teamwork Rules

## Working Directory

All agents work from project root. Visible:
- Project files and folders
- `.tayfa/` — team folder: common/, boss/, hr/, <name>/

## What Goes Where

- **Project root** — code, frontend/backend, design, product docs
- **`.tayfa/`** — communication: tasks, employees, rules, prompts

---

## Task and Sprint System

### Sprints

Sprint — group of tasks with common goal. **All tasks must belong to a sprint.**

- Only **boss** creates sprints
- "Finalize sprint" task is auto-created with dependencies on all sprint tasks

**Statuses:** `active` → `completed`

```bash
python .tayfa/common/task_manager.py create-sprint "Sprint Name" "Description"
python .tayfa/common/task_manager.py sprints
```

### Task Statuses

| Status | Meaning |
|--------|---------|
| `new` | Task created, ready for execution |
| `done` | Task completed |
| `questions` | Agent blocked — needs clarification |
| `cancelled` | Task cancelled |

### Task Roles

Each task has an **author** (who created it) and an **executor** (who does the work).

| Field | Description |
|-------|-------------|
| **author** | Who created the task |
| **executor** | Who executes → `done` or `questions` |

### Creating Tasks

```bash
python .tayfa/common/task_manager.py create "Title" "Description" \
  --author boss --executor developer \
  --sprint S001

# With dependencies
python .tayfa/common/task_manager.py create "Title" "Description" \
  --author boss --executor dev \
  --sprint S001 --depends-on T001 T002
```

---

## Task Communication — discussions/

All task messages go in:
```
.tayfa/common/discussions/{task_id}.md
```

### Format

```markdown
---

## [YYYY-MM-DD HH:MM] agent_name (role)

### Section Title
Content...
```

### Rules

1. **Auto-created** when task is created
2. **Append only** — don't delete previous content
3. **Read first** — understand context before working
4. **No questions** — make decisions, document them

---

## Handoff Formats

### Executor — Task Completed

```markdown
---

## [YYYY-MM-DD HH:MM] {agent} (executor)

### Result

#### What was done
- [Change 1]
- [Change 2]

#### Changed Files
- `path/file.py` — what changed

#### How to verify
- Run: `python script.py`
- Tests: `pytest tests/`
```

### Executor — Questions

```markdown
---

## [YYYY-MM-DD HH:MM] {agent} (executor)

### Status: QUESTIONS

#### What is needed
- [Detailed description of what is blocking the task]
- [What permissions/info/decisions are required]

#### What was attempted
- [What was tried before getting blocked]
```

---

## Employee Registry

Source of truth: **`.tayfa/common/employees.json`**

- New employees: `python .tayfa/hr/create_employee.py <name>`
- View: `python .tayfa/common/employee_manager.py list`

---

## Git Workflow

**Agents do NOT run git commands** — orchestrator does automatically.

| Event | Orchestrator Action |
|-------|---------------------|
| Create sprint | Create branch `sprint/S001` |
| Task → `done` | `git add -A && git commit` |
| Finalize sprint | Merge to main + tag + push |
