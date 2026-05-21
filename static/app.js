/**
 * JIRA Chat Agent - Frontend Application (ChatGPT-style)
 */

// ===== State =====
const state = {
    sessionId: null,
    messages: [],
    isLoading: false,
    charts: {},
    jiraUrl: null,
    contextMenu: null, // active context menu element
    selectedModel: null, // current AI model
    models: [], // available models
    outputMode: 'auto' // auto | chart | report
};

// ===== DOM Elements =====
const el = {
    sidebar: document.getElementById('sidebar'),
    sidebarToggle: document.getElementById('sidebarToggle'),
    sidebarOpen: document.getElementById('sidebarOpen'),
    sidebarHistory: document.getElementById('sidebarHistory'),
    clearBtn: document.getElementById('clearBtn'),
    chatScroll: document.getElementById('chatScroll'),
    welcomeMessage: document.getElementById('welcomeMessage'),
    messagesContainer: document.getElementById('messagesContainer'),
    loadingIndicator: document.getElementById('loadingIndicator'),
    suggestions: document.getElementById('suggestions'),
    messageInput: document.getElementById('messageInput'),
    sendBtn: document.getElementById('sendBtn'),
    modeBtn: document.getElementById('modeBtn'),
    modeMenu: document.getElementById('modeMenu'),
    modeIndicator: document.getElementById('modeIndicator'),
    modeChip: document.getElementById('modeChip'),
    modeChipIcon: document.getElementById('modeChipIcon'),
    modeChipLabel: document.getElementById('modeChipLabel'),
    modeChipClose: document.getElementById('modeChipClose'),
    modelDropdownBtn: document.getElementById('modelDropdownBtn'),
    modelMenu: document.getElementById('modelMenu'),
    modelName: document.getElementById('modelName'),
    chartModal: document.getElementById('chartModal'),
    modalChart: document.getElementById('modalChart'),
    chartTitle: document.getElementById('chartTitle'),
    // Login & Project
    loginPanel: document.getElementById('loginPanel'),
    userPanel: document.getElementById('userPanel'),
    loginUrl: document.getElementById('loginUrl'),
    loginUsername: document.getElementById('loginUsername'),
    loginPassword: document.getElementById('loginPassword'),
    loginProjectKey: document.getElementById('loginProjectKey'),
    loginBtn: document.getElementById('loginBtn'),
    loginError: document.getElementById('loginError'),
    logoutBtn: document.getElementById('logoutBtn'),
    userAvatarText: document.getElementById('userAvatarText'),
    userNameText: document.getElementById('userNameText'),
    projectKeyInput: document.getElementById('projectKeyInput'),
    // GitHub Token
    ghTokenPanel: document.getElementById('ghTokenPanel'),
    // AI API Key
    aiKeyPanel: document.getElementById('aiKeyPanel'),
    aiProviderSelect: document.getElementById('aiProviderSelect'),
    aiKeyInput: document.getElementById('aiKeyInput'),
    aiKeyBtn: document.getElementById('aiKeyBtn'),
    aiKeyStatus: document.getElementById('aiKeyStatus'),
    aiKeyForm: document.getElementById('aiKeyForm'),
    aiAuthInfo: document.getElementById('aiAuthInfo'),
    aiAuthAvatar: document.getElementById('aiAuthAvatar'),
    aiAuthName: document.getElementById('aiAuthName'),
    aiLogoutBtn: document.getElementById('aiLogoutBtn')
};

