// ── Agent Panel (streaming + config) ─────────────────────────────────────────

let panelOpen = false;
let panelAgent = null;
let activeStreamAbort = null;
let _lastMsgId = null;        // Track last message ID to avoid duplicate text
let _msgTextNode = null;      // Dedicated node for message-type events
let _activityPollTimer = null; // Polls agent activity while busy
let _taskStreamAbort = null;  // Abort controller for task stream SSE connection
let _streamOwner = null;      // Name of agent whose stream is currently displayed
const _agentStreamCache = {}; // Per-agent stream HTML cache: { name: innerHTML }

function _saveStreamCache() {
    if (_streamOwner) {
        const container = document.getElementById('streamContent');
        if (container) _agentStreamCache[_streamOwner] = container.innerHTML;
    }
}

function openAgentPanel(name) {
    if (!name) return;

    // Save current agent's stream before switching
    _saveStreamCache();

    panelAgent = name;
    panelOpen = true;

    const panel = document.getElementById('agentPanel');
    panel.style.display = 'flex';
    document.querySelector('.main').classList.add('panel-open');

    document.getElementById('agentPanelName').textContent = name;

    // Disconnect previous agent's task stream and polling
    _stopActivityPoll();
    _disconnectTaskStream();

    // Restore this agent's stream from cache (or start empty)
    _streamOwner = name;
    const container = document.getElementById('streamContent');
    const cached = _agentStreamCache[name];
    if (cached) {
        container.innerHTML = cached;
        document.getElementById('streamEmpty').style.display = 'none';
    } else {
        container.innerHTML = '';
        document.getElementById('streamEmpty').style.display = 'flex';
    }
    _lastMsgId = null;
    _msgTextNode = null;
    _streamTextNode = null;

    // Load config
    loadAgentConfig(name);

    // Check if agent is busy with a task and show activity
    _checkAgentActivity(name);
}

function closeAgentPanel() {
    panelOpen = false;
    panelAgent = null;
    _streamOwner = null;
    _stopActivityPoll();
    _disconnectTaskStream();

    const panel = document.getElementById('agentPanel');
    panel.style.display = 'none';
    document.querySelector('.main').classList.remove('panel-open');
}

function switchPanelTab(tab) {
    // Update tab buttons
    document.querySelectorAll('.agent-panel-tab').forEach(t => {
        t.classList.toggle('active', t.dataset.tab === tab);
    });

    // Show/hide content
    document.getElementById('agentStreamTab').style.display = tab === 'stream' ? '' : 'none';
    document.getElementById('agentConfigTab').style.display = tab === 'config' ? '' : 'none';
}

// ── Config ───────────────────────────────────────────────────────────────────

async function loadAgentConfig(name) {
    if (!name) return;
    try {
        const config = await api('GET', `/api/agent-config/${name}`);
        document.getElementById('cfgModel').value = config.model || '';
        document.getElementById('cfgAllowedTools').value = config.allowed_tools || '';
        document.getElementById('cfgPermissionMode').value = config.permission_mode || 'bypassPermissions';
        document.getElementById('cfgBudgetLimit').value = config.budget_limit ?? 10;
        document.getElementById('cfgWorkdir').value = config.workdir || '';
        document.getElementById('cfgSystemPromptFile').value = config.system_prompt_file || '';
        document.getElementById('cfgSystemPrompt').value = config.system_prompt || '';

        // Sessions display
        const sessions = config.session_id || {};
        const sessEl = document.getElementById('cfgSessions');
        if (typeof sessions === 'object' && Object.keys(sessions).length > 0) {
            sessEl.innerHTML = Object.entries(sessions)
                .map(([model, sid]) => `${model}: ${sid ? sid.substring(0, 8) + '...' : 'none'}`)
                .join('<br>');
        } else {
            sessEl.innerHTML = '<span style="color:var(--text-dim)">No active sessions</span>';
        }
    } catch (e) {
        console.error('Failed to load agent config:', e);
    }
}

