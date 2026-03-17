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

    // Load CLI tools status
    loadCliToolsStatus();

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


// ── CLI Tools ───────────────────────────────────────────────────────────────

function _cliStatusBadge(installed, loggedIn) {
    if (!installed) return { text: 'Not installed', bg: 'rgba(248,113,113,0.12)', color: 'var(--danger)' };
    if (!loggedIn) return { text: 'Not logged in', bg: 'rgba(251,191,36,0.15)', color: 'var(--warning)' };
    return { text: 'Ready', bg: 'rgba(52,211,153,0.15)', color: 'var(--success)' };
}

function _applyBadge(el, badge) {
    el.textContent = badge.text;
    el.style.background = badge.bg;
    el.style.color = badge.color;
}

function _renderCliActions(container, tool, installed, loggedIn) {
    container.innerHTML = '';
    const btn = (text, cls, fn) => {
        const b = document.createElement('button');
        b.className = 'btn sm' + (cls ? ' ' + cls : '');
        b.textContent = text;
        b.style.fontSize = '11px';
        b.onclick = fn;
        return b;
    };

    if (!installed) {
        container.appendChild(btn('Install', 'primary', () => installCliTool(tool)));
    } else if (!loggedIn) {
        container.appendChild(btn('Login', 'primary', () => loginCliTool(tool)));
    } else {
        container.appendChild(btn('Logout', '', () => logoutCliTool(tool)));
    }
    if (installed) {
        container.appendChild(btn('Refresh', '', () => loadCliToolsStatus()));
    }
}

function _renderToolStatus(tool, info) {
    const prefix = tool === 'claude' ? 'claude' : 'cursor';
    const statusEl = document.getElementById(`${prefix}CliStatus`);
    const actionsEl = document.getElementById(`${prefix}CliActions`);
    const accountEl = document.getElementById(`${prefix}CliAccount`);
    const detailsEl = document.getElementById(`${prefix}CliDetails`);

    if (!statusEl || !actionsEl || !accountEl) return;

    const badge = _cliStatusBadge(info.installed, info.logged_in);
    _applyBadge(statusEl, badge);
    _renderCliActions(actionsEl, tool, info.installed, info.logged_in);

    if (info.logged_in && info.account) {
        accountEl.textContent = `Account: ${info.account}`;
    } else if (info.installed) {
        accountEl.textContent = info.logged_in ? '' : 'Login required to use agents';
    } else {
        accountEl.textContent = tool === 'claude'
            ? 'Install Claude CLI to use Claude models (Opus, Sonnet, Haiku)'
            : 'Install Cursor Agent CLI to use Cursor models';
    }

    if (!detailsEl) return;

    if (!info.installed) {
        detailsEl.style.display = 'none';
        return;
    }
    detailsEl.style.display = '';

    const versionEl = document.getElementById(`${prefix}CliVersion`);
    if (versionEl) {
        versionEl.textContent = info.version ? `Version: ${info.version}` : '';
    }

    const dashEl = document.getElementById(`${prefix}CliDashboard`);
    if (dashEl && info.dashboard_url) {
        dashEl.href = info.dashboard_url;
    }

    if (tool === 'cursor') {
        updateCursorHeaderDot(info.logged_in);
        if (info.models) {
            _cursorModelsCache = info.models;
            _populateCfgModelSelect();
        }
    }
}

let _cursorModelsCache = [];
let _cursorModelsLoaded = false;
let _ollamaModelsCache = [];
let _ollamaModelsLoaded = false;

