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
        const endpoint = isAdmin ? 
            `/admin/api/automation/${automationId}/${isActive ? 'deactivate' : 'activate'}` :
            `/${isActive ? 'deactivate' : 'activate'}-automation/${automationId}`;
        
        return fetch(endpoint, {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json',
                'Accept': 'application/json'
            }
        })
        .then(response => response.json())
        .then(data => {
            if (data.error) {
                throw new Error(data.error);
            }
            return data;
        });
    },

    initializeEventListeners: function() {
        // JSON toggle buttons
        document.querySelectorAll('.toggle-json').forEach(button => {
            button.addEventListener('click', this.toggleJson);
        });

        // Status toggle buttons
        document.querySelectorAll('.status-button').forEach(button => {
            button.addEventListener('click', function() {
                const automationId = this.dataset.automationId;
                const isActive = JSON.parse(this.dataset.isActive);
                const isAdmin = this.dataset.isAdmin === 'true';

                WebhookManager.toggleAutomationStatus(automationId, isActive, isAdmin)
                    .then(() => window.location.reload())
                    .catch(error => alert('Error: ' + error.message));
            });
        });
    }
};

// Initialize when DOM is loaded
document.addEventListener('DOMContentLoaded', () => {
    WebhookManager.initializeEventListeners();
}); 