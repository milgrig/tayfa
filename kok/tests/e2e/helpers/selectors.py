"""
Centralized CSS selectors for Tayfa E2E tests.
Derived from kok/static/index.html.

When HTML changes, update selectors HERE — all tests use these constants.
"""


class Nav:
    """Sidebar navigation."""
    SIDEBAR = ".sidebar"
    BTN_TASK_BOARD = ".sidebar button:has-text('Task board')"
    BTN_BACKLOG = ".sidebar button:has-text('Backlog')"
    BTN_AGENT_LOAD = ".sidebar button:has-text('Agent Load')"
    BTN_SETTINGS = ".sidebar button:has-text('Settings')"
    BTN_TASKS_MD = ".sidebar button:has-text('Tasks (tasks.md)')"


class Header:
    """Top header bar."""
    BTN_ENSURE_AGENTS = "button:has-text('Ensure agents')"
    BTN_REFRESH = "button:has-text('Refresh')"
    BTN_START_SERVER = "#btnStartServer"
    BTN_STOP_SERVER = "#btnStopServer"
    PROJECT_BADGE = "#currentProjectBadge"
    PROJECT_NAME = "#currentProjectName"
    SETTINGS_GEAR = ".settings-btn"
    SETTINGS_DROPDOWN = "#settingsDropdown"
    THEME_SELECT = "#themeSelect"
    WSL_STATUS = "#wslStatus"
    API_STATUS = "#apiStatus"


class Screens:
    """Main content screens (shown/hidden by navigation)."""
    WELCOME = "#welcomeScreen"
    TASKS_BOARD = "#tasksBoardScreen"
    TASKS_OLD = "#tasksScreen"
    CHAT = "#chatScreen"
    BACKLOG = "#backlogScreen"
    AGENT_LOAD = "#agentLoadScreen"
    SETTINGS = "#settingsScreen"


class Agents:
    """Agent sidebar and list."""
    AGENT_LIST = "#agentList"
    AGENT_ITEM = ".agent-item"
    AGENT_NAME = ".agent-name"


class Chat:
    """Chat/prompt screen."""
    AGENT_NAME_HEADER = "#chatAgentName"
    CHAT_AREA = "#chatArea"
    PROMPT_INPUT = "#promptInput"
    BTN_SEND = "#btnSend"
    TYPING_INDICATOR = "#typingIndicator"


class TaskBoard:
    """Task board / kanban view."""
    WRAP = "#tasksBoardWrap"
    BTN_CREATE_SPRINT = "button:has-text('+ Sprint')"
    BTN_CREATE_TASK = "button:has-text('+ Task')"
    BTN_REPORT_BUG = "button:has-text('Bug')"
    BTN_CREATE_BACKLOG = "button:has-text('+ Backlog')"
    MAX_CONCURRENT_INPUT = "#maxConcurrentInput"


class Backlog:
    """Backlog screen."""
    CONTAINER = "#backlogContainer"
    FILTER_PRIORITY = "#backlogFilterPriority"
    FILTER_NEXT_SPRINT = "#backlogFilterNextSprint"


class Settings:
    """Settings screen."""
    VERSION = "#settingsTayfaVersion"
    PORT = "#settingsPort"
    AUTO_OPEN = "#settingsAutoOpen"
    AUTO_LAUNCH = "#settingsAutoLaunch"


class Modal:
    """Universal modal overlay."""
    OVERLAY = "#modalOverlay"
    CONTENT = "#modalContent"
    TITLE = "#modalTitle"
    BODY = "#modalBody"
    ACTIONS = "#modalActions"


class ProjectPicker:
    """Initial project selection screen."""
    ROOT = "#projectPicker"
    LIST = "#projectList"
    BTN_OPEN_FOLDER = "button:has-text('Open folder')"
    BTN_ENTER_PATH = "button:has-text('Enter path')"
    BTN_CANCEL = "#projectPickerCancel"