function _populateCfgModelSelect() {
    const select = document.getElementById('cfgModel');
    if (!select) return;

    const currentValue = select.value;

    // Refresh Cursor optgroup
    const oldGroup = select.querySelector('optgroup[label="Cursor"]');
    if (oldGroup) oldGroup.remove();

    if (_cursorModelsCache.length > 0) {
        const group = document.createElement('optgroup');
        group.label = 'Cursor';
        for (const m of _cursorModelsCache) {
            const opt = document.createElement('option');
            opt.value = m.id;
            opt.textContent = m.name || m.id;
            group.appendChild(opt);
        }
        select.appendChild(group);
    }

    // Refresh Ollama optgroup — only show when models exist
    const ollamaGroup = select.querySelector('#cfgModelOllamaGroup');
    if (ollamaGroup) {
        ollamaGroup.innerHTML = '';
        if (_ollamaModelsCache.length > 0) {
            ollamaGroup.style.display = '';
            for (const m of _ollamaModelsCache) {
                const opt = document.createElement('option');
                opt.value = m.name;
                const sizeMB = Math.round((m.size || 0) / 1024 / 1024);
                const sizeLabel = sizeMB > 1024 ? `${(sizeMB / 1024).toFixed(1)} GB` : `${sizeMB} MB`;
                opt.textContent = `${m.name} (${sizeLabel})`;
                ollamaGroup.appendChild(opt);
            }
        } else {
            ollamaGroup.style.display = 'none';
        }
    }

    if (currentValue) {
        ensureModelOption(select, currentValue);
        select.value = currentValue;
    }
}

async function loadOllamaModels() {
    try {
        const data = await api('GET', '/api/cli-tools/ollama-status');
        if (data.installed && data.running && data.models && data.models.length > 0) {
            _ollamaModelsCache = data.models;
            _ollamaModelsLoaded = true;
        } else {
            _ollamaModelsCache = [];
        }
    } catch (e) {
        console.warn('Failed to load Ollama models:', e);
        _ollamaModelsCache = [];
    }
    _populateCfgModelSelect();
}

async function loadCursorModels(retries = 2) {
    for (let attempt = 0; attempt <= retries; attempt++) {
        try {
            const data = await api('GET', '/api/cli-tools/status');
            const cursor = data.cursor || {};
            updateCursorHeaderDot(!!cursor.logged_in);
            if (cursor.models && cursor.models.length > 0) {
                _cursorModelsCache = cursor.models;
                _cursorModelsLoaded = true;
                _populateCfgModelSelect();
                return;
            }
        } catch (e) {
            console.warn(`Failed to load Cursor models (attempt ${attempt + 1}/${retries + 1}):`, e);
        }
        if (attempt < retries) {
            await new Promise(r => setTimeout(r, 3000 * (attempt + 1)));
        }
    }
}

function ensureCursorModelsLoaded() {
    if (!_cursorModelsLoaded) loadCursorModels();
}

function showCursorModelsModal() {
    const models = _cursorModelsCache;
    if (!models || models.length === 0) {
        openModal('Cursor Models', '<p style="color:var(--text-dim);">No models available. Make sure Cursor Agent CLI is installed and logged in.</p>',
            '<button class="btn" onclick="closeModal()">Close</button>');
        return;
    }

    const rows = models.map(m => {
        const badges = [];
        if (m.current) badges.push('<span style="font-size:10px; padding:1px 6px; border-radius:8px; background:var(--accent); color:#fff; margin-left:6px;">current</span>');
        if (m.default) badges.push('<span style="font-size:10px; padding:1px 6px; border-radius:8px; background:rgba(52,211,153,0.2); color:var(--success); margin-left:6px;">default</span>');
        return `<div style="display:flex; justify-content:space-between; align-items:center; padding:6px 10px; border-radius:6px; background:${m.current ? 'rgba(79,110,247,0.08)' : 'transparent'};">
            <span style="font-size:13px; color:${m.current ? 'var(--accent)' : 'var(--text)'};">${m.name || m.id}${badges.join('')}</span>
            <span style="font-size:11px; color:var(--text-dim); font-family:var(--mono);">${m.id}</span>
        </div>`;
    }).join('');

    const body = `<div style="max-height:60vh; overflow-y:auto; display:flex; flex-direction:column; gap:2px;">${rows}</div>
        <p style="font-size:11px; color:var(--text-dim); margin-top:12px;">${models.length} models available</p>`;
    openModal('Cursor — Available Models', body,
        '<button class="btn" onclick="closeModal()">Close</button>');
}

let _lastCliToolsData = null;

async function loadCliToolsStatus() {
    const fallback = { installed: false, logged_in: false, account: '' };
    try {
        const data = await api('GET', '/api/cli-tools/status');
        _lastCliToolsData = data;
        _renderToolStatus('claude', data.claude || fallback);
        _renderToolStatus('cursor', data.cursor || fallback);
    } catch (e) {
        console.warn('Failed to load CLI tools status:', e);
        if (_lastCliToolsData) {
            _renderToolStatus('claude', _lastCliToolsData.claude || fallback);
            _renderToolStatus('cursor', _lastCliToolsData.cursor || fallback);
        } else {
            _renderToolStatus('claude', fallback);
            _renderToolStatus('cursor', fallback);
        }
    }
    loadOllamaStatus();
}

