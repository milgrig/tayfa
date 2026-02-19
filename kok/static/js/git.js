// ── Git Functions ───────────────────────────────────────────────────────────

let gitStatus = null;
let gitHistoryExpanded = false;
let gitAutoRefreshTimer = null;

async function loadGitStatus() {
    const container = document.getElementById('gitStatusContainer');

    // Update indicator in header
    updateGitHeaderIndicator('loading');

    try {
        const data = await api('GET', '/api/git/status');
        console.log('git status response:', data);
        gitStatus = data;

        // Check initialized: false (Git not initialized)
        if (data && data.initialized === false) {
            updateGitHeaderIndicator('not_initialized', data);
            if (container) renderGitUnavailable(data.message || 'Git not initialized');
            return;
        }

        // Git initialized — show status
        if (container) renderGitSection(data);
        updateGitHeaderIndicator('success', data);
    } catch (e) {
        console.warn('Git unavailable:', e.message);
        if (container) renderGitUnavailable(e.message);
        updateGitHeaderIndicator('error', null, e.message);
    }
}

// Updates git status indicator in header
function updateGitHeaderIndicator(state, data = null, errorMsg = null) {
    const branchEl = document.getElementById('gitBranchHeader');
    const dotEl = document.getElementById('gitDotHeader');
    const indicator = document.getElementById('gitStatusIndicator');
    const initBtn = document.getElementById('gitInitBtnHeader');

    if (!branchEl || !dotEl || !indicator) return;

    // Hide Init button by default
    if (initBtn) initBtn.style.display = 'none';

    switch(state) {
        case 'loading':
            branchEl.textContent = '...';
            dotEl.className = 'git-dot loading';
            indicator.title = 'Loading git status...';
            break;

        case 'not_initialized':
            branchEl.textContent = 'No Git';
            dotEl.className = 'git-dot warning';
            indicator.title = 'Git not initialized. Click Init to initialize.';
            if (initBtn) initBtn.style.display = 'inline-block';
            break;

        case 'success':
            if (data) {
                const branchName = data.branch || '(no commits)';
                branchEl.textContent = branchName;
                const stagedCount = (data.staged || []).length;
                const unstagedCount = (data.unstaged || []).length;
                const untrackedCount = (data.untracked || []).length;
                const hasChanges = stagedCount + unstagedCount + untrackedCount > 0;

                dotEl.className = 'git-dot ' + (hasChanges ? 'dirty' : 'clean');

                // Build tooltip
                let tooltip = `Branch: ${branchName}\n`;
                if (hasChanges) {
                    if (stagedCount > 0) tooltip += `Staged: ${stagedCount} file(s)\n`;
                    if (unstagedCount > 0) tooltip += `Modified: ${unstagedCount} file(s)\n`;
                    if (untrackedCount > 0) tooltip += `Untracked: ${untrackedCount} file(s)`;
                } else {
                    tooltip += 'No local changes';
                }
                indicator.title = tooltip.trim();
            } else {
                // Fallback: no data
                updateGitHeaderIndicator('not_initialized');
                return;
            }
            break;

        case 'error':
            branchEl.textContent = '—';
            dotEl.className = 'git-dot error';
            indicator.title = errorMsg || 'Error getting git status';
            break;
    }
}

// Show toast notification for git operations
function showGitToast(message, type = 'error') {
    // Remove previous toast if exists
    const existing = document.querySelector('.git-toast');
    if (existing) existing.remove();

    const toast = document.createElement('div');
    toast.className = `git-toast ${type}`;
    toast.textContent = message;
    document.body.appendChild(toast);

    // Auto-remove after 5 seconds
    setTimeout(() => toast.remove(), 5000);
}

function renderGitUnavailable(message = 'Git unavailable') {
    const container = document.getElementById('gitStatusContainer');
    if (!container) return;

    // Check if this is an error "Git not initialized"
    const lowerMsg = message.toLowerCase();
    const isNotInitialized = lowerMsg.includes('initialized') ||
                              lowerMsg.includes('not a git') ||
                              lowerMsg.includes('not initialized') ||
                              lowerMsg.includes('"initialized"') ||
                              lowerMsg.includes('not git') ||
                              lowerMsg.includes('repository') ||
                              lowerMsg.includes('false');

    if (isNotInitialized) {
        container.innerHTML = `
            <div class="git-unavailable">
                <div class="icon">📁</div>
                <p>Git repository not initialized</p>
                <button class="btn primary" onclick="initGitRepo()" style="margin-top: 10px;">
                    🔧 Initialize Git
                </button>
            </div>
        `;
    } else {
        container.innerHTML = `
            <div class="git-unavailable">
                <div class="icon">⚠️</div>
                <p>${escapeHtml(message)}</p>
            </div>
        `;
    }
}

