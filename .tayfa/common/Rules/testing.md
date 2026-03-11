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
- ✅ Before marking task as `done`
- ✅ During local development

**Command:** `pytest tests/ -m "not e2e"` / `npm test` / project-specific

---

### Slow Tests (E2E — Playwright)

**Characteristic:** Require app launch, open a browser, may take longer.

| Type | Description | Tool |
|------|-------------|------|
| E2E (end-to-end) | Full user scenario in real browser | **Playwright** (standard) |
| Visual regression | Screenshot comparison | Playwright screenshots, Percy |

**Playwright is the standard E2E testing tool** for all Tayfa projects.

**When to run:**
- ⚠️ On request (not automatically on every commit)
- ⚠️ Before release / sprint finalization
- ⚠️ Night (scheduled CI)
- ✅ During development of UI features
- ❌ NOT on every commit (unless smoke tests only)

**Commands:**
```bash
# Run all E2E tests
pytest tests/e2e/ -m e2e -v

# Run only smoke (fast E2E subset)
pytest tests/e2e/ -m smoke -v

# Run with visible browser (debugging)
pytest tests/e2e/ -m e2e --headed

# Via run_tests.sh
bash ./run_tests.sh e2e
bash ./run_tests.sh smoke
bash ./run_tests.sh e2e --headed
```

---

## E2E Test Infrastructure (Playwright)

### Setup

```bash
pip install playwright pytest-playwright
python -m playwright install chromium
```

Or via run_tests.sh:
```bash
bash ./run_tests.sh --install
```

### Project Structure

```
tests/
├── conftest.py              # Server auto-start fixture, base_url
├── e2e/
│   ├── conftest.py          # app_page fixture (browser page with app loaded)
│   ├── helpers/
│   │   ├── selectors.py     # Centralized CSS selectors
│   │   └── actions.py       # Reusable page actions
│   ├── test_e2e_smoke.py    # Quick validation (app loads, navigation works)
│   ├── test_e2e_*.py        # Domain-specific E2E tests
│   └── ...
├── test_*.py                # Unit/API tests (unchanged)
```

### Key Concepts

1. **Auto-start server**: `conftest.py` starts the app on a free port before E2E tests and kills it after. No manual server start needed.

2. **Centralized selectors**: All CSS selectors in `helpers/selectors.py`. When HTML changes, update ONE file.

3. **Reusable actions**: Common operations in `helpers/actions.py`: `navigate_to_*()`, `select_agent()`, `ensure_agents()`, `send_prompt()`, etc.

4. **Markers**: All E2E tests must have `@pytest.mark.e2e`. Quick tests also get `@pytest.mark.smoke`.

5. **Naming convention**: Files — `test_e2e_<domain>.py`. Functions — `test_<domain>_<scenario>`.

### Writing a New E2E Test

```python
import pytest
from playwright.sync_api import expect
from .helpers.selectors import Screens, Nav
from .helpers.actions import navigate_to_task_board

@pytest.mark.e2e
def test_task_board_loads(app_page):
    """Task board screen is visible after navigation."""
    navigate_to_task_board(app_page)
    expect(app_page.locator(Screens.TASKS_BOARD)).to_be_visible()
```

### Best Practices

- ✅ Use `expect()` assertions with timeouts (not `assert` with manual waits)
- ✅ Use `page.wait_for_selector()` instead of `page.wait_for_timeout()`
- ✅ Create test data via API calls (fast), verify via UI (what we're testing)
- ✅ Keep smoke tests under 30 seconds total
- ❌ Don't hardcode URLs — use `base_url` fixture
- ❌ Don't use inline CSS selectors — use `helpers/selectors.py`

---

## When to Write Which Tests

### New Feature Development

| Stage | Test Type |
|-------|-----------|
| Development | Unit tests for logic |
| Integration | Integration tests |
| Before PR | All fast tests pass |
| Before release | E2E for critical path (Playwright) |

### Bug Fixing

1. Write test that reproduces bug (should fail)
2. Fix the bug
3. Test should pass

### UI Feature

1. Add/update selectors in `helpers/selectors.py`
2. Add helper actions if needed in `helpers/actions.py`
3. Write E2E test with `@pytest.mark.e2e`
4. Verify with `pytest tests/e2e/ -m e2e --headed`

---

## Test Suite Management

### Adding New Tests

New tests are **added** to mandatory suite automatically — just put in `tests/` (fast) or `tests/e2e/` (E2E).

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

When checking task:

- [ ] Fast tests pass (`pytest tests/ -m "not e2e"`)
- [ ] New code covered by tests (if applicable)
- [ ] Existing tests not broken
- [ ] If critical feature — E2E test exists (`pytest tests/e2e/ -m e2e`)

On sprint finalization:

- [ ] All fast tests pass
- [ ] Run E2E tests (`bash ./run_tests.sh e2e`)
- [ ] New E2E selectors are in `helpers/selectors.py` (not hardcoded)

---

## CI/CD Integration

```yaml
# GitHub Actions example
on: [push, pull_request]

jobs:
  fast-tests:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-python@v5
        with:
          python-version: '3.11'
      - run: pip install -r requirements.txt
      - run: pytest tests/ -m "not e2e" -v

  e2e-tests:
    runs-on: ubuntu-latest
    if: github.ref == 'refs/heads/main'
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-python@v5
        with:
          python-version: '3.11'
      - run: pip install -r requirements.txt
      - run: python -m playwright install chromium --with-deps
      - run: pytest tests/e2e/ -m e2e -v
        env:
          TAYFA_TEST_MODE: "1"
```

---

## Definition of Done (tests)

Task is complete if:

✅ Fast tests pass
✅ New code covered by unit tests
✅ Existing tests not broken
✅ For UI changes — E2E test added/updated (Playwright)
✅ New CSS selectors added to `helpers/selectors.py`
