// Application State Variables
let fileQueue = [];
let modelManagerList = [];
let wsConnection = null;
let currentTab = 0; // 0: Main log, 1-8: Worker logs
let ragContext = "";
let chatHistory = [];
let runningTask = false;

// DOM Elements
const elements = {
    hardwareSpec: document.getElementById('hardware-spec'),
    modelSelect: document.getElementById('model-select'),
    threadSelect: document.getElementById('thread-select'),
    statusIndicator: document.getElementById('status-indicator'),
    cpuBar: document.getElementById('cpu-bar'),
    cpuText: document.getElementById('cpu-text'),
    ramBar: document.getElementById('ram-bar'),
    ramText: document.getElementById('ram-text'),
    gpuBar: document.getElementById('gpu-bar'),
    gpuText: document.getElementById('gpu-text'),
    statTime: document.getElementById('stat-time'),
    statPower: document.getElementById('stat-power'),
    statTokens: document.getElementById('stat-tokens'),
    fileQueueList: document.getElementById('file-queue-list'),
    destInput: document.getElementById('dest-input'),
    srePolice: document.getElementById('sre-police'),
    minimiContainer: document.getElementById('minimi-container'),
    workerTabsContainer: document.getElementById('worker-tabs-container'),
    workerLogViews: document.getElementById('worker-log-views'),
    logViewMain: document.getElementById('log-view-main'),
    currentAction: document.getElementById('current-action'),
    globalProgressBar: document.getElementById('global-progress-bar'),
    cbTts: document.getElementById('cb-tts'),
    btnAddFiles: document.getElementById('btn-add-files'),
    btnAddLink: document.getElementById('btn-add-link'),
    btnClear: document.getElementById('btn-clear'),
    btnRun: document.getElementById('btn-run'),
    fileInputRaw: document.getElementById('file-input-raw'),
    btnModelManager: document.getElementById('btn-model-manager'),
    modalManager: document.getElementById('modal-manager'),
    modalClose: document.getElementById('modal-close'),
    modelTableBody: document.getElementById('model-table-body'),
    btnModalRefresh: document.getElementById('btn-modal-refresh'),
    chatDisplay: document.getElementById('chat-display'),
    chatInput: document.getElementById('chat-input'),
    btnSendChat: document.getElementById('btn-send-chat'),
    btnMainLog: document.getElementById('btn-main-log'),
    
    // RAG Settings elements
    btnRagSettings: document.getElementById('btn-rag-settings'),
    modalRagSettings: document.getElementById('modal-rag-settings'),
    modalRagSettingsClose: document.getElementById('modal-rag-settings-close'),
    btnRagSettingsCancel: document.getElementById('btn-rag-settings-cancel'),
    btnRagSettingsApply: document.getElementById('btn-rag-settings-apply'),
    inputChunkOverlap: document.getElementById('input-chunk-overlap'),
    sliderChunkOverlap: document.getElementById('slider-chunk-overlap'),
    inputTopK: document.getElementById('input-top-k'),
    sliderTopK: document.getElementById('slider-top-k'),
    inputHybridAlpha: document.getElementById('input-hybrid-alpha'),
    sliderHybridAlpha: document.getElementById('slider-hybrid-alpha'),
    hybridAlphaDesc: document.getElementById('hybrid-alpha-desc'),
    inputTemperature: document.getElementById('input-temperature'),
    sliderTemperature: document.getElementById('slider-temperature'),
    temperatureDesc: document.getElementById('temperature-desc')
};

// Initialization
document.addEventListener('DOMContentLoaded', () => {
    initApp();
    setupEventListeners();
});

async function initApp() {
    // 1. Fetch System Specs & Recomended Default Models
    try {
        const response = await fetch('/api/specs');
        const specs = await response.json();
        elements.hardwareSpec.innerHTML = `🖥️ ${specs.cpu_cores} Thrs | ${specs.ram_gb}GB RAM | GPU: ${specs.gpu_name}`;
        elements.statusIndicator.innerText = `● ${specs.mode} 분석 완료`;
        
        // Default destination folder path
        elements.destInput.value = window.location.pathname.substring(0, window.location.pathname.lastIndexOf('/')) + 'converted_outputs';
        if (elements.destInput.value === 'converted_outputs') {
            elements.destInput.value = 'C:\\AMEVA_Converted';
        }
    } catch (e) {
        console.error("Failed to load hardware specs", e);
    }

    // 2. Fetch Installed Models
    await refreshModels();
    
    // 3. Build Worker UI elements (Tabs & Minimies)
    buildWorkerUI();

    // 4. Fetch RAG Settings
    await loadRagSettings();
}

