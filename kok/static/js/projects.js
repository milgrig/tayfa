// ── Current Project Badge ──────────────────────────────────────────────────

function updateCurrentProjectBadge(project) {
    const nameEl = document.getElementById('currentProjectName');
    if (!nameEl) return;

    if (project && project.name) {
        nameEl.textContent = project.name;
    } else {
        nameEl.textContent = '—';
    }
}

// ── Project Picker Functions ───────────────────────────────────────────────

let projectsList = [];
let hasCurrentProject = false; // Flag: is there an open project

async function showProjectPicker() {
    // Check if there is a current project
    try {
        const status = await api('GET', '/api/status');
        hasCurrentProject = !!status.has_project;
    } catch {
        hasCurrentProject = false;
    }

    // Show/hide close buttons depending on whether a project exists
    const closeBtn = document.getElementById('projectPickerClose');
    const cancelBtn = document.getElementById('projectPickerCancel');

    if (closeBtn) {
        closeBtn.style.display = hasCurrentProject ? '' : 'none';
    }
    if (cancelBtn) {
        cancelBtn.style.display = hasCurrentProject ? '' : 'none';
    }

    document.getElementById('projectPicker').classList.add('show');
    document.getElementById('mainApp').style.display = 'none';
    loadProjectsList();
}

function hideProjectPicker() {
    document.getElementById('projectPicker').classList.remove('show');
    document.getElementById('mainApp').style.display = '';
}

// Try to close project-picker (only if there is an open project)
function tryCloseProjectPicker() {
    if (hasCurrentProject) {
        hideProjectPicker();
    }
}

// Click handler on overlay (background) of project-picker
document.getElementById('projectPicker').addEventListener('click', function(e) {
    // Close only if click was on the overlay itself (not on card) and there is an open project
    if (e.target === this && hasCurrentProject) {
        hideProjectPicker();
    }
});

let isNewUser = false;

async function loadProjectsList() {
    const container = document.getElementById('projectList');
    container.innerHTML = '<div class="project-empty"><div class="project-empty-icon">⏳</div><p>Loading...</p></div>';

    try {
        const data = await api('GET', '/api/projects');
        console.log('[loadProjectsList] API response:', data);
        projectsList = data.projects || [];
        isNewUser = data.is_new_user || false;
        renderProjectsList();
    } catch (error) {
        console.error('[loadProjectsList] Error:', error);
        container.innerHTML = `<div class="project-empty"><div class="project-empty-icon">❌</div><p>Loading error: ${escapeHtml(error.message)}</p></div>`;
    }
}

function renderProjectsList() {
    const container = document.getElementById('projectList');

    if (projectsList.length === 0) {
        if (isNewUser) {
            // Welcome message for new users
            container.innerHTML = `
                <div class="project-empty welcome-message">
                    <div class="project-empty-icon">👋</div>
                    <h3>Welcome to Tayfa!</h3>
                    <p style="color: var(--text-secondary); margin: 0.5rem 0 1rem; line-height: 1.5;">
                        Tayfa is a multi-agent system for development.<br>
                        AI agents work as a team: boss assigns tasks,<br>
                        developers write code, testers verify.
                    </p>
                    <p style="color: var(--accent); font-weight: 500;">
                        Open a project folder to get started
                    </p>
                </div>`;
        } else {
            container.innerHTML = `
                <div class="project-empty">
                    <div class="project-empty-icon">📂</div>
                    <p>No projects. Open a project folder.</p>
                </div>`;
        }
        return;
    }

    const html = projectsList.map(project => `
        <div class="project-item" onclick="openProject('${escapeHtml(project.path.replace(/\\/g, '\\\\').replace(/'/g, "\\'"))}')">
            <div class="project-item-icon">📁</div>
            <div class="project-item-info">
                <div class="project-item-name">${escapeHtml(project.name)}</div>
                <div class="project-item-path">${escapeHtml(project.path)}</div>
                <div class="project-item-time">Opened: ${formatLastOpened(project.last_opened)}</div>
            </div>
            <div class="project-item-remove" onclick="event.stopPropagation(); removeProject('${escapeHtml(project.path.replace(/\\/g, '\\\\').replace(/'/g, "\\'"))}')" title="Remove from list">×</div>
        </div>
    `).join('');

    container.innerHTML = html;
}

