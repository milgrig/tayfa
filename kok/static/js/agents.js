// ── Model helpers ─────────────────────────────────────────────────────────

const _CURSOR_MODELS = new Set(['composer']);
const _CLAUDE_MODELS = new Set(['opus', 'sonnet', 'haiku']);

function _modelDisplayLabel(model) {
    if (_CURSOR_MODELS.has(model)) return 'Cursor ' + model.charAt(0).toUpperCase() + model.slice(1);
    if (_CLAUDE_MODELS.has(model)) return model.charAt(0).toUpperCase() + model.slice(1);
    return model;
}

function _modelIsComposer(model) {
    return _CURSOR_MODELS.has(model);
}

// ── Agents ─────────────────────────────────────────────────────────────────

async function loadAgents() {
    const list = document.getElementById('agentList');
    try {
        agents = await api('GET', '/api/agents');
        if (!agents || typeof agents !== 'object' || Object.keys(agents).length === 0) {
            list.innerHTML = '<li class="empty-state">No agents</li>';
            return;
        }
        list.innerHTML = '';
        for (const [name, config] of Object.entries(agents)) {
            // Initialize runtime from agent's current model
            if (!agentRuntimes[name]) {
                agentRuntimes[name] = config.model || config.default_runtime || 'sonnet';
            }
            const li = document.createElement('li');
            li.className = `agent-item ${name === currentAgent ? 'active' : ''}`;
            li.onclick = () => selectAgent(name);
            const model = config.model || 'sonnet';
            // Display model with provider prefix for clarity
            const modelLabel = _modelDisplayLabel(model);
            li.innerHTML = `
                <div style="flex:1; min-width:0;">
                    <div class="agent-name">${name}<span class="agent-model model-${model}">${modelLabel}</span></div>
                    <div class="agent-role">${escapeHtml(config.role || '')}</div>
                </div>
            `;
            list.appendChild(li);
        }
    } catch {
        list.innerHTML = '<li class="empty-state">API unavailable</li>';
    }
}

async function selectAgent(name) {
    // Save draft of previous agent before switching.
    // saveCurrentDraft() checks chatScreen visibility, so it only saves
    // when chat is actually shown (prevents clearing drafts on re-entry).
    saveCurrentDraft();

    currentAgent = name;
    hideAllScreens();
    document.getElementById('chatScreen').style.display = 'flex';
    document.getElementById('chatAgentName').textContent = name;

    // Ensure runtime is initialized from current model
    if (!agentRuntimes[name]) {
        const config = agents[name] || {};
        agentRuntimes[name] = config.model || 'sonnet';
    }

    document.querySelectorAll('.agent-item').forEach(el => el.classList.remove('active'));
    document.querySelectorAll('.agent-item').forEach(el => {
        if (el.querySelector('.agent-name')?.textContent === name) el.classList.add('active');
    });

    // Load history from API if not yet in memory
    if (!chatHistories[name] || chatHistories[name].length === 0) {
        await loadChatHistory(name);
    } else {
        renderChat();
    }

    // Show/hide indicator depending on whether this agent is thinking
    updateTypingIndicator(name);

    // Load draft of new agent
    const input = document.getElementById('promptInput');
    if (input) {
        input.value = agentDrafts[name] || '';
        autoGrow(input);  // Adjust field height
    }

    document.getElementById('promptInput').focus();

    // Open agent panel (streaming + config)
    if (typeof openAgentPanel === 'function') {
        openAgentPanel(name);
    }
}

// toggleAgentRuntime removed — model is now managed via Config panel only

function getAgentRuntime(agentName) {
    // Use model from agent config (set when loading agents or saving config)
    if (agentRuntimes[agentName]) return agentRuntimes[agentName];
    const config = agents[agentName] || {};
    return config.model || 'sonnet';
}

function isAgentCursor(agentName) {
    return _modelIsComposer(getAgentRuntime(agentName));
}

async function resetCurrentAgent() {
    if (!currentAgent || !confirm(`Reset memory of agent "${currentAgent}"?`)) return;
    try {
        await api('POST', '/api/reset-agent', { name: currentAgent });
        // Chat history is preserved — only add a visual separator
        addSystemMessage(`─── Memory of ${currentAgent} reset ───`);
        // DO NOT clear chatHistories[currentAgent] — history stays in UI
        // DO NOT call renderChat() — chat is not re-rendered
    } catch (e) { addSystemMessage('Error: ' + e.message, true); }
}

