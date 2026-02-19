# Tester Verification Checklist

> Copy this checklist into the task discussion file when submitting your verification result.
> Fill in every checkbox and provide details where indicated.
> A task CANNOT be marked `done` without a completed checklist.

## Checklist for task: T___

**Tested by:** _(your name)_
**Date:** _(YYYY-MM-DD)_

### Execution steps

- [ ] **Dependencies installed** — ran `pip install -r kok/requirements.txt` (or equivalent) without errors
- [ ] **pytest passed** — ran `bash ./run_tests.sh` or `pytest kok/tests/ -v`
  - Result: _X passed / Y failed / Z errors_
  - Output summary: _(paste key lines or "all green")_
- [ ] **Server started** — server launched on port 8008 (or configured port) without crash
- [ ] **Endpoint hit** — sent real HTTP request to verify feature works
  - URL: _http://localhost:8008/..._
  - Method: _GET/POST_
  - Status code: _200 / ..._
  - Response snippet: _(brief)_
- [ ] **run_tests.sh exit code** — script exited with code 0 (success)

### Verdict

- [ ] **PASS** — all checks above succeeded, feature works as specified
- [ ] **FAIL** — one or more checks failed (details below)

**Failure details (if FAIL):**
_(Describe what failed, paste error output, explain what needs fixing)_

---

> **REMINDER:** Reading source code is NOT a substitute for execution.
> Your verification must be based on running the code, not reviewing it.