function setupEventListeners() {
    // Model Manager Modal
    elements.btnModelManager.addEventListener('click', () => {
        elements.modalManager.classList.add('open');
        refreshModalTable();
    });
    elements.modalClose.addEventListener('click', () => {
        elements.modalManager.classList.remove('open');
    });
    elements.btnModalRefresh.addEventListener('click', () => {
        refreshModalTable();
    });

    // RAG Source Modal Close
    const modalRagSource = document.getElementById('modal-rag-source');
    const modalRagClose = document.getElementById('modal-rag-close');
    const btnRagModalClose = document.getElementById('btn-rag-modal-close');
    if (modalRagClose) {
        modalRagClose.addEventListener('click', () => modalRagSource.classList.remove('open'));
    }
    if (btnRagModalClose) {
        btnRagModalClose.addEventListener('click', () => modalRagSource.classList.remove('open'));
    }

    // File input actions
    elements.btnAddFiles.addEventListener('click', () => elements.fileInputRaw.click());
    elements.fileInputRaw.addEventListener('change', handleFileSelection);

    // Link add action
    elements.btnAddLink.addEventListener('click', handleLinkAddition);

    // Clear queue
    elements.btnClear.addEventListener('click', () => {
        fileQueue = [];
        renderQueue();
        updateRunButtonState();
    });

    // Start execution
    elements.btnRun.addEventListener('click', toggleTaskExecution);

    // Dynamic threads count change updates Worker Minimies
    elements.threadSelect.addEventListener('change', buildWorkerUI);

    // Tab switching
    elements.btnMainLog.addEventListener('click', () => switchTab(0));

    // Chat RAG actions
    elements.btnSendChat.addEventListener('click', sendChatMsg);
    elements.chatInput.addEventListener('keypress', (e) => {
        if (e.key === 'Enter') sendChatMsg();
    });

    // RAG Settings Modal events
    elements.btnRagSettings.addEventListener('click', () => {
        elements.modalRagSettings.classList.add('open');
    });
    
    const closeRagSettings = () => {
        elements.modalRagSettings.classList.remove('open');
    };
    
    elements.modalRagSettingsClose.addEventListener('click', closeRagSettings);
    elements.btnRagSettingsCancel.addEventListener('click', closeRagSettings);
    
    // Slide bar & number field sync logic
    setupRagSettingSync(elements.sliderChunkOverlap, elements.inputChunkOverlap, null);
    setupRagSettingSync(elements.sliderTopK, elements.inputTopK, null);
    setupRagSettingSync(elements.sliderHybridAlpha, elements.inputHybridAlpha, updateHybridAlphaLabel);
    setupRagSettingSync(elements.sliderTemperature, elements.inputTemperature, updateTemperatureLabel);
    
    elements.btnRagSettingsApply.addEventListener('click', applyRagSettings);
}

// Build Worker Minimies and Tab logs dynamically
function buildWorkerUI() {
    const threadCount = parseInt(elements.threadSelect.value);
    
    // Clear dynamic UI elements
    elements.minimiContainer.innerHTML = '';
    elements.workerTabsContainer.innerHTML = '';
    elements.workerLogViews.innerHTML = '';
    
    for (let i = 1; i <= threadCount; i++) {
        // Create worker minimi
        const minimi = document.createElement('div');
        minimi.className = 'worker-minimi';
        minimi.id = `worker-minimi-${i}`;
        minimi.innerHTML = `
            <span class="worker-icon" id="worker-icon-${i}">😴</span>
            <span class="worker-label">P-${i}</span>
        `;
        minimi.addEventListener('click', () => switchTab(i));
        elements.minimiContainer.appendChild(minimi);
        
        // Create worker tab
        const tab = document.createElement('button');
        tab.className = 'log-tab';
        tab.setAttribute('data-tab', i);
        tab.id = `btn-tab-${i}`;
        tab.innerText = `🤖 Worker P-${i}`;
        tab.addEventListener('click', () => switchTab(i));
        elements.workerTabsContainer.appendChild(tab);
        
        // Create worker log display
        const display = document.createElement('div');
        display.className = 'log-display';
        display.id = `log-view-${i}`;
        elements.workerLogViews.appendChild(display);
    }

    // Reset current tab if it goes out of range
    if (currentTab > threadCount) {
        switchTab(0);
    }
}

