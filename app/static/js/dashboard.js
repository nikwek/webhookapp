document.addEventListener('DOMContentLoaded', function() {
    // Automations Section
    const automationsContainer = document.getElementById('automations-container');
    if (automationsContainer) {
        automationsContainer.addEventListener('click', function(e) {
            if (e.target.classList.contains('status-button')) {
                handleStatusToggle(e.target);
            } else if (e.target.classList.contains('edit-automation-name')) {
                handleEditAutomation(e.target);
            } else if (e.target.classList.contains('chevron-icon')) {
                toggleAutomationDetails(e.target);
            }
        });
    }

    // Create Automation Button
    const createAutomationBtn = document.getElementById('createAutomationBtn');
    if (createAutomationBtn) {
        createAutomationBtn.addEventListener('click', showCreateAutomationModal);
    }

    // Webhook Logs Section
    initializeSSE();
});

let evtSource = null;

function initializeSSE() {
    if (evtSource) {
        evtSource.close();
    }

    evtSource = new EventSource("/api/logs/stream");
    const logsTable = document.getElementById('logs');

    evtSource.onmessage = function(event) {
        const logs = JSON.parse(event.data);
        if (!logsTable || !logs.length) return;

        // Only update if there are new logs
        const currentFirstLogId = logsTable.querySelector('tbody tr:first-child')?.dataset.logId;
        const newFirstLogId = logs[0].id;

        if (currentFirstLogId !== newFirstLogId?.toString()) {
            const tbody = logsTable.querySelector('tbody');
            tbody.innerHTML = logs.map(log => `
                <tr data-log-id="${log.id}" class="webhook-type-${(log.payload.action || '').toLowerCase() || 'other'}">
                    <td>${new Date(log.timestamp).toLocaleString()}</td>
                    <td>${log.automation_name}</td>
                    <td>
                        <div class="payload-container">
                            <pre class="json-compact mb-0">${JSON.stringify(log.payload)}</pre>
                            <pre class="json-pretty mb-0" style="display:none">${JSON.stringify(log.payload, null, 2)}</pre>
                            <button class="btn btn-sm btn-secondary toggle-json">Expand</button>
                        </div>
                    </td>
                </tr>
            `).join('');
            
            // Reinitialize event listeners for new elements
            WebhookManager.initializeEventListeners();
        }
    };

    evtSource.onerror = function(error) {
        console.error('SSE Error:', error);
        if (evtSource.readyState === EventSource.CLOSED) {
            // Try to reconnect after 5 seconds
            setTimeout(initializeSSE, 5000);
        }
    };
}

// Clean up SSE connection when page is hidden
document.addEventListener('visibilitychange', () => {
    if (document.hidden && evtSource) {
        evtSource.close();
        evtSource = null;
    } else if (!document.hidden && !evtSource) {
        initializeSSE();
    }
});