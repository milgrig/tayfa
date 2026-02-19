// ── Settings Screen ────────────────────────────────────────────────────────

function updateSettingsScreen(settings) {
    if (!settings) return;

    // Theme — radio buttons
    const themeRadios = document.querySelectorAll('input[name="settingsTheme"]');
    themeRadios.forEach(radio => {
        radio.checked = radio.value === settings.theme;
        // Highlight selected option
        const label = radio.closest('.theme-option') || radio.parentElement;
        if (label) {
            label.style.borderColor = radio.checked ? 'var(--accent)' : 'var(--border)';
            label.style.background = radio.checked ? 'rgba(79,110,247,0.1)' : 'var(--bg-input)';
        }
    });

    // Port
    const portEl = document.getElementById('settingsPort');
    if (portEl) portEl.textContent = settings.port || '8008';

    // Language
    const langEl = document.getElementById('settingsLanguage');
    if (langEl) langEl.textContent = settings.language === 'ru' ? 'Russian' : 'English';

    // Auto-open browser
    const autoOpenEl = document.getElementById('settingsAutoOpen');
    if (autoOpenEl) autoOpenEl.checked = settings.autoOpenBrowser !== false;

    // Auto-launch sprints
    const autoLaunchEl = document.getElementById('settingsAutoLaunch');
    if (autoLaunchEl) autoLaunchEl.checked = settings.autoLaunchSprints === true;

    // Max tasks
    const maxTasksEl = document.getElementById('settingsMaxTasks');
    if (maxTasksEl) maxTasksEl.value = settings.maxConcurrentTasks || 5;

    // Git settings
    const gitSettings = settings.git || {};
    const gitUserNameEl = document.getElementById('settingsGitUserName');
    if (gitUserNameEl) gitUserNameEl.value = gitSettings.userName || '';
    const gitUserEmailEl = document.getElementById('settingsGitUserEmail');
    if (gitUserEmailEl) gitUserEmailEl.value = gitSettings.userEmail || '';
    const gitDefaultBranchEl = document.getElementById('settingsGitDefaultBranch');
    if (gitDefaultBranchEl) gitDefaultBranchEl.value = gitSettings.defaultBranch || 'main';
    const gitHubOwnerEl = document.getElementById('settingsGitHubOwner');
    if (gitHubOwnerEl) gitHubOwnerEl.value = gitSettings.githubOwner || '';
    const gitHubTokenEl = document.getElementById('settingsGitHubToken');
    if (gitHubTokenEl) gitHubTokenEl.value = gitSettings.githubToken || '';
    // Load per-project repoName
    loadProjectRepoName();
    updateComputedUrlDisplay();
}

async function showSettingsScreen() {
    saveCurrentDraft();
    hideAllScreens();
    document.getElementById('settingsScreen').style.display = 'flex';

    // Load and display current settings
    const settings = await loadSettings();
    updateSettingsScreen(settings);

    // Load Telegram settings
    loadTelegramSettings();

    // Add handlers for theme radio buttons
    document.querySelectorAll('input[name="settingsTheme"]').forEach(radio => {
        radio.onchange = async function() {
            await changeTheme(this.value);
            updateSettingsScreen(await api('GET', '/api/settings'));
        };
    });
}

async function saveSettingAutoOpen(value) {
    try {
        await api('POST', '/api/settings', { autoOpenBrowser: value });
    } catch (error) {
        alert('Error saving: ' + error.message);
        document.getElementById('settingsAutoOpen').checked = !value;
    }
}

async function saveSettingAutoLaunch(value) {
    try {
        await api('POST', '/api/settings', { autoLaunchSprints: value });
        if (value) {
            startAutoLaunchLoop();
        } else {
            stopAutoLaunchLoop();
        }
    } catch (error) {
        alert('Error saving: ' + error.message);
        document.getElementById('settingsAutoLaunch').checked = !value;
    }
}

async function saveSettingGit() {
    const userName = document.getElementById('settingsGitUserName').value.trim();
    const userEmail = document.getElementById('settingsGitUserEmail').value.trim();
    const defaultBranch = document.getElementById('settingsGitDefaultBranch').value.trim() || 'main';
    const githubOwner = document.getElementById('settingsGitHubOwner').value.trim();
    const githubToken = document.getElementById('settingsGitHubToken').value.trim();
    try {
        await api('POST', '/api/settings', {
            git: { userName, userEmail, defaultBranch, githubOwner, githubToken }
        });
        updateComputedUrlDisplay();
    } catch (error) {
        alert('Error saving Git settings: ' + error.message);
    }
}

