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

| Status | Description |
|--------|-------------|
| `pending` | Created, not started |
| `in_progress` | Developer working |
| `in_review` | Tester verifying |
| `done` | Done |
| `cancelled` | Cancelled |

### Task Roles

| Role | Action |
|------|--------|
| **Customer** | `pending` → details requirements → `in_progress` |
| **Developer** | `in_progress` → implements → `in_review` |
| **Tester** | `in_review` → verifies → `done` or back to `in_progress` |

### Creating Tasks

```bash
python .tayfa/common/task_manager.py create "Title" "Description" \
  --customer analyst --developer developer --tester tester \
  --sprint S001

# With dependencies
python .tayfa/common/task_manager.py create "Title" "Description" \
  --customer analyst --developer dev --tester tester \
  --sprint S001 --depends-on T001 T002
```

**Important:** Boss does NOT assign himself as customer in regular tasks.

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

### Customer → Developer

```markdown
---

## [YYYY-MM-DD HH:MM] {agent} (customer)

### Task Details

#### What to do
[2-3 sentences]

#### Acceptance Criteria
- [ ] Criterion 1: specific, measurable
- [ ] Criterion 2: specific, measurable

#### Test Cases
1. [Action] → [Expected result]
2. [Edge case] → [Expected result]

#### Technical Details (optional)
- Files to change: ...
- APIs: ...
```

### Developer → Tester

```markdown
---

## [YYYY-MM-DD HH:MM] {agent} (developer)

### Implementation Result

#### What was done
- [Change 1]
- [Change 2]

#### Changed Files
- `path/file.py` — what changed

#### How to verify
- Run: `python script.py`
- Tests: `pytest tests/`

#### Checklist for tester
- [ ] Criterion 1: how to check
- [ ] Criterion 2: how to check
```

### Tester → Done/Return

**If OK:**
```markdown
---

## [YYYY-MM-DD HH:MM] {agent} (tester)

### Test Result: ✅ ACCEPTED

#### Verified Criteria
- [✓] Criterion 1: how verified
- [✓] Criterion 2: how verified

#### Additional Checks
- Edge cases: ✓ OK
- Regression: ✓ OK
```

**If issues:**
```markdown
---

## [YYYY-MM-DD HH:MM] {agent} (tester)

### Test Result: ❌ RETURNED

#### Verified Criteria
- [✓] Criterion 1: OK
- [✗] Criterion 2: FAILED

#### Bugs Found

##### Bug 1: Title
**Severity**: Critical / High / Medium / Low
**Steps**:
1. Step 1
2. Step 2

**Expected**: what should happen
**Actual**: what happens
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
| Task → `in_review` | `git add -A && git commit` |
| Finalize sprint | Merge to main + tag + push |
