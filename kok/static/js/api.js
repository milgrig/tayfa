// ── API Calls ──────────────────────────────────────────────────────────────

async function api(method, path, body = null) {
    const url = API_BASE ? (API_BASE + path) : path;
    const opts = { method, headers: { 'Content-Type': 'application/json' } };
    if (body) opts.body = JSON.stringify(body);
    const resp = await fetch(url, opts);
    if (!resp.ok) {
        const err = await resp.json().catch(() => ({ detail: resp.statusText }));
        let msg = err.detail || resp.statusText || 'API Error';
        throw new Error(typeof msg === 'string' ? msg : JSON.stringify(msg));
    }
    return resp.json();
}

function escapeHtml(s) {
    const div = document.createElement('div');
    div.textContent = s;
    return div.innerHTML;
}

function formatDate(dateStr) {
    if (!dateStr) return '—';
    const date = new Date(dateStr);
    const now = new Date();
    const diffMs = now - date;
    const diffMins = Math.floor(diffMs / 60000);
    const diffHours = Math.floor(diffMs / 3600000);
    const diffDays = Math.floor(diffMs / 86400000);

    if (diffMins < 1) return 'just now';
    if (diffMins < 60) return `${diffMins} min ago`;
    if (diffHours < 24) return `${diffHours} h ago`;
    if (diffDays < 7) return `${diffDays} d ago`;

    return date.toLocaleDateString('en-US', { day: '2-digit', month: '2-digit', year: 'numeric' });
}

// ── Screens ────────────────────────────────────────────────────────────────

function saveCurrentDraft() {
    const chatScreen = document.getElementById('chatScreen');
    if (!chatScreen || chatScreen.style.display === 'none') return;  // Only save when chat is visible
    const input = document.getElementById('promptInput');
    if (currentAgent && input) {
        const currentDraft = input.value.trim();
        if (currentDraft) {
            agentDrafts[currentAgent] = currentDraft;
        } else {
            delete agentDrafts[currentAgent];  // Remove empty drafts
        }
    }
}

function hideAllScreens() {
    ['welcomeScreen','tasksBoardScreen','tasksScreen','chatScreen','settingsScreen','backlogScreen'].forEach(id => {
        document.getElementById(id).style.display = 'none';
    });
    stopBoardAutoRefresh();
    stopRunningTasksTimer();
}

// ── Status ─────────────────────────────────────────────────────────────────

async function checkStatus() {
    try {
        const s = await api('GET', '/api/status');
        updateStatusUI(s);
        return s;
    } catch {
        updateStatusUI({ claude_api_running: false, api_running: false });
        return null;
    }
}

function updateStatusUI(s) {
    document.getElementById('wslDot').className = `status-dot ${s.claude_api_running ? 'on' : 'off'}`;
    document.getElementById('apiDot').className = `status-dot ${s.api_running ? 'on' : 'off'}`;
    document.getElementById('wslStatus').textContent = s.claude_api_running ? 'running' : 'off';
    document.getElementById('apiStatus').textContent = s.api_running ? 'running' : 'off';
    document.getElementById('btnStartServer').style.display = s.api_running ? 'none' : '';
    document.getElementById('btnStopServer').style.display = s.api_running ? '' : 'none';

    // Show/hide warning banner based on api_running
    const banner = document.getElementById('claude-api-warning-banner');
    if (banner) {
        if (!s.api_running) {
            banner.classList.add('visible');
            banner.style.display = '';
        } else {
            banner.classList.remove('visible');
            banner.style.display = 'none';
        }
    }

    // Update current project badge
    if (s.current_project) {
        updateCurrentProjectBadge(s.current_project);
        // Update document.title
        if (s.current_project.name) {
            document.title = s.current_project.name + ' — Tayfa';
        }
    }

    // Disable project switching when locked
    if (s.locked_project) {
        disableProjectSwitching();
    }
}

async function startServer() {
    const btn = document.getElementById('btnStartServer');
    btn.disabled = true; btn.textContent = 'Starting...';
    document.getElementById('wslDot').className = 'status-dot loading';
    try {
        await api('POST', '/api/start-server');
        await checkStatus(); await loadAgents();
    } catch (e) { addSystemMessage('Start error: ' + e.message, true); }
    finally { btn.disabled = false; btn.textContent = 'Start server'; }
}

async function stopServer() {
    try { await api('POST', '/api/stop-server'); await checkStatus(); }
    catch (e) { addSystemMessage('Error: ' + e.message, true); }
}

// ── Employees (data for task creation modal) ──────────────────────────

async function loadEmployees() {
    try {
        const data = await api('GET', '/api/employees');
        employees = data.employees || {};
    } catch {
        employees = {};
    }
}

// ── Modals ──────────────────────────────────────────────────────────────────

function openModal(title, bodyHtml, actionsHtml) {
    document.getElementById('modalTitle').textContent = title;
    document.getElementById('modalBody').innerHTML = bodyHtml;
    document.getElementById('modalActions').innerHTML = actionsHtml;
    document.getElementById('modalOverlay').classList.add('show');
}

function closeModal() {
    document.getElementById('modalOverlay').classList.remove('show');
}

document.getElementById('modalOverlay').addEventListener('click', function(e) {
    if (e.target === this) closeModal();
});
