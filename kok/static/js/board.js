// ── Tasks Board (NEW — kanban with sprints) ────────────────────────────────

const STATUS_LABELS = {
    'new': 'New',
    'done': 'Done',
    'questions': 'Questions',
    'cancelled': 'Cancelled',
};

// For 'new' tasks: resolve executor from task
function _getTaskAgent(task) {
    if (task.executor) return { agent: task.executor, role: 'executor' };
    return { agent: '—', role: 'executor' };
}

const STATUS_NEXT_ROLE = {
    'new': { label: 'Execute', btnClass: 'primary' },
};

let boardAutoRefreshTimer = null;
let expandedSprints = {};  // { sprintId: true/false } — which sprints are expanded
let allSprints = [];       // sprints cache
let allTasks = [];         // tasks cache
let taskFailures = {};     // { taskId: [failure, ...] } — unresolved failures cache

function showTasksBoard() {
    saveCurrentDraft();
    hideAllScreens();
    document.getElementById('tasksBoardScreen').style.display = 'flex';
    refreshTasksBoardNew();
    startBoardAutoRefresh();
}

function startBoardAutoRefresh() {
    stopBoardAutoRefresh();
    boardAutoRefreshTimer = setInterval(() => {
        if (document.getElementById('tasksBoardScreen').style.display !== 'none') {
            fetchRunningTasks().then(() => {
                if (Object.keys(runningTasks).length > 0) {
                    refreshTasksBoardNew();
                }
            });
        } else {
            stopBoardAutoRefresh();
        }
    }, 5000);
}

function stopBoardAutoRefresh() {
    if (boardAutoRefreshTimer) { clearInterval(boardAutoRefreshTimer); boardAutoRefreshTimer = null; }
}

async function fetchRunningTasks() {
    try {
        const data = await api('GET', '/api/running-tasks');
        const serverRunning = data.running || {};
        for (const tid of Object.keys(runningTasks)) {
            if (!serverRunning[tid] && runningTasks[tid]._local) {
                serverRunning[tid] = runningTasks[tid];
            }
        }
        runningTasks = serverRunning;
        updateRunningTasksIndicator();
    } catch { }
}

function startRunningTasksTimer() {
    stopRunningTasksTimer();
    runningTasksTimer = setInterval(() => {
        const badges = document.querySelectorAll('.task-running-badge .elapsed');
        badges.forEach(el => {
            const startedAt = parseFloat(el.dataset.startedAt);
            if (startedAt) {
                const elapsed = Math.round(Date.now() / 1000 - startedAt);
                el.textContent = formatElapsed(elapsed);
            }
        });
    }, 1000);
}

function stopRunningTasksTimer() {
    if (runningTasksTimer) { clearInterval(runningTasksTimer); runningTasksTimer = null; }
}

function formatElapsed(seconds) {
    if (seconds < 60) return `${seconds}s`;
    const m = Math.floor(seconds / 60);
    const s = seconds % 60;
    return `${m}m ${s}s`;
}

function toggleSprint(sprintId) {
    expandedSprints[sprintId] = !expandedSprints[sprintId];
    const body = document.getElementById('sprint-body-' + sprintId);
    const toggle = document.getElementById('sprint-toggle-' + sprintId);
    if (body) body.classList.toggle('open', expandedSprints[sprintId]);
    if (toggle) toggle.classList.toggle('open', expandedSprints[sprintId]);
}