function switchTab(tabIndex) {
    currentTab = tabIndex;
    
    // Remove active state from all tabs
    document.querySelectorAll('.log-tab').forEach(t => t.classList.remove('active'));
    document.querySelectorAll('.log-display').forEach(d => d.classList.remove('active'));
    
    if (tabIndex === 0) {
        elements.btnMainLog.classList.add('active');
        elements.logViewMain.classList.add('active');
    } else {
        const activeTab = document.getElementById(`btn-tab-${tabIndex}`);
        const activeView = document.getElementById(`log-view-${tabIndex}`);
        if (activeTab && activeView) {
            activeTab.classList.add('active');
            activeView.classList.add('active');
        }
    }
}

// Fetch installed models list from server
async function refreshModels() {
    try {
        const response = await fetch('/api/models');
        const data = await response.json();
        
        elements.modelSelect.innerHTML = '';
        if (data.installed.length === 0) {
            elements.modelSelect.innerHTML = '<option value="">설치된 모델이 없습니다. 모델 관리를 사용하세요.</option>';
        } else {
            data.installed.forEach(m => {
                const opt = document.createElement('option');
                opt.value = m.name;
                opt.innerText = `${m.name} (${m.size_gb}GB)`;
                elements.modelSelect.appendChild(opt);
            });
        }
        updateRunButtonState();
    } catch (e) {
        console.error("Failed to fetch models", e);
    }
}

function updateRunButtonState() {
    const hasFiles = fileQueue.length > 0;
    const hasModel = elements.modelSelect.value !== "";
    
    if (hasFiles && hasModel && !runningTask) {
        elements.btnRun.disabled = false;
        elements.btnRun.style.backgroundColor = '#d35400';
    } else {
        elements.btnRun.disabled = true;
        elements.btnRun.style.backgroundColor = '#333';
    }
}

// File and Link queue management
async function handleFileSelection(e) {
    const files = e.target.files;
    if (!files.length) return;
    
    for (let file of files) {
        const formData = new FormData();
        formData.append('file', file);
        
        appendLog(`[SYSTEM] 파일 업로드 중: ${file.name}...`);
        
        try {
            const res = await fetch('/api/upload', {
                method: 'POST',
                body: formData
            });
            const data = await res.json();
            
            fileQueue.push({
                name: data.filename,
                path: data.path,
                size: data.size,
                summarize: true,
                is_done: false,
                output_paths: null
            });
            
            appendLog(`<font color='#2ecc71'>✔ 업로드 성공: ${data.filename}</font>`);
        } catch (err) {
            appendLog(`<font color='red'>✘ 업로드 실패: ${file.name} - ${err.message}</font>`);
        }
    }
    
    renderQueue();
    updateRunButtonState();
    elements.fileInputRaw.value = ''; // Reset file input
}

async function handleLinkAddition() {
    const url = prompt("다운로드 URL (Google Drive/Sheets 등)을 입력하세요:");
    if (!url || !url.trim()) return;
    
    appendLog(`[SYSTEM] 링크 분석 및 파일 가져오는 중...`);
    
    const formData = new FormData();
    formData.append('url', url.trim());
    
    try {
        const res = await fetch('/api/download-link', {
            method: 'POST',
            body: formData
        });
        const data = await res.json();
        
        fileQueue.push({
            name: data.filename,
            path: data.path,
            size: data.size,
            summarize: true,
            is_done: false,
            output_paths: null
        });
        
        appendLog(`<font color='#2ecc71'>✔ 다운로드 성공: ${data.filename}</font>`);
    } catch (err) {
        appendLog(`<font color='red'>✘ 다운로드 실패: ${err.message}</font>`);
    }
    
    renderQueue();
    updateRunButtonState();
}

function renderQueue() {
    elements.fileQueueList.innerHTML = '';
    
    fileQueue.forEach((item, index) => {
        const li = document.createElement('li');
        li.className = `file-item ${item.is_done ? 'done' : ''}`;
        
        // Status tag
        let tag = item.is_done ? '[완료]' : '[요약]';
        
        li.innerHTML = `
            <input type="checkbox" id="chk-file-${index}" ${item.summarize ? 'checked' : ''} ${item.is_done ? 'disabled' : ''}>
            <span class="file-name" id="name-file-${index}">${tag} ${item.name}</span>
            <div class="actions-links" id="links-file-${index}"></div>
        `;
        
        elements.fileQueueList.appendChild(li);
        
        // Add check listener
        const chk = document.getElementById(`chk-file-${index}`);
        chk.addEventListener('change', (e) => {
            fileQueue[index].summarize = e.target.checked;
        });
        
        // Add output download links if available
        if (item.is_done && item.output_paths) {
            const linkArea = document.getElementById(`links-file-${index}`);
            if (item.output_paths.base_url) {
                linkArea.innerHTML += `<a href="${item.output_paths.base_url}" target="_blank" class="file-action-btn">기본 PDF</a> `;
            }
            if (item.output_paths.summary_url) {
                linkArea.innerHTML += `<a href="${item.output_paths.summary_url}" target="_blank" class="file-action-btn">요약 PDF</a> `;
            }
            if (item.output_paths.audio_url) {
                linkArea.innerHTML += `<a href="${item.output_paths.audio_url}" target="_blank" class="file-action-btn">오디오북</a>`;
            }
        }
    });
}

