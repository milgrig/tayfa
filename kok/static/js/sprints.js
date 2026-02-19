// ── Sprint Auto-Run ────────────────────────────────────────────────────────

function renderSprintToolbar(sprint, sprintTasks) {
    // Only show toolbar for active sprints that have tasks
    const nonFinalTasks = sprintTasks.filter(t => !t.is_finalize);
    if (nonFinalTasks.length === 0) return '';

    const isAutoRunning = sprintAutoRunState[sprint.id]?.running;
    const doneCount = sprintTasks.filter(t => t.status === 'done' || t.status === 'cancelled').length;
    const totalCount = sprintTasks.length;
    const allDone = sprintTasks.every(t => t.status === 'done' || t.status === 'cancelled');

    let btnHtml = '';
    if (allDone && sprint.status === 'completed') {
        btnHtml = `<span style="font-size:12px; color:var(--success); font-weight:600;">✓ Released ${sprint.version || ''}</span>`;
    } else if (allDone) {
        btnHtml = `<button class="btn sm success" onclick="event.stopPropagation(); showReleaseModal('${sprint.id}')">🚀 Release</button>`;
    } else if (isAutoRunning) {
        btnHtml = `<button class="btn sm auto-stop" onclick="event.stopPropagation(); stopSprintAutoRun('${sprint.id}')">⏹ Stop</button>`;
        btnHtml += `<div class="auto-run-progress"><div class="spinner"></div><span>Auto-run: ${doneCount}/${totalCount} tasks done</span></div>`;
    } else {
        btnHtml = `<button class="btn sm auto-run" onclick="event.stopPropagation(); runAllSprintTasks('${sprint.id}')">▶ Run all sprint tasks</button>`;
    }

    // Ready to execute toggle (only for active sprints that aren't fully done)
    let readyToggle = '';
    if (sprint.status === 'active' && !allDone) {
        const checked = sprint.ready_to_execute ? 'checked' : '';
        readyToggle = `<label style="display:flex; align-items:center; gap:6px; cursor:pointer; margin-left:auto; font-size:12px; color:var(--text-dim);" onclick="event.stopPropagation();">
            <input type="checkbox" ${checked} style="accent-color:var(--success); width:14px; height:14px;" onchange="toggleSprintReady('${sprint.id}', this.checked)">
            Ready to execute
        </label>`;
    }

    return `<div class="sprint-toolbar">${btnHtml}${readyToggle}</div>`;
}

async function toggleSprintReady(sprintId, ready) {
    try {
        await api('PUT', `/api/sprints/${sprintId}`, { ready_to_execute: ready });
        // Update local cache
        const sprint = allSprints.find(s => s.id === sprintId);
        if (sprint) sprint.ready_to_execute = ready;
        await refreshTasksBoardNew();
    } catch (e) {
        console.error('[toggleSprintReady] Error:', e);
        alert('Error updating sprint: ' + e.message);
    }
}

// ── Release Functions ───────────────────────────────────────────────────────

async function showReleaseModal(sprintId) {
    // Show modal with loading indicator
    const loadingBody = `
        <div style="text-align:center; padding:20px;">
            <div class="spinner" style="margin:0 auto 16px;"></div>
            <p>Checking release readiness...</p>
        </div>
    `;
    openModal('🚀 Release', loadingBody, '');

    try {
        const releaseInfo = await api('GET', `/api/sprints/${sprintId}/release-ready`);

        if (!releaseInfo.ready) {
            const pendingIds = (releaseInfo.pending_tasks || []).map(t => t.id || t).join(', ');
            closeModal();
            alert('Not all tasks are done: ' + pendingIds);
            return;
        }

        const sprint = allSprints.find(s => s.id === sprintId);
        const sprintTitle = sprint?.title || sprintId;
        const nextVersion = releaseInfo.next_version || 'v0.1.0';
        const doneCount = releaseInfo.done_count || '?';

        const body = `
            <div style="display:flex; flex-direction:column; gap:16px;">
                <div>
                    <label style="font-size:12px; color:var(--text-dim);">Sprint</label>
                    <p style="margin:4px 0; font-weight:600;">${escapeHtml(sprintId)} "${escapeHtml(sprintTitle)}"</p>
                </div>
                <div>
                    <label style="font-size:12px; color:var(--text-dim);">Tasks done</label>
                    <p style="margin:4px 0;">${doneCount}</p>
                </div>
                <div>
                    <label style="font-size:12px; color:var(--text-dim);">Release version</label>
                    <input type="text" id="releaseVersion" value="${escapeHtml(nextVersion)}" style="width:100%; margin-top:4px;">
                </div>
                <p style="font-size:12px; color:var(--text-dim); margin:0;">
                    A commit with all changes, a version tag, and a push to GitHub will be created.
                </p>
            </div>
        `;

        openModal('🚀 Release', body,
            `<button class="btn" onclick="closeModal()">Cancel</button>
             <button class="btn success" onclick="executeRelease('${sprintId}')">Release</button>`);
    } catch (e) {
        closeModal();
        alert('Readiness check error: ' + e.message);
    }
}