function formatLastOpened(isoDate) {
    if (!isoDate) return 'unknown';

    const date = new Date(isoDate);
    const now = new Date();
    const diffMs = now - date;
    const diffDays = Math.floor(diffMs / (1000 * 60 * 60 * 24));

    if (diffDays === 0) {
        const diffHours = Math.floor(diffMs / (1000 * 60 * 60));
        if (diffHours === 0) {
            const diffMins = Math.floor(diffMs / (1000 * 60));
            if (diffMins < 1) return 'just now';
            return diffMins + ' min ago';
        }
        return 'today at ' + date.toLocaleTimeString('en', { hour: '2-digit', minute: '2-digit' });
    } else if (diffDays === 1) {
        return 'yesterday';
    } else if (diffDays < 7) {
        return diffDays + ' days ago';
    } else {
        return date.toLocaleDateString('en');
    }
}

async function openProject(path) {
    const container = document.getElementById('projectList');
    const originalContent = container.innerHTML;
    container.innerHTML = '<div class="project-empty"><div class="project-empty-icon">⏳</div><p>Opening project...</p></div>';

    console.log('[openProject] Opening project:', path);

    try {
        const result = await api('POST', '/api/projects/open', { path });
        console.log('[openProject] API response:', result);

        if (result.status === 'opened' || result.status === 'initialized') {
            console.log('[openProject] Success! Hiding picker...');
            hasCurrentProject = true; // Now there is an open project
            hideProjectPicker();

            // Reload agents and status (errors should not block opening)
            try {
                await Promise.all([loadAgents(), checkStatus(), loadEmployees()]);
            } catch (loadError) {
                console.warn('[openProject] Data loading error (non-critical):', loadError);
            }

            // Update project name in header
            updateCurrentProjectBadge(result.project);

            // Project name in result.project.name or fallback to path
            const projectName = result.project?.name || path.split(/[\\\/]/).pop() || path;
            document.title = projectName + ' — Tayfa';
            addSystemMessage(`Project "${projectName}" opened`);
            console.log('[openProject] Done!');
        } else {
            console.error('[openProject] Unexpected status:', result.status);
            throw new Error(result.error || 'Unknown error');
        }
    } catch (error) {
        console.error('[openProject] Error:', error);
        container.innerHTML = originalContent;
        alert('Error opening project: ' + error.message);
    }
}

async function removeProject(path) {
    if (!confirm('Remove project from recent list?\n\nThe project folder will not be deleted.')) return;

    try {
        await api('POST', '/api/projects/remove', { path });
        await loadProjectsList();
    } catch (error) {
        alert('Error: ' + error.message);
    }
}

async function openFolderDialog() {
    // Call server API to open system dialog
    try {
        const container = document.getElementById('projectList');
        const originalContent = container.innerHTML;
        container.innerHTML = '<div class="project-empty"><div class="project-empty-icon">📂</div><p>Opening folder picker dialog...</p></div>';

        const result = await api('GET', '/api/browse-folder');

        if (result.error) {
            container.innerHTML = originalContent;
            alert('Error: ' + result.error);
            return;
        }

        if (result.cancelled || !result.path) {
            container.innerHTML = originalContent;
            return; // User cancelled selection
        }

        // Open selected project
        await openProject(result.path);

    } catch (error) {
        console.error('[openFolderDialog] Error:', error);
        // Fallback to manual input
        openFolderManual();
    }
}

function openFolderManual(suggestedName = '') {
    const placeholder = suggestedName
        ? `Example: C:\\Projects\\${suggestedName}`
        : 'Example: C:\\Projects\\MyApp or /home/user/projects/app';

    const body = `
        <p style="font-size:13px; color:var(--text-dim); margin-bottom:12px;">
            Enter the full path to the project folder:
        </p>
        <input type="text" id="manualPathInput" placeholder="${placeholder}"
               style="width:100%; margin-bottom:8px;" autofocus>
        <p style="font-size:11px; color:var(--text-dim);">
            Browser does not allow automatic folder path retrieval.
            Enter path manually or copy from file explorer.
        </p>
    `;

    openModal('Open project folder', body,
        `<button class="btn" onclick="closeModal()">Cancel</button>
         <button class="btn primary" onclick="submitManualPath()">Open</button>`);

    // Focus on input
    setTimeout(() => {
        const input = document.getElementById('manualPathInput');
        if (input) input.focus();
    }, 100);
}

