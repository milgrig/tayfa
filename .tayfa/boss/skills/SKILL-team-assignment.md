---
name: team-assignment
description: "Selects the optimal executor for a task from Tayfa employees. Use when you need to assign a task, decide who to delegate work to, or determine which employee will handle it best. Triggers: 'who to assign', 'who will handle it best', 'find an executor', or when creating a task and need to specify an assignee."
---

# Team Assignment

You are the boss of Tayfa. Your task is to assign the right employees to the right tasks.

## Source of Truth

Employee list: `.tayfa/common/employees.json`

Before assigning, always check:
```bash
python .tayfa/common/employee_manager.py list
```

## Employee Profiles

For each employee, study their profile:
- `.tayfa/{employee}/profile.md` — skills, specialization, experience
- `.tayfa/{employee}/prompt.md` — how they work, their style
- `.tayfa/{employee}/tasks.md` — current tasks (workload)

## Criteria for Selecting an Executor

### 1. Skill Match

**Priority:** the employee's skills must match the task.

| Task Type | Suitable Roles |
|-----------|---------------|
| Backend logic, API, DB | developer_python, developer_backend |
| UI, layout, React/Vue | developer_frontend |
| Mobile application | developer_mobile |
| Testing, QA | qa_tester |
| DevOps, CI/CD | devops_engineer |
| AI/ML tasks | ai_expert |
| Research, analysis | analyst, ai_expert |

### 2. Current Workload

Check how many tasks the employee has:
```bash
python .tayfa/common/task_manager.py list --assignee {employee}
```

**Rules:**
- No more than 2-3 active tasks per employee
- If overloaded — find an alternative or wait

### 3. Context and History

Consider:
- Has the employee worked with this module before?
- Do they have context from previous tasks?
- Is the task related to their recent work?

**Context advantage:** if the employee has already worked with the code, they will complete it faster.

### 4. Task Dependencies

If task B depends on task A:
- Can assign to the same employee (context preservation)
- Can assign to another (parallel work after A is completed)

## Assignment Workflow

### 1. Task Analysis

```
What skills are needed?
  → Backend? Frontend? Testing? Research?

What is the complexity?
  → Can a junior handle it? Need a senior?

Is there anything specific?
  → Does it require knowledge of a specific technology?
```

### 2. Finding Candidates

```bash
# View all employees
python .tayfa/common/employee_manager.py list

# View candidate profile
cat .tayfa/{candidate}/profile.md

# View workload
python .tayfa/common/task_manager.py list --assignee {candidate}
```

### 3. Making the Decision

**Ideal candidate:**
- Skills match the task
- Not overloaded (< 3 active tasks)
- Has context (worked with this code)
- Available to start now

**Compromises:**
- No ideal candidate → choose by skills
- Everyone is busy → wait or redistribute
- Context needed → add detailed instructions

### 4. Assignment

```bash
python .tayfa/common/task_manager.py assign T001 {employee}
```

## Assignment Matrix

### Standard Tayfa Roles

| Role | Primary Tasks | Do Not Assign |
|------|--------------|---------------|
| developer_python | Backend, API, scripts, DB | UI, layout |
| developer_frontend | UI, components, styles | Backend logic |
| qa_tester | Testing, bug reports | Feature development |
| devops_engineer | CI/CD, deployment, infrastructure | Business logic |
| ai_expert | ML, prompts, research | Routine code |

### Special Cases

**Research task:**
→ Assign to someone who can make decisions and has a broad perspective

**Urgent production bug:**
→ Assign to someone who knows this code best (even if busy)

**New technology:**
→ Assign to someone who wants to learn and is ready to experiment

**Routine task:**
→ Assign to someone with the lightest workload

## Communication During Assignment

### Task Format for the Employee

When creating a task via task_manager.py:

```
title: Clear name
description: What to do and why
instructions:
  - Step-by-step instructions
  - With specific details
  - And links to code if needed
acceptance_criteria:
  - How to verify it is done
assignee: {employee}
```

### Feedback

After assignment:
1. Make sure the employee saw the task
2. Answer questions if any
3. Check progress via `task_manager.py get {task_id}`

## Task Redistribution

**When to redistribute:**
- Employee is blocked
- Urgency changed
- Discovered that different skills are needed

**How to redistribute:**
```bash
python .tayfa/common/task_manager.py assign T001 {new_employee}
```

## Assignment Checklist

- [ ] Checked employees.json — employee exists
- [ ] Read profile.md — skills match
- [ ] Checked workload — not overloaded
- [ ] Task contains clear instructions
- [ ] Acceptance criteria are defined
- [ ] Dependencies are accounted for (task is not blocked)