async function executeRelease(sprintId) {
    const versionInput = document.getElementById('releaseVersion');
    const version = versionInput?.value?.trim();

    document.getElementById('modalBody').innerHTML = `
        <div style="text-align:center; padding:20px;">
            <div class="spinner" style="margin:0 auto 16px;"></div>
            <p>Creating release...</p>
            <p style="font-size:12px; color:var(--text-dim); margin-top:8px;">Commit, tag, push to GitHub...</p>
        </div>
    `;
    document.getElementById('modalActions').innerHTML = '';

    try {
        const result = await api('POST', '/api/git/release', {
            sprint_id: sprintId,
            version: version || undefined
        });

        closeModal();

        if (result.success) {
            const successMsg = `🚀 Release ${result.version} published!\nCommit: ${result.commit || 'created'}\nTag: ${result.tag_created ? 'created' : 'no'}`;
            alert(successMsg);

            await Promise.all([
                refreshTasksBoardNew(),
                loadSprints(),
                loadGitStatus()
            ]);
        } else {
            alert('Release error: ' + (result.error || result.message || 'Unknown error'));
        }
    } catch (e) {
        closeModal();
        alert('Error: ' + e.message);
    }
}

async function triggerTaskAutoRun(taskId, runtime) {
    if (runningTasks[taskId]) return;

    const task = allTasks.find(t => t.id === taskId);
    if (!task) return;
    const next = STATUS_NEXT_ROLE[task.status];
    if (!next) return;
    const agentName = task[next.role] || '?';

    runningTasks[taskId] = {
        agent: agentName,
        role: next.label || '',
        runtime: runtime,
        started_at: Date.now() / 1000,
        elapsed_seconds: 0,
        _local: true,
    };
    updateRunningTasksIndicator();

    try {
        const result = await api('POST', `/api/tasks-list/${taskId}/trigger`, { runtime });
        if (result.agent && result.result) {
            addChatMessage(result.agent, 'system', `Task ${taskId}: ${result.role}`);
            addChatMessage(result.agent, 'agent', result.result);
        }
    } catch (e) {
        console.error(`[AutoRun] triggerTask ${taskId} error:`, e.message);
        // Mark task as failed in local cache for sprint loop awareness
        if (!taskFailures[taskId]) taskFailures[taskId] = [];
        taskFailures[taskId].push({ task_id: taskId, error_type: 'autorun', message: e.message });
    } finally {
        delete runningTasks[taskId];
        updateRunningTasksIndicator();
        // Signal any waiting loops that a task slot freed up
        const resolvers = _taskCompletionResolvers.splice(0);
        resolvers.forEach(r => r());
    }
}

