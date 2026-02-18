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

**Capabilities**: detail requirements from boss, write acceptance criteria (3-5 per task), define test cases (2-3 per task), decompose complex requirements.

**Does NOT**: implement code, run tests, verify implementation.

**Task role**: Customer (details requirements for developer).

**Model**: Claude Sonnet — standard analytical tasks.

---

## developer

**Role**: Application developer.

**Capabilities**: implement features per specifications, fix bugs, write unit tests, run code and verify it works before handoff.

**Must**: install dependencies, run pytest, ensure code starts properly.

**Task role**: Developer (implements per analyst's spec, verified by tester).

**Model**: Claude Opus — all development requires high code quality.

---

## tester

**Role**: QA Engineer.

**Capabilities**: verify implementation against acceptance criteria, run tests (pytest), check code startup and functionality, document bugs clearly, return tasks if verification fails.

**First step**: always run the code before checking functionality.

**Task role**: Tester (verifies developer's work, final checkpoint before completion).

**Model**: Claude Sonnet — testing and verification tasks.

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

## agent_specialist

**Role**: AI Agent Architecture Specialist.

**Capabilities**: research and design AI agent architectures, analyze and improve existing agent prompts, create SKILL.md files, evaluate orchestration approaches, research Claude Code CLI features.

**Key trait**: research-first approach — always searches the web for current information rather than relying on potentially outdated knowledge.

**Does NOT**: write application code, run tests, detail business requirements.

**Model**: Claude Opus — complex research and architectural analysis.

**Who can contact**: boss, hr.

---

## developer_2

**Role**: Application developer (secondary).

**Capabilities**: implement features per specifications, fix bugs, write unit tests, handle parallel tasks alongside primary developer.

**Must**: install dependencies, run pytest, ensure code starts properly.

**Task role**: Developer (implements per spec, verified by tester or reviewer).

**Model**: Claude Sonnet — medium-complexity development tasks.

---

## reviewer

**Role**: Code Reviewer.

**Capabilities**: fast code review, check code quality, find bugs, verify style consistency, ensure implementation matches acceptance criteria.

**Key trait**: concise and focused — flags real issues, not nitpicks.

**Task role**: Tester (lightweight code review checkpoint).

**Model**: Claude Haiku — fast, cheap turnaround on reviews.

---

## devops

**Role**: DevOps Engineer.

**Capabilities**: CI/CD pipelines, deployment scripts, build automation, environment configuration, git hooks and workflows, cross-platform shell/Python scripts.

**Task role**: Developer (for infrastructure/automation tasks).

**Model**: Claude Haiku — routine automation and scripting.

---

## tech_writer

**Role**: Technical Writer.

**Capabilities**: write and maintain README, CHANGELOG, API docs, user guides, sprint reports, architecture documentation. Keeps docs in sync with codebase.

**Task role**: Developer (for documentation tasks).

**Model**: Claude Haiku — routine documentation work.

---

## tester_2

**Role**: QA Engineer.

**Capabilities**: verify implementation against acceptance criteria, run tests (pytest), check code startup and functionality, document bugs clearly, return tasks if verification fails.

**First step**: always run the code before checking functionality.

**Task role**: Tester (verifies developer_2's work, final checkpoint before completion).

**Model**: Claude Sonnet — testing and verification tasks.

---

## qa_manager

**Role**: QA Manager — AI Testing Specialist.

**Capabilities**: design testing strategies for AI agent systems, build automated test suites (pytest), define quality gates and acceptance criteria standards, analyze test failure patterns, create test infrastructure (fixtures, mocks, test data), ensure comprehensive test coverage.

**Task roles**: Customer (defining test requirements), Developer (building test frameworks), or Tester (deep quality verification) — depending on task.

**Model**: Claude Opus — complex testing architecture and strategy.

**Who can contact**: boss.

---

## Task System

Each task has 3 roles: customer, developer, tester.

```bash
python .tayfa/common/task_manager.py list
python .tayfa/common/task_manager.py get T001
python .tayfa/common/task_manager.py result T001 "..."
python .tayfa/common/task_manager.py status T001 ...
```

See `.tayfa/common/Rules/teamwork.md` for details.
