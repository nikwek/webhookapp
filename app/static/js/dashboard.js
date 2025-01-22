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

function handleStatusToggle(button) {
    const automationId = button.dataset.automationId;
    const isActive = JSON.parse(button.dataset.isActive);

    fetch(`/api/automation/${automationId}/${isActive ? 'deactivate' : 'activate'}`, {
        method: 'POST',
        headers: {
            'Content-Type': 'application/json',
            'Accept': 'application/json'
        }
    })
    .then(response => response.json())
    .then(data => {
        if (data.error) throw new Error(data.error);
        button.textContent = isActive ? 'Inactive' : 'Active';
        button.classList.toggle('btn-success');
        button.classList.toggle('btn-danger');
        button.dataset.isActive = (!isActive).toString();
        button.closest('.automation-row').classList.toggle('text-muted', !isActive);
    })
    .catch(error => {
        console.error('Error:', error);
        alert('An error occurred while updating the automation status.');
    });
}

function handleEditAutomation(button) {
    const automationId = button.dataset.automationId;
    const automationName = button.dataset.automationName;
    // Implement edit automation logic here
}

function toggleAutomationDetails(chevron) {
    const row = chevron.closest('.automation-row');
    const details = row.querySelector('.automation-details');
    details.style.display = details.style.display === 'none' ? 'block' : 'none';
    chevron.classList.toggle('fa-chevron-down');
    chevron.classList.toggle('fa-chevron-right');
}

function showCreateAutomationModal() {
    // Implement show create automation modal logic here
}

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