async function runAllSprintTasks(sprintId) {
    if (sprintAutoRunState[sprintId]?.running) return;
    delete autoLaunchFinished[sprintId];  // Reset so manual re-launch is always allowed

    const maxConcurrent = parseInt(document.getElementById('maxConcurrentInput')?.value) || 5;
    sprintAutoRunState[sprintId] = { running: true, cancelled: false, finished: false };
    const failedTaskIds = new Set();  // Track tasks that failed during this run

    // Expand this sprint so user sees progress
    expandedSprints[sprintId] = true;
    await refreshTasksBoardNew();

    console.log(`[AutoRun] Starting sprint ${sprintId}, maxConcurrent=${maxConcurrent}`);

    try {
        while (!sprintAutoRunState[sprintId]?.cancelled) {
            // Refresh all tasks from server
            const tasksData = await api('GET', '/api/tasks-list');
            const allTasksFresh = tasksData.tasks || [];
            allTasks = allTasksFresh; // update global cache

            // Refresh failures cache
            try {
                const fData = await api('GET', '/api/agent-failures?resolved=false');
                taskFailures = {};
                for (const f of (fData.failures || [])) {
                    if (!taskFailures[f.task_id]) taskFailures[f.task_id] = [];
                    taskFailures[f.task_id].push(f);
                    failedTaskIds.add(f.task_id);
                }
            } catch {}

            const sprintTasks = allTasksFresh.filter(t => t.sprint_id === sprintId);

            // Check if all tasks are done
            const allDone = sprintTasks.every(t =>
                t.status === 'done' || t.status === 'cancelled'
            );
            if (allDone) {
                console.log(`[AutoRun] Sprint ${sprintId}: all tasks done!`);
                break;
            }

            // Find actionable tasks (only 'new' status is actionable)
            const actionable = sprintTasks.filter(t => t.status === 'new');

            if (actionable.length === 0) break;

            // Find ready tasks: not currently running, dependencies met
            const ready = actionable.filter(t => {
                // Skip already running
                if (runningTasks[t.id]) return false;

                // Skip tasks with unresolved failures (don't retry automatically)
                if (taskFailures[t.id] && taskFailures[t.id].length > 0) return false;

                // Check all dependencies are done/cancelled
                const deps = t.depends_on || [];
                return deps.every(depId => {
                    const depTask = allTasksFresh.find(x => x.id === depId);
                    return depTask && (depTask.status === 'done' || depTask.status === 'cancelled');
                });
            });

            // Sort by task number (lower number = higher priority)
            ready.sort((a, b) => {
                const numA = parseInt(a.id.replace(/\D/g, ''));
                const numB = parseInt(b.id.replace(/\D/g, ''));
                return numA - numB;
            });

            // Calculate available slots
            const currentRunning = Object.keys(runningTasks).length;
            const slots = Math.max(0, maxConcurrent - currentRunning);
            const batch = ready.slice(0, slots);

            console.log(`[AutoRun] Sprint ${sprintId}: actionable=${actionable.length}, ready=${ready.length}, running=${currentRunning}, slots=${slots}, batch=${batch.length}, failed=${failedTaskIds.size}`);

            if (batch.length === 0) {
                if (currentRunning > 0) {
                    // Wait for ANY running task to complete (event-driven, not polling)
                    await new Promise(r => {
                        _taskCompletionResolvers.push(r);
                        // Safety fallback: don't wait more than 500ms
                        setTimeout(r, 500);
                    });
                    await refreshTasksBoardNew();
                    continue;
                }
                // Nothing running and nothing ready - stuck (deps block or error)
                console.warn(`[AutoRun] Sprint ${sprintId}: no tasks ready and nothing running. Stopping.`);
                break;
            }

            // Update board to show running state
            await refreshTasksBoardNew();

            // Fire-and-forget: launch batch tasks without waiting for all to complete.
            // Each task clears its runningTasks entry on completion and signals the loop.
            batch.forEach(t => {
                const { agent: agentName } = _getTaskAgent(t);
                const runtime = getAgentRuntime(agentName);
                triggerTaskAutoRun(t.id, runtime);
            });

            // Wait for ANY task in the batch to complete before re-evaluating
            await new Promise(r => {
                _taskCompletionResolvers.push(r);
            });

            // Refresh board after a task completes
            await refreshTasksBoardNew();
        }
    } catch (e) {
        console.error('[AutoRun] Error:', e);
    } finally {
        const wasCancelled = sprintAutoRunState[sprintId]?.cancelled;
        const finished = sprintAutoRunState[sprintId]?.finished;

        // Only show finish message once
        if (sprintAutoRunState[sprintId] && !finished) {
            sprintAutoRunState[sprintId].finished = true;
            await refreshTasksBoardNew();

            if (failedTaskIds.size > 0) {
                const failList = [...failedTaskIds].join(', ');
                console.warn(`[AutoRun] Sprint ${sprintId} finished with ${failedTaskIds.size} failed task(s): ${failList}`);
                addSystemMessage(`Sprint ${sprintId} auto-run finished. ${failedTaskIds.size} task(s) failed: ${failList}`);
            } else {
                console.log(`[AutoRun] Sprint ${sprintId} finished. ${wasCancelled ? '(cancelled)' : '(complete)'}`);
            }
        }

        delete sprintAutoRunState[sprintId];
    }
}

function stopSprintAutoRun(sprintId) {
    if (sprintAutoRunState[sprintId]) {
        sprintAutoRunState[sprintId].cancelled = true;
        console.log(`[AutoRun] Sprint ${sprintId}: cancel requested`);
    }
}