// Modal Model Manager logic
const availableModels = [
    { name: "gemma2:2b", desc: "구글 경량 모델", req: "RAM 4GB 이상" },
    { name: "qwen2.5:1.5b", desc: "Qwen 초경량 모델", req: "RAM 4GB 이상" },
    { name: "llama3.1:8b", desc: "Meta 범용 모델", req: "RAM 16GB, VRAM 6GB 이상" },
    { name: "qwen2.5-coder:7b", desc: "코딩/문서 특화", req: "RAM 16GB, VRAM 6GB 이상" }
];

async function refreshModalTable() {
    elements.modelTableBody.innerHTML = '<tr><td colspan="4" style="text-align:center;">불러오는 중...</td></tr>';
    
    try {
        const response = await fetch('/api/models');
        const data = await response.json();
        const installedNames = data.installed.map(m => m.name);
        
        elements.modelTableBody.innerHTML = '';
        
        availableModels.forEach((model) => {
            const tr = document.createElement('tr');
            
            // Check if installed
            const isInstalled = installedNames.some(name => name.includes(model.name));
            
            // Status cell
            const statusCell = document.createElement('td');
            statusCell.style.textAlign = 'center';
            statusCell.innerHTML = isInstalled ? 
                `<span style="color:#2ecc71; font-weight:bold; font-size: 1.2rem;">✔</span>` : 
                `<span style="color:#7f8c8d; font-size: 1.2rem;">○</span>`;
            tr.appendChild(statusCell);
            
            // Model name cell
            const nameCell = document.createElement('td');
            nameCell.innerText = model.name;
            tr.appendChild(nameCell);
            
            // Spec cell
            const specCell = document.createElement('td');
            specCell.innerText = `${model.desc} (${model.req})`;
            tr.appendChild(specCell);
            
            // Action cell
            const actionCell = document.createElement('td');
            actionCell.id = `action-model-${model.name.replace(/[^a-zA-Z0-9]/g, '_')}`;
            if (isInstalled) {
                const btn = document.createElement('button');
                btn.className = 'btn btn-danger';
                btn.style.padding = '4px 8px';
                btn.innerText = '삭제';
                btn.onclick = () => deleteModel(model.name);
                actionCell.appendChild(btn);
            } else {
                const btn = document.createElement('button');
                btn.className = 'btn btn-primary';
                btn.style.padding = '4px 8px';
                btn.innerText = '설치';
                btn.onclick = () => pullModel(model.name);
                actionCell.appendChild(btn);
            }
            tr.appendChild(actionCell);
            
            elements.modelTableBody.appendChild(tr);
        });
    } catch (e) {
        elements.modelTableBody.innerHTML = '<tr><td colspan="4" style="text-align:center;color:red;">새로고침 에러</td></tr>';
    }
}

async function deleteModel(name) {
    if (!confirm(`${name} 모델을 삭제하겠습니까?`)) return;
    
    const formData = new FormData();
    formData.append('model_name', name);
    
    try {
        await fetch('/api/models/delete', {
            method: 'POST',
            body: formData
        });
        refreshModalTable();
        refreshModels();
    } catch (err) {
        alert("모델 삭제 실패: " + err.message);
    }
}