async function saveAgentConfig() {
    if (!panelAgent) return;
    const data = {};

    const model = document.getElementById('cfgModel').value;
    const tools = document.getElementById('cfgAllowedTools').value.trim();
    const perm = document.getElementById('cfgPermissionMode').value;
    const budget = parseFloat(document.getElementById('cfgBudgetLimit').value);
    const workdir = document.getElementById('cfgWorkdir').value.trim();
    const promptFile = document.getElementById('cfgSystemPromptFile').value.trim();
    const prompt = document.getElementById('cfgSystemPrompt').value.trim();

    if (model) data.model = model;
    if (tools) data.allowed_tools = tools;
    if (perm) data.permission_mode = perm;
    if (!isNaN(budget)) data.budget_limit = budget;
    if (workdir) data.workdir = workdir;
    if (promptFile) data.system_prompt_file = promptFile;
    if (prompt) data.system_prompt = prompt;

    try {
        await api('PUT', `/api/agent-config/${panelAgent}`, data);
        addSystemMessage(`Config updated for ${panelAgent}`);
        // Update runtime and badge in employee list when model changes
        if (model) {
            agentRuntimes[panelAgent] = model;
            if (agents[panelAgent]) agents[panelAgent].model = model;
            await loadAgents();
        }
    } catch (e) {
        alert('Error saving config: ' + e.message);
    }
}

async function resetAgentSession() {
    if (!panelAgent) return;
    if (!confirm(`Reset all sessions for ${panelAgent}?`)) return;

    try {
        await api('POST', `/api/agent-config/${panelAgent}/reset-session`, {});
        addSystemMessage(`Sessions cleared for ${panelAgent}`);
        loadAgentConfig(panelAgent);
    } catch (e) {
        alert('Error: ' + e.message);
    }
}

// ── Streaming ────────────────────────────────────────────────────────────────

function appendStreamEvent(type, text) {
    const container = document.getElementById('streamContent');
    const empty = document.getElementById('streamEmpty');
    if (empty) empty.style.display = 'none';

    const div = document.createElement('div');
    div.className = `stream-event ${type}`;

    switch (type) {
        case 'thinking':
            div.textContent = text;
            break;
        case 'tool':
            div.textContent = text;
            break;
        case 'text':
            div.textContent = text;
            break;
        case 'error':
            div.textContent = text;
            break;
        case 'result':
            div.textContent = text;
            break;
        default:
            div.textContent = text;
    }

    container.appendChild(div);

    // Auto-scroll
    const streamTab = document.getElementById('agentStreamTab');
    streamTab.scrollTop = streamTab.scrollHeight;
}

function clearStream() {
    document.getElementById('streamContent').innerHTML = '';
    document.getElementById('streamEmpty').style.display = 'flex';
    _lastMsgId = null;
    _msgTextNode = null;
    // Also clear cache for current agent
    if (_streamOwner) delete _agentStreamCache[_streamOwner];
}

// Current text accumulator for streaming deltas
let _streamTextNode = null;
let _pendingTool = null;  // Tracks tool_use being streamed: { name, inputJson }