// ===== API =====
const api = {
    baseUrl: '/api',
    async chat(message, sessionId = null) {
        const body = { message, session_id: sessionId };
        if (state.selectedModel) body.model = state.selectedModel;
        if (state.outputMode && state.outputMode !== 'auto') body.output_mode = state.outputMode;
        if (state.aiApiKey) body.ai_api_key = state.aiApiKey;
        const res = await fetch(`${this.baseUrl}/chat`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(body)
        });
        if (!res.ok) { const e = await res.json(); throw new Error(e.error || 'Request failed'); }
        return res.json();
    },
    async getSuggestions() {
        const res = await fetch(`${this.baseUrl}/suggestions`);
        if (!res.ok) return { suggestions: [] };
        return res.json();
    },
    async listSessions() {
        const res = await fetch(`${this.baseUrl}/sessions`);
        if (!res.ok) return { sessions: [] };
        return res.json();
    },
    async getSession(id) {
        const res = await fetch(`${this.baseUrl}/sessions/${id}`);
        if (!res.ok) return null;
        return res.json();
    },
    async deleteSession(id) {
        await fetch(`${this.baseUrl}/sessions/${id}`, { method: 'DELETE' });
    },
    async getConfig() {
        const res = await fetch(`${this.baseUrl}/config`);
        if (!res.ok) return {};
        return res.json();
    },
    async listModels() {
        const res = await fetch(`${this.baseUrl}/models`);
        if (!res.ok) return { models: [], current: 'gpt-4o' };
        return res.json();
    },
    async login(url, username, password, projectKey) {
        const res = await fetch(`${this.baseUrl}/login`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ url, username, password, project_key: projectKey })
        });
        const data = await res.json();
        if (!res.ok) throw new Error(data.error || 'Login failed');
        return data;
    },
    async logout() {
        await fetch(`${this.baseUrl}/logout`, { method: 'POST' });
    },
    async setProject(projectKey) {
        const res = await fetch(`${this.baseUrl}/project`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ project_key: projectKey })
        });
        const data = await res.json();
        if (!res.ok) throw new Error(data.error || 'Failed');
        return data;
    },
    async listProjects() {
        const res = await fetch(`${this.baseUrl}/projects`);
        if (!res.ok) return { projects: [] };
        return res.json();
    },
    async switchProvider(provider, token = '', model = '') {
        const body = { provider };
        if (token) body.token = token;
        if (model) body.model = model;
        const res = await fetch(`${this.baseUrl}/provider`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(body)
        });
        const data = await res.json();
        if (!res.ok) throw new Error(data.error || 'Switch failed');
        return data;
    },
    async verifyKey(provider, token) {
        const res = await fetch(`${this.baseUrl}/ai/verify`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ provider, token })
        });
        const data = await res.json();
        if (!res.ok) throw new Error(data.error || 'Verification failed');
        return data;
    }
};

// ===== Textarea auto-resize =====
function autoResize() {
    const input = el.messageInput;
    input.style.height = 'auto';
    input.style.height = Math.min(input.scrollHeight, 200) + 'px';
    el.sendBtn.disabled = !input.value.trim();
}

// ===== Copy to clipboard =====
function createCopyButton(bodyElement) {
    const btn = document.createElement('button');
    btn.className = 'copy-btn';
    btn.title = 'Copy';
    btn.innerHTML = '<svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><rect x="9" y="9" width="13" height="13" rx="2" ry="2"/><path d="M5 15H4a2 2 0 0 1-2-2V4a2 2 0 0 1 2-2h9a2 2 0 0 1 2 2v1"/></svg><span>Copy</span>';
    btn.onclick = async () => {
        try {
            // Clone to avoid modifying the visible DOM
            const clone = bodyElement.cloneNode(true);
            // Remove chart canvases and expand buttons (not useful in clipboard)
            clone.querySelectorAll('canvas, .expand-chart-btn').forEach(el => el.remove());
            const html = clone.innerHTML;
            const text = clone.innerText || clone.textContent;

            // Try rich text copy (HTML + plain text)
            if (navigator.clipboard.write && typeof ClipboardItem !== 'undefined') {
                const htmlBlob = new Blob([html], { type: 'text/html' });
                const textBlob = new Blob([text], { type: 'text/plain' });
                await navigator.clipboard.write([
                    new ClipboardItem({ 'text/html': htmlBlob, 'text/plain': textBlob })
                ]);
            } else {
                await navigator.clipboard.writeText(text);
            }
            btn.classList.add('copied');
            btn.innerHTML = '<svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><polyline points="20 6 9 17 4 12"/></svg><span>Copied!</span>';
            setTimeout(() => {
                btn.classList.remove('copied');
                btn.innerHTML = '<svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><rect x="9" y="9" width="13" height="13" rx="2" ry="2"/><path d="M5 15H4a2 2 0 0 1-2-2V4a2 2 0 0 1 2-2h9a2 2 0 0 1 2 2v1"/></svg><span>Copy</span>';
            }, 2000);
        } catch (e) { /* fallback: ignore */ }
    };
    return btn;
}

