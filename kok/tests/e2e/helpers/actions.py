"""
Reusable Playwright page actions for Tayfa E2E tests.

All navigation and interaction helpers in one place.
"""
from playwright.sync_api import Page, expect

from .selectors import Nav, Header, Agents, Chat, TaskBoard, Screens, Modal


# ---------------------------------------------------------------------------
# Navigation
# ---------------------------------------------------------------------------

def navigate_to_task_board(page: Page):
    """Click 'Task board' in sidebar and wait for screen."""
    page.locator(Nav.BTN_TASK_BOARD).click()
    page.wait_for_selector(Screens.TASKS_BOARD, state="visible", timeout=5000)


def navigate_to_backlog(page: Page):
    """Click 'Backlog' in sidebar and wait for screen."""
    page.locator(Nav.BTN_BACKLOG).click()
    page.wait_for_selector(Screens.BACKLOG, state="visible", timeout=5000)


def navigate_to_settings(page: Page):
    """Click 'Settings' in sidebar and wait for screen."""
    page.locator(Nav.BTN_SETTINGS).click()
    page.wait_for_selector(Screens.SETTINGS, state="visible", timeout=5000)


def navigate_to_agent_load(page: Page):
    """Click 'Agent Load' in sidebar and wait for screen."""
    page.locator(Nav.BTN_AGENT_LOAD).click()
    page.wait_for_selector(Screens.AGENT_LOAD, state="visible", timeout=5000)


def navigate_to_tasks_md(page: Page):
    """Click 'Tasks (tasks.md)' in sidebar."""
    page.locator(Nav.BTN_TASKS_MD).click()
    page.wait_for_timeout(300)


# ---------------------------------------------------------------------------
# Agent actions
# ---------------------------------------------------------------------------

def select_agent(page: Page, agent_name: str):
    """Click an agent in the sidebar to open their chat."""
    agent_item = page.locator(
        f"{Agents.AGENT_ITEM}:has({Agents.AGENT_NAME}:text-is('{agent_name}'))"
    ).first
    agent_item.click()
    page.wait_for_selector(Screens.CHAT, state="visible", timeout=5000)


def ensure_agents(page: Page, timeout: int = 15000):
    """Click 'Ensure agents' button and wait for agent list to populate."""
    page.locator(Header.BTN_ENSURE_AGENTS).click()
    page.wait_for_selector(
        f"{Agents.AGENT_LIST} {Agents.AGENT_ITEM}",
        timeout=timeout,
    )


# ---------------------------------------------------------------------------
# Chat actions
# ---------------------------------------------------------------------------

def type_draft(page: Page, text: str):
    """Type text into the chat prompt input."""
    page.locator(Chat.PROMPT_INPUT).fill(text)


def get_draft(page: Page) -> str:
    """Get current value of the chat prompt input."""
    return page.locator(Chat.PROMPT_INPUT).input_value()


def send_prompt(page: Page, text: str):
    """Type a prompt and click Send."""
    page.locator(Chat.PROMPT_INPUT).fill(text)
    page.locator(Chat.BTN_SEND).click()


def wait_for_response(page: Page, timeout: int = 30000):
    """Wait for typing indicator to appear and then disappear (response complete)."""
    page.locator(Chat.TYPING_INDICATOR).wait_for(state="visible", timeout=5000)
    page.locator(Chat.TYPING_INDICATOR).wait_for(state="hidden", timeout=timeout)


# ---------------------------------------------------------------------------
# Task board actions
# ---------------------------------------------------------------------------

def create_task_via_modal(page: Page, title: str):
    """Open create-task modal, fill title, submit."""
    page.locator(TaskBoard.BTN_CREATE_TASK).click()
    page.wait_for_selector(Modal.OVERLAY, state="visible", timeout=5000)
    # Fill the title field in the modal
    page.locator(f"{Modal.BODY} input").first.fill(title)
    # Click primary submit button
    page.locator(
        f"{Modal.ACTIONS} button.primary, {Modal.ACTIONS} button:has-text('Create')"
    ).first.click()
    page.wait_for_selector(Modal.OVERLAY, state="hidden", timeout=5000)