async function sendPromptStreaming() {
    if (!currentAgent) return;
    const input = document.getElementById('promptInput');
    const text = input.value.trim();
    if (!text) return;
    input.value = ''; input.style.height = 'auto';

    // Clear draft
    delete agentDrafts[currentAgent];

    addChatMessage(currentAgent, 'user', text);

    const agentForRequest = currentAgent;
    const btn = document.getElementById('btnSend');
    btn.disabled = true; btn.textContent = '...';

    thinkingAgents[agentForRequest] = true;
    updateTypingIndicator(currentAgent);

    // Clear stream panel and switch to stream tab
    clearStream();
    _streamOwner = agentForRequest;
    if (panelOpen) switchPanelTab('stream');

    const runtime = getAgentRuntime(agentForRequest);
    _streamTextNode = null;

    // Abort controller for cancellation
    const abortController = new AbortController();
    activeStreamAbort = abortController;

    try {
        const response = await fetch('/api/send-prompt-stream', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
                name: agentForRequest,
                prompt: text,
                runtime: runtime
            }),
            signal: abortController.signal
        });

        if (!response.ok) {
            const err = await response.text();
            addChatMessage(agentForRequest, 'error', 'Error: ' + err);
            return;
        }

        const reader = response.body.getReader();
        const decoder = new TextDecoder();
        let buffer = '';
        let fullResult = '';
        let costUsd = 0;
        let numTurns = 0;

        while (true) {
            const { done, value } = await reader.read();
            if (done) break;

            buffer += decoder.decode(value, { stream: true });
            const lines = buffer.split('\n');
            buffer = lines.pop(); // Keep incomplete line in buffer

            for (const line of lines) {
                if (!line.startsWith('data: ')) continue;
                const jsonStr = line.substring(6).trim();
                if (!jsonStr) continue;

                try {
                    let event = JSON.parse(jsonStr);
                    // Unwrap stream_event wrapper before processing
                    if (event.type === 'stream_event' && event.event) {
                        event = event.event;
                    }
                    // Only render to stream panel if this agent is still selected
                    if (_streamOwner === agentForRequest) {
                        processStreamEvent(event);
                    }

                    // Accumulate result
                    if (event.type === 'result') {
                        fullResult = event.result || fullResult;
                        costUsd = event.cost_usd || 0;
                        numTurns = event.num_turns || 0;
                    } else if (event.type === 'message' && Array.isArray(event.content)) {
                        // Full message object — take last text block as full result (replaces prior)
                        for (const block of event.content) {
                            if (block.type === 'text' && block.text) {
                                fullResult = block.text;
                            }
                        }
                    } else if (event.type === 'assistant' && (event.subtype === 'text' || event.subtype === 'text_delta')) {
                        fullResult += (event.delta || event.text || '');
                    } else if (event.type === 'content_block_delta' && event.delta?.type === 'text_delta') {
                        fullResult += (event.delta.text || '');
                    } else if (event.type === 'streamlined_text' && event.text) {
                        fullResult = event.text;
                    }
                } catch (parseErr) {
                    // Skip unparseable lines
                }
            }
        }

        // Add final message to chat
        const meta = [];
        if (costUsd) meta.push(`$${costUsd.toFixed(4)}`);
        if (numTurns) meta.push(`${numTurns} turns`);
        if (fullResult) {
            addChatMessage(agentForRequest, 'agent', fullResult, meta.join(' &middot; '));
        }

    } catch (e) {
        if (e.name !== 'AbortError') {
            addChatMessage(agentForRequest, 'error', 'Error: ' + e.message);
        }
    } finally {
        btn.disabled = false; btn.textContent = 'Send';
        delete thinkingAgents[agentForRequest];
        updateTypingIndicator(currentAgent);
        activeStreamAbort = null;
        _streamTextNode = null;
    }
}

