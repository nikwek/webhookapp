// app/static/js/common.js
// Common utilities for webhook manager
const WebhookManager = {
    toggleJson: function(event) {
        const container = event.target.closest('.payload-container');
        const compact = container.querySelector('.json-compact');
        const pretty = container.querySelector('.json-pretty');
        const button = container.querySelector('.toggle-json');
        
        if (compact.style.display === 'none') {
            compact.style.display = 'block';
            pretty.style.display = 'none';
            button.textContent = 'Expand';
        } else {
            compact.style.display = 'none';
            pretty.style.display = 'block';
            button.textContent = 'Collapse';
        }
    },

    toggleAutomationStatus: function(automationId, isActive, isAdmin = false) {
        const button = document.querySelector(`.status-button[data-automation-id="${automationId}"]`);
        if (button) {
            button.disabled = true;
        }

        const endpoint = isAdmin ? 
            `/admin/api/automation/${automationId}/${isActive ? 'deactivate' : 'activate'}` :
            `/automation/${automationId}/status`;
        
        return fetch(endpoint, {
            method: 'PUT',
            headers: {
                'Content-Type': 'application/json',
                'Accept': 'application/json'
            },
            body: JSON.stringify({ is_active: !isActive })
        })
        .then(response => response.json())
        .then(data => {
            if (data.error) {
                throw new Error(data.error);
            }

            if (button) {
                const newIsActive = !isActive;
                button.textContent = newIsActive ? 'Active' : 'Inactive';
                button.classList.remove(newIsActive ? 'btn-danger' : 'btn-success');
                button.classList.add(newIsActive ? 'btn-success' : 'btn-danger');
                button.dataset.isActive = newIsActive.toString();
                button.disabled = false;

                // Update row styling
                const row = button.closest('.automation-row');
                if (row) {
                    row.classList.toggle('text-muted', !newIsActive);
                }
            }
            return data;
        })
        .catch(error => {
            if (button) {
                button.disabled = false;
            }
            throw error;
        });
    },

    initializeEventListeners: function() {
        // Status button handlers
        document.querySelectorAll('.status-button').forEach(button => {
            if (!button.hasListener) {
                button.hasListener = true;
                button.addEventListener('click', (e) => {
                    e.stopPropagation();
                    const automationId = button.dataset.automationId;
                    const isActive = JSON.parse(button.dataset.isActive);
                    const isAdmin = button.dataset.isAdmin === 'true';

                    this.toggleAutomationStatus(automationId, isActive, isAdmin)
                        .catch(error => alert('Error: ' + error.message));
                });
            }
        });
    }
};

// Initialize when DOM is loaded
document.addEventListener('DOMContentLoaded', () => {
    WebhookManager.initializeEventListeners();
});