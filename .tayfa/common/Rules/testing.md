# Testing Rules

## Mandatory Autotests

Autotests are **mandatory part of Definition of Done**. Task is not complete if:
- Code not covered by autotests (where applicable)
- Existing tests fail

---

## Test Classification

### Fast Tests

**Characteristic:** Don't require app launch, no UI interaction, don't disturb user.

| Type | Description | Examples |
|------|-------------|----------|
| Unit tests | Testing individual functions/classes | pytest, jest, vitest |
| Integration (no UI) | Testing module interaction | API tests, DB tests |
| Snapshot tests | Comparing output with reference | React snapshot testing |

**When to run:**
- ✅ On every commit (CI/CD)
- ✅ Before moving task to `in_review`
- ✅ During local development

**Command:** `npm test` / `pytest` / project-specific

---

### Slow Tests

**Characteristic:** Require app launch, capture mouse/keyboard, **disturb user**.

| Type | Description | Examples |
|------|-------------|----------|
| E2E (end-to-end) | Full user scenario | Playwright, Cypress, Selenium |
| UI autotests | Automation via interface | pyautogui, robot framework |
| Visual regression | Screenshot comparison | Percy, Chromatic |

**When to run:**
- ⚠️ On request (not automatically)
- ⚠️ Before release / sprint finalization
- ⚠️ Night (scheduled CI)
- ❌ NOT on every commit

**Important:** Slow tests **capture control** — warn the user!

```
⚠️ Warning: Running E2E tests.
Tests will take ~X minutes and control mouse/keyboard.
Do not touch the computer until completion.
```

---

## Project Test Structure

```
tests/
├── fast/                 # Fast tests
│   ├── unit/            # Unit tests
│   └── integration/     # Integration (no UI)
└── slow/                 # Slow tests
    ├── e2e/             # End-to-end
    └── visual/          # Visual regression
```

Or via markers/tags in test framework:
- `@fast` / `@slow`
- `pytest -m "not slow"` — fast only
- `pytest -m slow` — slow only

---

## When to Write Which Tests

### New Feature Development

| Stage | Test Type |
|-------|-----------|
| Development | Unit tests for logic |
| Integration | Integration tests |
| Before PR | All fast tests pass |
| Before release | E2E for critical path |

### Bug Fixing

1. Write test that reproduces bug (should fail)
2. Fix the bug
3. Test should pass

---

## Test Suite Management

### Adding New Tests

New tests are **added** to mandatory suite automatically — just put in `tests/fast/`.

### Changing/Removing Old Tests

Tests **can be removed or changed** if:
- Functionality removed from product
- Test was for deprecated behavior
- Test was incorrect (false positive/negative)

**Procedure:**
1. Create task "Test revision" with reasons
2. Get confirmation from qa_tester
3. Remove/change tests
4. Document in PR/commit

### Flaky Tests (unstable)

Tests that pass/fail randomly:
1. Mark `@flaky` or `@skip`
2. Create task to fix
3. Either fix or remove

**Cannot:** ignore flaky tests without documentation.

---

## Checklist for qa_tester

When checking task (`in_review`):

- [ ] Fast tests pass (`npm test` / `pytest`)
- [ ] New code covered by tests (if applicable)
- [ ] Existing tests not broken
- [ ] If critical feature — E2E test exists

On sprint finalization:

- [ ] All fast tests pass
- [ ] Run slow tests (E2E)
- [ ] Visual regression (if exists)

---

## CI/CD Integration

```yaml
# GitHub Actions example
on: [push, pull_request]

jobs:
  fast-tests:
    runs-on: ubuntu-latest
    steps:
      - run: npm test  # Fast tests on every push

  slow-tests:
    runs-on: ubuntu-latest
    if: github.ref == 'refs/heads/main'  # Only on merge to main
    steps:
      - run: npm run test:e2e  # Slow tests
```

---

## Definition of Done (tests)

Task is complete if:

✅ Fast tests pass
✅ New code covered by unit tests
✅ Existing tests not broken
✅ For critical changes — E2E test added/updated