function processStreamEvent(event) {
    // Unwrap stream_event wrapper (Claude CLI stream-json format)
    // {"type": "stream_event", "event": {"type": "content_block_delta", ...}}
    if (event.type === 'stream_event' && event.event) {
        return processStreamEvent(event.event);
    }

    const type = event.type || '';
    const subtype = event.subtype || '';

    if (type === 'assistant') {
        if (subtype === 'text_delta' || subtype === 'text') {
            _appendTextDelta(event.delta || event.text || '');
        } else if (subtype === 'thinking') {
            _streamTextNode = null;
            appendStreamEvent('thinking', event.delta || event.text || '');
        } else {
            // Unknown assistant subtype — only show string text content (never raw JSON)
            const val = event.delta || event.text || '';
            if (typeof val === 'string' && val) _appendTextDelta(val);
        }

    } else if (type === 'content_block_start') {
        _streamTextNode = null;
        _pendingTool = null;
        const block = event.content_block || {};
        if (block.type === 'thinking') {
            appendStreamEvent('thinking', block.text || '');
        } else if (block.type === 'tool_use') {
            const bName = block.name || 'tool';
            // Track this tool — input will accumulate via input_json_delta
            _pendingTool = { name: bName, inputJson: '' };
            // Show tool label immediately (except AskUserQuestion — wait for full input)
            if (bName !== 'AskUserQuestion') {
                appendStreamEvent('tool', _formatToolUse(bName, block.input));
            }
        }
        // text blocks — wait for deltas

    } else if (type === 'content_block_delta') {
        const delta = event.delta || {};
        if (delta.type === 'thinking_delta') {
            appendStreamEvent('thinking', delta.text || '');
        } else if (delta.type === 'text_delta') {
            _appendTextDelta(delta.text || '');
        } else if (delta.type === 'input_json_delta') {
            // Accumulate tool input JSON fragments
            if (_pendingTool) _pendingTool.inputJson += (delta.partial_json || '');
        } else {
            // Unknown delta type — only show if it has text content (never raw JSON)
            const val = delta.text || '';
            if (val) _appendTextDelta(val);
        }

    } else if (type === 'content_block_stop') {
        _streamTextNode = null;
        // If we accumulated a tool with deferred rendering — render now
        if (_pendingTool && _pendingTool.name === 'AskUserQuestion' && _pendingTool.inputJson) {
            try {
                const fullInput = JSON.parse(_pendingTool.inputJson);
                _renderAskUserQuestionButtons(fullInput);
            } catch (e) {
                appendStreamEvent('question', '❓ Agent is asking a question');
            }
        }
        _pendingTool = null;

    } else if (type === 'tool_use') {
        _streamTextNode = null;
        const toolName = event.name || event.tool || 'tool';
        if (toolName === 'AskUserQuestion') {
            _renderAskUserQuestionButtons(event.input);
        } else {
            appendStreamEvent('tool', _formatToolUse(toolName, event.input));
        }

    } else if (type === 'tool_result') {
        let content = event.content || '';
        // content can be a string, an array of content blocks, or an object
        if (Array.isArray(content)) {
            // Extract text from content blocks (e.g. [{type:"text", text:"..."}])
            content = content
                .filter(b => b && b.type === 'text' && b.text)
                .map(b => b.text)
                .join('\n');
        } else if (typeof content !== 'string') {
            content = '';  // Skip non-text content (don't show raw JSON)
        }
        if (content && content.length < 200) {
            appendStreamEvent('text', `  => ${content}`);
        }

    } else if (type === 'result') {
        _streamTextNode = null;
        const parts = [];
        if (event.cost_usd) parts.push(`$${event.cost_usd.toFixed(4)}`);
        if (event.num_turns) parts.push(`${event.num_turns} turns`);
        appendStreamEvent('result', `Done${parts.length ? ' \u2022 ' + parts.join(' \u2022 ') : ''}`);

    } else if (type === 'error') {
        _streamTextNode = null;
        appendStreamEvent('error', event.error || 'Unknown error');

    } else if (type === 'raw') {
        appendStreamEvent('text', event.content || '');

    } else if (type === 'message') {
        // Full API message object from Claude CLI --verbose stream-json.
        // Each event contains full accumulated content (not deltas).
        // Use message ID to detect same-message updates vs new messages.
        const contentArr = event.content;
        if (!Array.isArray(contentArr)) return;

        const msgId = event.id || '';

        // If this is the same message ID, replace the text node
        if (msgId && msgId === _lastMsgId && _msgTextNode) {
            // Update text in-place (same message, more content accumulated)
            const textBlocks = contentArr.filter(b => b.type === 'text' && b.text);
            if (textBlocks.length) {
                _msgTextNode.textContent = textBlocks.map(b => b.text).join('\n');
            }
        } else {
            // New message — process each content block
            _lastMsgId = msgId;
            _streamTextNode = null;
            _msgTextNode = null;

            for (const block of contentArr) {
                if (block.type === 'text' && block.text) {
                    _msgTextNode = document.createElement('div');
                    _msgTextNode.className = 'stream-event text';
                    _msgTextNode.textContent = block.text;
                    document.getElementById('streamContent').appendChild(_msgTextNode);
                    const empty = document.getElementById('streamEmpty');
                    if (empty) empty.style.display = 'none';
                } else if (block.type === 'tool_use') {
                    const bName = block.name || 'tool';
                    if (bName === 'AskUserQuestion') {
                        _renderAskUserQuestionButtons(block.input);
                    } else {
                        appendStreamEvent('tool', _formatToolUse(bName, block.input));
                    }
                } else if (block.type === 'thinking' && block.text) {
                    appendStreamEvent('thinking', block.text);
                }
            }
        }

        // Auto-scroll
        const streamTab = document.getElementById('agentStreamTab');
        streamTab.scrollTop = streamTab.scrollHeight;

    } else if (type === 'streamlined_text') {
        // Claude CLI v2: final text content (replaces assistant message in streamlined output)
        _streamTextNode = null;
        if (event.text) {
            appendStreamEvent('text', event.text);
        }

    } else if (type === 'streamlined_tool_use_summary') {
        // Claude CLI v2: summary of tool calls (e.g. "Read 2 files, wrote 1 file")
        _streamTextNode = null;
        if (event.tool_summary) {
            appendStreamEvent('tool', event.tool_summary);
        }

    } else if (type === 'system' || type === 'user' || type === 'message_start' || type === 'message_delta' || type === 'message_stop' || type === 'keep_alive') {
        // Internal metadata / lifecycle / heartbeat — skip

    } else {
        // Unknown event type — log only, don't pollute stream
        console.log('[Stream] unknown event:', event);
    }
}

