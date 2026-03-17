// ── Backlog Functions ──────────────────────────────────────────────────────

let allBacklogItems = [];

function showBacklogScreen() {
    saveCurrentDraft();
    hideAllScreens();
    document.getElementById('backlogScreen').style.display = 'flex';
    refreshBacklog();
}

async function refreshBacklog() {
    const container = document.getElementById('backlogContainer');
    container.innerHTML = '<div class="empty-state">Loading...</div>';

    try {
        // Get filters
        const priority = document.getElementById('backlogFilterPriority').value;
        const nextSprintOnly = document.getElementById('backlogFilterNextSprint').checked;

        // Build query params
        const params = new URLSearchParams();
        if (priority) params.append('priority', priority);
        if (nextSprintOnly) params.append('next_sprint', 'true');

        const data = await api('GET', `/api/backlog?${params.toString()}`);
        allBacklogItems = data.items || [];

        // Sort: priority (high -> medium -> low), then by date (newest first)
        const priorityOrder = { high: 0, medium: 1, low: 2 };
        allBacklogItems.sort((a, b) => {
            const pDiff = priorityOrder[a.priority] - priorityOrder[b.priority];
            if (pDiff !== 0) return pDiff;
            return new Date(b.created_at) - new Date(a.created_at);
        });

        // Always show the + card first, then other cards
        const cards = [renderAddNewCard(), ...allBacklogItems.map(item => renderBacklogCard(item))];
        container.innerHTML = cards.join('');
    } catch (e) {
        container.innerHTML = `<div class="empty-state">⚠️ Load error: ${escapeHtml(e.message)}</div>`;
    }
}

function renderBacklogCard(item) {
    const priorityClass = item.priority || 'medium';
    const nextSprintClass = item.next_sprint ? 'next-sprint' : '';

    return `
        <div class="backlog-card priority-${priorityClass} ${nextSprintClass}" onclick="startEditBacklogItem('${item.id}')">
            <div class="backlog-card-description">${escapeHtml(item.description || item.title || '')}</div>
            <div class="backlog-card-footer">
                <div class="backlog-card-meta">
                    ${item.created_by ? `${escapeHtml(item.created_by)} • ` : ''}${formatDate(item.created_at)}
                </div>
                <div class="backlog-card-actions">
                    <label class="backlog-next-sprint-toggle ${item.next_sprint ? 'active' : ''}"
                           onclick="toggleBacklogNextSprint('${item.id}', event)">
                        <input type="checkbox" ${item.next_sprint ? 'checked' : ''} onclick="event.stopPropagation()">
                        🚀
                    </label>
                    <button class="btn icon danger" onclick="deleteBacklogItem('${item.id}'); event.stopPropagation()" title="Delete">🗑️</button>
                </div>
            </div>
        </div>
    `;
}

function renderAddNewCard() {
    return `
        <div class="backlog-card add-new" onclick="startCreateBacklogItem()">
            <div class="add-new-content">
                <div class="add-new-icon">+</div>
                <div class="add-new-text">Add entry</div>
            </div>
        </div>
    `;
}

function showCreateBacklogItemModal() {
    const body = `
        <label>Title <span style="color:var(--danger);">*</span></label>
        <input type="text" id="backlogItemTitle" placeholder="Brief task name">

        <label>Description</label>
        <textarea id="backlogItemDescription" rows="4" placeholder="Detailed task description"></textarea>

        <label>Priority</label>
        <select id="backlogItemPriority">
            <option value="low">Low</option>
            <option value="medium" selected>Medium</option>
            <option value="high">High</option>
        </select>

        <label style="display:flex; align-items:center; gap:8px; cursor:pointer; margin-top:12px;">
            <input type="checkbox" id="backlogItemNextSprint" style="accent-color:var(--success);">
            <span>🚀 Add to next sprint</span>
        </label>
    `;

    openModal('Add to backlog', body,
        `<button class="btn" onclick="closeModal()">Cancel</button>
         <button class="btn primary" onclick="createBacklogItem()">Create</button>`);
}