async function refreshTasksBoardNew() {
    const wrap = document.getElementById('tasksBoardWrap');
    wrap.innerHTML = '<div class="empty-state">Loading...</div>';
    try {
        const [tasksData, sprintsData, , failuresData] = await Promise.all([
            api('GET', '/api/tasks-list'),
            api('GET', '/api/sprints'),
            fetchRunningTasks(),
            api('GET', '/api/agent-failures?resolved=false').catch(() => ({ failures: [] })),
        ]);
        allTasks = tasksData.tasks || [];
        allSprints = sprintsData.sprints || [];

        // Build taskFailures map from unresolved failures
        taskFailures = {};
        for (const f of (failuresData.failures || [])) {
            if (!taskFailures[f.task_id]) taskFailures[f.task_id] = [];
            taskFailures[f.task_id].push(f);
        }

        if (allTasks.length === 0 && allSprints.length === 0) {
            wrap.innerHTML = `<div class="empty-state" style="padding:40px;">
                <p style="margin-bottom:16px;">No tasks or sprints yet. Create the first sprint.</p>
                <button class="btn primary" onclick="showCreateSprintModal()">+ Create sprint</button>
            </div>`;
            stopRunningTasksTimer();
            return;
        }

        const hasRunning = Object.keys(runningTasks).length > 0;

        // Group tasks by sprints
        const tasksBySprint = {};
        const orphanTasks = [];
        for (const t of allTasks) {
            const sid = t.sprint_id || '';
            if (sid) {
                if (!tasksBySprint[sid]) tasksBySprint[sid] = [];
                tasksBySprint[sid].push(t);
            } else {
                orphanTasks.push(t);
            }
        }

        let html = '';

        // Sprints: oldest at bottom -> render in reverse order (newest on top)
        const sortedSprints = [...allSprints].reverse();

        for (const sprint of sortedSprints) {
            const sprintTasks = tasksBySprint[sprint.id] || [];
            const isOpen = expandedSprints[sprint.id] || false;
            const doneCount = sprintTasks.filter(t => t.status === 'done').length;
            const totalCount = sprintTasks.length;
            const finalizeTask = sprintTasks.find(t => t.is_finalize);
            let statusClass, statusText;
            if (sprint.status === 'released') {
                statusClass = 'released';
                statusText = '🚀 released ' + (sprint.version || '');
            } else if (sprint.status === 'completed' || (finalizeTask && finalizeTask.status === 'done')) {
                statusClass = 'done';
                statusText = 'completed';
            } else {
                statusClass = 'active';
                statusText = 'active';
            }
            const statusBadge = `<span class="sprint-badge ${statusClass}">${statusText}</span>`;
            const readyBadge = sprint.ready_to_execute ? `<span class="sprint-badge sprint-badge-autorun">⚡ Auto-run</span>` : '';

            // Count unresolved failures for tasks in this sprint
            const sprintFailureCount = sprintTasks.reduce((n, t) => n + (taskFailures[t.id] ? 1 : 0), 0);
            const failureBadge = sprintFailureCount > 0 ? `<span class="sprint-badge" style="background:var(--danger); color:#fff; font-size:11px; padding:2px 8px; border-radius:4px; margin-left:4px;">${sprintFailureCount} failed</span>` : '';

            html += `<div class="sprint-section">
                <div class="sprint-header" onclick="toggleSprint('${sprint.id}')">
                    <div class="sprint-header-left">
                        <span class="sprint-toggle${isOpen ? ' open' : ''}" id="sprint-toggle-${sprint.id}">&#9654;</span>
                        <span class="sprint-id">${escapeHtml(sprint.id)}</span>
                        <span class="sprint-title">${escapeHtml(sprint.title)}</span>
                    </div>
                    <div class="sprint-meta">
                        ${readyBadge}
                        ${failureBadge}
                        ${statusBadge}
                        <span class="sprint-progress">${doneCount}/${totalCount} tasks</span>
                    </div>
                </div>
                <div class="sprint-body${isOpen ? ' open' : ''}" id="sprint-body-${sprint.id}">
                    ${sprint.description ? `<div class="sprint-desc">${escapeHtml(sprint.description)}</div>` : ''}
                    ${renderSprintToolbar(sprint, sprintTasks)}
                    ${renderKanbanBoard(sprintTasks)}
                </div>
            </div>`;
        }

        // Tasks without sprint (if any)
        if (orphanTasks.length > 0) {
            const isOpen = expandedSprints['_orphan'] || false;
            html += `<div class="sprint-section" style="border-color: var(--text-dim);">
                <div class="sprint-header" onclick="toggleSprint('_orphan')">
                    <div class="sprint-header-left">
                        <span class="sprint-toggle${isOpen ? ' open' : ''}" id="sprint-toggle-_orphan">&#9654;</span>
                        <span class="sprint-id" style="color:var(--text-dim);">—</span>
                        <span class="sprint-title" style="color:var(--text-dim);">Tasks without sprint</span>
                    </div>
                    <div class="sprint-meta">
                        <span class="sprint-progress">${orphanTasks.length} tasks</span>
                    </div>
                </div>
                <div class="sprint-body${isOpen ? ' open' : ''}" id="sprint-body-_orphan">
                    ${renderKanbanBoard(orphanTasks)}
                </div>
            </div>`;
        }

        wrap.innerHTML = html;

        if (hasRunning) {
            startRunningTasksTimer();
        } else {
            stopRunningTasksTimer();
        }
    } catch (e) {
        wrap.innerHTML = '<div class="empty-state" style="color:var(--danger);">Error: ' + escapeHtml(e.message) + '</div>';
    }
}