function _appendTextDelta(text) {
    if (!text) return;
    if (!_streamTextNode) {
        _streamTextNode = document.createElement('div');
        _streamTextNode.className = 'stream-event text';
        document.getElementById('streamContent').appendChild(_streamTextNode);
    }
    _streamTextNode.textContent += text;
    const streamTab = document.getElementById('agentStreamTab');
    streamTab.scrollTop = streamTab.scrollHeight;
}

function _formatToolUse(toolName, input) {
    if (!input || typeof input !== 'object') return toolName;

    // Extract the most useful parameter for each known tool
    switch (toolName) {
        case 'Read':
            return `Read → ${_shortPath(input.file_path)}`;
        case 'Write':
            return `Write → ${_shortPath(input.file_path)}`;
        case 'Edit':
            return `Edit → ${_shortPath(input.file_path)}`;
        case 'Glob':
            return `Glob → ${input.pattern || ''}${input.path ? '  in ' + _shortPath(input.path) : ''}`;
        case 'Grep':
            return `Grep → "${_truncStr(input.pattern || '', 40)}"${input.path ? '  in ' + _shortPath(input.path) : ''}`;
        case 'Bash': {
            const cmd = input.description || input.command || '';
            return `Bash → ${_truncStr(cmd, 100)}`;
        }
        case 'Task':
            return `Task → ${_truncStr(input.description || '', 60)}`;
        case 'WebFetch':
            return `WebFetch → ${_truncStr(input.url || '', 80)}`;
        case 'WebSearch':
            return `WebSearch → "${_truncStr(input.query || '', 60)}"`;
        case 'TodoWrite':
            return `TodoWrite (${(input.todos || []).length} items)`;
        case 'NotebookEdit':
            return `NotebookEdit → ${_shortPath(input.notebook_path)}`;
        case 'AskUserQuestion': {
            const q = (input.questions || [])[0];
            return q ? `❓ ${_truncStr(q.question || '', 80)}` : '❓ Agent is asking a question';
        }
        default: {
            // Generic: show first string value
            const vals = Object.values(input);
            const first = vals.find(v => typeof v === 'string' && v.length > 0);
            if (first) return `${toolName} → ${_truncStr(first, 80)}`;
            return `${toolName}(${Object.keys(input).join(', ')})`;
        }
    }
}

function _formatAskUserQuestion(input) {
    if (!input || !input.questions || !Array.isArray(input.questions)) return '❓ Agent is asking a question';
    const parts = ['❓ Agent is asking:'];
    for (const q of input.questions) {
        parts.push(q.question || '(no question text)');
        if (Array.isArray(q.options)) {
            for (const opt of q.options) {
                parts.push(`  • ${opt.label}${opt.description ? ' — ' + opt.description : ''}`);
            }
        }
    }
    return parts.join('\n');
}

/**
 * Render AskUserQuestion as interactive buttons in the Stream panel.
 * Clicking a button sends the answer as a prompt directly to the agent
 * that asked the question (uses panelAgent, not currentAgent).
 */