async function initGitRepo() {
    const container = document.getElementById('gitStatusContainer');
    if (container) {
        container.innerHTML = `
            <div class="git-unavailable">
                <div class="icon">⏳</div>
                <p>Initializing repository...</p>
            </div>
        `;
    }

    try {
        const result = await api('POST', '/api/git/init', { create_gitignore: true });
        console.log('git init result:', result);
        if (result.success) {
            showGitToast('Git repository initialized' + (result.gitignore_created ? ' (.gitignore created)' : ''), 'success');
            await loadGitStatus();
        } else {
            throw new Error(result.message || 'Initialization error');
        }
    } catch (e) {
        console.error('git init error:', e);
        showGitToast('Initialization error: ' + e.message, 'error');
        updateGitHeaderIndicator('error', null, e.message);
        renderGitUnavailable(e.message);
    }
}

function renderGitSection(data) {
    const container = document.getElementById('gitStatusContainer');
    if (!container) return;

    // If initialized=true but branch empty — repo without commits
    if (!data) {
        renderGitUnavailable('Not a Git repository');
        return;
    }

    // Use branch or fallback for new repo without commits
    const branchName = data.branch || '(no commits)';

    // Count files from arrays
    const stagedCount = (data.staged || []).length;
    const unstagedCount = (data.unstaged || []).length;
    const untrackedCount = (data.untracked || []).length;
    const isClean = stagedCount === 0 && unstagedCount === 0 && untrackedCount === 0;
    const statusClass = isClean ? 'clean' : 'dirty';
    const statusText = isClean ? 'clean' : 'dirty';

    // Format changes
    let changesHtml = '';
    if (stagedCount > 0 || unstagedCount > 0 || untrackedCount > 0) {
        changesHtml = `<div class="git-changes">`;
        if (stagedCount > 0) changesHtml += `<span class="staged">+${stagedCount} staged</span> `;
        if (unstagedCount > 0) changesHtml += `<span class="unstaged">${unstagedCount} modified</span> `;
        if (untrackedCount > 0) changesHtml += `<span class="untracked">${untrackedCount} untracked</span>`;
        changesHtml += `</div>`;
    }

    container.innerHTML = `
        <div class="git-status-card">
            <div class="git-branch-row">
                <span class="git-branch-icon">🌿</span>
                <span class="git-branch-name">${escapeHtml(branchName)}</span>
                <span class="git-status-dot ${statusClass}" title="${statusText}"></span>
            </div>
            ${changesHtml}
        </div>

        <div class="git-actions">
            <button class="btn sm" onclick="showGitCommitModal()" ${isClean ? 'disabled title="No changes"' : ''}>📝 Commit</button>
            <button class="btn sm" onclick="gitPush()">⬆️ Push</button>
            <button class="btn sm" onclick="showGitPRModal()">🔀 PR</button>
        </div>

        <div class="git-history">
            <div class="git-history-toggle" onclick="toggleGitHistory()">
                <span class="arrow ${gitHistoryExpanded ? 'open' : ''}" id="gitHistoryArrow">▶</span>
                <span>History (last 20)</span>
            </div>
            <div class="git-history-list ${gitHistoryExpanded ? 'open' : ''}" id="gitHistoryList">
                <div style="text-align:center; padding:10px; color:var(--text-dim);">Loading...</div>
            </div>
        </div>
    `;

    if (gitHistoryExpanded) {
        loadGitHistory();
    }
}

async function toggleGitHistory() {
    gitHistoryExpanded = !gitHistoryExpanded;
    const arrow = document.getElementById('gitHistoryArrow');
    const list = document.getElementById('gitHistoryList');

    if (arrow) arrow.classList.toggle('open', gitHistoryExpanded);
    if (list) list.classList.toggle('open', gitHistoryExpanded);

    if (gitHistoryExpanded) {
        await loadGitHistory();
    }
}

async function loadGitHistory() {
    const list = document.getElementById('gitHistoryList');
    if (!list) return;

    try {
        const data = await api('GET', '/api/git/log?limit=20');
        const commits = data.commits || [];

        if (commits.length === 0) {
            list.innerHTML = '<div style="text-align:center; padding:10px; color:var(--text-dim);">No commits</div>';
            return;
        }

        list.innerHTML = commits.map(c => `
            <div class="git-commit-item">
                <span class="git-commit-hash">${escapeHtml(c.hash?.slice(0, 7) || '?')}</span>
                <span class="git-commit-msg" title="${escapeHtml(c.message || '')}">${escapeHtml(c.message?.split('\n')[0] || '')}</span>
                <span class="git-commit-time">${formatGitTime(c.date)}</span>
            </div>
        `).join('');
    } catch (e) {
        list.innerHTML = `<div style="text-align:center; padding:10px; color:var(--danger);">Error: ${escapeHtml(e.message)}</div>`;
    }
}

