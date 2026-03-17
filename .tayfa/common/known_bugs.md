# Known Bugs & Lessons Learned

This file is auto-injected into every task prompt.
Agents MUST check this list before marking any task as done.
If you fixed a bug that is NOT listed here — **add it** following the format below.

---

## KB-001: Sprint release push fails silently when remote main has diverged history

**Symptom:** Sprint finalization completes locally (merge + tag created) but `pushed=false`. The release result reports success with the merge but changes never reach GitHub.
**Root Cause:** `release_sprint()` used a plain `git push origin main --tags` without checking whether `origin/main` is an ancestor of local `main`. When someone force-pushes an orphan/squashed commit to `origin/main` (e.g. via GitHub UI "initial commit"), the histories diverge and a non-force push is rejected. The code did not detect this scenario.
**Prevention:** (1) `release_sprint()` now detects divergence via `merge-base --is-ancestor` before push and uses `--force` when needed, with a `--force-with-lease` final fallback. (2) `git pull` in step 2 uses `--ff-only` to safely reject diverged remote history. (3) `check_git_ready_for_release()` warns about diverged/orphan remote before release starts. (4) Always verify `origin/main` history before first release of a new repo.
**Recurred:** 1 time / S002

## KB-002: GitHub token leaks into .git/config after push

**Symptom:** After a release push, `git remote get-url origin` contains the plaintext GitHub token (e.g. `https://ghp_xxx@github.com/...`), visible to anyone reading `.git/config`.
**Root Cause:** `_setup_git_remote()` injects the token into the origin URL for authentication in WSL (where no credential helper is available), but never cleaned it up after the push completed.
**Prevention:** Added `_cleanup_remote_token()` that resets origin URL to the clean (tokenless) form. Called in `finally` block of `release_sprint()` and after `check_git_ready_for_release()`.
**Recurred:** 1 time / S002

## KB-003: Install update fails with "Not possible to fast-forward" on diverged histories

**Symptom:** Clicking "Install update" in Settings returns error: "fatal: Not possible to fast-forward, aborting". The update is not applied.
**Root Cause:** `install_update()` used `git pull --ff-only` which fails when local and remote histories have diverged (e.g. after a force push to GitHub, or local commits on main).
**Prevention:** `install_update()` now uses a 3-strategy escalation: (1) fast-forward pull, (2) rebase pull, (3) `git reset --hard origin/<branch>`. Since Tayfa app code should always match GitHub and user project files are NOT in the Tayfa repo, hard reset is safe. Strategy used is returned in the response for debugging.
**Recurred:** 1 time / S003

---

<!--
FORMAT FOR NEW ENTRIES:

## KB-XXX: Short Title

**Symptom:** What the user sees
**Root Cause:** Why it happens
**Prevention:** Steps to avoid it
**Recurred:** How many times / which sprints

===

FUTURE SPECIALIZATION:
Currently this file is shared by ALL agents. In the future, it can be split
into role-specific files for teams with diverse specialists:
  - known_bugs.md              (shared, cross-role issues)
  - known_bugs_developer.md    (code-level patterns)
  - known_bugs_tester.md       (testing anti-patterns)
  - known_bugs_sql.md          (SQL-specific issues)
  - known_bugs_frontend.md     (UI/UX patterns)
The orchestrator (tasks.py) would then inject only the relevant file(s)
based on the agent's role.
-->