// ── Ollama (Local LLM) status and management ─────────────────────────────

function _ollamaStatusBadge(installed, running, modelCount) {
    if (!installed) return { text: 'Not installed', bg: 'rgba(248,113,113,0.12)', color: 'var(--danger)' };
    if (!running) return { text: 'Not running', bg: 'rgba(251,191,36,0.15)', color: 'var(--warning)' };
    if (modelCount === 0) return { text: 'No models', bg: 'rgba(251,191,36,0.15)', color: 'var(--warning)' };
    return { text: `${modelCount} model${modelCount > 1 ? 's' : ''} ready`, bg: 'rgba(52,211,153,0.15)', color: 'var(--success)' };
}

function _renderOllamaModelsList(models) {
    const container = document.getElementById('ollamaModelsList');
    if (!container) return;
    if (!models || models.length === 0) {
        container.innerHTML = '<div style="font-size:12px; color:var(--text-dim);">No models downloaded. Use the selector below to download one.</div>';
        return;
    }
    container.innerHTML = models.map(m => {
        const sizeMB = Math.round((m.size || 0) / 1024 / 1024);
        const sizeLabel = sizeMB > 1024 ? `${(sizeMB / 1024).toFixed(1)} GB` : `${sizeMB} MB`;
        return `<div style="display:flex; justify-content:space-between; align-items:center; padding:4px 8px; border-radius:4px; background:var(--bg-card);">
            <span style="font-size:12px; color:var(--text);">${m.name}</span>
            <div style="display:flex; align-items:center; gap:8px;">
                <span style="font-size:11px; color:var(--text-dim); font-family:var(--mono);">${sizeLabel}</span>
                <button class="btn sm" style="font-size:10px; padding:1px 6px; color:var(--danger);" onclick="deleteOllamaModel('${m.name}')">✕</button>
            </div>
        </div>`;
    }).join('');
}

async function loadOllamaStatus() {
    const statusEl = document.getElementById('ollamaCliStatus');
    const actionsEl = document.getElementById('ollamaCliActions');
    const accountEl = document.getElementById('ollamaCliAccount');
    const detailsEl = document.getElementById('ollamaCliDetails');
    if (!statusEl) return;

    try {
        const data = await api('GET', '/api/cli-tools/ollama-status');

        const badge = _ollamaStatusBadge(data.installed, data.running, (data.models || []).length);
        _applyBadge(statusEl, badge);

        actionsEl.innerHTML = '';
        const btn = (text, cls, fn) => {
            const b = document.createElement('button');
            b.className = 'btn sm' + (cls ? ' ' + cls : '');
            b.textContent = text;
            b.style.fontSize = '11px';
            b.onclick = fn;
            return b;
        };

        if (!data.installed) {
            actionsEl.appendChild(btn('Install', 'primary', installOllama));
            accountEl.textContent = 'Install Ollama to run AI models locally for free';
            detailsEl.style.display = 'none';
        } else if (!data.running) {
            actionsEl.appendChild(btn('Start', 'primary', startOllama));
            actionsEl.appendChild(btn('Refresh', '', loadOllamaStatus));
            accountEl.textContent = 'Ollama installed but not running';
            detailsEl.style.display = 'none';
        } else {
            actionsEl.appendChild(btn('Refresh', '', loadOllamaStatus));
            accountEl.textContent = data.version || 'Ollama running';
            detailsEl.style.display = '';
            _renderOllamaModelsList(data.models || []);

            // Update Ollama models cache for config panel
            _ollamaModelsCache = data.models || [];
            _ollamaModelsLoaded = true;
            _populateCfgModelSelect();
        }
    } catch (e) {
        console.warn('Failed to load Ollama status:', e);
        _applyBadge(statusEl, { text: 'Error', bg: 'rgba(248,113,113,0.12)', color: 'var(--danger)' });
        accountEl.textContent = 'Could not check Ollama status';
        detailsEl.style.display = 'none';
    }
}

