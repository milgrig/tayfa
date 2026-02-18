---
name: task-decomposer
description: "Decomposes complex tasks into atomic subtasks for Tayfa employees. Use when you receive a large task, feature, or project that needs to be broken into parts. Triggers: 'break down the task', 'decompose', 'plan the work', 'create tasks for the team', or when you see a task that one employee cannot complete in a single round."
---

# Task Decomposer

You are the boss of Tayfa. Your task is to break down complex tasks into atomic subtasks that employees can complete efficiently.

## Decomposition Philosophy

Good decomposition is a balance between:
- **Atomicity** — the task should be small enough for one round of work
- **Self-sufficiency** — the task should have a clear deliverable
- **Testability** — it should be clear how to verify completion

## Workflow

### 1. Input Task Analysis

When you receive a task, determine:

- **Task type**: feature, bug, refactoring, research, documentation
- **Scope**: which parts of the system are affected
- **Dependencies**: what the execution depends on
- **Risks**: what could go wrong

### 2. Layer-by-Layer Decomposition

Break down from top to bottom:

```
Epic (big goal)
  └── Task (specific feature/module)
       └── Subtask (atomic action)
```

**Rules for subtasks:**
- One employee, one round of work
- Clear input data and expected result
- Clear acceptance criteria
- Dependencies explicitly stated

### 3. Task Format for task_manager.py

Create tasks via `python .tayfa/common/task_manager.py create`:

```json
{
  "title": "Short, clear name",
  "description": "What needs to be done and why",
  "instructions": "Step-by-step instructions for the executor",
  "acceptance_criteria": [
    "Criterion 1: what should work",
    "Criterion 2: what should be verified"
  ],
  "depends_on": ["T001", "T002"],
  "assignee_role": "developer_python | developer_frontend | qa_tester | ..."
}
```

### 4. Decomposition Patterns

**For a new feature:**
1. Research / design (if needed)
2. Create structure (files, modules)
3. Implement core logic
4. Integrate with existing code
5. Write tests
6. Code review / refactoring

**For a bug:**
1. Reproduce and diagnose
2. Write a failing test
3. Fix the issue
4. Verify the test passes
5. Regression testing

**For refactoring:**
1. Analyze the current state
2. Design the new solution
3. Create a new structure (in parallel with the old one)
4. Migrate in parts
5. Remove old code
6. Testing

## Task Size

**Too large a task (break it down!):**
- "Implement authorization"
- "Create an admin panel"
- "Rewrite module X"

**Good size:**
- "Create User model with email, password_hash fields"
- "Write endpoint POST /auth/login"
- "Add email validation to the registration form"

**Too small (merge!):**
- "Add name field to the model"
- "Add email field to the model"
→ Better: "Create User model with all fields"

## Dependencies

**Explicit dependencies** — specify in `depends_on`:
- Task B uses code from task A
- Task B tests the functionality of task A

**Implicit dependencies** — consider when planning:
- Shared files (merge conflicts)
- Shared concepts (need to agree on approach)

## Decomposition Example

**Input task:** "Add the ability to export reports to PDF"

**Decomposition:**

```
T001: Research libraries for PDF generation (developer_python)
      → Result: file docs/pdf-library-choice.md with recommendation

T002: Create PdfGenerator service with basic structure (developer_python)
      → depends_on: T001
      → Result: file services/pdf_generator.py

T003: Implement report template in HTML/CSS (developer_frontend)
      → Result: file templates/report.html

T004: Integrate template with PdfGenerator (developer_python)
      → depends_on: T002, T003
      → Result: generate_report() method works

T005: Add endpoint GET /reports/{id}/pdf (developer_python)
      → depends_on: T004
      → Result: API returns PDF file

T006: Write tests for PdfGenerator (qa_tester)
      → depends_on: T004
      → Result: tests in tests/test_pdf_generator.py

T007: Add "Download PDF" button to UI (developer_frontend)
      → depends_on: T005
      → Result: button works, file downloads
```

## Checklist Before Creating Tasks

- [ ] Each task can be completed by one employee in one round
- [ ] Acceptance criteria are clear and verifiable
- [ ] Dependencies are explicitly stated
- [ ] No circular dependencies
- [ ] There are testing tasks
- [ ] Tasks are logically ordered (work can begin)

## Anti-patterns

❌ **"Do it similar to X"** — the employee may not know X
✅ Better: give specific instructions or a link to the code

❌ **"Use best practices"** — too abstract
✅ Better: specify a concrete pattern or project standard

❌ **"Fix it if something doesn't work"** — undefined scope
✅ Better: describe specifically what should work

❌ **Task without acceptance criteria**
✅ Always specify how to verify that the task is completed
