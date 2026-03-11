"""
E2E Smoke Tests — quick validation that Tayfa app loads and basic UI works.

Run: pytest tests/e2e/test_e2e_smoke.py -m smoke -v
"""
import pytest
import httpx
from playwright.sync_api import expect

from .helpers.selectors import Nav, Header, Screens


@pytest.mark.e2e
@pytest.mark.smoke
class TestSmoke:
    """Quick smoke tests to validate E2E infrastructure works."""

    def test_app_loads(self, app_page):
        """The Tayfa app loads and shows the main container."""
        expect(app_page.locator("#mainApp")).to_be_visible()

    def test_health_endpoint(self, tayfa_server):
        """/api/health returns HTTP 200."""
        resp = httpx.get(f"{tayfa_server}/api/health", timeout=5.0)
        assert resp.status_code == 200

    def test_status_endpoint(self, tayfa_server):
        """/api/status returns valid JSON with expected fields."""
        resp = httpx.get(f"{tayfa_server}/api/status", timeout=5.0)
        assert resp.status_code == 200
        data = resp.json()
        assert "has_project" in data

    def test_no_js_errors_on_load(self, app_page):
        """No JavaScript errors on initial page load."""
        errors = []
        app_page.on("pageerror", lambda err: errors.append(str(err)))
        app_page.reload()
        app_page.wait_for_load_state("networkidle")
        assert len(errors) == 0, f"JS errors on load: {errors}"

    def test_sidebar_visible(self, app_page):
        """The sidebar navigation is visible."""
        expect(app_page.locator(Nav.SIDEBAR)).to_be_visible()

    def test_header_visible(self, app_page):
        """The header with project badge is visible."""
        expect(app_page.locator(Header.PROJECT_BADGE)).to_be_visible()


@pytest.mark.e2e
@pytest.mark.smoke
class TestNavigation:
    """Basic tab navigation works without errors."""

    def test_navigate_to_task_board(self, app_page):
        """Clicking 'Task board' shows the task board screen."""
        app_page.locator(Nav.BTN_TASK_BOARD).click()
        expect(app_page.locator(Screens.TASKS_BOARD)).to_be_visible()

    def test_navigate_to_backlog(self, app_page):
        """Clicking 'Backlog' shows the backlog screen."""
        app_page.locator(Nav.BTN_BACKLOG).click()
        expect(app_page.locator(Screens.BACKLOG)).to_be_visible()

    def test_navigate_to_settings(self, app_page):
        """Clicking 'Settings' shows the settings screen."""
        app_page.locator(Nav.BTN_SETTINGS).click()
        expect(app_page.locator(Screens.SETTINGS)).to_be_visible()

    def test_navigate_all_screens_no_crash(self, app_page):
        """Navigate through all screens without JS errors."""
        errors = []
        app_page.on("pageerror", lambda err: errors.append(str(err)))

        app_page.locator(Nav.BTN_TASK_BOARD).click()
        app_page.wait_for_timeout(300)
        app_page.locator(Nav.BTN_BACKLOG).click()
        app_page.wait_for_timeout(300)
        app_page.locator(Nav.BTN_SETTINGS).click()
        app_page.wait_for_timeout(300)
        app_page.locator(Nav.BTN_TASK_BOARD).click()
        app_page.wait_for_timeout(300)

        assert len(errors) == 0, f"JS errors during navigation: {errors}"
