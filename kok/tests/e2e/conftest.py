"""
E2E-specific fixtures for Tayfa Playwright tests.

Provides app_page — a page navigated to the running Tayfa app,
with initial load and project picker handled.
"""
import pytest
from playwright.sync_api import Page

from .helpers.selectors import ProjectPicker, Screens


@pytest.fixture()
def app_page(page: Page, base_url: str):
    """
    Navigate to the Tayfa app, wait for full load,
    and handle the project picker if shown.

    Uses pytest-playwright's built-in `page` fixture (function-scoped)
    and the session-scoped `base_url` from tests/conftest.py.
    """
    page.goto(base_url)
    page.wait_for_load_state("networkidle")

    # If project picker is visible, handle it
    picker = page.locator(ProjectPicker.ROOT)
    if picker.is_visible(timeout=2000):
        # In test mode with --project flag, picker should auto-close
        # But if it shows, click the first project or cancel
        first_project = page.locator(f"{ProjectPicker.LIST} .project-item").first
        if first_project.is_visible(timeout=1000):
            first_project.click()
            page.wait_for_load_state("networkidle")
        else:
            cancel = page.locator(ProjectPicker.BTN_CANCEL)
            if cancel.is_visible():
                cancel.click()

    yield page
