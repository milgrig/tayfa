// ── Agent Load Dashboard ────────────────────────────────────────────────────
// Polls GET /api/agents/metrics every 5s and renders a per-agent metrics table
// with status indicator, cost, request count bar, task ID, and token estimates.

let _agentLoadPollTimer = null;
let _agentLoadActiveWindow = 'last_60s';  // which time bucket to display
let _agentLoadLastData = null;

function showAgentLoadScreen() {
    saveCurrentDraft();
    hideAllScreens();
    document.getElementById('agentLoadScreen').style.display = 'flex';
    refreshAgentLoad();
    startAgentLoadPoll();
}

function startAgentLoadPoll() {
    if (_agentLoadPollTimer) return;
    _agentLoadPollTimer = setInterval(refreshAgentLoad, 5000);
}

function stopAgentLoadPoll() {
    if (_agentLoadPollTimer) {
        clearInterval(_agentLoadPollTimer);
        _agentLoadPollTimer = null;
    }
}

async function refreshAgentLoad() {
    try {
        const data = await api('GET', '/api/agents/metrics?window=60');
        _agentLoadLastData = data;
        renderAgentLoad(data);
    } catch (e) {
        const container = document.getElementById('agentLoadContainer');
        container.innerHTML = `<div class="empty-state">Failed to load metrics: ${escapeHtml(e.message)}</div>`;
    }
}

function switchAgentLoadWindow(windowKey) {
    _agentLoadActiveWindow = windowKey;
    // Update tab visuals
    document.querySelectorAll('.agent-load-window-tab').forEach(el => {
        el.classList.toggle('active', el.dataset.window === windowKey);
    });
    if (_agentLoadLastData) renderAgentLoad(_agentLoadLastData);
}

function _formatCost(val) {
    if (val === 0) return '$0.00';
    if (val < 0.01) return '$' + val.toFixed(4);
    return '$' + val.toFixed(2);
}

function _formatTokens(n) {
    if (n === 0) return '0';
    if (n >= 1_000_000) return (n / 1_000_000).toFixed(1) + 'M';
    if (n >= 1_000) return (n / 1_000).toFixed(1) + 'k';
    return String(n);
}

function _formatDuration(sec) {
    if (sec === 0) return '0s';
    if (sec < 60) return sec.toFixed(1) + 's';
    const m = Math.floor(sec / 60);
    const s = Math.round(sec % 60);
    return m + 'm ' + s + 's';
}