// ── Create Sprint Modal ────────────────────────────────────────────────────

function showCreateSprintModal() {
    const body = `
        <label>Sprint name</label>
        <input type="text" id="newSprintTitle" placeholder="e.g.: MVP, Sprint 4 — Voiceover">
        <label>Description</label>
        <textarea id="newSprintDesc" rows="3" placeholder="Sprint goal, key tasks (optional)"></textarea>
        <div style="margin-top:16px; padding-top:16px; border-top:1px solid var(--border);">
            <label style="display:flex; align-items:center; gap:10px; cursor:pointer; padding:12px 14px; border-radius:8px; border:1px solid var(--success); background:rgba(52,211,153,0.06); transition:background 0.15s;">
                <input type="checkbox" id="newSprintReady" style="accent-color:var(--success); width:18px; height:18px; flex-shrink:0;">
                <div>
                    <span style="font-size:14px; font-weight:600; color:var(--text-bright);">⚡ Ready to execute</span>
                    <p style="font-size:12px; color:var(--text-dim); margin-top:4px; line-height:1.4;">When checked, the sprint will be automatically executed after creation — all tasks will be launched sequentially.</p>
                </div>
            </label>
        </div>
    `;
    openModal('Create sprint', body,
        `<button class="btn" onclick="closeModal()">Cancel</button>
         <button class="btn primary" onclick="createSprintFromModal()">Create</button>`);
}

async function createSprintFromModal() {
    const title = document.getElementById('newSprintTitle').value.trim();
    if (!title) { alert('Enter sprint name'); return; }
    const data = {
        title,
        description: document.getElementById('newSprintDesc').value.trim(),
        created_by: 'boss',
        ready_to_execute: document.getElementById('newSprintReady').checked,
    };
    try {
        const sprint = await api('POST', '/api/sprints', data);
        closeModal();
        // Automatically expand new sprint
        expandedSprints[sprint.id] = true;
        await refreshTasksBoardNew();
        addSystemMessage(`Sprint ${sprint.id} created: ${sprint.title}`);
    } catch (e) { alert('Error: ' + e.message); }
}

// ── Create Task Modal ──────────────────────────────────────────────────────

function showCreateTaskModal() {
    const empOptions = Object.keys(employees).map(n => `<option value="${n}">${n} — ${escapeHtml(employees[n].role || '')}</option>`).join('');
    const sprintOptions = '<option value="">— no sprint —</option>' +
        allSprints.filter(s => s.status === 'active').map(s =>
            `<option value="${s.id}">${s.id} — ${escapeHtml(s.title)}</option>`
        ).join('');
    const taskOptions = allTasks.map(t =>
        `<option value="${t.id}">${t.id} — ${escapeHtml(t.title.slice(0, 50))}</option>`
    ).join('');

    const body = `
        <label>Sprint</label>
        <select id="newTaskSprint">${sprintOptions}</select>
        <label>Title</label>
        <input type="text" id="newTaskTitle" placeholder="Brief task name">
        <label>Description</label>
        <textarea id="newTaskDesc" rows="3" placeholder="Detailed description (optional)"></textarea>
        <label>Executor</label>
        <select id="newTaskExecutor">${empOptions}</select>
        <label>Depends on tasks (Ctrl+Click for multiple selection)</label>
        <select id="newTaskDeps" multiple size="4" style="min-height:80px;">${taskOptions}</select>
    `;
    openModal('Create task', body,
        `<button class="btn" onclick="closeModal()">Cancel</button>
         <button class="btn primary" onclick="createTaskFromModal()">Create</button>`);
}

async function createTaskFromModal() {
    const title = document.getElementById('newTaskTitle').value.trim();
    if (!title) { alert('Enter title'); return; }
    const depsSelect = document.getElementById('newTaskDeps');
    const depends_on = Array.from(depsSelect.selectedOptions).map(o => o.value);
    const data = {
        title,
        description: document.getElementById('newTaskDesc').value.trim(),
        author: 'boss',
        executor: document.getElementById('newTaskExecutor').value,
        sprint_id: document.getElementById('newTaskSprint').value,
        depends_on: depends_on.length > 0 ? depends_on : undefined,
    };
    try {
        const task = await api('POST', '/api/tasks-list', data);
        closeModal();
        // Expand sprint where task was added
        if (task.sprint_id) expandedSprints[task.sprint_id] = true;
        await refreshTasksBoardNew();
        addSystemMessage(`Task ${task.id} created: ${task.title}`);
    } catch (e) { alert('Error: ' + e.message); }
}