function renderKanbanBoard(tasks) {
    const statuses = ['new', 'done', 'questions', 'cancelled'];
    const grouped = {};
    statuses.forEach(s => grouped[s] = []);
    tasks.forEach(t => {
        if (grouped[t.status]) grouped[t.status].push(t);
        else grouped['new'].push(t);
    });

    let html = '<div class="tasks-columns">';
    for (const status of statuses) {
        const col = grouped[status];
        html += `<div class="tasks-column col-${status}">
            <div class="tasks-column-title">${STATUS_LABELS[status]} <span class="count">${col.length}</span></div>`;
        for (const t of col) {
            html += renderTaskCard(t);
        }
        html += '</div>';
    }
    html += '</div>';
    return html;
}

function renderTaskCard(t) {
    const isRunning = !!runningTasks[t.id];
    const runInfo = runningTasks[t.id];
    const next = STATUS_NEXT_ROLE[t.status];
    let actionsHtml = '';
    const isFinalize = t.is_finalize || false;

    if (isRunning) {
        actionsHtml += `<button class="btn sm running" disabled title="Agent ${escapeHtml(runInfo.agent || '?')} is running...">${escapeHtml(runInfo.agent || 'Agent')} thinking...</button>`;
    } else if (next) {
        const { agent: agentName, role: agentRole } = _getTaskAgent(t);
        const agentRuntime = getAgentRuntime(agentName);
        const runtimeLabel = isAgentCursor(agentName) ? 'Via Cursor CLI' : 'Via Claude API';
        actionsHtml += `<button class="btn sm ${next.btnClass}" onclick="triggerTask('${t.id}','${agentRuntime}')" title="${runtimeLabel}">${escapeHtml(next.label)} · ${escapeHtml(agentRole)} (${escapeHtml(agentName)})</button>`;
    }

    if (!isRunning && t.status !== 'done' && t.status !== 'cancelled') {
        actionsHtml += `<button class="btn sm danger" onclick="cancelTask('${t.id}')" title="Cancel task">Cancel</button>`;
    }
    if (!isRunning && t.status === 'questions') {
        actionsHtml += `<button class="btn sm" onclick="returnToNew('${t.id}')" title="Return task to New for re-execution">↩ Return to New</button>`;
    }

    let resultHtml = '';
    if (t.result) {
        resultHtml = `<div class="task-card-result">${escapeHtml(t.result.slice(0, 200))}${t.result.length > 200 ? '...' : ''}</div>`;
    }

    // Dependencies
    let depsHtml = '';
    const deps = t.depends_on || [];
    if (deps.length > 0) {
        const depTags = deps.map(depId => {
            const depTask = allTasks.find(x => x.id === depId);
            const depStatus = depTask ? depTask.status : '?';
            const depDone = depStatus === 'done';
            const depColor = depDone ? 'color:var(--success)' : 'color:var(--warning)';
            const icon = depDone ? '&#10003;' : '&#9679;';
            return `<span class="dep-tag" style="${depColor}" title="${depId}: ${depStatus}">${icon} ${depId}</span>`;
        }).join('');
        depsHtml = `<div class="task-card-deps">Depends on: ${depTags}</div>`;
    }

    // Running badge
    let runningBadgeHtml = '';
    if (isRunning) {
        const elapsed = runInfo.elapsed_seconds || 0;
        const startedAt = runInfo.started_at || (Date.now() / 1000 - elapsed);
        const runtimeIcon = runInfo.runtime === 'cursor' ? 'Cursor' : 'Claude';
        runningBadgeHtml = `<div class="task-running-badge">
            <div class="spinner"></div>
            <span>${escapeHtml(runInfo.agent || '?')} · ${escapeHtml(runInfo.role || '')} · ${runtimeIcon}</span>
            <span class="elapsed" data-started-at="${startedAt}">${formatElapsed(elapsed)}</span>
        </div>`;
    }

    // Failure badge + retry button
    let failureBadgeHtml = '';
    const failures = taskFailures[t.id] || [];
    if (failures.length > 0 && !isRunning) {
        const latest = failures[failures.length - 1];
        const errorType = escapeHtml(latest.error_type || 'unknown');
        failureBadgeHtml = `<div style="display:flex; align-items:center; gap:8px; margin-top:4px;">
            <span style="background:var(--danger); color:#fff; font-size:11px; padding:2px 8px; border-radius:4px; font-weight:600;">FAILED:${errorType}</span>
            <button class="btn sm" style="font-size:11px; padding:2px 8px;" onclick="retryFailedTask('${t.id}')" title="Clear failure and re-trigger">Retry</button>
        </div>`;
    }

    return `<div class="task-card${isRunning ? ' running' : ''}${isFinalize ? ' task-card-finalize' : ''}">
        <div class="task-card-id">${escapeHtml(t.id)}${isFinalize ? ' · FINALIZE' : ''} · ${escapeHtml((t.updated_at || t.created_at || '').replace('T',' ').slice(0,16))}</div>
        <div class="task-card-title">${escapeHtml(t.title)}</div>
        ${t.description && !isFinalize ? `<div style="font-size:12px;color:var(--text-dim);margin-bottom:6px;">${escapeHtml(t.description.slice(0, 120))}${t.description.length > 120 ? '...' : ''}</div>` : ''}
        <div class="task-card-roles">
            <strong>Executor:</strong> ${escapeHtml(t.executor || '—')} &nbsp;
            <strong>Author:</strong> ${escapeHtml(t.author || '—')}
        </div>
        ${depsHtml}
        ${resultHtml}
        ${runningBadgeHtml}
        ${failureBadgeHtml}
        <div class="task-card-actions">${actionsHtml}</div>
    </div>`;
}