async function createBacklogItem() {
    const title = document.getElementById('backlogItemTitle').value.trim();
    const description = document.getElementById('backlogItemDescription').value.trim();
    const priority = document.getElementById('backlogItemPriority').value;
    const nextSprint = document.getElementById('backlogItemNextSprint').checked;

    if (!title) {
        alert('Enter title');
        return;
    }

    try {
        await api('POST', '/api/backlog', {
            title,
            description,
            priority,
            next_sprint: nextSprint,
            created_by: 'boss'  // TODO: use current user
        });
        closeModal();
        await refreshBacklog();
        addSystemMessage(`Backlog entry created: ${title}`);
    } catch (e) {
        alert('Error: ' + e.message);
    }
}

function showEditBacklogItemModal(itemId) {
    const item = allBacklogItems.find(i => i.id === itemId);
    if (!item) {
        alert('Entry not found');
        return;
    }

    const body = `
        <label>Title <span style="color:var(--danger);">*</span></label>
        <input type="text" id="editBacklogItemTitle" value="${escapeHtml(item.title)}">

        <label>Description</label>
        <textarea id="editBacklogItemDescription" rows="4">${escapeHtml(item.description || '')}</textarea>

        <label>Priority</label>
        <select id="editBacklogItemPriority">
            <option value="low" ${item.priority === 'low' ? 'selected' : ''}>Low</option>
            <option value="medium" ${item.priority === 'medium' ? 'selected' : ''}>Medium</option>
            <option value="high" ${item.priority === 'high' ? 'selected' : ''}>High</option>
        </select>

        <label style="display:flex; align-items:center; gap:8px; cursor:pointer; margin-top:12px;">
            <input type="checkbox" id="editBacklogItemNextSprint" ${item.next_sprint ? 'checked' : ''} style="accent-color:var(--success);">
            <span>🚀 Add to next sprint</span>
        </label>
    `;

    openModal('Edit entry', body,
        `<button class="btn" onclick="closeModal()">Cancel</button>
         <button class="btn primary" onclick="updateBacklogItem('${itemId}')">Save</button>`);
}

async function updateBacklogItem(itemId) {
    const title = document.getElementById('editBacklogItemTitle').value.trim();
    const description = document.getElementById('editBacklogItemDescription').value.trim();
    const priority = document.getElementById('editBacklogItemPriority').value;
    const nextSprint = document.getElementById('editBacklogItemNextSprint').checked;

    if (!title) {
        alert('Enter title');
        return;
    }

    try {
        await api('PUT', `/api/backlog/${itemId}`, {
            title,
            description,
            priority,
            next_sprint: nextSprint
        });
        closeModal();
        await refreshBacklog();
        addSystemMessage(`Entry ${itemId} updated`);
    } catch (e) {
        alert('Error: ' + e.message);
    }
}

// Inline editing
function startEditBacklogItem(itemId) {
    const item = allBacklogItems.find(i => i.id === itemId);
    if (!item) return;

    const card = event.currentTarget;
    const originalHTML = card.innerHTML;

    card.classList.add('editing');
    card.onclick = null;

    card.innerHTML = `
        <textarea id="editInlineDescription" rows="6">${escapeHtml(item.description || item.title || '')}</textarea>
        <div class="backlog-edit-actions">
            <button class="btn primary" onclick="saveInlineEdit('${itemId}')">Save</button>
            <button class="btn" onclick="cancelInlineEdit('${itemId}')">Cancel</button>
            <button class="btn icon danger" onclick="deleteBacklogItem('${itemId}')" title="Delete">🗑️</button>
        </div>
    `;

    const textarea = card.querySelector('textarea');
    textarea.focus();
    textarea.setSelectionRange(textarea.value.length, textarea.value.length);

    // Save original HTML for cancel
    card.dataset.originalHtml = originalHTML;
    card.dataset.itemId = itemId;

    // Ctrl+Enter to save, Esc to cancel
    textarea.addEventListener('keydown', (e) => {
        if (e.key === 'Escape') {
            cancelInlineEdit(itemId);
        } else if (e.ctrlKey && e.key === 'Enter') {
            saveInlineEdit(itemId);
        }
    });
}