function showCreateBacklogModal() {
    const sprintOptions = '<option value="">— no sprint —</option>' +
        allSprints.filter(s => s.status === 'active').map(s =>
            `<option value="${s.id}">${s.id} — ${escapeHtml(s.title)}</option>`
        ).join('');

    const body = `
        <label>Sprint for all backlog tasks</label>
        <select id="backlogSprint">${sprintOptions}</select>
        <p style="font-size:13px;color:var(--text-dim);margin-bottom:12px; margin-top:12px;">
            Paste a JSON array of tasks. Each task: { "title", "description", "author", "executor" }.
            The sprint_id field will be added automatically from the selected sprint.
        </p>
        <textarea id="backlogJson" rows="12" style="font-family:var(--mono); font-size:12px;" placeholder='[
  {
    "title": "Task name",
    "description": "Description",
    "author": "boss",
    "executor": "developer"
  }
]'></textarea>
    `;
    openModal('Create backlog', body,
        `<button class="btn" onclick="closeModal()">Cancel</button>
         <button class="btn primary" onclick="createBacklogFromModal()">Create</button>`);
}

async function createBacklogFromModal() {
    const text = document.getElementById('backlogJson').value.trim();
    const sprintId = document.getElementById('backlogSprint').value;
    let tasks;
    try { tasks = JSON.parse(text); } catch { alert('Invalid JSON'); return; }
    if (!Array.isArray(tasks) || tasks.length === 0) { alert('Non-empty array of tasks required'); return; }
    // Add sprint_id to all tasks
    if (sprintId) {
        tasks = tasks.map(t => ({ ...t, sprint_id: sprintId }));
    }
    try {
        const result = await api('POST', '/api/tasks-list', { tasks });
        closeModal();
        if (sprintId) expandedSprints[sprintId] = true;
        await refreshTasksBoardNew();
        addSystemMessage(`Created ${result.count} tasks`);
    } catch (e) { alert('Error: ' + e.message); }
}

// ── Auto-launch sprints loop ────────────────────────────────────────────────

let autoLaunchTimer = null;
let autoLaunchRunning = {};  // { sprintId: true } — sprints currently being auto-launched
let autoLaunchFinished = {};  // { sprintId: true } — sprints that completed auto-run (prevent re-launch loop)

function startAutoLaunchLoop() {
    if (autoLaunchTimer) return;
    console.log('[AutoLaunch] Loop started');
    autoLaunchTimer = setInterval(checkAndAutoLaunchReadySprints, 10000);
    // Run immediately on start too
    checkAndAutoLaunchReadySprints();
}

function stopAutoLaunchLoop() {
    if (autoLaunchTimer) {
        clearInterval(autoLaunchTimer);
        autoLaunchTimer = null;
        console.log('[AutoLaunch] Loop stopped');
    }
}

async function checkAndAutoLaunchReadySprints() {
    try {
        const sprintsData = await api('GET', '/api/sprints');
        const sprints = sprintsData.sprints || [];
        for (const sprint of sprints) {
            if (
                sprint.ready_to_execute &&
                sprint.status === 'active' &&
                !autoLaunchRunning[sprint.id] &&
                !autoLaunchFinished[sprint.id] &&
                !sprintAutoRunState[sprint.id]?.running
            ) {
                console.log(`[AutoLaunch] Launching sprint ${sprint.id}: ${sprint.title}`);
                autoLaunchRunning[sprint.id] = true;
                // Fire and forget — runAllSprintTasks handles its own lifecycle
                runAllSprintTasks(sprint.id).finally(() => {
                    delete autoLaunchRunning[sprint.id];
                    autoLaunchFinished[sprint.id] = true;  // Prevent re-launch after completion
                });
            }
        }
    } catch (e) {
        console.error('[AutoLaunch] Error checking sprints:', e);
    }
}

// ── Refresh ────────────────────────────────────────────────────────────────

async function refreshAll() {
    await Promise.all([checkStatus(), loadEmployees(), loadAgents(), fetchRunningTasks(), loadSprints(), loadGitStatus()]);
    updateRunningTasksIndicator();
}

async function loadSprints() {
    try {
        const data = await api('GET', '/api/sprints');
        allSprints = data.sprints || [];
    } catch {
        allSprints = [];
    }
}
