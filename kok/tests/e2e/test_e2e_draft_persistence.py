"""
E2E: Preserve chat input draft when navigating away.

Migrated from test_t036_draft_persistence.py to use shared Playwright infrastructure.
Tests that typing text in chat input, navigating to another screen,
and returning preserves the draft text.
"""
import pytest
from playwright.sync_api import Page

from .helpers.selectors import Chat
from .helpers.actions import (
    select_agent, ensure_agents, type_draft, get_draft,
    navigate_to_settings, navigate_to_task_board,
    navigate_to_backlog, navigate_to_tasks_md,
)


DRAFT_TEXT = "This is my unsent draft message for testing"


@pytest.mark.e2e
class TestDraftPersistence:
    """Chat draft text is preserved across navigation."""

    @pytest.fixture(autouse=True)
    def _setup_agents(self, app_page):
        """Ensure agents exist before each test."""
        ensure_agents(app_page)

    # AC1: Type text, go to Settings, return — text preserved
    def test_draft_preserved_after_settings(self, app_page):
        select_agent(app_page, "boss")
        type_draft(app_page, DRAFT_TEXT)
        navigate_to_settings(app_page)
        select_agent(app_page, "boss")
        assert get_draft(app_page) == DRAFT_TEXT, "Draft lost after Settings navigation"

    # AC2: Type text, go to Task Board, return — text preserved
    def test_draft_preserved_after_task_board(self, app_page):
        select_agent(app_page, "boss")
        type_draft(app_page, DRAFT_TEXT)
        navigate_to_task_board(app_page)
        select_agent(app_page, "boss")
        assert get_draft(app_page) == DRAFT_TEXT, "Draft lost after Task Board navigation"

    # AC3: Type text, go to Backlog, return — text preserved
    def test_draft_preserved_after_backlog(self, app_page):
        select_agent(app_page, "boss")
        type_draft(app_page, DRAFT_TEXT)
        navigate_to_backlog(app_page)
        select_agent(app_page, "boss")
        assert get_draft(app_page) == DRAFT_TEXT, "Draft lost after Backlog navigation"

    # AC4: Type text, go to Tasks (tasks.md), return — text preserved
    def test_draft_preserved_after_tasks_md(self, app_page):
        select_agent(app_page, "boss")
        type_draft(app_page, DRAFT_TEXT)
        navigate_to_tasks_md(app_page)
        select_agent(app_page, "boss")
        assert get_draft(app_page) == DRAFT_TEXT, "Draft lost after Tasks navigation"

    # AC5: Switching between agents preserves per-agent drafts
    def test_draft_per_agent_isolation(self, app_page):
        draft_boss = "Draft for boss agent"
        draft_dev = "Draft for developer agent"

        select_agent(app_page, "boss")
        type_draft(app_page, draft_boss)

        select_agent(app_page, "developer")
        type_draft(app_page, draft_dev)

        select_agent(app_page, "boss")
        assert get_draft(app_page) == draft_boss, "Boss draft lost after agent switch"

        select_agent(app_page, "developer")
        assert get_draft(app_page) == draft_dev, "Developer draft lost after agent switch"

    # AC6: Sending a message clears the draft
    def test_send_clears_draft(self, app_page):
        select_agent(app_page, "boss")
        type_draft(app_page, "Message to send")
        app_page.locator(Chat.BTN_SEND).click()
        app_page.wait_for_timeout(500)

        navigate_to_settings(app_page)
        select_agent(app_page, "boss")
        draft = get_draft(app_page)
        assert draft == "", f"Draft should be empty after send, got: '{draft}'"

    # AC7: Empty input does not create a draft entry
    def test_empty_input_no_draft(self, app_page):
        select_agent(app_page, "boss")
        type_draft(app_page, "")  # empty

        navigate_to_settings(app_page)

        # Check that agentDrafts doesn't have an entry for boss
        has_draft = app_page.evaluate("() => 'boss' in agentDrafts")
        assert not has_draft, "Empty input should not create a draft entry"