async function pullModel(name) {
    const actionCell = document.getElementById(`action-model-${name.replace(/[^a-zA-Z0-9]/g, '_')}`);
    actionCell.innerHTML = `
        <div class="modal-pbar">
            <div class="modal-pbar-chunk" id="pbar-chunk-${name.replace(/[^a-zA-Z0-9]/g, '_')}" style="width: 0%;"></div>
            <span class="modal-pbar-text" id="pbar-text-${name.replace(/[^a-zA-Z0-9]/g, '_')}">준비 중...</span>
        </div>
    `;
    
    const formData = new FormData();
    formData.append('model_name', name);
    
    try {
        const response = await fetch('/api/models/pull', {
            method: 'POST',
            body: formData
        });
        
        const reader = response.body.getReader();
        const decoder = new TextDecoder();
        let buffer = '';
        
        while (true) {
            const { value, done } = await reader.read();
            if (done) break;
            
            buffer += decoder.decode(value);
            const lines = buffer.split('\n');
            
            // Keep last element in buffer in case it is incomplete
            buffer = lines.pop();
            
            for (let line of lines) {
                if (line.startsWith('data: ')) {
                    const data = JSON.parse(line.substring(6));
                    
                    const progressChunk = document.getElementById(`pbar-chunk-${name.replace(/[^a-zA-Z0-9]/g, '_')}`);
                    const progressText = document.getElementById(`pbar-text-${name.replace(/[^a-zA-Z0-9]/g, '_')}`);
                    
                    if (data.status === 'progress') {
                        if (progressChunk) progressChunk.style.width = `${data.percent}%`;
                        if (progressText) progressText.innerText = `${data.message} (${Math.round(data.percent)}%)`;
                    } else if (data.status === 'success') {
                        appendLog(`<font color='#2ecc71'>✔ [SYSTEM] ${data.message}</font>`);
                        refreshModalTable();
                        refreshModels();
                    } else if (data.status === 'error') {
                        alert(data.message);
                        refreshModalTable();
                    }
                }
            }
        }
    } catch (err) {
        alert("모델 소환 실패: " + err.message);
        refreshModalTable();
    }
}

// WebSocket task running & SRE telemetry loop
function toggleTaskExecution() {
    if (runningTask) {
        // Stop command
        if (wsConnection) {
            wsConnection.send(JSON.stringify({ action: "stop" }));
        }
    } else {
        // Start command
        startTaskExecution();
    }
}

function startTaskExecution() {
    const model = elements.modelSelect.value;
    const dest = elements.destInput.value;
    const threadCount = parseInt(elements.threadSelect.value);
    const doTts = elements.cbTts.checked;
    
    if (!model || fileQueue.length === 0 || !dest) return;
    
    // Clear terminals
    elements.logViewMain.innerHTML = '';
    document.querySelectorAll('.log-display').forEach(d => {
        if (d.id !== 'log-view-main') d.innerText = '';
    });
    
    // Reset worker icons
    for (let i = 1; i <= threadCount; i++) {
        const icon = document.getElementById(`worker-icon-${i}`);
        const minimi = document.getElementById(`worker-minimi-${i}`);
        if (icon) icon.innerText = '😴';
        if (minimi) minimi.style.backgroundColor = 'transparent';
    }
    
    runningTask = true;
    elements.btnRun.innerText = '작업 중지';
    elements.btnRun.style.backgroundColor = '#c0392b';
    elements.btnModelManager.disabled = true;
    elements.btnRagSettings.disabled = true;
    elements.btnAddFiles.disabled = true;
    elements.btnAddLink.disabled = true;
    elements.btnClear.disabled = true;
    elements.threadSelect.disabled = true;
    
    // Chat block to protect VRAM during summaries
    elements.chatInput.disabled = true;
    elements.btnSendChat.disabled = true;
    elements.chatInput.placeholder = "요약 중에는 VRAM 보호를 위해 채팅이 제한됩니다...";
    
    // Animate police
    elements.srePolice.classList.add('police-patrolling');
    
    // Open WebSocket
    const wsUrl = `ws://${window.location.host}/ws/process`;
    wsConnection = new WebSocket(wsUrl);
    
    wsConnection.onopen = () => {
        wsConnection.send(JSON.stringify({
            action: "start",
            files_data: fileQueue.map(f => ({ path: f.path, summarize: f.summarize, is_done: f.is_done })),
            dest: dest,
            model: model,
            thread_count: threadCount,
            do_tts: doTts
        }));
    };
    
    wsConnection.onmessage = (event) => {
        const msg = JSON.parse(event.data);
        const payload = msg.payload;
        
        switch (msg.type) {
            case "stats":
                updateTelemetry(payload);
                break;
            case "log":
                appendLog(payload);
                break;
            case "status_msg":
                elements.currentAction.innerText = payload;
                break;
            case "progress":
                elements.globalProgressBar.style.width = `${payload}%`;
                break;
            case "file_start":
                // Handle file starts (clear dynamic minimies/tabs)
                break;
            case "worker_state":
                updateWorkerMinimi(payload);
                break;
            case "worker_stream":
                appendWorkerLog(payload.t_id, payload.text);
                break;
            case "file_done":
                fileQueue[payload.file_idx].is_done = true;
                fileQueue[payload.file_idx].output_paths = payload.output_paths;
                renderQueue();
                break;
            case "rag_ready":
                ragContext = payload.context;
                chatHistory = [];
                const banner = document.createElement('div');
                banner.innerHTML = `<hr style='border:1px dashed var(--border-color); margin:10px 0;'><b>[시스템]</b> 🧠 RAG 메모리 최적화 완료! 이제 문서에 대해 질문해 보세요.`;
                elements.chatDisplay.appendChild(banner);
                elements.chatDisplay.scrollTop = elements.chatDisplay.scrollHeight;
                break;
            case "finished":
                stopTaskUI();
                break;
        }
    };
    
    wsConnection.onclose = () => {
        stopTaskUI();
    };
    
    wsConnection.onerror = (err) => {
        appendLog(`<font color='red'>[ERROR] 통신 오류가 발생했습니다: ${err.message}</font>`);
        stopTaskUI();
    };
}