// ===== UI =====
const ui = {
    showLoading() {
        state.isLoading = true;
        el.loadingIndicator.classList.remove('hidden');
        el.sendBtn.disabled = true;
        el.messageInput.disabled = true;
        this.scrollToBottom();
    },
    hideLoading() {
        state.isLoading = false;
        el.loadingIndicator.classList.add('hidden');
        el.messageInput.disabled = false;
        el.sendBtn.disabled = !el.messageInput.value.trim();
        el.messageInput.focus();
    },
    hideWelcome() { el.welcomeMessage.classList.add('hidden'); },
    showWelcome() {
        el.welcomeMessage.classList.remove('hidden');
        el.messagesContainer.innerHTML = '';
    },
    scrollToBottom() {
        el.chatScroll.scrollTop = el.chatScroll.scrollHeight;
    },

    renderMessage(message) {
        const { role, content, output_type, table_data, chart_config } = message;

        const msg = document.createElement('div');
        msg.className = `message ${role}`;

        const row = document.createElement('div');
        row.className = 'message-row';

        // Icon
        const icon = document.createElement('div');
        icon.className = 'message-icon';
        if (role === 'user') {
            icon.textContent = 'B';
        } else {
            icon.innerHTML = '<svg width="16" height="16" viewBox="0 0 24 24" fill="currentColor"><path d="M12 2L2 7L12 12L22 7L12 2Z" opacity="0.85"/><path d="M2 17L12 22L22 17" stroke="currentColor" stroke-width="2" fill="none"/><path d="M2 12L12 17L22 12" stroke="currentColor" stroke-width="2" fill="none"/></svg>';
        }

        // Body wrapper (body + actions)
        const bodyWrap = document.createElement('div');
        bodyWrap.style.flex = '1';
        bodyWrap.style.minWidth = '0';

        const body = document.createElement('div');
        body.className = 'message-body';

        if (content) {
            const textDiv = document.createElement('div');
            textDiv.innerHTML = marked.parse(content);
            body.appendChild(textDiv);
        }
        if (output_type === 'table' && table_data && table_data.length > 0) {
            body.appendChild(this.createTable(table_data));
        }
        if (output_type === 'chart' && chart_config) {
            body.appendChild(this.createChart(chart_config));
        }

        bodyWrap.appendChild(body);

        // Copy button for assistant messages
        if (role === 'assistant') {
            const actions = document.createElement('div');
            actions.className = 'message-actions';
            actions.appendChild(createCopyButton(body));
            bodyWrap.appendChild(actions);
        }

        row.appendChild(icon);
        row.appendChild(bodyWrap);
        msg.appendChild(row);
        el.messagesContainer.appendChild(msg);
        this.scrollToBottom();
    },

    createTable(data) {
        const wrapper = document.createElement('div');
        wrapper.style.overflowX = 'auto';
        const table = document.createElement('table');
        table.className = 'data-table';

        const columnOrder = [
            'sprint', 'count', 'key', 'status', 'summary', 'assignee', 'reporter',
            'component', 'defect_type', 'due_date', 'created_date', 'priority'
        ];
        const allColumns = Object.keys(data[0]);
        const columns = allColumns.sort((a, b) => {
            const oA = columnOrder.indexOf(a), oB = columnOrder.indexOf(b);
            return (oA === -1 ? 999 : oA) - (oB === -1 ? 999 : oB);
        });
        const labels = {
            key:'Key', summary:'Summary', status:'Status', priority:'Priority',
            assignee:'Assignee', reporter:'Reporter', component:'Component',
            defect_type:'Defect Type', due_date:'Due Date', created_date:'Created',
            sprint:'Sprint', count:'Count'
        };

        const thead = document.createElement('thead');
        const hr = document.createElement('tr');
        columns.forEach(c => { const th = document.createElement('th'); th.textContent = labels[c]||c; hr.appendChild(th); });
        thead.appendChild(hr); table.appendChild(thead);

        const tbody = document.createElement('tbody');
        data.forEach(row => {
            const tr = document.createElement('tr');
            columns.forEach(col => {
                const td = document.createElement('td');
                const val = row[col];
                if (col === 'key') {
                    const a = document.createElement('a');
                    a.className = 'issue-key';
                    if (state.jiraUrl) { a.href = `${state.jiraUrl}/browse/${val}`; a.target = '_blank'; a.rel = 'noopener noreferrer'; }
                    else { a.href = '#'; }
                    a.textContent = val; td.appendChild(a);
                } else if (col === 'priority') {
                    const b = document.createElement('span');
                    b.className = `priority-badge priority-${val.toLowerCase()}`; b.textContent = val; td.appendChild(b);
                } else if (col === 'status') {
                    const b = document.createElement('span');
                    b.className = `status-badge status-${val.toLowerCase().replace(/\s+/g,'')}`; b.textContent = val; td.appendChild(b);
                } else { td.textContent = val || '-'; }
                tr.appendChild(td);
            });
            tbody.appendChild(tr);
        });
        table.appendChild(tbody);
        wrapper.appendChild(table);
        return wrapper;
    },

    createChart(chartConfig) {
        const container = document.createElement('div');
        container.className = 'chart-container';
        const canvas = document.createElement('canvas');
        const chartId = `chart-${Date.now()}`;
        canvas.id = chartId;
        container.appendChild(canvas);

        const expandBtn = document.createElement('button');
        expandBtn.className = 'expand-chart-btn';
        expandBtn.textContent = '↗ Phóng to';
        expandBtn.onclick = () => openChartModal(chartConfig);
        container.appendChild(expandBtn);

        setTimeout(() => {
            if (state.charts[chartId]) state.charts[chartId].destroy();
            const ctx = document.getElementById(chartId);
            if (ctx) {
                state.charts[chartId] = new Chart(ctx, {
                    type: chartConfig.type || 'bar', data: chartConfig.data,
                    options: { ...chartConfig.options, responsive: true, maintainAspectRatio: true }
                });
            }
        }, 100);
        return container;
    },

    renderSuggestions(suggestions) {
        el.suggestions.innerHTML = '';
        suggestions.forEach(s => {
            const btn = document.createElement('button');
            btn.className = 'suggestion-chip';
            btn.textContent = s;
            btn.onclick = () => sendMessage(s);
            el.suggestions.appendChild(btn);
        });
    }
};

