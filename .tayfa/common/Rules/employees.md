# Employee List

## Registry

Source of truth: **`.tayfa/common/employees.json`**

- New employees: `python .tayfa/hr/create_employee.py <name>`
- View: `python .tayfa/common/employee_manager.py list`
- Remove: `python .tayfa/common/employee_manager.py remove <name>` (cannot remove boss/hr)

---

## boss

**Role**: Project manager, task coordinator.

**When to contact**: task done, serious questions, need new employee.

**Who can contact**: any employee.

---

## hr

**Role**: HR manager, employee and agent management.

**Capabilities**: create employees via `create_employee.py`, edit prompts.

**Who can contact**: only boss.

---

## analyst

**Role**: System analyst, requirements and task specification.

**Capabilities**: detail requirements, write user stories, acceptance criteria, decompose tasks.

**Task role**: Executor (details requirements, analyzes).

---

## developer

**Role**: Application developer.

**Capabilities**: implement features, fix bugs, refactor, write tests.

**Task role**: Executor (implements per spec).

---

## tester

**Role**: QA Engineer.

**Capabilities**: test functionality, verify acceptance criteria, document bugs.

**Task role**: Executor (verifies and accepts/returns).

---

## python_dev

**Role**: Senior Python Developer (Opus model).

**Capabilities**: architecture, core modules, complex integrations, optimization.

**Model**: Claude Opus — for complex architectural tasks.

**When NOT to use** (use developer): simple CRUD, field additions, typo fixes.

---

## junior_analyst

**Role**: Quick requirements structuring.

**Capabilities**: structure requirements into acceptance criteria (3-5 items), add test cases (2-3).

**Does NOT**: ask questions, research code, add own requirements.

**Model**: Claude Haiku — for fast template operations.

---

## developer_python

**Role**: Backend Developer (Senior Python).

**Capabilities**: Python backend development, FastAPI, REST API design, SQLAlchemy, database architecture, backend testing (pytest).

**Model**: Claude Opus — critical backend code requires highest quality.

**Task role**: Executor (implements backend features, APIs, database logic).

---

## developer_frontend

**Role**: Frontend Developer (Middle+).

**Capabilities**: UI implementation, HTML/CSS/JavaScript, React/Vue, responsive design, E2E testing (Playwright), frontend performance optimization.

**Model**: Claude Opus — UI code quality impacts user experience directly.

**Task role**: Executor (implements UI, components, styles, frontend tests).

---

## qa_tester

**Role**: QA Engineer.

**Capabilities**: test strategy, automated testing (pytest, Playwright), regression testing, bug reporting, test execution via `run_tests.sh`.

**Model**: Claude Sonnet — standard testing tasks.

**Task role**: Executor (verifies features, runs tests, documents bugs).

**Testing approach**: EXECUTION-ONLY (runs tests, does NOT read source code for verification).

---

## Task System

Each task has 2 fields: author (who created) and executor (who does the work).

```bash
python .tayfa/common/task_manager.py list
python .tayfa/common/task_manager.py get T001
python .tayfa/common/task_manager.py result T001 "..."
python .tayfa/common/task_manager.py status T001 ...
```

See `.tayfa/common/Rules/teamwork.md` for details.