function formatGitTime(dateStr) {
    if (!dateStr) return '';
    const date = new Date(dateStr);
    const now = new Date();
    const diffMs = now - date;
    const diffHours = Math.floor(diffMs / (1000 * 60 * 60));

    if (diffHours < 1) return 'just now';
    if (diffHours < 24) return `${diffHours}h ago`;
    const diffDays = Math.floor(diffHours / 24);
    if (diffDays < 7) return `${diffDays}d ago`;
    return date.toLocaleDateString('en');
}

// ── Git Commit Modal ────────────────────────────────────────────────────────

async function showGitCommitModal() {
    // Show modal with loading
    const loadingBody = `
        <div style="text-align:center; padding:20px; color:var(--text-dim);">
            <div style="font-size:24px; margin-bottom:10px;">⏳</div>
            <p>Loading file list...</p>
        </div>
    `;
    openModal('Commit', loadingBody, '<button class="btn" onclick="closeModal()">Cancel</button>');

    try {
        const data = await api('GET', '/api/git/status');

        const staged = data.staged || [];
        const unstaged = data.unstaged || [];
        const untracked = data.untracked || [];
        const isClean = staged.length === 0 && unstaged.length === 0 && untracked.length === 0;

        if (isClean) {
            closeModal();
            alert('No changes to commit');
            return;
        }

        let filesHtml = '';
        if (staged.length > 0) {
            filesHtml += `<div style="font-size:12px; color:var(--success); margin:8px 0 4px;">Staged (${staged.length})</div>`;
            filesHtml += staged.map(f => renderCommitFileItem(f, true)).join('');
        }
        if (unstaged.length > 0) {
            filesHtml += `<div style="font-size:12px; color:var(--warning); margin:8px 0 4px;">Modified (${unstaged.length})</div>`;
            filesHtml += unstaged.map(f => renderCommitFileItem(f, false)).join('');
        }
        if (untracked.length > 0) {
            filesHtml += `<div style="font-size:12px; color:var(--text-dim); margin:8px 0 4px;">Untracked (${untracked.length})</div>`;
            filesHtml += untracked.map(f => renderCommitFileItem(f, false)).join('');
        }

        const body = `
            <div class="commit-type-row">
                <select id="commitType">
                    <option value="feat">feat</option>
                    <option value="fix">fix</option>
                    <option value="docs">docs</option>
                    <option value="style">style</option>
                    <option value="refactor">refactor</option>
                    <option value="test">test</option>
                    <option value="chore">chore</option>
                </select>
                <input type="text" id="commitScope" placeholder="scope (optional)">
            </div>
            <label>Message</label>
            <textarea id="commitMessage" rows="3" placeholder="Describe changes..."></textarea>

            <label>Files</label>
            <div class="commit-files-list">
                ${filesHtml}
            </div>
        `;

        openModal('Commit', body,
            `<button class="btn" onclick="closeModal()">Cancel</button>
             <button class="btn primary" onclick="submitGitCommit()">Commit</button>`);

    } catch (e) {
        closeModal();
        alert('Error getting status: ' + e.message);
    }
}

function renderCommitFileItem(file, isStaged) {
    // file can be a string (filename) or object
    const path = typeof file === 'string' ? file : (file.path || file.file || '');

    return `
        <div class="commit-file-item">
            <input type="checkbox" name="commitFiles" value="${escapeHtml(path)}" ${isStaged ? 'checked' : ''}>
            <span class="commit-file-path" title="${escapeHtml(path)}">${escapeHtml(path)}</span>
        </div>
    `;
}

async function submitGitCommit() {
    const type = document.getElementById('commitType').value;
    const scope = document.getElementById('commitScope').value.trim();
    const message = document.getElementById('commitMessage').value.trim();

    if (!message) {
        alert('Enter commit message');
        return;
    }

    // Collect selected files
    const checkboxes = document.querySelectorAll('input[name="commitFiles"]:checked');
    const files = Array.from(checkboxes).map(cb => cb.value);

    if (files.length === 0) {
        alert('Select at least one file');
        return;
    }

    // Build commit message
    const fullMessage = scope
        ? `${type}(${scope}): ${message}`
        : `${type}: ${message}`;

    try {
        const result = await api('POST', '/api/git/commit', {
            message: fullMessage,
            files: files
        });

        closeModal();
        addSystemMessage(`Commit created: ${result.hash?.slice(0, 7) || 'OK'}`);
        showGitToast('Commit created successfully', 'success');
        await loadGitStatus();
    } catch (e) {
        const errorMsg = parseGitError(e.message);
        showGitToast('Git error: ' + errorMsg, 'error');
        updateGitHeaderIndicator('error', null, errorMsg);
    }
}

// ── Git Push ────────────────────────────────────────────────────────────────