async function submitManualPath() {
    const input = document.getElementById('manualPathInput');
    const path = input.value.trim();

    if (!path) {
        alert('Enter the folder path');
        return;
    }

    console.log('[submitManualPath] Path:', path);
    closeModal();
    await openProject(path);
}

// Function to show project-picker from settings or header
function switchProject() {
    closeSettingsDropdown();
    showProjectPicker();
}


// ── Disable project switching when instance is locked ─────────────────────

function disableProjectSwitching() {
    // Disable the project badge click
    const badge = document.getElementById('currentProjectBadge');
    if (badge) {
        badge.onclick = null;
        badge.style.cursor = 'default';
        badge.title = 'Project locked (instance mode)';
    }

    // Disable "Switch project" in settings dropdown
    const settingsDropdown = document.getElementById('settingsDropdown');
    if (settingsDropdown) {
        const items = settingsDropdown.querySelectorAll('.settings-item');
        items.forEach(item => {
            if (item.textContent.includes('Switch project')) {
                item.onclick = null;
                item.style.opacity = '0.4';
                item.style.cursor = 'default';
                item.style.pointerEvents = 'none';
                item.title = 'Project locked (instance mode)';
            }
        });
    }
}


// ── Open Project in New Window ────────────────────────────────────────────

async function openProjectInNewWindow() {
    closeSettingsDropdown();

    // Load projects list for the modal
    let projects = [];
    try {
        const data = await api('GET', '/api/projects');
        projects = data.projects || [];
    } catch (error) {
        alert('Error loading projects: ' + error.message);
        return;
    }

    if (projects.length === 0) {
        alert('No projects available. Add a project first.');
        return;
    }

    // Build project list HTML for modal
    const listHtml = projects.map(p => `
        <div class="project-item" style="cursor:pointer; padding:10px 14px; border:1px solid var(--border); border-radius:8px; margin-bottom:8px; background:var(--bg-input); transition:background 0.15s;"
             onmouseover="this.style.background='var(--bg-hover)'"
             onmouseout="this.style.background='var(--bg-input)'"
             onclick="launchInstanceForProject('${escapeHtml(p.path.replace(/\\/g, '\\\\').replace(/'/g, "\\'"))}')">
            <div style="font-weight:600; color:var(--text-bright); font-size:14px;">📁 ${escapeHtml(p.name)}</div>
            <div style="font-size:12px; color:var(--text-dim); margin-top:2px; font-family:var(--mono);">${escapeHtml(p.path)}</div>
        </div>
    `).join('');

    const body = `
        <p style="font-size:13px; color:var(--text-dim); margin-bottom:14px;">
            Select a project to open in a new browser window. A new Tayfa instance will be launched for it.
        </p>
        <div style="max-height:350px; overflow-y:auto;">
            ${listHtml}
        </div>
    `;

    openModal('Open in New Window', body,
        `<button class="btn" onclick="closeModal()">Cancel</button>`);
}


async function launchInstanceForProject(path) {
    closeModal();

    // Show loading notification
    const loadingMsg = addSystemMessage(`Launching new instance for project...`);

    try {
        const result = await api('POST', '/api/launch-instance', { path });

        if (result.status === 'already_running') {
            addSystemMessage(`Instance already running. Opening: ${result.url}`);
            window.open(result.url, '_blank');
        } else if (result.status === 'launched') {
            addSystemMessage(`New instance launched on port ${result.port}. Opening: ${result.url}`);
            window.open(result.url, '_blank');
        } else {
            addSystemMessage(`Unexpected response: ${JSON.stringify(result)}`, true);
        }
    } catch (error) {
        addSystemMessage('Error launching instance: ' + error.message, true);
    }
}
