<!-- Updated: 2025-02-13 | Sprint: - | Tasks: - -->

# Git Integration

## Brief Description

Automatic integration with Git: creating branches for sprints, commits on task status changes, merge and tags on finalization.

## User Value

**As** an agent,
**I want to** not worry about git commands,
**so that** I can focus on completing the task.

**As** a user (human),
**I want to** automatically get a change history with versions,
**so that** I can track project progress.

## Main Usage Scenarios

### Scenario 1: Creating a Sprint

1. Boss creates a sprint via `task_manager.py create-sprint`
2. The system automatically creates a branch `sprint/S001`
3. All changes in the sprint go to this branch

### Scenario 2: Automatic Commit

1. Developer moves the task to `in_review`
2. Orchestrator runs `git add -A`
3. Orchestrator runs `git commit -m "T001: Task Title"`
4. Changes are committed

### Scenario 3: Sprint Finalization

1. All sprint tasks are completed
2. Boss moves "Finalize sprint" to `done`
3. The system performs:
   - `git checkout main`
   - `git merge sprint/S001`
   - `git tag v0.1.0`
   - `git push origin main --tags`
4. Sprint is released

## Key Behavior

| Event | Git Action |
|-------|------------|
| Sprint creation | `git checkout -b sprint/S001` |
| Task -> `in_review` | `git add -A && git commit -m "T001: ..."` |
| Sprint finalization | Merge to main + tag + push |

## Branch Structure

```
main (stable version)
  │
  ├── sprint/S001
  │     ├── commit: T001 — Title
  │     ├── commit: T002 — Title
  │     └── finalization -> merge + tag v0.1.0
  │
  ├── sprint/S002
  │     └── ... -> merge + tag v0.2.0
  │
  └── sprint/S003 (active)
```

## Versioning

Semantic Versioning (SemVer) is used:

| Change | Version |
|--------|---------|
| Initial | v0.1.0 |
| Minor (new feature) | v0.2.0 |
| Patch (bugfix) | v0.2.1 |
| Major (breaking changes) | v1.0.0 |

On sprint finalization, the version is incremented automatically (minor by default).

## Rules for Agents

**Agents do NOT run git commands.** They only:
1. Perform work on the task
2. Record the result via `task_manager.py result`
3. Change status via `task_manager.py status`

Git operations are performed by the orchestrator automatically.

## Constraints and Notes

- Requires configured git (user.name, user.email)
- GitHub token in `settings.json` for push
- Merge conflicts are not handled automatically
- No retry on network errors

## Related Components

- `kok/git_manager.py` — all git operations
- `kok/app.py` — triggers in orchestrator
- `.tayfa/common/task_manager.py` — calls git on status change

## Change History

| Date | Sprint | What Changed |
|------|--------|--------------|
| 2025-02-13 | - | Initial version of documentation |