// ===== Chat History Sidebar =====
async function refreshHistory() {
    try {
        const { sessions } = await api.listSessions();
        // Keep the "Recents" label, clear only history items
        el.sidebarHistory.querySelectorAll('.history-item').forEach(i => i.remove());

        const label = el.sidebarHistory.querySelector('.history-section-label');
        if (sessions.length === 0 && label) {
            label.classList.add('hidden');
        } else if (label) {
            label.classList.remove('hidden');
        }

        sessions.forEach(s => {
            const item = document.createElement('div');
            item.className = 'history-item' + (s.session_id === state.sessionId ? ' active' : '');
            item.dataset.sessionId = s.session_id;

            const title = document.createElement('span');
            title.className = 'history-title';
            title.textContent = s.title;
            title.title = s.title;

            const menuBtn = document.createElement('button');
            menuBtn.className = 'history-menu-btn';
            menuBtn.title = 'Tùy chọn';
            menuBtn.innerHTML = '<svg width="16" height="16" viewBox="0 0 24 24" fill="currentColor"><circle cx="12" cy="5" r="1.5"/><circle cx="12" cy="12" r="1.5"/><circle cx="12" cy="19" r="1.5"/></svg>';
            menuBtn.onclick = (e) => { e.stopPropagation(); showHistoryMenu(e, s.session_id); };

            item.appendChild(title);
            item.appendChild(menuBtn);
            item.onclick = () => loadSession(s.session_id);
            el.sidebarHistory.appendChild(item);
        });
    } catch (e) { /* ignore */ }
}

function showHistoryMenu(e, sessionId) {
    closeHistoryMenu();
    const menu = document.createElement('div');
    menu.className = 'history-context-menu';

    const deleteBtn = document.createElement('button');
    deleteBtn.className = 'delete-btn';
    deleteBtn.innerHTML = '<svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round"><polyline points="3 6 5 6 21 6"/><path d="M19 6v14a2 2 0 0 1-2 2H7a2 2 0 0 1-2-2V6m3 0V4a2 2 0 0 1 2-2h4a2 2 0 0 1 2 2v2"/></svg>Xóa cuộc trò chuyện';
    deleteBtn.onclick = async (ev) => {
        ev.stopPropagation();
        closeHistoryMenu();
        try {
            await api.deleteSession(sessionId);
            if (state.sessionId === sessionId) {
                state.sessionId = null;
                destroyAllCharts();
                ui.showWelcome();
            }
            refreshHistory();
        } catch (err) { /* ignore */ }
    };

    menu.appendChild(deleteBtn);

    // Position
    const rect = e.target.closest('.history-menu-btn').getBoundingClientRect();
    menu.style.top = rect.bottom + 4 + 'px';
    menu.style.left = rect.left + 'px';

    document.body.appendChild(menu);
    state.contextMenu = menu;
}