function stopTaskUI() {
    runningTask = false;
    elements.btnRun.innerText = 'AI 변환 시작';
    elements.btnRun.style.backgroundColor = '#d35400';
    elements.btnModelManager.disabled = false;
    elements.btnRagSettings.disabled = false;
    elements.btnAddFiles.disabled = false;
    elements.btnAddLink.disabled = false;
    elements.btnClear.disabled = false;
    elements.threadSelect.disabled = false;
    
    // Enable Chat
    elements.chatInput.disabled = false;
    elements.btnSendChat.disabled = false;
    elements.chatInput.placeholder = "요약된 문서에 대해 질문하세요...";
    
    // Stop police patrol
    elements.srePolice.classList.remove('police-patrolling');
    elements.srePolice.style.left = '0%';
    
    // Set completed anims for workers
    const threadCount = parseInt(elements.threadSelect.value);
    for (let i = 1; i <= threadCount; i++) {
        const icon = document.getElementById(`worker-icon-${i}`);
        const minimi = document.getElementById(`worker-minimi-${i}`);
        if (icon && icon.innerText !== '💀') {
            icon.innerText = '🎉';
            if (minimi) minimi.style.backgroundColor = 'rgba(39, 174, 96, 0.4)';
        }
    }
    
    if (wsConnection) {
        wsConnection.close();
        wsConnection = null;
    }
    updateRunButtonState();
}

function updateTelemetry(data) {
    // Bars
    elements.cpuBar.style.width = `${data.cpu}%`;
    elements.cpuText.innerText = `${Math.round(data.cpu)}%`;
    
    elements.ramBar.style.width = `${data.ram}%`;
    elements.ramText.innerText = `${Math.round(data.ram)}%`;
    
    elements.gpuBar.style.width = `${data.gpu}%`;
    elements.gpuText.innerText = `${Math.round(data.gpu)}%`;
    
    // Stats
    elements.statTime.innerText = `⏱️ ${data.time_str}`;
    elements.statPower.innerText = `⚡ ${data.power_wh.toFixed(4)} Wh (${data.power_w.toFixed(1)}W)`;
    elements.statTokens.innerText = `🪙 ${data.tokens.toLocaleString()} T`;
}

function updateWorkerMinimi(data) {
    const icon = document.getElementById(`worker-icon-${data.t_id}`);
    const minimi = document.getElementById(`worker-minimi-${data.t_id}`);
    if (!icon || !minimi) return;
    
    if (data.is_dead) {
        icon.innerText = '💀';
        minimi.style.backgroundColor = 'rgba(231, 76, 60, 0.4)';
    } else if (data.is_working) {
        // Alternate frames
        const frames = ["🔨🤖", "⚡🤖"];
        icon.innerText = frames[data.current % 2];
        
        const progress = data.current / data.total;
        minimi.style.backgroundColor = `rgba(39, 174, 96, ${progress})`;
    } else {
        icon.innerText = '✅';
        minimi.style.backgroundColor = 'rgba(39, 174, 96, 0.7)';
    }
}

// Log utility helpers
function appendLog(html) {
    const ts = new Date().toLocaleTimeString('ko-KR', { hour12: false });
    const wrapper = document.createElement('div');
    wrapper.innerHTML = `<span style="color:#7f8c8d;">[${ts}]</span> ${html}`;
    elements.logViewMain.appendChild(wrapper);
    elements.logViewMain.scrollTop = elements.logViewMain.scrollHeight;
}

function appendWorkerLog(tId, text) {
    const view = document.getElementById(`log-view-${tId}`);
    if (view) {
        view.innerText += text;
        view.scrollTop = view.scrollHeight;
    }
}