function _renderAskUserQuestionButtons(input) {
    const container = document.getElementById('streamContent');
    const empty = document.getElementById('streamEmpty');
    if (empty) empty.style.display = 'none';

    const div = document.createElement('div');
    div.className = 'stream-event question';

    if (!input || !input.questions || !Array.isArray(input.questions)) {
        div.textContent = '❓ Agent is asking a question';
        container.appendChild(div);
        return;
    }

    // Capture which agent asked — use panelAgent (the agent whose stream we're viewing)
    const askingAgent = panelAgent || currentAgent;

    for (const q of input.questions) {
        // Question text
        const textEl = document.createElement('div');
        textEl.className = 'question-text';
        textEl.textContent = '❓ ' + (q.question || '(no question text)');
        div.appendChild(textEl);

        // Buttons container
        if (Array.isArray(q.options) && q.options.length > 0) {
            const btnsWrap = document.createElement('div');
            btnsWrap.className = 'question-buttons';

            for (const opt of q.options) {
                const btn = document.createElement('button');
                btn.className = 'question-btn';
                btn.textContent = opt.label;
                if (opt.description) btn.title = opt.description;

                btn.addEventListener('click', () => {
                    // Disable all buttons in this group
                    btnsWrap.querySelectorAll('.question-btn').forEach(b => { b.disabled = true; });
                    btn.classList.add('selected');

                    // If the asking agent is the current chat agent, use full streaming flow
                    if (askingAgent === currentAgent) {
                        const promptInput = document.getElementById('promptInput');
                        if (promptInput) {
                            promptInput.value = opt.label;
                            sendPromptStreaming();
                        }
                    } else {
                        // Different agent — send via non-streaming API (fire-and-forget)
                        const runtime = getAgentRuntime(askingAgent);
                        api('POST', '/api/send-prompt', {
                            name: askingAgent,
                            prompt: opt.label,
                            runtime: runtime
                        }).catch(e => console.error('[QuestionBtn] Error:', e));
                    }
                });

                btnsWrap.appendChild(btn);
            }

            div.appendChild(btnsWrap);
        }
    }

    container.appendChild(div);

    // Auto-scroll
    const streamTab = document.getElementById('agentStreamTab');
    if (streamTab) streamTab.scrollTop = streamTab.scrollHeight;
}

function _shortPath(p) {
    if (!p) return '...';
    const norm = p.replace(/\\/g, '/');
    const parts = norm.split('/').filter(Boolean);
    if (parts.length <= 2) return parts.join('/');
    return '…/' + parts.slice(-2).join('/');
}

function _truncStr(s, max) {
    if (!s) return '';
    return s.length > max ? s.substring(0, max) + '…' : s;
}

// ── Agent Activity Indicator ────────────────────────────────────────────────

function _stopActivityPoll() {
    if (_activityPollTimer) {
        clearInterval(_activityPollTimer);
        _activityPollTimer = null;
    }
}

function _formatElapsed(seconds) {
    const m = Math.floor(seconds / 60);
    const s = seconds % 60;
    return m > 0 ? `${m}m ${s}s` : `${s}s`;
}

async function _checkAgentActivity(name) {
    if (name !== panelAgent) return;
    try {
        const activity = await api('GET', `/api/agent-activity/${name}`);
        if (name !== panelAgent) return; // Agent changed while waiting

        if (activity.busy) {
            _showAgentBusy(activity);
            // Connect to live stream to show agent's thoughts
            _connectTaskStream(name);
            // Start polling to update elapsed time and detect completion
            _stopActivityPoll();
            _activityPollTimer = setInterval(() => _pollAgentActivity(name), 2000);
        } else if (!_agentStreamCache[name]) {
            // Agent idle, no cached stream — try to load replay from backend buffer
            // (last task execution). If backend has no buffer, SSE returns empty.
            _connectTaskStream(name);
        }
    } catch (e) {
        console.warn('[AgentActivity] Error checking activity:', e.message);
    }
}

async function _pollAgentActivity(name) {
    if (name !== panelAgent) { _stopActivityPoll(); return; }
    try {
        const activity = await api('GET', `/api/agent-activity/${name}`);
        if (name !== panelAgent) { _stopActivityPoll(); return; }

        if (activity.busy) {
            _updateAgentBusy(activity);
        } else {
            // Agent finished — clear indicator, stop polling, disconnect stream
            _stopActivityPoll();
            _disconnectTaskStream();
            _clearAgentBusy();
        }
    } catch (e) {
        console.warn('[AgentActivity] Poll error:', e.message);
    }
}