async function triggerTask(taskId, runtime) {
    if (runningTasks[taskId]) return;

    const btn = event.target;
    runningTasks[taskId] = {
        agent: btn.textContent.match(/\(([^)]+)\)/)?.[1] || '?',
        role: '',
        runtime: runtime,
        started_at: Date.now() / 1000,
        elapsed_seconds: 0,
        _local: true,
    };
    updateRunningTasksIndicator();
    await refreshTasksBoardNew();

    try {
        const result = await api('POST', `/api/tasks-list/${taskId}/trigger`, { runtime });
        if (result.agent) {
            addChatMessage(result.agent, 'system', `Task ${taskId}: ${result.role}`);
            if (result.result) {
                addChatMessage(result.agent, 'agent', result.result);
            }
        }
    } catch (e) {
        console.error('triggerTask error:', e.message);
        if (!e.message.includes('already running')) {
            alert('Error: ' + e.message);
        }
    } finally {
        delete runningTasks[taskId];
        // Signal any waiting auto-run loops that a task slot freed up
        const resolvers = _taskCompletionResolvers.splice(0);
        resolvers.forEach(r => r());
        if (document.getElementById('tasksBoardScreen').style.display !== 'none') {
            await refreshTasksBoardNew();
        }
    }
}

async function cancelTask(taskId) {
    if (!confirm(`Cancel task ${taskId}?`)) return;
    try {
        await api('PUT', `/api/tasks-list/${taskId}/status`, { status: 'cancelled' });
        await refreshTasksBoardNew();
    } catch (e) { alert('Error: ' + e.message); }
}

async function returnToNew(taskId) {
    try {
        await api('PUT', `/api/tasks-list/${taskId}/status`, { status: 'new' });
        await refreshTasksBoardNew();
    } catch (e) { alert('Error: ' + e.message); }
}

async function retryFailedTask(taskId) {
    // Resolve all unresolved failures for this task, then re-trigger
    const failures = taskFailures[taskId] || [];
    try {
        await Promise.all(failures.map(f => api('DELETE', `/api/agent-failures/${f.id}`).catch(() => {})));
        delete taskFailures[taskId];
    } catch {}
    // Determine runtime from the task's agent
    const task = allTasks.find(t => t.id === taskId);
    const { agent: agentName } = task ? _getTaskAgent(task) : { agent: '' };
    const runtime = getAgentRuntime(agentName);
    triggerTask(taskId, runtime);
}

// ── Old Tasks Board (tasks.md) ─────────────────────────────────────────────

function showOldTasksBoard() {
    saveCurrentDraft();
    hideAllScreens();
    document.getElementById('tasksScreen').style.display = 'flex';
    refreshOldTasksBoard();
}

async function refreshOldTasksBoard() {
    const el = document.getElementById('oldTasksBoardContent');
    el.textContent = 'Loading...';
    try {
        const data = await api('GET', '/api/tasks');
        el.textContent = data.content || '';
    } catch (e) { el.textContent = 'Error: ' + e.message; }
}
