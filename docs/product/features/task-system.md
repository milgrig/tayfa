<!-- Updated: 2025-02-13 | Sprint: - | Tasks: - -->

# Task and Sprint System

## Brief Description

A centralized task management system where all tasks are linked to sprints and go through three stages: detailing -> development -> testing.

## User Value

**As** a project manager (boss),
**I want to** create tasks with three assigned executors,
**so that** I can ensure quality requirement elaboration, implementation, and verification.

## Main Usage Scenarios

### Scenario 1: Creating a Sprint

1. Boss runs the command `task_manager.py create-sprint "Name" "Description"`
2. The system creates a sprint with a unique ID (S001, S002, ...)
3. A "Finalize sprint" task is automatically created
4. A git branch `sprint/S001` is created

### Scenario 2: Creating a Task

1. Boss runs `task_manager.py create "Title" "Description" --customer analyst --developer developer --tester tester --sprint S001`
2. The system creates a task with a unique ID (T001, T002, ...)
3. The task appears with status `pending`
4. In the orchestrator, the task is displayed on the sprint kanban board

### Scenario 3: Task Progression Through Stages

```
[pending]
    | requester details, writes in discussions/
    | result: "Detailed. See discussions/T001.md"
    | status: in_progress
[in_progress]
    | developer implements, appends to discussions/
    | result: "Completed. See discussions/T001.md"
    | status: in_review
    | -> automatic git commit
[in_review]
    | tester verifies, appends result
    | result: "Accepted" -> status: done
    | result: "Returned" -> status: in_progress
[done]
```

### Scenario 4: Sprint Finalization

1. All sprint tasks are in status `done` or `cancelled`
2. Boss moves the "Finalize sprint" task to `done`
3. The system performs merge `sprint/S001` -> `main`
4. A version tag is created (v0.1.0, v0.2.0, ...)
5. Push to remote
6. Sprint is archived

## Key Behavior

| Situation | System Behavior |
|-----------|-----------------|
| Sprint creation | Auto-creates "Finalize" task with dependencies on all tasks |
| Status change to `in_review` | Automatic git commit |
| Sprint finalization | Merge + tag + push |
| Task with dependencies | Cannot start until dependencies are done |

## Task Statuses

| Status | Description | Who Works |
|--------|-------------|-----------|
| `pending` | Task created | Requester (customer) |
| `in_progress` | Requirements detailed | Developer (developer) |
| `in_review` | Implementation completed | Tester (tester) |
| `done` | Verification passed | — |
| `cancelled` | Task cancelled | — |

## Task Roles

| Role | What They Do | Typical Agents |
|------|-------------|----------------|
| **Requester (customer)** | Details requirements, writes acceptance criteria | analyst, product_manager |
| **Developer (developer)** | Implements features | developer_python, developer_frontend |
| **Tester (tester)** | Verifies quality | qa_tester, tester |

## Constraints and Notes

- All tasks must be linked to a sprint
- Boss does not assign himself as requester in regular tasks
- The JSON file `tasks.json` is edited only through `task_manager.py`
- Dependencies block task execution

## Related Components

- `.tayfa/common/task_manager.py` — task management CLI
- `.tayfa/common/tasks.json` — task storage
- `kok/app.py` — orchestrator (Web UI)
- `.tayfa/common/discussions/` — task discussions

## CLI Commands

```bash
# Sprints
python .tayfa/common/task_manager.py create-sprint "Name" "Description"
python .tayfa/common/task_manager.py sprints
python .tayfa/common/task_manager.py sprint S001

# Tasks
python .tayfa/common/task_manager.py create "Title" "Description" \
  --customer analyst --developer developer --tester tester --sprint S001
python .tayfa/common/task_manager.py list
python .tayfa/common/task_manager.py list --status in_progress
python .tayfa/common/task_manager.py list --sprint S001
python .tayfa/common/task_manager.py get T001

# Working with a task
python .tayfa/common/task_manager.py result T001 "Result description"
python .tayfa/common/task_manager.py status T001 in_progress
```

## Change History

| Date | Sprint | What Changed |
|------|--------|--------------|
| 2025-02-13 | - | Initial version of documentation |