async function deleteCurrentAgent() {
    if (!currentAgent || !confirm(`Delete agent "${currentAgent}"?`)) return;
    try {
        await api('DELETE', `/api/agents/${currentAgent}`);
        addSystemMessage(`Agent ${currentAgent} deleted`);
        currentAgent = null;
        hideAllScreens();
        document.getElementById('welcomeScreen').style.display = 'flex';
        await loadAgents();
    } catch (e) { addSystemMessage('Error: ' + e.message, true); }
}

// ── Chat ───────────────────────────────────────────────────────────────────

// Format time for chat (hours:minutes only)
function formatChatTime(isoString) {
    if (!isoString) return '';
    const d = new Date(isoString);
    return d.toLocaleTimeString('en', { hour: '2-digit', minute: '2-digit' });
}

// Build metadata string for agent message
function buildChatMeta(msg) {
    const parts = [];
    if (msg.runtime) parts.push(msg.runtime);
    if (msg.cost_usd && msg.cost_usd > 0) parts.push(`$${msg.cost_usd.toFixed(4)}`);
    if (msg.duration_sec && msg.duration_sec > 0) parts.push(`${msg.duration_sec.toFixed(1)}s`);
    if (msg.task_id) parts.push(msg.task_id);
    if (msg.timestamp) parts.push(formatChatTime(msg.timestamp));
    return parts.join(' · ');
}

// Load chat history from API
async function loadChatHistory(agentName) {
    const area = document.getElementById('chatArea');
    area.innerHTML = '<div class="chat-loading"><div class="chat-loading-spinner"></div><span>Loading history...</span></div>';

    try {
        const data = await api('GET', `/api/chat-history/${agentName}?limit=50`);
        chatHistories[agentName] = [];

        // Convert API messages to chat format
        for (const msg of data.messages || []) {
            // User prompt
            if (msg.prompt) {
                chatHistories[agentName].push({
                    type: 'user',
                    text: msg.prompt,
                    meta: formatChatTime(msg.timestamp)
                });
            }
            // Agent response
            if (msg.result) {
                chatHistories[agentName].push({
                    type: msg.success === false ? 'error' : 'agent',
                    text: msg.result,
                    meta: buildChatMeta(msg)
                });
            }
        }

        renderChat();

        // Show empty state if no messages
        if (chatHistories[agentName].length === 0) {
            area.innerHTML = '<div class="chat-empty"><p>History is empty</p><p style="font-size:12px; margin-top:8px;">Send a message to the agent</p></div>';
        }
    } catch (e) {
        console.warn('[loadChatHistory] Loading error:', e.message);
        // If API does not support history — just initialize empty array
        chatHistories[agentName] = [];
        area.innerHTML = '<div class="chat-empty"><p>Start a conversation</p></div>';
    }
}

// Clear chat history
async function clearChatHistory() {
    if (!currentAgent || !confirm('Clear all chat history with this agent?')) return;
    try {
        await api('POST', `/api/chat-history/${currentAgent}/clear`);
        chatHistories[currentAgent] = [];
        renderChat();
        addSystemMessage('Chat history cleared');
    } catch (e) {
        addSystemMessage('Error: ' + e.message, true);
    }
}

function renderChat() {
    const area = document.getElementById('chatArea');
    area.innerHTML = '';
    const history = chatHistories[currentAgent] || [];
    for (const msg of history) {
        const div = document.createElement('div');
        div.className = `message ${msg.type}`;
        div.textContent = msg.text;
        if (msg.meta) {
            const metaDiv = document.createElement('div');
            metaDiv.className = 'meta';
            metaDiv.innerHTML = msg.meta;
            div.appendChild(metaDiv);
        }
        area.appendChild(div);
    }
    area.scrollTop = area.scrollHeight;
}

function addChatMessage(agent, type, text, meta = '') {
    if (!chatHistories[agent]) chatHistories[agent] = [];
    chatHistories[agent].push({ type, text, meta });
    if (agent === currentAgent) renderChat();
}

function addSystemMessage(text, isError = false) {
    if (currentAgent) addChatMessage(currentAgent, isError ? 'error' : 'system', text);
    console.log(`[${isError ? 'ERR' : 'SYS'}] ${text}`);
}

function updateTypingIndicator(agentName) {
    const indicator = document.getElementById('typingIndicator');
    indicator.classList.toggle('show', !!thinkingAgents[agentName]);
}