function closeHistoryMenu() {
    if (state.contextMenu) {
        state.contextMenu.remove();
        state.contextMenu = null;
    }
}

async function loadSession(sessionId) {
    if (sessionId === state.sessionId) return;
    try {
        const data = await api.getSession(sessionId);
        if (!data) return;

        destroyAllCharts();
        state.sessionId = sessionId;
        el.messagesContainer.innerHTML = '';
        ui.hideWelcome();

        // Render all messages from history
        data.messages.forEach(m => {
            ui.renderMessage({
                role: m.role,
                content: m.content,
                output_type: m.output_type,
                table_data: m.table_data,
                chart_config: m.chart_config
            });
        });

        // Highlight active in sidebar
        el.sidebarHistory.querySelectorAll('.history-item').forEach(item => {
            item.classList.toggle('active', item.dataset.sessionId === sessionId);
        });

        ui.scrollToBottom();
    } catch (e) { /* ignore */ }
}

function destroyAllCharts() {
    Object.values(state.charts).forEach(c => c && c.destroy && c.destroy());
    state.charts = {};
}

// ===== Chat =====
async function sendMessage(message = null) {
    const text = message || el.messageInput.value.trim();
    if (!text || state.isLoading) return;

    el.messageInput.value = '';
    autoResize();
    ui.hideWelcome();
    ui.renderMessage({ role: 'user', content: text });
    ui.showLoading();

    try {
        const result = await api.chat(text, state.sessionId);
        state.sessionId = result.session_id;
        ui.renderMessage({ role: 'assistant', ...result.response });
        refreshHistory(); // Update sidebar after each message
    } catch (error) {
        ui.renderMessage({ role: 'assistant', content: `Lỗi: ${error.message}` });
    } finally {
        ui.hideLoading();
    }
}

async function newChat() {
    // Check if AI key is set
    if (!state.aiApiKey) {
        el.aiKeyInput.focus();
        el.aiKeyStatus.textContent = 'Vui lòng xác thực API Key trước khi chat.';
        el.aiKeyStatus.classList.remove('hidden');
        el.aiKeyStatus.style.color = '';
        setTimeout(() => el.aiKeyStatus.classList.add('hidden'), 4000);
        return;
    }
    state.sessionId = null;
    destroyAllCharts();
    ui.showWelcome();
    el.messageInput.focus();
    // Deselect active history
    el.sidebarHistory.querySelectorAll('.history-item').forEach(i => i.classList.remove('active'));
}

// ===== Sidebar =====
function toggleSidebar() {
    const collapsed = el.sidebar.classList.toggle('collapsed');
    el.sidebarOpen.classList.toggle('hidden', !collapsed);
}

// ===== Chart Modal =====
let modalChartInstance = null;
function openChartModal(cfg) {
    el.chartModal.classList.remove('hidden');
    el.chartTitle.textContent = cfg.options?.plugins?.title?.text || 'Biểu đồ';
    if (modalChartInstance) modalChartInstance.destroy();
    modalChartInstance = new Chart(el.modalChart, {
        type: cfg.type || 'bar', data: cfg.data,
        options: { ...cfg.options, responsive: true, maintainAspectRatio: true }
    });
}
function closeChartModal() {
    el.chartModal.classList.add('hidden');
    if (modalChartInstance) { modalChartInstance.destroy(); modalChartInstance = null; }
}