async function saveInlineEdit(itemId) {
    const card = document.querySelector(`[data-item-id="${itemId}"]`);
    if (!card) return;

    const textarea = card.querySelector('textarea');
    const description = textarea.value.trim();

    if (!description) {
        alert('Enter description');
        return;
    }

    const item = allBacklogItems.find(i => i.id === itemId);

    try {
        await api('PUT', `/api/backlog/${itemId}`, {
            title: item.title || description.substring(0, 50),
            description: description,
            priority: item.priority,
            next_sprint: item.next_sprint
        });
        await refreshBacklog();
        addSystemMessage(`Entry ${itemId} updated`);
    } catch (e) {
        alert('Error: ' + e.message);
        cancelInlineEdit(itemId);
    }
}

function cancelInlineEdit(itemId) {
    const card = document.querySelector(`[data-item-id="${itemId}"]`);
    if (!card) return;

    card.classList.remove('editing');
    card.innerHTML = card.dataset.originalHtml;
    delete card.dataset.originalHtml;
    delete card.dataset.itemId;

    // Restore click handler
    card.onclick = () => startEditBacklogItem(itemId);
}

// Inline creation
function startCreateBacklogItem() {
    const addCard = document.querySelector('.backlog-card.add-new');
    if (!addCard) return;

    addCard.classList.add('editing');
    addCard.onclick = null;

    addCard.innerHTML = `
        <textarea id="createInlineDescription" rows="6" placeholder="Task description..."></textarea>
        <div class="backlog-edit-actions">
            <button class="btn primary" onclick="saveInlineCreate()">Create</button>
            <button class="btn" onclick="cancelInlineCreate()">Cancel</button>
        </div>
    `;

    const textarea = addCard.querySelector('textarea');
    textarea.focus();

    // Ctrl+Enter to create, Esc to cancel
    textarea.addEventListener('keydown', (e) => {
        if (e.key === 'Escape') {
            cancelInlineCreate();
        } else if (e.ctrlKey && e.key === 'Enter') {
            saveInlineCreate();
        }
    });
}

async function saveInlineCreate() {
    const textarea = document.getElementById('createInlineDescription');
    const description = textarea.value.trim();

    if (!description) {
        alert('Enter description');
        return;
    }

    try {
        await api('POST', '/api/backlog', {
            title: description.substring(0, 50),
            description: description,
            priority: 'medium',
            next_sprint: false
        });
        await refreshBacklog();
        addSystemMessage('New backlog item added');
    } catch (e) {
        alert('Error: ' + e.message);
        cancelInlineCreate();
    }
}

function cancelInlineCreate() {
    const addCard = document.querySelector('.backlog-card.add-new');
    if (!addCard) return;

    addCard.classList.remove('editing');
    addCard.innerHTML = `
        <div class="add-new-content">
            <div class="add-new-icon">+</div>
            <div class="add-new-text">Add entry</div>
        </div>
    `;
    addCard.onclick = startCreateBacklogItem;
}

async function deleteBacklogItem(itemId) {
    const item = allBacklogItems.find(i => i.id === itemId);
    const title = item ? item.title : itemId;

    if (!confirm(`Delete entry "${title}"?`)) {
        return;
    }

    try {
        await api('DELETE', `/api/backlog/${itemId}`);
        await refreshBacklog();
        addSystemMessage(`Entry ${itemId} deleted`);
    } catch (e) {
        alert('Error: ' + e.message);
    }
}

async function toggleBacklogNextSprint(itemId, event) {
    event.preventDefault();
    event.stopPropagation();

    try {
        await api('POST', `/api/backlog/${itemId}/toggle`);
        await refreshBacklog();
    } catch (e) {
        alert('Error: ' + e.message);
    }
}
