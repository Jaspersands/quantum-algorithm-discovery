document.addEventListener('DOMContentLoaded', () => {
    let historyData = [];

    // Fetch and render data
    async function updateDashboard() {
        try {
            const [statusRes, queueRes, historyRes] = await Promise.all([
                fetch('status.json?nocache=' + Date.now()).then(r => r.json()).catch(() => ({ status: 'sleeping' })),
                fetch('queue.json?nocache=' + Date.now()).then(r => r.json()).catch(() => []),
                fetch('history.json?nocache=' + Date.now()).then(r => r.json()).catch(() => [])
            ]);

            renderStatus(statusRes);
            renderQueue(queueRes);
            historyData = historyRes;
            renderHistory(historyData);

        } catch (error) {
            console.error('Error fetching dashboard stats:', error);
        }
    }

    // Render live status
    function renderStatus(data) {
        const pulse = document.getElementById('global-pulse');
        const statusText = document.getElementById('global-status-text');
        const activeBadge = document.getElementById('active-badge');
        const noActive = document.getElementById('no-active-run');
        const activeDetails = document.getElementById('active-run-details');

        // Reset pulse styles
        pulse.className = 'pulse-indicator';
        activeBadge.className = 'badge';

        if (data.status === 'searching') {
            pulse.classList.add('active');
            statusText.innerText = 'SEARCHING FOR ALGORITHMS...';
            activeBadge.innerText = 'SEARCHING';
            activeBadge.classList.add('searching');

            noActive.classList.add('hidden');
            activeDetails.classList.remove('hidden');

            document.getElementById('active-problem-name').innerText = data.current_run?.problem_name || 'Quantum Discovery';
            document.getElementById('active-description').innerText = data.current_run?.description || '';

            // Update Progress Stepper
            const stages = ['theorist', 'simulating', 'synthesizing', 'analyzing'];
            const currentStage = data.current_run?.stage;
            const currentIdx = stages.indexOf(currentStage);

            stages.forEach((stage, idx) => {
                const stepElem = document.getElementById('step-' + stage);
                if (stepElem) {
                    stepElem.className = 'step';
                    if (idx < currentIdx) {
                        stepElem.classList.add('completed');
                    } else if (idx === currentIdx) {
                        stepElem.classList.add('active');
                    }
                }
            });

        } else if (data.status === 'sleeping') {
            pulse.classList.add('sleeping');
            statusText.innerText = 'RESTING BETWEEN SEARCHES';
            activeBadge.innerText = 'SLEEPING';
            activeBadge.classList.add('sleeping');

            noActive.classList.remove('hidden');
            activeDetails.classList.add('hidden');

            const countdown = document.getElementById('sleep-countdown');
            if (data.next_run_at) {
                const nextRun = new Date(data.next_run_at);
                const secondsLeft = Math.max(0, Math.floor((nextRun - new Date()) / 1000));
                countdown.innerText = `Next search run starts in ~${secondsLeft}s`;
            } else {
                countdown.innerText = 'Next search run is queueing up.';
            }
        } else {
            pulse.classList.add('idle');
            statusText.innerText = 'SYSTEM STANDBY';
            activeBadge.innerText = 'STANDBY';

            noActive.classList.remove('hidden');
            activeDetails.classList.add('hidden');
            document.getElementById('sleep-countdown').innerText = 'Persistent search engine is ready.';
        }
    }

    // Render backlog queue
    function renderQueue(items) {
        const queueList = document.getElementById('queue-list');
        const queueCount = document.getElementById('queue-count');
        queueList.innerHTML = '';
        queueCount.innerText = `${items.length} items`;

        if (items.length === 0) {
            queueList.innerHTML = `
                <div class="empty-state">
                    <p style="font-size: 0.85rem; color: var(--text-muted);">Backlog is empty. Theorist will queue items soon.</p>
                </div>
            `;
            return;
        }

        items.forEach(item => {
            const itemDiv = document.createElement('div');
            itemDiv.className = 'queue-item';
            
            const priorityClass = (item.priority || 'medium').toLowerCase();
            itemDiv.innerHTML = `
                <span class="theme">${item.theme || 'Exploration Topic'}</span>
                <span class="priority ${priorityClass}">${item.priority || 'Medium'}</span>
            `;
            queueList.appendChild(itemDiv);
        });
    }

    // Render search history
    function renderHistory(runs) {
        const historyList = document.getElementById('history-list');
        const historyCount = document.getElementById('history-count');
        historyList.innerHTML = '';
        historyCount.innerText = `${runs.length} runs`;

        if (runs.length === 0) {
            historyList.innerHTML = `
                <div class="empty-state">
                    <i class="fa-solid fa-folder-open"></i>
                    <p>No algorithms discovered yet.</p>
                </div>
            `;
            return;
        }

        runs.forEach((run, index) => {
            const card = document.createElement('div');
            card.className = 'history-card';
            card.addEventListener('click', () => openModal(run));

            card.innerHTML = `
                <div class="history-info">
                    <h3>${run.problem_name}</h3>
                    <p>${run.description}</p>
                </div>
                <div class="history-stats">
                    <span class="stat-pill speedup"><i class="fa-solid fa-gauge-high"></i> ${run.speedup_type || 'Unknown'}</span>
                    <span class="stat-pill success"><i class="fa-solid fa-circle-check"></i> ${run.success_rate * 100}%</span>
                    <i class="fa-solid fa-chevron-right"></i>
                </div>
            `;
            historyList.appendChild(card);
        });
    }

    // Filter history on search input
    document.getElementById('history-search').addEventListener('input', (e) => {
        const searchVal = e.target.value.toLowerCase();
        const filtered = historyData.filter(run => 
            run.problem_name.toLowerCase().includes(searchVal) ||
            run.description.toLowerCase().includes(searchVal) ||
            (run.speedup_type && run.speedup_type.toLowerCase().includes(searchVal))
        );
        renderHistory(filtered);
    });

    // Modal Operations
    const modal = document.getElementById('detail-modal');
    const closeModal = document.getElementById('close-modal');

    function openModal(run) {
        document.getElementById('modal-title').innerText = run.problem_name;
        document.getElementById('modal-speedup').innerText = run.speedup_type || 'Unknown';
        document.getElementById('modal-query').innerText = run.quantum_query_complexity || 'O(1)';
        document.getElementById('modal-gates').innerText = run.quantum_gate_complexity || 'O(N)';
        document.getElementById('modal-success').innerText = run.success_rate;
        document.getElementById('modal-description').innerText = run.description;

        // Code and theory text
        document.getElementById('modal-qiskit-code').innerText = run.synthesis_code || '# No code generated';
        document.getElementById('modal-analysis-text').innerText = run.analysis_text || 'No scaling details available.';
        document.getElementById('modal-applications-text').innerText = run.potential_applications || 'No practical application mapping available yet.';
        document.getElementById('modal-base-code').innerText = run.base_function_code || '# N/A';
        document.getElementById('modal-oracle-code').innerText = run.oracle_generator_code || '# N/A';

        // Reset tabs
        document.querySelectorAll('.tab-btn').forEach(btn => btn.classList.remove('active'));
        document.querySelectorAll('.tab-pane').forEach(pane => pane.classList.remove('active'));
        document.querySelector('[data-tab="tab-code"]').classList.add('active');
        document.getElementById('tab-code').classList.add('active');

        modal.classList.remove('hidden');
    }

    closeModal.addEventListener('click', () => {
        modal.classList.add('hidden');
    });

    window.addEventListener('click', (e) => {
        if (e.target === modal) {
            modal.classList.add('hidden');
        }
    });

    // Modal Tabs Navigation
    document.querySelectorAll('.tab-btn').forEach(button => {
        button.addEventListener('click', () => {
            document.querySelectorAll('.tab-btn').forEach(btn => btn.classList.remove('active'));
            document.querySelectorAll('.tab-pane').forEach(pane => pane.classList.remove('active'));

            button.classList.add('active');
            const tabId = button.getAttribute('data-tab');
            document.getElementById(tabId).classList.add('active');
        });
    });

    // Initial update and periodic polling (every 10 seconds)
    updateDashboard();
    setInterval(updateDashboard, 10000);
});