// ===== Events =====
function initEventListeners() {
    el.sendBtn.addEventListener('click', () => sendMessage());
    el.messageInput.addEventListener('input', autoResize);
    el.messageInput.addEventListener('keydown', (e) => {
        if (e.key === 'Enter' && !e.shiftKey) { e.preventDefault(); sendMessage(); }
    });
    el.clearBtn.addEventListener('click', newChat);
    el.sidebarToggle.addEventListener('click', toggleSidebar);
    el.sidebarOpen.addEventListener('click', toggleSidebar);

    // Model dropdown
    el.modelDropdownBtn.addEventListener('click', (e) => {
        e.stopPropagation();
        el.modelMenu.classList.toggle('hidden');
        el.modeMenu.classList.add('hidden');
    });

    // Mode selector
    el.modeBtn.addEventListener('click', (e) => {
        e.stopPropagation();
        el.modeMenu.classList.toggle('hidden');
        el.modelMenu.classList.add('hidden');
    });
    el.modeMenu.querySelectorAll('.mode-option').forEach(opt => {
        opt.addEventListener('click', (e) => {
            e.stopPropagation();
            selectOutputMode(opt.dataset.mode);
        });
    });
    el.modeChipClose.addEventListener('click', () => selectOutputMode('auto'));

    el.chartModal.addEventListener('click', (e) => {
        if (e.target === el.chartModal) closeChartModal();
    });
    document.addEventListener('keydown', (e) => {
        if (e.key === 'Escape') {
            if (!el.chartModal.classList.contains('hidden')) closeChartModal();
            closeHistoryMenu();
            el.modelMenu.classList.add('hidden');
            el.modeMenu.classList.add('hidden');
        }
    });
    // Close context menu / model dropdown / mode menu on outside click
    document.addEventListener('click', (e) => {
        if (state.contextMenu && !state.contextMenu.contains(e.target)) {
            closeHistoryMenu();
        }
        if (!e.target.closest('.model-dropdown')) {
            el.modelMenu.classList.add('hidden');
        }
        if (!e.target.closest('.mode-selector')) {
            el.modeMenu.classList.add('hidden');
        }
    });
}

// ===== Output Mode Selector =====
const MODE_CONFIG = {
    chart: {
        label: 'Chart',
        chipClass: 'chart',
        icon: '<svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round"><path d="M21.21 15.89A10 10 0 1 1 8 2.83"/><path d="M22 12A10 10 0 0 0 12 2v10z"/></svg>'
    },
    report: {
        label: 'Report',
        chipClass: 'report',
        icon: '<svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round"><rect x="3" y="3" width="18" height="18" rx="2"/><line x1="3" y1="9" x2="21" y2="9"/><line x1="3" y1="15" x2="21" y2="15"/><line x1="9" y1="3" x2="9" y2="21"/></svg>'
    }
};

function selectOutputMode(mode) {
    state.outputMode = mode;
    el.modeMenu.classList.add('hidden');
    el.modeMenu.querySelectorAll('.mode-option').forEach(opt => {
        opt.classList.toggle('active', opt.dataset.mode === mode);
    });
    el.modeBtn.classList.toggle('has-mode', mode !== 'auto');
    el.modeBtn.title = mode === 'auto' ? 'Chọn chế độ output' : `Chế độ: ${mode.charAt(0).toUpperCase() + mode.slice(1)}`;
    updateModeIndicator(mode);
}

function updateModeIndicator(mode) {
    if (mode === 'auto') {
        el.modeIndicator.classList.add('hidden');
        return;
    }
    const cfg = MODE_CONFIG[mode];
    if (!cfg) return;
    el.modeChip.className = 'mode-chip ' + cfg.chipClass;
    el.modeChipIcon.innerHTML = cfg.icon;
    el.modeChipLabel.textContent = cfg.label;
    el.modeIndicator.classList.remove('hidden');
}

// ===== Model Selector =====
function renderModelMenu() {
    el.modelMenu.innerHTML = '';
    const standardModels = state.models.filter(m => !m.premium);
    const premiumModels = state.models.filter(m => m.premium);

    standardModels.forEach(m => {
        const item = document.createElement('button');
        item.className = 'model-option' + (m.id === state.selectedModel ? ' active' : '');
        item.innerHTML = `<span class="model-option-name">${m.name}</span><span class="model-option-desc">${m.description}</span>`;
        item.onclick = () => selectModel(m.id, m.name);
        el.modelMenu.appendChild(item);
    });

    if (premiumModels.length > 0) {
        const divider = document.createElement('div');
        divider.className = 'model-divider';
        divider.innerHTML = '<span>Premium</span>';
        el.modelMenu.appendChild(divider);

        premiumModels.forEach(m => {
            const item = document.createElement('button');
            item.className = 'model-option premium' + (m.id === state.selectedModel ? ' active' : '');
            item.innerHTML = `<span class="model-option-name">${m.name}<span class="premium-badge">PRO</span></span><span class="model-option-desc">${m.description}</span>`;
            item.onclick = () => selectModel(m.id, m.name);
            el.modelMenu.appendChild(item);
        });
    }
}

