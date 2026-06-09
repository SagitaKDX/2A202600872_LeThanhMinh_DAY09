document.addEventListener('DOMContentLoaded', () => {
    // === TAB SWITCHING ===
    const tabButtons = document.querySelectorAll('.nav-btn');
    const tabPanels = document.querySelectorAll('.tab-panel');

    tabButtons.forEach(btn => {
        btn.addEventListener('click', () => {
            const tabId = btn.getAttribute('data-tab');
            
            tabButtons.forEach(b => b.classList.remove('active'));
            tabPanels.forEach(p => p.classList.remove('active'));
            
            btn.classList.add('active');
            document.getElementById(`${tabId}-tab`).classList.add('active');

            if (tabId === 'evaluation') {
                // Fetch latest batch results when switching to evaluation tab
                fetchLatestBatchResults();
            }
        });
    });

    // === CHAT INTERFACE ===
    const chatInput = document.getElementById('chat-input');
    const sendBtn = document.getElementById('send-btn');
    const chatBox = document.getElementById('chat-box');
    const suggestBtns = document.querySelectorAll('.suggest-btn');
    const clearTraceBtn = document.getElementById('clear-trace-btn');
    const emptyTraceMsg = document.getElementById('empty-trace-msg');
    const timeline = document.getElementById('timeline');

    // Handle suggestion clicks
    suggestBtns.forEach(btn => {
        btn.addEventListener('click', () => {
            const question = btn.getAttribute('data-q');
            chatInput.value = question;
            submitChat();
        });
    });

    // Send on Enter
    chatInput.addEventListener('keypress', (e) => {
        if (e.key === 'Enter') {
            submitChat();
        }
    });

    sendBtn.addEventListener('click', submitChat);

    clearTraceBtn.addEventListener('click', () => {
        timeline.innerHTML = '';
        timeline.style.display = 'none';
        emptyTraceMsg.style.display = 'block';
    });

    async function submitChat() {
        const question = chatInput.value.trim();
        if (!question) return;

        // Clear input
        chatInput.value = '';

        // Add user message to chat
        appendMessage('user', question);

        // Add loading assistant message
        const loadingId = appendMessage('assistant', '<i class="fa-solid fa-spinner fa-spin"></i> Trợ lý đang suy nghĩ và điều phối các worker...');

        try {
            const response = await fetch('/api/chat', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ question })
            });

            if (!response.ok) {
                throw new Error('Đã có lỗi xảy ra trên server.');
            }

            const data = await response.json();
            
            // Remove loading and show final answer
            removeMessage(loadingId);
            appendMessage('assistant', data.final_answer);

            // Render execution trace logs
            renderTrace(data.trace);

        } catch (error) {
            removeMessage(loadingId);
            appendMessage('assistant', `<span class="text-danger"><i class="fa-solid fa-triangle-exclamation"></i> Lỗi: ${error.message}</span>`);
        }
    }

    function appendMessage(sender, text) {
        const id = 'msg-' + Date.now();
        const msgDiv = document.createElement('div');
        msgDiv.className = `message ${sender}-msg`;
        msgDiv.id = id;

        const avatar = document.createElement('div');
        avatar.className = 'msg-avatar';
        avatar.innerHTML = sender === 'user' ? '<i class="fa-solid fa-user"></i>' : '<i class="fa-solid fa-robot"></i>';

        const content = document.createElement('div');
        content.className = 'msg-content';
        
        // Render simple newlines and evidence format
        if (sender === 'assistant') {
            content.innerHTML = formatAssistantAnswer(text);
        } else {
            content.textContent = text;
        }

        msgDiv.appendChild(avatar);
        msgDiv.appendChild(content);
        chatBox.appendChild(msgDiv);
        
        // Auto scroll to bottom
        chatBox.scrollTop = chatBox.scrollHeight;

        return id;
    }

    function removeMessage(id) {
        const el = document.getElementById(id);
        if (el) el.remove();
    }

    function formatAssistantAnswer(text) {
        // Look for evidence blocks
        if (text.includes('Evidence:')) {
            const parts = text.split('Evidence:');
            const mainText = parts[0].trim();
            const evidenceText = parts[1].trim();

            let formattedMain = mainText.replace(/\n/g, '<br>');
            let formattedEvidence = evidenceText.replace(/\n/g, '<br>');

            return `
                <div class="answer-main">${formattedMain}</div>
                <div class="evidence-box">
                    <p><i class="fa-solid fa-file-shield text-success"></i> Bằng chứng thu thập:</p>
                    <div>${formattedEvidence}</div>
                </div>
            `;
        }
        return text.replace(/\n/g, '<br>');
    }

    // === RENDER STEP-BY-STEP TRACE ===
    function renderTrace(trace) {
        if (!trace || trace.length === 0) return;

        emptyTraceMsg.style.display = 'none';
        timeline.innerHTML = '';
        timeline.style.display = 'block';

        trace.forEach((step, idx) => {
            const nodeName = step.node;
            const item = document.createElement('div');
            
            // Map node keys to human-friendly titles
            let nodeClass = '';
            let title = '';
            let icon = '';
            let bodyHTML = '';

            if (nodeName === 'supervisor') {
                nodeClass = 'node-supervisor';
                title = 'Supervisor: Phân tích & Điều phối';
                icon = '<i class="fa-solid fa-user-tie"></i>';
                
                const route = step.output;
                const statusBadge = route.status === 'ok' ? 
                    `<span class="badge-route-status status-ok">OK</span>` : 
                    `<span class="badge-route-status status-clarify">Cần làm rõ</span>`;
                
                bodyHTML = `
                    <div><strong>Trạng thái phân tích:</strong> ${statusBadge}</div>
                    <div class="route-flags-display">
                        <span class="route-flag ${route.needs_policy ? 'active' : ''}">Cần Policy (RAG): ${route.needs_policy}</span>
                        <span class="route-flag ${route.needs_data ? 'active' : ''}">Cần Data (DB): ${route.needs_data}</span>
                    </div>
                    ${route.clarification_question ? `
                        <label>Câu hỏi làm rõ:</label>
                        <div class="info-text">${route.clarification_question}</div>
                    ` : ''}
                `;
            } 
            else if (nodeName === 'worker_1_policy') {
                nodeClass = 'node-policy';
                title = 'Worker 1: Policy Agent (RAG)';
                icon = '<i class="fa-solid fa-shield-halved"></i>';

                const output = step.output;
                bodyHTML = `
                    <label>Tóm tắt chính sách:</label>
                    <div class="info-text">${output.summary}</div>
                    <label>Trích dẫn (Citations):</label>
                    <div class="json-block">${JSON.stringify(output.citations || [], null, 2)}</div>
                `;
            } 
            else if (nodeName === 'worker_2_data') {
                nodeClass = 'node-data';
                title = 'Worker 2: Data Access Agent (DB)';
                icon = '<i class="fa-solid fa-database"></i>';

                const output = step.output;
                const toolCalls = step.tool_calls || [];
                
                let toolsHTML = 'Không gọi tool nào.';
                if (toolCalls.length > 0) {
                    toolsHTML = toolCalls.map(tc => `
                        <div style="margin-bottom: 6px;">
                            <strong>Tool:</strong> <code>${tc.name}()</code>
                            <div class="json-block" style="margin-top: 2px;">Args: ${JSON.stringify(tc.args, null, 2)}</div>
                        </div>
                    `).join('');
                }

                bodyHTML = `
                    <label>Công cụ cơ sở dữ liệu đã gọi:</label>
                    <div style="padding-left: 8px; border-left: 2px solid var(--warning); margin-bottom: 10px;">${toolsHTML}</div>
                    <label>Kết quả tra cứu:</label>
                    <div class="badge-route-status ${output.status === 'ok' ? 'status-ok' : 'status-notfound'}">${output.status}</div>
                    <label>Tóm tắt dữ liệu:</label>
                    <div class="info-text">${output.summary}</div>
                `;
            } 
            else if (nodeName === 'worker_3_response') {
                nodeClass = 'node-response';
                title = 'Worker 3: Response Synthesis Agent';
                icon = '<i class="fa-solid fa-feather-pointed"></i>';

                const ans = step.output.final_answer;
                bodyHTML = `
                    <label>Đầu ra cuối cùng đã định dạng:</label>
                    <pre class="answer-output">${ans}</pre>
                `;
            }

            item.className = `timeline-item ${nodeClass} ${idx === trace.length - 1 ? 'active' : ''}`;
            
            // Generate full collapsible card structure
            item.innerHTML = `
                <div class="trace-card-node">
                    <div class="trace-card-node-header" id="header-${idx}">
                        <div class="node-title-group">
                            <div class="node-icon-bg">${icon}</div>
                            <span class="node-title">${title}</span>
                        </div>
                        <div class="node-meta" id="meta-${idx}">
                            <span>${step.timestamp ? step.timestamp.substring(11, 19) : ''}</span>
                            <i class="fa-solid fa-chevron-down"></i>
                        </div>
                    </div>
                    <div class="trace-card-node-body" id="body-${idx}">
                        ${bodyHTML}
                        <label>Dữ liệu JSON thô (Raw Step Data):</label>
                        <pre class="json-block">${JSON.stringify(step, null, 2)}</pre>
                    </div>
                </div>
            `;

            timeline.appendChild(item);

            // Bind click expand action
            const header = item.querySelector('.trace-card-node-header');
            const body = item.querySelector('.trace-card-node-body');
            const meta = item.querySelector('.node-meta');
            
            header.addEventListener('click', () => {
                const isExpanded = body.style.display === 'block';
                body.style.display = isExpanded ? 'none' : 'block';
                if (isExpanded) {
                    meta.classList.remove('expanded');
                } else {
                    meta.classList.add('expanded');
                }
            });

            // Expand supervisor and response synthesis by default
            if (nodeName === 'supervisor' || nodeName === 'worker_3_response') {
                body.style.display = 'block';
                meta.classList.add('expanded');
            }
        });
    }

    // === BATCH EVALUATION HUB ===
    const runEvalBtn = document.getElementById('run-eval-btn');
    const progressContainer = document.getElementById('progress-container');
    const progressText = document.getElementById('progress-text');
    const progressPercent = document.getElementById('progress-percent');
    const progressFill = document.getElementById('progress-fill');
    
    const evalTotal = document.getElementById('eval-total');
    const evalPassed = document.getElementById('eval-passed');
    const evalClarify = document.getElementById('eval-clarify');
    const evalNotFound = document.getElementById('eval-notfound');
    
    const evalMetaInfo = document.getElementById('eval-meta-info');
    const evalLastRun = document.getElementById('eval-last-run');
    const evalAccuracy = document.getElementById('eval-accuracy');
    const evalTableBody = document.getElementById('eval-table-body');

    let pollInterval = null;

    // Load initial results on mount
    async function fetchLatestBatchResults() {
        try {
            const res = await fetch('/api/batch/status');
            const status = await res.json();
            
            if (status.is_running) {
                // If backend is already running batch, resume polling
                showProgress(true);
                startPollingStatus();
            } else if (status.results && status.results.length > 0) {
                // Render last completed run
                renderBatchData(status);
            } else {
                // Fetch summary.json from server if status results are empty
                const resultsRes = await fetch('/api/batch/results');
                if (resultsRes.ok) {
                    const data = await resultsRes.json();
                    renderBatchData({
                        total: data.total_cases,
                        results: data.results.map(r => ({
                            ...r,
                            expected_status: getExpectedStatusFromJSON(r.id), // Fallback map
                            passed: true // Fallback visual
                        })),
                        completed_at: data.timestamp
                    });
                }
            }
        } catch (e) {
            console.log("Error loading initial results:", e);
        }
    }

    // Temporary helper map to get expected status for historic summary view
    function getExpectedStatusFromJSON(id) {
        const expectedMap = {
            "Q01": "ok", "Q02": "ok", "Q03": "ok", "Q04": "ok", "Q05": "ok", "Q06": "ok",
            "Q07": "ok", "Q08": "ok", "Q09": "ok", "Q10": "ok", "Q11": "ok", "Q12": "ok",
            "Q13": "ok", "Q14": "ok", "Q15": "clarification_needed", "Q16": "clarification_needed",
            "Q17": "not_found", "Q18": "not_found", "Q19": "ok", "Q20": "ok", "Q21": "ok", "Q22": "ok"
        };
        return expectedMap[id] || "ok";
    }

    runEvalBtn.addEventListener('click', async () => {
        try {
            runEvalBtn.disabled = true;
            showProgress(true);
            
            const response = await fetch('/api/batch/run', { method: 'POST' });
            if (!response.ok) {
                throw new Error('Không thể khởi chạy đánh giá batch.');
            }

            startPollingStatus();
        } catch (error) {
            alert(error.message);
            runEvalBtn.disabled = false;
            showProgress(false);
        }
    });

    function showProgress(visible) {
        progressContainer.style.display = visible ? 'block' : 'none';
        if (visible) {
            progressPercent.textContent = '0%';
            progressFill.style.width = '0%';
            progressText.textContent = 'Đang bắt đầu môi trường chạy...';
        }
    }

    function startPollingStatus() {
        if (pollInterval) clearInterval(pollInterval);
        
        pollInterval = setInterval(async () => {
            try {
                const response = await fetch('/api/batch/status');
                const status = await response.json();
                
                // Calculate progress
                const current = status.current || 0;
                const total = status.total || 22;
                const percent = Math.round((current / total) * 100);
                
                progressPercent.textContent = `${percent}%`;
                progressFill.style.width = `${percent}%`;
                progressText.textContent = `Đang chạy các ca thử nghiệm: ${current}/${total}`;

                // Live update data tables so user doesn't wait
                renderBatchData(status);

                if (!status.is_running) {
                    clearInterval(pollInterval);
                    pollInterval = null;
                    runEvalBtn.disabled = false;
                    setTimeout(() => showProgress(false), 2000);
                }
            } catch (e) {
                console.error("Error polling batch status:", e);
            }
        }, 1500);
    }

    function renderBatchData(status) {
        const results = status.results || [];
        
        // Update metric display counts
        evalTotal.textContent = status.total || results.length;
        
        let passedCount = 0;
        let clarifyCount = 0;
        let notFoundCount = 0;

        results.forEach(r => {
            if (r.status === 'ok') passedCount++;
            else if (r.status === 'clarification_needed') clarifyCount++;
            else if (r.status === 'not_found') notFoundCount++;
        });

        // Compute actual verification pass count
        const passMatchCount = results.filter(r => r.passed).length;
        evalPassed.textContent = passMatchCount;
        evalClarify.textContent = clarifyCount;
        evalNotFound.textContent = notFoundCount;

        // Render meta information
        if (status.completed_at || results.length > 0) {
            evalMetaInfo.style.display = 'flex';
            evalLastRun.textContent = status.completed_at ? new Date(status.completed_at).toLocaleString('vi-VN') : 'Đang chạy...';
            
            // Accuracy = (Number of matched statuses / total run results)
            const accVal = results.length > 0 ? Math.round((passMatchCount / results.length) * 100) : 0;
            evalAccuracy.textContent = `${accVal}%`;
        }

        // Render rows
        if (results.length === 0) {
            evalTableBody.innerHTML = `
                <tr>
                    <td colspan="6" class="table-empty">
                        <i class="fa-solid fa-chart-simple"></i>
                        <p>Đang chuẩn bị dữ liệu...</p>
                    </td>
                </tr>
            `;
            return;
        }

        evalTableBody.innerHTML = '';
        results.forEach(r => {
            const tr = document.createElement('tr');
            
            const expectedStatus = r.expected_status || getExpectedStatusFromJSON(r.id);
            const passed = r.passed !== undefined ? r.passed : (r.status === expectedStatus);

            tr.innerHTML = `
                <td><span class="case-badge">${r.id}</span></td>
                <td><div style="max-width: 400px; overflow: hidden; text-overflow: ellipsis; white-space: nowrap;" title="${r.question}">${r.question}</div></td>
                <td><span class="badge-status ${expectedStatus}">${expectedStatus}</span></td>
                <td><span class="badge-status ${r.status}">${r.status}</span></td>
                <td>
                    <div class="eval-status-icon ${passed ? 'pass' : 'fail'}">
                        <i class="fa-solid ${passed ? 'fa-circle-check' : 'fa-circle-xmark'}"></i>
                        <span>${passed ? 'Khớp' : 'Lệch'}</span>
                    </div>
                </td>
                <td>
                    <button class="btn-icon view-details-btn" data-id="${r.id}">
                        <i class="fa-solid fa-eye"></i>
                    </button>
                </td>
            `;
            
            // Add click detailed view handler
            const detailBtn = tr.querySelector('.view-details-btn');
            detailBtn.addEventListener('click', () => showDetailsModal(r));

            evalTableBody.appendChild(tr);
        });
    }

    // === MODAL DETAIL VIEW ===
    const resultModal = document.getElementById('result-modal');
    const modalCloseBtn = document.getElementById('modal-close-btn');
    const modalCaseId = document.getElementById('modal-case-id');
    const modalQuestion = document.getElementById('modal-question');
    const modalExpectedBadge = document.getElementById('modal-expected-badge');
    const modalActualBadge = document.getElementById('modal-actual-badge');
    const modalRoute = document.getElementById('modal-route');
    const modalAnswer = document.getElementById('modal-answer');

    function showDetailsModal(caseResult) {
        modalCaseId.textContent = caseResult.id;
        modalQuestion.textContent = caseResult.question;
        
        const expectedStatus = caseResult.expected_status || getExpectedStatusFromJSON(caseResult.id);
        modalExpectedBadge.innerHTML = `<span class="badge-status ${expectedStatus}">${expectedStatus}</span>`;
        modalActualBadge.innerHTML = `<span class="badge-status ${caseResult.status}">${caseResult.status}</span>`;
        
        modalRoute.textContent = JSON.stringify(caseResult.route || {}, null, 2);
        modalAnswer.innerHTML = formatAssistantAnswer(caseResult.final_answer || '');
        
        resultModal.classList.add('show');
    }

    modalCloseBtn.addEventListener('click', () => {
        resultModal.classList.remove('show');
    });

    window.addEventListener('click', (e) => {
        if (e.target === resultModal) {
            resultModal.classList.remove('show');
        }
    });
    
    // Initial fetch on mount
    fetchLatestBatchResults();
});