function renderAgentLoad(data) {
    const container = document.getElementById('agentLoadContainer');
    const agentsMap = data.agents || {};
    const agentNames = Object.keys(agentsMap);

    if (agentNames.length === 0) {
        container.innerHTML = '<div class="empty-state">No agents found</div>';
        return;
    }

    // Find the max request count for the bar scaling
    let maxReqs = 1;
    for (const name of agentNames) {
        const m = agentsMap[name];
        const bucket = m[_agentLoadActiveWindow] || m['total'] || {};
        if (bucket.request_count > maxReqs) maxReqs = bucket.request_count;
    }

    // Compute totals
    let totalCost = 0, totalDuration = 0, totalReqs = 0;
    let totalEstInput = 0, totalEstOutput = 0;
    let totalSessionCost = 0;
    let busyCount = 0;

    for (const name of agentNames) {
        const m = agentsMap[name];
        const bucket = m[_agentLoadActiveWindow] || m['total'] || {};
        totalCost += bucket.cost_usd || 0;
        totalDuration += bucket.duration_sec || 0;
        totalReqs += bucket.request_count || 0;
        totalEstInput += bucket.est_input_tokens || 0;
        totalEstOutput += bucket.est_output_tokens || 0;
        totalSessionCost += (m['total'] || {}).cost_usd || 0;
        if (m.is_busy) busyCount++;
    }

    // Window tabs
    const windowTabs = `
        <div class="agent-load-window-tabs">
            <button class="agent-load-window-tab ${_agentLoadActiveWindow === 'last_60s' ? 'active' : ''}"
                    data-window="last_60s" onclick="switchAgentLoadWindow('last_60s')">Last 60s</button>
            <button class="agent-load-window-tab ${_agentLoadActiveWindow === 'last_10m' ? 'active' : ''}"
                    data-window="last_10m" onclick="switchAgentLoadWindow('last_10m')">Last 10 min</button>
            <button class="agent-load-window-tab ${_agentLoadActiveWindow === 'total' ? 'active' : ''}"
                    data-window="total" onclick="switchAgentLoadWindow('total')">Total session</button>
        </div>
    `;

    // Build table rows
    let rows = '';
    for (const name of agentNames) {
        const m = agentsMap[name];
        const bucket = m[_agentLoadActiveWindow] || m['total'] || {};
        const reqs = bucket.request_count || 0;
        const cost = bucket.cost_usd || 0;
        const duration = bucket.duration_sec || 0;
        const estIn = bucket.est_input_tokens || 0;
        const estOut = bucket.est_output_tokens || 0;
        const barPct = maxReqs > 0 ? Math.round((reqs / maxReqs) * 100) : 0;

        const statusCls = m.is_busy ? 'busy' : 'idle';
        const taskHtml = m.current_task_id
            ? `<span class="agent-load-task">${escapeHtml(m.current_task_id)}</span>`
            : `<span class="agent-load-task none">--</span>`;

        const costCls = cost > 0.5 ? ' highlight' : '';

        rows += `
            <tr>
                <td>
                    <div class="agent-load-name">
                        <span class="agent-load-status ${statusCls}"></span>
                        <span class="agent-load-name-text">${escapeHtml(name)}</span>
                    </div>
                </td>
                <td>${taskHtml}</td>
                <td>
                    <span class="agent-load-bar-wrap"><span class="agent-load-bar" style="width:${barPct}%"></span></span>
                    <span class="agent-load-count">${reqs}</span>
                </td>
                <td><span class="agent-load-cost${costCls}">${_formatCost(cost)}</span></td>
                <td><span class="agent-load-cost">${_formatDuration(duration)}</span></td>
                <td><span class="agent-load-tokens">${_formatTokens(estIn)} in / ${_formatTokens(estOut)} out</span></td>
            </tr>
        `;
    }

    // Totals row
    const totalsRow = `
        <tr class="totals-row">
            <td>
                <div class="agent-load-name">
                    <span style="font-size:14px; margin-right:4px;">&#931;</span>
                    <span class="agent-load-name-text">Totals (${busyCount} busy)</span>
                </div>
            </td>
            <td></td>
            <td><span class="agent-load-count" style="font-weight:600;">${totalReqs}</span></td>
            <td><span class="agent-load-cost highlight">${_formatCost(totalCost)}</span></td>
            <td><span class="agent-load-cost">${_formatDuration(totalDuration)}</span></td>
            <td><span class="agent-load-tokens">${_formatTokens(totalEstInput)} in / ${_formatTokens(totalEstOutput)} out</span></td>
        </tr>
    `;

    // Session total summary
    const summaryHtml = `
        <div style="margin-top:16px; display:flex; gap:24px; padding:12px 16px; background:var(--bg-card); border:1px solid var(--border); border-radius:10px;">
            <div>
                <div style="font-size:11px; color:var(--text-dim); text-transform:uppercase; letter-spacing:0.5px; margin-bottom:4px;">Session Total Cost</div>
                <div style="font-size:20px; font-weight:700; font-family:var(--mono); color:var(--text-bright);">${_formatCost(totalSessionCost)}</div>
            </div>
            <div>
                <div style="font-size:11px; color:var(--text-dim); text-transform:uppercase; letter-spacing:0.5px; margin-bottom:4px;">Active Agents</div>
                <div style="font-size:20px; font-weight:700; color:${busyCount > 0 ? 'var(--success)' : 'var(--text-dim)'};">${busyCount} / ${agentNames.length}</div>
            </div>
            <div>
                <div style="font-size:11px; color:var(--text-dim); text-transform:uppercase; letter-spacing:0.5px; margin-bottom:4px;">Window Requests</div>
                <div style="font-size:20px; font-weight:700; font-family:var(--mono); color:var(--text-bright);">${totalReqs}</div>
            </div>
        </div>
    `;

    container.innerHTML = windowTabs + `
        <table class="agent-load-table">
            <thead>
                <tr>
                    <th>Agent</th>
                    <th>Task</th>
                    <th>Requests</th>
                    <th>Cost</th>
                    <th>Duration</th>
                    <th>Tokens (est.)</th>
                </tr>
            </thead>
            <tbody>
                ${rows}
                ${totalsRow}
            </tbody>
        </table>
    ` + summaryHtml;
}