async function saveSettingRepoName() {
    const repoName = document.getElementById('settingsGitRepoName').value.trim();
    try {
        await api('POST', '/api/projects/repo-name', { repoName });
        updateComputedUrlDisplay();
    } catch (error) {
        alert('Error saving repo name: ' + error.message);
    }
}

async function loadProjectRepoName() {
    try {
        const data = await api('GET', '/api/current-project');
        const el = document.getElementById('settingsGitRepoName');
        if (el && data && data.project) {
            el.value = data.project.repoName || '';
        }
    } catch { }
}

function updateComputedUrlDisplay() {
    const owner = (document.getElementById('settingsGitHubOwner')?.value || '').trim();
    const repo = (document.getElementById('settingsGitRepoName')?.value || '').trim();
    const el = document.getElementById('settingsComputedUrl');
    if (el) {
        if (owner && repo) {
            el.textContent = `Remote: https://github.com/${owner}/${repo}.git`;
        } else {
            el.textContent = owner ? 'Set Repo Name to configure remote' : 'Set GitHub Owner to configure remote';
        }
    }
}

// ── Telegram ───────────────────────────────────────────────────────────────

async function loadTelegramSettings() {
    try {
        const data = await api('GET', '/api/telegram-settings');
        const tokenEl = document.getElementById('settingsTelegramToken');
        const chatIdEl = document.getElementById('settingsTelegramChatId');
        const statusEl = document.getElementById('telegramStatus');

        if (chatIdEl) chatIdEl.value = data.chatId || '';
        // Don't overwrite token field with masked value if user is editing
        if (tokenEl && !tokenEl.value) {
            tokenEl.placeholder = data.botToken || '123456:ABC-DEF1234ghIkl-zyx57W2v...';
        }

        if (statusEl) {
            if (data.running) {
                statusEl.textContent = '● Connected';
                statusEl.style.background = 'rgba(52,211,153,0.15)';
                statusEl.style.color = 'var(--success)';
            } else if (data.configured) {
                statusEl.textContent = '● Configured';
                statusEl.style.background = 'rgba(251,191,36,0.15)';
                statusEl.style.color = 'var(--warning)';
            } else {
                statusEl.textContent = '○ Not configured';
                statusEl.style.background = 'rgba(248,113,113,0.1)';
                statusEl.style.color = 'var(--text-dim)';
            }
        }
    } catch (e) {
        console.warn('Failed to load Telegram settings:', e);
    }
}

async function saveTelegramSettings() {
    const token = document.getElementById('settingsTelegramToken').value.trim();
    const chatId = document.getElementById('settingsTelegramChatId').value.trim();

    if (!token || !chatId) {
        alert('Both Bot Token and Chat ID are required');
        return;
    }

    try {
        const result = await api('POST', '/api/telegram-settings', {
            botToken: token,
            chatId: chatId,
        });
        addSystemMessage('Telegram bot connected!');
        loadTelegramSettings();
    } catch (e) {
        alert('Error connecting Telegram: ' + e.message);
    }
}

async function testTelegram() {
    try {
        await api('POST', '/api/telegram-test');
        addSystemMessage('Telegram test message sent!');
    } catch (e) {
        alert('Error: ' + e.message);
    }
}

async function disconnectTelegram() {
    if (!confirm('Disconnect Telegram bot?')) return;
    try {
        await api('POST', '/api/telegram-disconnect');
        document.getElementById('settingsTelegramToken').value = '';
        document.getElementById('settingsTelegramChatId').value = '';
        addSystemMessage('Telegram bot disconnected');
        loadTelegramSettings();
    } catch (e) {
        alert('Error: ' + e.message);
    }
}


async function saveSettingMaxTasks(value) {
    const numValue = parseInt(value);
    if (isNaN(numValue) || numValue < 1 || numValue > 50) {
        alert('Value must be between 1 and 50');
        document.getElementById('settingsMaxTasks').value = 5;
        return;
    }
    try {
        await api('POST', '/api/settings', { maxConcurrentTasks: numValue });
        // Sync with input on task board
        const boardInput = document.getElementById('maxConcurrentInput');
        if (boardInput) boardInput.value = numValue;
    } catch (error) {
        alert('Error saving: ' + error.message);
    }
}
