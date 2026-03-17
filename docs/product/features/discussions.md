<!-- Updated: 2025-02-13 | Sprint: - | Tasks: - -->

# Discussion System (Discussions)

## Brief Description

A centralized place for agent communication on each task. Each task has its own discussion file where the complete handoff history between stages is preserved.

## User Value

**As** an agent (requester/developer/tester),
**I want to** see the complete work history for a task,
**so that** I understand the context and don't lose information during handoff.

**As** a user (human),
**I want to** read the discussion history in a simple format,
**so that** I understand what happened with the task.

## Main Usage Scenarios

### Scenario 1: Requester Creates a Discussion

1. Requester receives a task with status `pending`
2. Creates the file `.tayfa/common/discussions/T001.md`
3. Writes details: acceptance criteria, test cases
4. Records a brief status in task_manager
5. Moves the task to `in_progress`

### Scenario 2: Developer Appends Result

1. Developer reads the file `discussions/T001.md`
2. Sees the details from the requester
3. Performs the work
4. Appends their result to the end of the file
5. Moves the task to `in_review`

### Scenario 3: Tester Completes the Cycle

1. Tester reads the entire file `discussions/T001.md`
2. Sees: details + developer's result
3. Verifies against the checklist
4. Appends testing results
5. Moves to `done` or returns to `in_progress`

## Key Behavior

| Situation | Behavior |
|-----------|----------|
| First agent (requester) | Creates file with the task title |
| Subsequent agents | Append to the end, without deleting previous content |
| task_manager.py result | Contains only a brief status with a reference to the file |

## Discussion File Format

```markdown
# T001: Task Title

---

## [2025-01-15 10:00] analyst (requester)

### Task Details

#### What Needs to Be Done
...

#### Acceptance Criteria
- [ ] Criterion 1
- [ ] Criterion 2

#### Test Cases
1. Action -> Result

---

## [2025-01-15 14:00] developer (developer)

### Execution Result

#### What Was Done
- ...

#### Changed Files
- `path/to/file.py` — description

#### Checklist for Tester
- [ ] Verify criterion 1

---

## [2025-01-15 16:00] tester (tester)

### Testing Result: ACCEPTED

#### Verified Criteria
- [x] Criterion 1: verified
- [x] Criterion 2: verified
```

## Mandatory Handoff Formats

### Requester -> Developer

- What needs to be done
- Acceptance Criteria (measurable)
- Test Cases (happy path + edge cases)
- Technical details (optional)

### Developer -> Tester

- What was done
- Changed files
- How to verify (commands, URLs)
- Checklist for tester

### Tester -> Completion/Return

- Status for each criterion
- Found bugs (if any)
- Steps to reproduce bugs

## Constraints and Notes

- Files are only appended to, never overwritten
- Separator between messages: `---`
- Header format: `## [date time] agent_name (role)`
- In task_manager.py result, only a brief status is written

## Related Components

- `.tayfa/common/discussions/` — folder with discussion files
- `.tayfa/common/task_manager.py` — records brief status
- Agent prompts — contain handoff formats

## Change History