function selectModel(id, name) {
    state.selectedModel = id;
    el.modelName.textContent = name;
    el.modelMenu.classList.add('hidden');
    renderModelMenu(); // update active state
}

async function loadModels() {
    try {
        const { models, current } = await api.listModels();
        state.models = models;
        state.selectedModel = current;
        const m = models.find(m => m.id === current);
        if (m) el.modelName.textContent = m.name;
        renderModelMenu();
    } catch(e) { /* ignore */ }
}

// ===== Init =====
// ===== AI Provider =====
state.aiApiKey = localStorage.getItem('ai_api_key') || '';
state.aiProvider = localStorage.getItem('ai_provider') || 'github';

// ===== Login & Project =====

// ===== AI API Key =====
function handleAiKeySave() {
    const key = el.aiKeyInput.value.trim();
    if (!key) return;
    
    el.aiKeyBtn.disabled = true;
    el.aiKeyBtn.textContent = 'Đang xác thực...';
    el.aiKeyStatus.classList.add('hidden');
    
    api.verifyKey(state.aiProvider, key).then(data => {
        state.aiApiKey = key;
        localStorage.setItem('ai_api_key', key);
        el.aiKeyInput.value = '';
        // Show authenticated state
        const name = data.username || state.aiProvider.toUpperCase();
        showAiAuth(name);
        loadModels();
    }).catch(err => {
        el.aiKeyStatus.textContent = err.message;
        el.aiKeyStatus.classList.remove('hidden');
        el.aiKeyStatus.style.color = '';
    }).finally(() => {
        el.aiKeyBtn.disabled = false;
        el.aiKeyBtn.textContent = 'Xác thực';
    });
}

function handleAiLogout() {
    state.aiApiKey = '';
    localStorage.removeItem('ai_api_key');
    showAiForm();
}

function showAiAuth(name) {
    el.aiKeyForm.classList.add('hidden');
    el.aiAuthInfo.classList.remove('hidden');
    el.aiAuthName.textContent = name || 'Authenticated';
    if (state.aiProvider === 'github') {
        el.aiAuthAvatar.textContent = 'GH';
    } else {
        el.aiAuthAvatar.textContent = 'AI';
    }
}

function showAiForm() {
    el.aiKeyForm.classList.remove('hidden');
    el.aiAuthInfo.classList.add('hidden');
}

function handleProviderChange() {
    const provider = el.aiProviderSelect.value;
    state.aiProvider = provider;
    localStorage.setItem('ai_provider', provider);
    
    // Update placeholder based on provider
    if (provider === 'github') {
        el.aiKeyInput.placeholder = 'GitHub Token (ghp_...)';
    } else if (provider === 'azure') {
        el.aiKeyInput.placeholder = 'Azure API Key';
    } else {
        el.aiKeyInput.placeholder = 'OpenAI API Key (sk-...)';
    }
    
    // Reset to form view when changing provider
    state.aiApiKey = '';
    localStorage.removeItem('ai_api_key');
    showAiForm();
    api.switchProvider(provider, '').then(() => loadModels());
}

function showLoginPanel() {
    el.loginPanel.classList.remove('hidden');
    el.userPanel.classList.add('hidden');
}

function showUserPanel(username, projectKey) {
    el.loginPanel.classList.add('hidden');
    el.userPanel.classList.remove('hidden');
    el.userAvatarText.textContent = (username || 'U').charAt(0).toUpperCase();
    el.userNameText.textContent = username || 'user';
    // Populate project dropdown after showing panel
    populateProjectDropdown(projectKey);
}