async function sendPrompt() {
    if (!currentAgent) return;

    // Use streaming when panel is open and model is not a Cursor model
    const runtime = getAgentRuntime(currentAgent);
    if (!isAgentCursor(currentAgent) && typeof sendPromptStreaming === 'function' && panelOpen) {
        return sendPromptStreaming();
    }

    const input = document.getElementById('promptInput');
    const text = input.value.trim();
    if (!text) return;
    input.value = ''; input.style.height = 'auto';

    // Clear draft of current agent after sending
    delete agentDrafts[currentAgent];

    addChatMessage(currentAgent, 'user', text);

    const agentForRequest = currentAgent;  // Save agent for this request
    const btn = document.getElementById('btnSend');
    btn.disabled = true; btn.textContent = '...';

    // Set "thinking" state for this agent
    thinkingAgents[agentForRequest] = true;
    updateTypingIndicator(currentAgent);

    try {
        if (isAgentCursor(agentForRequest)) {
            const result = await api('POST', '/api/send-prompt-cursor', { name: agentForRequest, prompt: text });
            if (result.success) {
                addChatMessage(agentForRequest, 'agent', result.result || '(Empty response)', result.stderr ? `Cursor CLI` : 'Cursor CLI');
            } else {
                addChatMessage(agentForRequest, 'error', (result.stderr || result.result || 'Cursor CLI Error').trim());
            }
        } else {
            const result = await api('POST', '/api/send-prompt', { name: agentForRequest, prompt: text, runtime: runtime });
            const response = result.result || result.stdout || JSON.stringify(result);
            const meta = [];
            if (result.cost_usd) meta.push(`$${result.cost_usd.toFixed(4)}`);
            if (result.num_turns) meta.push(`${result.num_turns} turns`);
            addChatMessage(agentForRequest, 'agent', response, meta.join(' &middot; '));
        }
    } catch (e) {
        addChatMessage(agentForRequest, 'error', 'Error: ' + e.message);
    } finally {
        btn.disabled = false; btn.textContent = 'Send';
        // Remove "thinking" state for this agent
        delete thinkingAgents[agentForRequest];
        updateTypingIndicator(currentAgent);
    }
}

function handleKeyDown(e) { if (e.key === 'Enter' && !e.shiftKey) { e.preventDefault(); sendPrompt(); } }
function autoGrow(el) { el.style.height = 'auto'; el.style.height = Math.min(el.scrollHeight, 200) + 'px'; }

// ── Ensure Agents ──────────────────────────────────────────────────────────

async function ensureAgents() {
    addSystemMessage('Checking agents...');
    try {
        const body = {};
        try {
            const cur = await api('GET', '/api/current-project');
            if (cur && cur.path) body.project_path = cur.path;
        } catch (_) {}
        const result = await api('POST', '/api/ensure-agents', Object.keys(body).length ? body : undefined);
        for (const r of result.results) {
            addSystemMessage(`Agent "${r.agent}": ${r.status}`, r.status === 'error');
        }
        await loadAgents();
    } catch (e) { addSystemMessage('Error: ' + e.message, true); }
}

async function killAllAgents() {
    addSystemMessage('Deleting all agents...');
    try {
        const body = {};
        try {
            const cur = await api('GET', '/api/current-project');
            if (cur && cur.path) body.project_path = cur.path;
        } catch (_) {}
        const result = await api('POST', '/api/kill-agents?stop_server=false', Object.keys(body).length ? body : undefined);
        addSystemMessage('All agents deleted. Use \'Provision agents\' to restore.');
        await loadAgents();
    } catch (e) {
        addSystemMessage('Error deleting agents: ' + e.message, true);
    }
}

async function createCursorChats() {
    addSystemMessage('Creating Cursor chats...');
    try {
        const result = await api('POST', '/api/cursor-create-chats');
        for (const r of result.results || []) {
            if (r.created && r.chat_id) addSystemMessage(`Cursor chat "${r.agent}": ${r.chat_id}`);
            else if (r.chat_id) addSystemMessage(`Chat "${r.agent}" already exists`);
            else addSystemMessage(`"${r.agent}": ${r.error || 'not created'}`, true);
        }
    } catch (e) { addSystemMessage('Error: ' + e.message, true); }
}

// ── Running tasks header indicator ─────────────────────────────────────────

function updateRunningTasksIndicator() {
    const count = Object.keys(runningTasks).length;
    const el = document.getElementById('runningTasksIndicator');
    const countEl = document.getElementById('runningTasksCount');
    if (count > 0) {
        el.style.display = 'flex';
        countEl.textContent = count;
    } else {
        el.style.display = 'none';
    }
}

// Global polling of running tasks (not only when board is visible)
let globalRunningPollTimer = null;

function startGlobalRunningPoll() {
    if (globalRunningPollTimer) return;
    globalRunningPollTimer = setInterval(async () => {
        await fetchRunningTasks();
        updateRunningTasksIndicator();
    }, 1000);
}
