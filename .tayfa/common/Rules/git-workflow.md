# Git Workflow for Tayfa

## 1. Initial Setup (once)

User configures in **Settings → Git / GitHub**:
- `userName` — name for commits
- `userEmail` — email for commits
- `defaultBranch` — main branch (main)
- `githubToken` — Personal Access Token with `repo` rights

## 2. Connecting Project to Git

When opening a project:

| State | Action |
|-------|--------|
| No `.git` | Ask: "Track project with Git?" → Yes: `git init` + remote setup |
| Has `.git`, no remote | Ask: "Specify GitHub repository?" |
| Has `.git` and remote | Ready to work |
| Git declined | Work without Git, don't ask again |

**Repository creation:**
- Repo name = project name (or user input)
- Remote URL: `https://github.com/{user}/{repo}.git`
- Default branch: `main`

## 3. Sprint Workflow

```
main (stable version)
  │
  └── sprint/S001 (sprint branch)
        │
        ├── commit: T001 — description
        ├── commit: T002 — description
        ├── commit: T003 — description
        └── finalize → merge to main + tag vX.Y.Z
```

### 3.1 Sprint Start
```bash
git checkout main
git pull origin main
git checkout -b sprint/S001
```

### 3.2 Task Work
After completing a task:
```bash
git add <files>
git commit -m "T001: Brief task description"
git push origin sprint/S001
```

### 3.3 Sprint Finalization
Last sprint task — "Finalization":
1. Ensure all tests pass
2. Merge to main:
```bash
git checkout main
git merge sprint/S001 --no-ff -m "Merge sprint S001"
git tag -a vX.Y.Z -m "Release vX.Y.Z"
git push origin main --tags
```
3. Delete sprint branch (optional)

## 4. Conventions

### Commit Format
```
T001: Brief description (up to 50 chars)

Detailed description if needed.
```

### Branch Naming
- `main` — stable version
- `sprint/S001` — sprint branch
- `feature/T001-name` — feature branch (optional)
- `fix/T002-name` — bugfix (optional)

### Version Tags
- Format: `vMAJOR.MINOR.PATCH` (e.g. `v0.2.0`)
- Created on sprint finalization
- Auto-increment configured in settings.json

## 5. API Endpoints

| Endpoint | Description |
|----------|-------------|
| `POST /api/git/init` | Init + remote setup |
| `POST /api/git/commit` | Commit changes |
| `POST /api/git/push` | Push to remote |
| `POST /api/git/release` | Finalize: merge + tag + push |
| `GET /api/git/status` | Repository status |

## 6. Git Opt-out Flag

If user declined Git:
- Save in project `config.json`: `"useGit": false`
- Don't show Git functions in UI
- Don't ask again
