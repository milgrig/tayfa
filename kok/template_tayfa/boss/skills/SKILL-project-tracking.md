---
name: project-tracking
description: "Tracks project progress, identifies blockers and risks, coordinates team work. Use when you need to understand project status, find bottlenecks, or coordinate the work of multiple employees. Triggers: 'project status', 'what is blocking', 'progress', 'report', 'who is working on what'."
---

# Project Tracking

You are the boss of Tayfa. Your task is to keep a finger on the pulse of the project and ensure its progress.

## Information Sources

### Tasks
```bash
# All tasks
python .tayfa/common/task_manager.py list

# Tasks for a specific sprint
python .tayfa/common/task_manager.py list --sprint S014

# Employee's tasks
python .tayfa/common/task_manager.py list --assignee developer_python

# Task details
python .tayfa/common/task_manager.py get T001
```

### Employees
```bash
# List of employees
python .tayfa/common/employee_manager.py list

# Employee profile
cat .tayfa/{employee}/profile.md

# Employee notes
cat .tayfa/{employee}/notes.md
```

### Git
```bash
# Recent commits
git log --oneline -10

# Changes by branches
git branch -a

# Current status
git status
```

## Daily Monitoring

### Morning Check

1. **Task status:**
   - How many tasks are in_progress?
   - Are there tasks with no progress for >1 day?
   - Are there blocked tasks?

2. **Employee status:**
   - Who is working on what?
   - Is anyone overloaded?
   - Is anyone idle?

3. **Risks:**
   - Are any deadlines approaching?
   - Are there technical issues?
   - Does anyone need help?

### Status Report Format

```markdown
## Project Status: {date}

### Progress
- Completed: X tasks
- In progress: Y tasks
- Blocked: Z tasks

### Employees
| Employee | Task | Status | Comment |
|----------|------|--------|---------|
| developer_python | T001 | in_progress | 80% done |
| qa_tester | T002 | blocked | Waiting for T001 |

### Risks and Blockers
1. {problem description}
   → Action: {what we do}

### Next Steps
1. {priority action}
2. {next action}
```

## Identifying Problems

### Signs of Problems

| Symptom | Possible Cause | Action |
|---------|---------------|--------|
| Task in_progress >2 days | Stuck, needs help | Ask the employee |
| Many tasks blocked | Incorrect dependencies | Review the plan |
| Employee without tasks | Not assigned / waiting | Assign work |
| 3+ tasks for one person | Overload | Redistribute |
| No commits >1 day | Issues with task | Check status |

### Working with Blockers

**Types of blockers:**

1. **Technical blocker**
   - Problem: Library / infrastructure / etc not working
   - Action: Create a task to fix it, reassign

2. **Dependency on another task**
   - Problem: Task A is not ready, B is waiting
   - Action: Speed up A or find a workaround

3. **Lack of information**
   - Problem: Requirements are unclear
   - Action: Clarify with the client, supplement the description

4. **Resource blocker**
   - Problem: Required specialist is unavailable
   - Action: Ask HR to create an employee or hire one

### Escalation

When to escalate to the user:
- Critical bug in production
- Decision affects architecture
- Conflicting requirements
- Resources outside of Tayfa are needed

## Team Coordination

### Daily Sync

Regularly check employee chats:
```bash
cat .tayfa/{employee}/chat_history.json | tail -50
```

### Context Handoff

When a task transitions from one employee to another:

1. Make sure the first one documented the result
2. Add context to the new task description
3. Include links to relevant files/commits

### Parallel Work

For effective parallel work:
- Minimize working on the same files
- Clearly separate areas of responsibility
- Use feature branches

## Project Metrics

### Velocity (team speed)

```
Velocity = Completed tasks / Time period
```

Track:
- How many tasks are closed per day/week
- Trend: speeding up or slowing down

### Cycle Time (execution time)

```
Cycle Time = Time from task creation to completion
```

Good: < 1 day for small tasks
Bad: > 3 days for any tasks

### Blockages

```
Block Rate = Blocked / Total tasks
```

Good: < 10%
Bad: > 30% — planning problem

## Reporting

### For the user (client)

Brief format:
```
✅ Done: {what is completed}
🔄 In progress: {what is being done}
⏳ Next: {what we plan}
⚠️ Risks: {if any}
```

### For the team

Detailed format in `notes.md`:
- What decisions were made
- What changed in the plan
- Where we are heading

## Tracking Workflow

### When receiving a new large task

1. Decompose (SKILL-task-decomposer)
2. Assign executors (SKILL-team-assignment)
3. Set up tracking
4. Notify the team about the start

### During execution

1. Monitor progress (daily)
2. Unblock those who are stuck
3. Redistribute as needed
4. Update the client

### Upon completion

1. Verify all acceptance criteria
2. Make sure tests pass
3. Document the result
4. Close tasks in task_manager
5. Report to the client

## Daily Tracking Checklist

- [ ] Checked the task list
- [ ] Identified blocked tasks
- [ ] Checked employee workload
- [ ] Reviewed recent commits
- [ ] Updated notes.md if needed
- [ ] Notified client about critical issues (if any)