// Chat functions
async function sendChatMsg() {
    const query = elements.chatInput.value.trim();
    if (!query) return;
    
    const model = elements.modelSelect.value;
    if (!model) return;
    
    // Append user message
    const userBubble = document.createElement('div');
    userBubble.className = 'chat-bubble user';
    userBubble.innerText = query;
    elements.chatDisplay.appendChild(userBubble);
    elements.chatInput.value = '';
    
    // Append AI bubble wrapper
    const aiBubble = document.createElement('div');
    aiBubble.className = 'chat-bubble assistant';
    aiBubble.innerText = '생각 중...';
    elements.chatDisplay.appendChild(aiBubble);
    
    elements.chatDisplay.scrollTop = elements.chatDisplay.scrollHeight;
    
    // Disable inputs during chat processing
    elements.chatInput.disabled = true;
    elements.btnSendChat.disabled = true;
    
    // Setup history
    chatHistory.push({ role: 'user', content: query });
    
    const formData = new FormData();
    formData.append('model', model);
    formData.append('messages', JSON.stringify(chatHistory));
    
    try {
        const response = await fetch('/api/chat', {
            method: 'POST',
            body: formData
        });
        
        aiBubble.innerText = '';
        
        const reader = response.body.getReader();
        const decoder = new TextDecoder();
        let replyText = '';
        let cleanReply = '';
        let sources = null;
        
        while (true) {
            const { value, done } = await reader.read();
            if (done) break;
            
            const text = decoder.decode(value);
            replyText += text;
            
            if (replyText.includes('__RAG_SOURCES__')) {
                const parts = replyText.split('__RAG_SOURCES__');
                cleanReply = parts[0].trim();
                aiBubble.innerText = cleanReply;
                try {
                    sources = JSON.parse(parts[1].trim());
                } catch (e) {
                    // JSON parsing might be incomplete during stream
                }
            } else {
                aiBubble.innerText = replyText;
            }
            elements.chatDisplay.scrollTop = elements.chatDisplay.scrollHeight;
        }
        
        // Final parsing check
        if (replyText.includes('__RAG_SOURCES__')) {
            const parts = replyText.split('__RAG_SOURCES__');
            cleanReply = parts[0].trim();
            aiBubble.innerText = cleanReply;
            try {
                sources = JSON.parse(parts[1].trim());
                if (sources && sources.length > 0) {
                    renderSources(aiBubble, sources, query);
                }
            } catch (e) {
                console.error("Failed to parse sources", e);
            }
            chatHistory.push({ role: 'assistant', content: cleanReply });
        } else {
            chatHistory.push({ role: 'assistant', content: replyText });
        }
    } catch (err) {
        aiBubble.innerText = `[대답 생성 중 오류 발생: ${err.message}]`;
    } finally {
        elements.chatInput.disabled = false;
        elements.btnSendChat.disabled = false;
        elements.chatInput.focus();
    }
}

function renderSources(bubbleElement, sources, query) {
    const sourcesContainer = document.createElement('div');
    sourcesContainer.className = 'chat-sources';
    sourcesContainer.style.marginTop = '8px';
    sourcesContainer.style.paddingTop = '6px';
    sourcesContainer.style.borderTop = '1px dashed rgba(255,255,255,0.1)';
    sourcesContainer.style.fontSize = '0.75rem';
    sourcesContainer.style.display = 'flex';
    sourcesContainer.style.gap = '8px';
    sourcesContainer.style.flexWrap = 'wrap';
    
    const label = document.createElement('span');
    label.style.color = 'var(--text-muted)';
    label.innerText = '출처: ';
    sourcesContainer.appendChild(label);
    
    sources.forEach((src, idx) => {
        const link = document.createElement('a');
        link.href = '#';
        link.style.color = 'var(--color-primary)';
        link.style.textDecoration = 'underline';
        link.style.fontWeight = 'bold';
        link.innerText = `[출처 ${idx + 1}]`;
        link.onclick = (e) => {
            e.preventDefault();
            openRAGModal(src, query);
        };
        sourcesContainer.appendChild(link);
    });
    
    bubbleElement.appendChild(sourcesContainer);
}

function openRAGModal(src, query) {
    const modal = document.getElementById('modal-rag-source');
    const textContainer = document.getElementById('rag-modal-text');
    const scoreContainer = document.getElementById('rag-modal-score');
    const title = document.getElementById('rag-modal-title');
    
    title.innerText = `출처 [인덱스 #${src.index + 1}]`;
    scoreContainer.innerText = `유사도 점수: ${(src.score * 100).toFixed(1)}%`;
    
    // Highlight matched words from the query
    let highlightedText = src.text;
    
    const terms = query.toLowerCase().match(/[가-힣a-zA-Z0-9]+/g);
    if (terms) {
        const uniqueTerms = [...new Set(terms)].sort((a, b) => b.length - a.length);
        
        uniqueTerms.forEach(term => {
            if (term.length < 2) return;
            const escapedTerm = term.replace(/[-\/\\^$*+?.()|[\]{}]/g, '\\$&');
            const regex = new RegExp(`(${escapedTerm})`, 'gi');
            highlightedText = highlightedText.replace(regex, '<mark style="background-color: rgba(241, 196, 15, 0.4); color: #fff; padding: 2px 4px; border-radius: 3px; border-bottom: 2px solid #f1c40f;">$1</mark>');
        });
    }
    
    textContainer.innerHTML = highlightedText;
    modal.classList.add('open');
}

