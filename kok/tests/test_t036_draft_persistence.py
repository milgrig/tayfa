"""
T036: E2E test - Preserve chat input draft when navigating away.

Tests that typing text in chat input, navigating to another screen,
and returning preserves the draft text.
"""
import pytest
from playwright.sync_api import sync_playwright, expect

BASE_URL = "http://127.0.0.1:8008"
DRAFT_TEXT = "This is my unsent draft message for testing"


@pytest.fixture(scope="module")
def browser_page():
    """Launch browser, open app, yield page, cleanup."""
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        context = browser.new_context()
        page = context.new_page()
        # Force fresh load (no cache)
        page.goto(BASE_URL + "?_nocache=" + str(__import__('time').time()))
        page.wait_for_load_state("networkidle")
        yield page
        browser.close()


def _select_agent(page, agent_name="boss"):
    """Click on an agent in the sidebar to open their chat."""
    agent_item = page.locator(f".agent-item:has(.agent-name:text-is('{agent_name}'))").first
    agent_item.click()
    page.wait_for_timeout(300)


def _type_draft(page, text):
    """Type text into the chat input."""
    input_el = page.locator("#promptInput")
    input_el.fill(text)


def _get_draft(page):
    """Get current value of the chat input."""
    return page.locator("#promptInput").input_value()


def _navigate_to_settings(page):
    """Click Settings button."""
    page.locator("button:has-text('Settings')").click()
    page.wait_for_timeout(300)


def _navigate_to_task_board(page):
    """Click Task board button in sidebar."""
    page.locator(".sidebar button:has-text('Task board')").first.click()
    page.wait_for_timeout(300)


def _navigate_to_backlog(page):
    """Click Backlog button in sidebar."""
    page.locator(".sidebar button:has-text('Backlog')").first.click()
    page.wait_for_timeout(300)


def _navigate_to_tasks_md(page):
    """Click Tasks (tasks.md) button."""
    page.locator("button:has-text('Tasks (tasks.md)')").click()
    page.wait_for_timeout(300)


# AC1: Type text, go to Settings, return - text preserved
def test_ac1_draft_preserved_after_settings(browser_page):
    page = browser_page
    _select_agent(page, "boss")
    _type_draft(page, DRAFT_TEXT)
    _navigate_to_settings(page)
    _select_agent(page, "boss")
    assert _get_draft(page) == DRAFT_TEXT, "Draft lost after Settings navigation"


# AC2: Type text, go to Task Board, return - text preserved
def test_ac2_draft_preserved_after_task_board(browser_page):
    page = browser_page
    _select_agent(page, "boss")
    _type_draft(page, DRAFT_TEXT)
    _navigate_to_task_board(page)
    _select_agent(page, "boss")
    assert _get_draft(page) == DRAFT_TEXT, "Draft lost after Task Board navigation"


# AC3: Type text, go to Backlog, return - text preserved
def test_ac3_draft_preserved_after_backlog(browser_page):
    page = browser_page
    _select_agent(page, "boss")
    _type_draft(page, DRAFT_TEXT)
    _navigate_to_backlog(page)
    _select_agent(page, "boss")
    assert _get_draft(page) == DRAFT_TEXT, "Draft lost after Backlog navigation"


# AC4: Type text, go to Tasks (tasks.md), return - text preserved
def test_ac4_draft_preserved_after_tasks_md(browser_page):
    page = browser_page
    _select_agent(page, "boss")
    _type_draft(page, DRAFT_TEXT)
    _navigate_to_tasks_md(page)
    _select_agent(page, "boss")
    assert _get_draft(page) == DRAFT_TEXT, "Draft lost after Tasks navigation"


# AC5: Switching between agents still works correctly
def test_ac5_draft_preserved_switching_agents(browser_page):
    page = browser_page
    draft_boss = "Draft for boss agent"
    draft_dev = "Draft for developer agent"

    # Type draft for boss
    _select_agent(page, "boss")
    _type_draft(page, draft_boss)

    # Switch to developer, type draft there
    _select_agent(page, "developer")
    _type_draft(page, draft_dev)

    # Switch back to boss - draft should be preserved
    _select_agent(page, "boss")
    assert _get_draft(page) == draft_boss, "Boss draft lost after agent switch"

    # Switch to developer - draft should be preserved
    _select_agent(page, "developer")
    assert _get_draft(page) == draft_dev, "Developer draft lost after agent switch"


# AC6: Sending a message still clears the draft
def test_ac6_sending_clears_draft(browser_page):
    page = browser_page
    _select_agent(page, "boss")
    _type_draft(page, "Message to send")

    # Press Enter to send (sendPrompt is triggered)
    page.locator("#btnSend").click()
    page.wait_for_timeout(500)

    # Navigate away and return - draft should be empty
    _navigate_to_settings(page)
    _select_agent(page, "boss")
    draft = _get_draft(page)
    assert draft == "", f"Draft should be empty after send, got: '{draft}'"


# AC7: Empty input does not create a draft entry
def test_ac7_empty_input_no_draft(browser_page):
    page = browser_page
    _select_agent(page, "boss")
    _type_draft(page, "")  # empty

    # Navigate away
    _navigate_to_settings(page)

    # Check that agentDrafts doesn't have an entry for boss
    has_draft = page.evaluate("() => 'boss' in agentDrafts")
    assert not has_draft, "Empty input should not create a draft entry"