async function installOllama() {
    const statusEl = document.getElementById('ollamaCliStatus');
    statusEl.textContent = 'Installing...';
    statusEl.style.color = 'var(--text-dim)';
    statusEl.style.background = 'rgba(79,110,247,0.1)';

    try {
        const data = await api('POST', '/api/cli-tools/ollama-install');
        if (data.status === 'installed' || data.status === 'already_installed') {
            addSystemMessage('Ollama installed successfully!');
        } else {
            alert(`Installation failed: ${data.error || 'Unknown error'}${data.hint ? '\n\n' + data.hint : ''}`);
        }
    } catch (e) {
        alert('Installation error: ' + e.message);
    }
    loadOllamaStatus();
}

async function startOllama() {
    const statusEl = document.getElementById('ollamaCliStatus');
    statusEl.textContent = 'Starting...';
    statusEl.style.color = 'var(--text-dim)';
    statusEl.style.background = 'rgba(79,110,247,0.1)';

    try {
        const data = await api('POST', '/api/cli-tools/ollama-start');
        if (data.status === 'started' || data.status === 'already_running') {
            addSystemMessage('Ollama is running');
        } else {
            alert('Failed to start Ollama: ' + (data.error || 'Unknown error'));
        }
    } catch (e) {
        alert('Start error: ' + e.message);
    }
    loadOllamaStatus();
}

async function pullOllamaModel() {
    const select = document.getElementById('ollamaPullModelSelect');
    const model = select.value;
    if (!model) return;

    const btn = document.getElementById('btnOllamaPull');
    const statusEl = document.getElementById('ollamaPullStatus');
    btn.disabled = true;
    btn.textContent = 'Downloading...';
    statusEl.textContent = `Pulling ${model}... (this may take several minutes)`;

    try {
        const data = await api('POST', '/api/cli-tools/ollama-pull', { model });
        if (data.status === 'pulled') {
            statusEl.textContent = `${model} downloaded!`;
            statusEl.style.color = 'var(--success)';
            addSystemMessage(`Ollama model ${model} downloaded`);
        } else {
            statusEl.textContent = `Error: ${data.error || 'Unknown'}`;
            statusEl.style.color = 'var(--danger)';
        }
    } catch (e) {
        statusEl.textContent = 'Error: ' + e.message;
        statusEl.style.color = 'var(--danger)';
    }
    btn.disabled = false;
    btn.textContent = 'Download';
    loadOllamaStatus();
}

async function deleteOllamaModel(model) {
    if (!confirm(`Delete model "${model}"? It will need to be re-downloaded to use again.`)) return;
    try {
        const data = await api('POST', '/api/cli-tools/ollama-delete', { model });
        if (data.status === 'deleted') {
            addSystemMessage(`Ollama model ${model} deleted`);
        } else {
            alert(`Delete failed: ${data.error || 'Unknown error'}`);
        }
    } catch (e) {
        alert('Delete error: ' + e.message);
    }
    loadOllamaStatus();
}

async function installCliTool(tool) {
    const statusEl = document.getElementById(tool === 'claude' ? 'claudeCliStatus' : 'cursorCliStatus');
    const prevText = statusEl.textContent;
    statusEl.textContent = 'Installing...';
    statusEl.style.color = 'var(--text-dim)';
    statusEl.style.background = 'rgba(79,110,247,0.1)';

    try {
        const data = await api('POST', '/api/cli-tools/install', { tool });
        if (data.status === 'installed' || data.status === 'already_installed') {
            addSystemMessage(`${tool === 'claude' ? 'Claude' : 'Cursor'} CLI installed!`);
        } else {
            const hint = data.hint || '';
            alert(`Installation failed: ${data.error || 'Unknown error'}${hint ? '\n\n' + hint : ''}`);
        }
    } catch (e) {
        alert(`Installation error: ${e.message}`);
    }
    loadCliToolsStatus();
}