function setupRagSettingSync(slider, input, labelUpdateFn) {
    slider.addEventListener('input', (e) => {
        input.value = e.target.value;
        if (labelUpdateFn) labelUpdateFn(e.target.value);
    });
    input.addEventListener('change', (e) => {
        let val = parseFloat(e.target.value);
        if (isNaN(val)) val = parseFloat(slider.value);
        
        // Clamp values
        const min = parseFloat(input.min);
        const max = parseFloat(input.max);
        if (val < min) val = min;
        if (val > max) val = max;
        
        input.value = val;
        slider.value = val;
        if (labelUpdateFn) labelUpdateFn(val);
    });
}

function updateHybridAlphaLabel(val) {
    val = parseFloat(val);
    let desc = "";
    if (val === 0.0) desc = "0.0 (Sparse 전용)";
    else if (val <= 0.4) desc = `${val.toFixed(2)} (Sparse 위주)`;
    else if (val === 0.5) desc = "0.5 (Hybrid)";
    else if (val <= 0.9) desc = `${val.toFixed(2)} (Dense 위주)`;
    else desc = "1.0 (Dense 전용)";
    elements.hybridAlphaDesc.innerText = desc;
}

function updateTemperatureLabel(val) {
    val = parseFloat(val);
    let desc = "";
    if (val <= 0.4) desc = `${val.toFixed(2)} (Fact 중심)`;
    else if (val < 1.0) desc = `${val.toFixed(2)} (균형 모드)`;
    else desc = `${val.toFixed(2)} (Creativity 중심)`;
    elements.temperatureDesc.innerText = desc;
}

async function loadRagSettings() {
    try {
        const res = await fetch('/api/rag/settings');
        const data = await res.json();
        
        elements.inputChunkOverlap.value = data.chunk_overlap;
        elements.sliderChunkOverlap.value = data.chunk_overlap;
        
        elements.inputTopK.value = data.top_k;
        elements.sliderTopK.value = data.top_k;
        
        elements.inputHybridAlpha.value = data.hybrid_alpha;
        elements.sliderHybridAlpha.value = data.hybrid_alpha;
        updateHybridAlphaLabel(data.hybrid_alpha);
        
        elements.inputTemperature.value = data.temperature;
        elements.sliderTemperature.value = data.temperature;
        updateTemperatureLabel(data.temperature);
    } catch (e) {
        console.error("Failed to load RAG settings", e);
    }
}

async function applyRagSettings() {
    const formData = new FormData();
    formData.append('chunk_overlap', elements.inputChunkOverlap.value);
    formData.append('top_k', elements.inputTopK.value);
    formData.append('hybrid_alpha', elements.inputHybridAlpha.value);
    formData.append('temperature', elements.inputTemperature.value);
    
    try {
        const res = await fetch('/api/rag/settings', {
            method: 'POST',
            body: formData
        });
        const result = await res.json();
        if (result.success) {
            elements.modalRagSettings.classList.remove('open');
            appendLog(`<font color='#2ecc71'>✔ RAG 설정 적용 완료 (Overlap: ${result.settings.chunk_overlap}자, Top-K: ${result.settings.top_k}개, Hybrid Alpha: ${result.settings.hybrid_alpha}, Temp: ${result.settings.temperature})</font>`);
            
            // If RAG context is already loaded, notify user
            if (ragContext) {
                const banner = document.createElement('div');
                banner.innerHTML = `<hr style='border:1px dashed var(--border-color); margin:10px 0;'><b>[시스템]</b> ⚙️ RAG 실시간 제어 설정이 변경되었습니다. 다음 질문부터 적용됩니다.`;
                elements.chatDisplay.appendChild(banner);
                elements.chatDisplay.scrollTop = elements.chatDisplay.scrollHeight;
            }
        } else {
            alert("RAG 설정 적용에 실패했습니다.");
        }
    } catch (err) {
        alert("RAG 설정 적용 중 에러 발생: " + err.message);
    }
}