async function populateProjectDropdown(selectedKey) {
    try {
        const { projects } = await api.listProjects();
        // Login panel dropdown
        el.loginProjectKey.innerHTML = '<option value="">-- Ch\u1ECDn Project --</option>';
        el.loginProjectKey.disabled = false;
        // User panel dropdown
        el.projectKeyInput.innerHTML = '';
        projects.forEach(p => {
            const opt1 = document.createElement('option');
            opt1.value = p.key;
            opt1.textContent = `${p.key} - ${p.name}`;
            el.loginProjectKey.appendChild(opt1);

            const opt2 = document.createElement('option');
            opt2.value = p.key;
            opt2.textContent = `${p.key} - ${p.name}`;
            el.projectKeyInput.appendChild(opt2);
        });
        if (selectedKey) {
            el.loginProjectKey.value = selectedKey;
            el.projectKeyInput.value = selectedKey;
        }
    } catch (e) { /* ignore */ }
}

async function handleLogin() {
    const url = el.loginUrl.value.trim();
    const username = el.loginUsername.value.trim();
    const password = el.loginPassword.value.trim();
    const projectKey = el.loginProjectKey.value.trim();

    el.loginError.classList.add('hidden');
    el.loginBtn.disabled = true;
    el.loginBtn.textContent = 'Đang kết nối...';

    try {
        const result = await api.login(url, username, password, projectKey);
        state.jiraUrl = result.jira_url;
        showUserPanel(result.username, result.project_key);
        // Clear password from DOM
        el.loginPassword.value = '';
    } catch (err) {
        el.loginError.textContent = err.message;
        el.loginError.classList.remove('hidden');
        // Still try to load projects if login succeeded partially
    } finally {
        el.loginBtn.disabled = false;
        el.loginBtn.textContent = 'Đăng nhập';
    }
}

async function handleLogout() {
    await api.logout();
    state.jiraUrl = null;
    showLoginPanel();
}

async function handleProjectChange() {
    const key = el.projectKeyInput.value.trim().toUpperCase();
    if (!key) return;
    try {
        await api.setProject(key);
    } catch (err) {
        alert(err.message);
    }
}

// ===== Init =====
async function init() {
    initEventListeners();

    // Login event listeners
    el.loginBtn.addEventListener('click', handleLogin);
    el.loginPassword.addEventListener('keydown', (e) => {
        if (e.key === 'Enter') handleLogin();
    });
    el.logoutBtn.addEventListener('click', handleLogout);
    el.projectKeyInput.addEventListener('change', handleProjectChange);

    // AI API Key events
    el.aiKeyBtn.addEventListener('click', handleAiKeySave);
    el.aiKeyInput.addEventListener('keydown', (e) => {
        if (e.key === 'Enter') handleAiKeySave();
    });
    el.aiProviderSelect.addEventListener('change', handleProviderChange);
    el.aiLogoutBtn.addEventListener('click', handleAiLogout);

    // Check login status
    try {
        const cfg = await api.getConfig();
        state.jiraUrl = cfg.jira_url;
        state.aiProvider = localStorage.getItem('ai_provider') || cfg.ai_provider || 'github';
        el.aiProviderSelect.value = state.aiProvider;
        // Set placeholder based on provider
        if (state.aiProvider === 'github') {
            el.aiKeyInput.placeholder = 'GitHub Token (ghp_...)';
        } else if (state.aiProvider === 'azure') {
            el.aiKeyInput.placeholder = 'Azure API Key';
        } else {
            el.aiKeyInput.placeholder = 'OpenAI API Key (sk-...)';
        }
        // Restore auth state if key saved
        if (state.aiApiKey) {
            api.verifyKey(state.aiProvider, state.aiApiKey).then(data => {
                const name = data.username || state.aiProvider.toUpperCase();
                showAiAuth(name);
            }).catch(() => {
                // Key expired/invalid, clear it
                state.aiApiKey = '';
                localStorage.removeItem('ai_api_key');
                showAiForm();
            });
        }
        if (cfg.logged_in) {
            showUserPanel(cfg.username, cfg.project_key);
        } else {
            showLoginPanel();
        }
    } catch(e) {
        showLoginPanel();
    }

    // Load models
    loadModels();
    try {
        const { suggestions } = await api.getSuggestions();
        ui.renderSuggestions(suggestions);
    } catch(e) {
        ui.renderSuggestions(["Có bao nhiêu bug đang open?", "Liệt kê các task đang bị trễ", "Thống kê bug theo sprint"]);
    }
    refreshHistory();
    el.messageInput.focus();
}

document.addEventListener('DOMContentLoaded', init);