async function loginCliTool(tool) {
    const statusEl = document.getElementById(tool === 'claude' ? 'claudeCliStatus' : 'cursorCliStatus');
    statusEl.textContent = 'Logging in...';
    statusEl.style.color = 'var(--text-dim)';
    statusEl.style.background = 'rgba(79,110,247,0.1)';

    try {
        const data = await api('POST', '/api/cli-tools/login', { tool });
        if (data.status === 'login_initiated') {
            addSystemMessage(`${tool === 'claude' ? 'Claude' : 'Cursor'} login initiated. Check your browser.`);
        } else {
            alert(`Login failed: ${data.output || 'Unknown error'}`);
        }
    } catch (e) {
        alert(`Login error: ${e.message}`);
    }
    // Give the login a few seconds to complete via browser, then refresh
    setTimeout(() => loadCliToolsStatus(), 5000);
}

async function logoutCliTool(tool) {
    if (!confirm(`Logout from ${tool === 'claude' ? 'Claude' : 'Cursor'} CLI?`)) return;
    try {
        const result = await api('POST', '/api/cli-tools/logout', { tool });
        if (result.status === 'logged_out') {
            addSystemMessage(`Logged out from ${tool === 'claude' ? 'Claude' : 'Cursor'} CLI`);
        } else {
            alert(`Logout failed: ${result.output || 'Unknown error'}`);
        }
    } catch (e) {
        alert(`Logout error: ${e.message}`);
    }
    loadCliToolsStatus();
}


// ── Updates ─────────────────────────────────────────────────────────────────

let _lastUpdateCheck = null;

async function checkForUpdates() {
    const statusEl = document.getElementById('updateStatus');
    const btnCheck = document.getElementById('btnCheckUpdate');
    const btnInstall = document.getElementById('btnInstallUpdate');
    const changelogEl = document.getElementById('updateChangelog');

    btnCheck.disabled = true;
    btnCheck.textContent = 'Checking...';
    statusEl.textContent = 'Checking for updates...';
    statusEl.style.color = 'var(--text-dim)';
    changelogEl.style.display = 'none';
    btnInstall.style.display = 'none';

    try {
        const data = await api('GET', '/api/updates/check');
        _lastUpdateCheck = data;

        if (data.has_update) {
            statusEl.textContent = `Update available! ${data.commits_behind} new commit${data.commits_behind > 1 ? 's' : ''} (${data.current_commit} → ${data.latest_commit})`;
            statusEl.style.color = 'var(--accent)';
            btnInstall.style.display = '';

            if (data.changelog && data.changelog.length > 0) {
                changelogEl.innerHTML = data.changelog.map(line => {
                    const hash = line.substring(0, 7);
                    const msg = line.substring(8);
                    return `<div style="margin-bottom:4px;"><span style="color:var(--accent);">${hash}</span> ${msg}</div>`;
                }).join('');
                changelogEl.style.display = 'block';
            }
        } else {
            statusEl.textContent = `Up to date (v${data.tayfa_version || '?'}, commit ${data.current_commit})`;
            statusEl.style.color = 'var(--success)';
        }
    } catch (e) {
        statusEl.textContent = 'Failed to check: ' + (e.message || e);
        statusEl.style.color = 'var(--danger)';
    } finally {
        btnCheck.disabled = false;
        btnCheck.textContent = 'Check for updates';
    }
}

async function installUpdate() {
    const statusEl = document.getElementById('updateStatus');
    const btnInstall = document.getElementById('btnInstallUpdate');
    const changelogEl = document.getElementById('updateChangelog');

    if (!confirm('Install the latest Tayfa update? The server will need to be restarted after installation.')) {
        return;
    }

    btnInstall.disabled = true;
    btnInstall.textContent = 'Installing...';
    statusEl.textContent = 'Installing update...';
    statusEl.style.color = 'var(--text-dim)';

    try {
        const data = await api('POST', '/api/updates/install');
        statusEl.textContent = `Updated to v${data.new_version || '?'}! Restart server to apply.`;
        statusEl.style.color = 'var(--success)';
        btnInstall.style.display = 'none';
        changelogEl.style.display = 'none';

        // Offer restart
        if (confirm('Update installed! Restart the server now?')) {
            try {
                await api('POST', '/api/shutdown');
            } catch { }
            statusEl.textContent = 'Server is restarting...';
        }
    } catch (e) {
        statusEl.textContent = 'Update failed: ' + (e.message || e);
        statusEl.style.color = 'var(--danger)';
        btnInstall.disabled = false;
        btnInstall.textContent = 'Install update';
    }
}
