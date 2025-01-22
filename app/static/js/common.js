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

        // Sorting functionality
        document.querySelectorAll('th.sortable').forEach(header => {
            header.addEventListener('click', function() {
                const table = this.closest('table');
                const tbody = table.querySelector('tbody');
                const rows = Array.from(tbody.querySelectorAll('tr'));
                const column = this.cellIndex;
                const dataSort = this.getAttribute('data-sort');

                rows.sort((a, b) => {
                    const aValue = a.cells[column].textContent;
                    const bValue = b.cells[column].textContent;
                    return aValue.localeCompare(bValue);
                });

                if (this.classList.contains('asc')) {
                    rows.reverse();
                    this.classList.remove('asc');
                    this.classList.add('desc');
                } else {
                    this.classList.remove('desc');
                    this.classList.add('asc');
                }

                tbody.append(...rows);
            });
        });
    }
};

// Initialize when DOM is loaded
document.addEventListener('DOMContentLoaded', () => {
    WebhookManager.initializeEventListeners();
}); 