async function gitPush() {
    if (!confirm('Perform git push?')) return;

    try {
        const result = await api('POST', '/api/git/push');
        addSystemMessage(`Push completed: ${result.message || 'OK'}`);
        showGitToast('Push completed successfully', 'success');
        await loadGitStatus();
    } catch (e) {
        const errorMsg = parseGitError(e.message);
        showGitToast('Git error: ' + errorMsg, 'error');
        updateGitHeaderIndicator('error', null, errorMsg);
    }
}

// Parse git error messages for user-friendly display
function parseGitError(message) {
    const lowerMsg = (message || '').toLowerCase();

    if (lowerMsg.includes('could not resolve host') || lowerMsg.includes('unable to access')) {
        return 'Cannot access remote repository';
    }
    if (lowerMsg.includes('permission denied') || lowerMsg.includes('authentication failed')) {
        return 'Authentication error';
    }
    if (lowerMsg.includes('merge conflict') || lowerMsg.includes('conflict')) {
        return 'Merge conflict';
    }
    if (lowerMsg.includes('already exists')) {
        return 'Branch already exists';
    }
    if (lowerMsg.includes('not a git repository')) {
        return 'Not a Git repository';
    }
    if (lowerMsg.includes('rejected') || lowerMsg.includes('failed to push')) {
        return 'Push rejected (you may need to pull first)';
    }
    if (lowerMsg.includes('nothing to commit')) {
        return 'No changes to commit';
    }

    return message || 'Unknown error';
}

// ── Git PR Modal ────────────────────────────────────────────────────────────

async function showGitPRModal() {
    // Load branches
    const loadingBody = `
        <div style="text-align:center; padding:20px; color:var(--text-dim);">
            <div style="font-size:24px; margin-bottom:10px;">⏳</div>
            <p>Loading branches...</p>
        </div>
    `;
    openModal('Create Pull Request', loadingBody, '<button class="btn" onclick="closeModal()">Cancel</button>');

    try {
        const [statusData, branchesData] = await Promise.all([
            api('GET', '/api/git/status'),
            api('GET', '/api/git/branches')
        ]);

        const currentBranch = statusData.branch || 'unknown';
        const branches = branchesData.branches || [];

        // Options for base branch (excluding current branch)
        const baseOptions = branches
            .filter(b => b !== currentBranch)
            .map(b => `<option value="${escapeHtml(b)}" ${b === 'develop' ? 'selected' : ''}>${escapeHtml(b)}</option>`)
            .join('');

        const body = `
            <div style="margin-bottom:12px;">
                <label style="display:block; margin-bottom:4px;">Branch</label>
                <div style="font-family:var(--mono); font-size:14px; color:var(--accent);">${escapeHtml(currentBranch)}</div>
            </div>

            <label>Base branch</label>
            <select id="prBaseBranch">${baseOptions}</select>

            <label>Title</label>
            <input type="text" id="prTitle" placeholder="PR title" value="${escapeHtml(currentBranch)}">

            <label>Description</label>
            <textarea id="prDescription" rows="6" placeholder="## Summary&#10;- ...&#10;&#10;## Changes&#10;- ..."></textarea>
        `;

        openModal('Create Pull Request', body,
            `<button class="btn" onclick="closeModal()">Cancel</button>
             <button class="btn primary" onclick="submitGitPR()">Create PR</button>`);

    } catch (e) {
        closeModal();
        alert('Error: ' + e.message);
    }
}

async function submitGitPR() {
    const baseBranch = document.getElementById('prBaseBranch').value;
    const title = document.getElementById('prTitle').value.trim();
    const description = document.getElementById('prDescription').value.trim();

    if (!title) {
        alert('Enter PR title');
        return;
    }

    try {
        const result = await api('POST', '/api/git/pr', {
            base: baseBranch,
            title: title,
            body: description
        });

        closeModal();

        if (result.url) {
            addSystemMessage(`PR created: ${result.url}`);
            showGitToast('PR created successfully', 'success');
            if (confirm(`PR created!\n\nOpen in browser?\n${result.url}`)) {
                window.open(result.url, '_blank');
            }
        } else {
            addSystemMessage(`PR created: ${result.number || 'OK'}`);
            showGitToast('PR created successfully', 'success');
        }

        await loadGitStatus();
    } catch (e) {
        const errorMsg = parseGitError(e.message);
        showGitToast('Git error: ' + errorMsg, 'error');
    }
}

// ── Git Auto-refresh ────────────────────────────────────────────────────────

function startGitAutoRefresh() {
    if (gitAutoRefreshTimer) return;
    gitAutoRefreshTimer = setInterval(() => {
        loadGitStatus();
    }, 30000); // every 30 seconds
}

function stopGitAutoRefresh() {
    if (gitAutoRefreshTimer) {
        clearInterval(gitAutoRefreshTimer);
        gitAutoRefreshTimer = null;
    }
}