function _showAgentBusy(activity) {
    const container = document.getElementById('streamContent');
    const empty = document.getElementById('streamEmpty');

    // Only show if stream is currently empty (don't overwrite active stream)
    if (container.children.length > 0 && !container.querySelector('.agent-busy-indicator')) return;

    if (empty) empty.style.display = 'none';

    // Remove existing busy indicator if any
    const existing = container.querySelector('.agent-busy-indicator');
    if (existing) existing.remove();

    const taskTitle = _getTaskTitle(activity.task_id);

    const div = document.createElement('div');
    div.className = 'agent-busy-indicator';
    div.innerHTML = `
        <div class="busy-spinner-wrap">
            <div class="spinner"></div>
        </div>
        <div class="busy-info">
            <div class="busy-title">Agent is working on a task</div>
            <div class="busy-task">
                <span class="busy-task-id">${activity.task_id}</span>
                <span class="busy-task-title">${taskTitle ? ' — ' + escapeHtml(taskTitle) : ''}</span>
            </div>
            <div class="busy-meta">
                <span class="busy-role">${activity.role || ''}</span>
                <span class="busy-sep">·</span>
                <span class="busy-runtime">${activity.runtime || ''}</span>
                <span class="busy-sep">·</span>
                <span class="busy-elapsed">${_formatElapsed(activity.elapsed_seconds || 0)}</span>
            </div>
        </div>
    `;
    container.appendChild(div);
}

function _updateAgentBusy(activity) {
    const el = document.querySelector('.agent-busy-indicator');
    if (!el) { _showAgentBusy(activity); return; }

    const elapsed = el.querySelector('.busy-elapsed');
    if (elapsed) elapsed.textContent = _formatElapsed(activity.elapsed_seconds || 0);
}

function _clearAgentBusy() {
    const el = document.querySelector('.agent-busy-indicator');
    if (el) {
        // Replace with "completed" message
        el.innerHTML = `
            <div class="busy-info" style="text-align:center;">
                <div class="busy-title" style="color:var(--success);">✓ Task completed</div>
                <div class="busy-meta" style="margin-top:4px;">Agent is now idle</div>
            </div>
        `;
        // Auto-remove after 5 seconds
        setTimeout(() => {
            if (el.parentNode) el.remove();
            const container = document.getElementById('streamContent');
            if (container && container.children.length === 0) {
                const empty = document.getElementById('streamEmpty');
                if (empty) empty.style.display = 'flex';
            }
        }, 5000);
    }
}

function _getTaskTitle(taskId) {
    // Try to find task title from allTasks cache (board.js global)
    if (typeof allTasks !== 'undefined' && Array.isArray(allTasks)) {
        const task = allTasks.find(t => t.id === taskId);
        if (task) return task.title;
    }
    return '';
}

// ── Live Task Stream (SSE connection to agent's task execution) ──────────────

function _disconnectTaskStream() {
    if (_taskStreamAbort) {
        _taskStreamAbort.abort();
        _taskStreamAbort = null;
    }
}

async function _connectTaskStream(name) {
    // Disconnect any previous task stream
    _disconnectTaskStream();

    const abortController = new AbortController();
    _taskStreamAbort = abortController;
    // Capture owner at connection time — if panel switches, this connection stops rendering
    const myOwner = name;

    _streamTextNode = null;

    try {
        const response = await fetch(`/api/agent-stream/${name}`, {
            signal: abortController.signal
        });

        if (!response.ok) {
            console.warn('[TaskStream] Failed to connect:', response.status);
            return;
        }

        const reader = response.body.getReader();
        const decoder = new TextDecoder();
        let buffer = '';

        while (true) {
            // If this connection was superseded, stop immediately
            if (_taskStreamAbort !== abortController) return;

            const { done, value } = await reader.read();
            if (done) break;

            // Double-check: panel may have switched during read()
            if (_streamOwner !== myOwner) return;

            buffer += decoder.decode(value, { stream: true });
            const lines = buffer.split('\n');
            buffer = lines.pop(); // Keep incomplete line in buffer

            for (const line of lines) {
                if (!line.startsWith('data: ')) continue;
                const jsonStr = line.substring(6).trim();
                if (!jsonStr) continue;

                try {
                    const event = JSON.parse(jsonStr);

                    // Stream ended — stop
                    if (event.type === 'stream_end') return;

                    // Skip keep-alive heartbeats
                    if (event.type === 'keep_alive') continue;

                    // Process the event (reuse the same handler as manual chat streaming)
                    processStreamEvent(event);
                } catch (parseErr) {
                    // Skip unparseable lines
                }
            }
        }
    } catch (e) {
        if (e.name !== 'AbortError') {
            console.warn('[TaskStream] Connection error:', e.message);
        }
    } finally {
        if (_taskStreamAbort === abortController) {
            _taskStreamAbort = null;
        }
    }
}
