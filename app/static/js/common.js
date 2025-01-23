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

    createAutomation: function(name) {
        return fetch('/create-automation', {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json',
            },
            body: JSON.stringify({ name: name })
        })
        .then(response => response.json())
        .then(data => {
            if (data.error) {
                throw new Error(data.error);
            }
            // Add name to the data object before adding to DOM
            data.name = name;
            this.addAutomationToDOM(data);
            return data;
        });
    },

    addAutomationToDOM: function(data) {
        // Always look for the table body first
        let container = document.querySelector('.automations-container table tbody');
        if (!container) {
            console.error('Automations container not found');
            return;
        }
        
        const newAutomationHtml = `
            <tr class="automation-row" data-automation-id="${data.automation_id}">
                <td>
                    <i class="fas fa-chevron-right chevron-icon me-2"></i>
                    ${data.name}
                </td>
                <td class="text-end">
                    <button class="btn btn-sm btn-secondary edit-automation-name" 
                            data-automation-id="${data.automation_id}" 
                            data-automation-name="${data.name}">
                        Edit
                    </button>
                    <button class="btn btn-sm status-button btn-success" 
                            data-automation-id="${data.automation_id}" 
                            data-is-active="true">
                        Active
                    </button>
                </td>
            </tr>
            <tr class="automation-details" style="display: none;">
                <td colspan="2">
                    <div class="p-3">
                        <h5>Webhook URL:</h5>
                        <code class="d-block mb-3">${window.location.origin}/webhook?automation_id=${data.automation_id}</code>
                        <h5>Template:</h5>
                        <div class="position-relative">
                            <pre class="bg-light p-3 mb-2"><code id="template-${data.automation_id}">
{
    "action": "{{strategy.order.action}}",
    "ticker": "{{ticker}}",
    "order_size": "100%",
    "position_size": "{{strategy.position_size}}",
    "schema": "2",
    "timestamp": "{{time}}"
}
</code></pre>
                        </div>
                    </div>
                </td>
            </tr>
        `;
        
        // Insert at the beginning of the tbody
        container.insertAdjacentHTML('afterbegin', newAutomationHtml);
    
        // Reinitialize event listeners for the new automation
        this.initializeEventListeners();
    },

    updateAutomationName: function(automationId, newName) {
        return fetch('/update_automation_name', {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json',
            },
            body: JSON.stringify({ 
                automation_id: automationId,
                name: newName 
            })
        })
        .then(response => response.json())
        .then(data => {
            if (data.error) {
                throw new Error(data.error);
            }
            
            // Update the name in the DOM
            const row = document.querySelector(`.automation-row[data-automation-id="${automationId}"]`);
            if (row) {
                const nameElement = row.querySelector('.chevron-icon').nextSibling;
                nameElement.textContent = ` ${newName}`;
                
                // Update the edit button's data attribute
                const editButton = row.querySelector('.edit-automation-name');
                if (editButton) {
                    editButton.dataset.automationName = newName;
                }
            }
            
            return data;
        });
    },

    toggleAutomationStatus: function(automationId, isActive, isAdmin = false) {
        const button = document.querySelector(`.status-button[data-automation-id="${automationId}"]`);
        if (button) {
            button.disabled = true;
        }

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

    toggleAutomationDetails: function(row) {
        const detailsRow = row.nextElementSibling;
        if (detailsRow && detailsRow.classList.contains('automation-details')) {
            const chevron = row.querySelector('.chevron-icon');
            const isHidden = detailsRow.style.display === 'none';
            detailsRow.style.display = isHidden ? 'table-row' : 'none';
            chevron.classList.toggle('fa-chevron-down', isHidden);
            chevron.classList.toggle('fa-chevron-right', !isHidden);
        }
    },

    initializeEventListeners: function() {
        // Create New Automation button
        const createBtn = document.getElementById('createAutomationBtn');
        if (createBtn && !createBtn.hasListener) {
            createBtn.hasListener = true;
            createBtn.addEventListener('click', () => {
                const modal = new bootstrap.Modal(document.getElementById('createAutomationModal'));
                modal.show();
            });
        }

        // Create Automation form handler
        const createForm = document.getElementById('createAutomationForm');
        if (createForm && !createForm.hasListener) {
            createForm.hasListener = true;
            createForm.addEventListener('submit', (e) => {
                e.preventDefault();
                const nameInput = document.getElementById('automationName');
                const name = nameInput.value.trim();
                
                if (!name) {
                    alert('Please enter an automation name');
                    return;
                }
        
                this.createAutomation(name)
                    .then(() => {
                        // Close the modal and reset the form
                        const modal = bootstrap.Modal.getInstance(document.getElementById('createAutomationModal'));
                        modal.hide();
                        createForm.reset();
                    })
                    .catch(error => {
                        console.error('Error:', error);
                        alert('Error creating automation: ' + error.message);
                    });
            });
        }

        // Edit Automation form handler
        const editForm = document.getElementById('editAutomationForm');
        if (editForm && !editForm.hasListener) {
            editForm.hasListener = true;
            editForm.addEventListener('submit', (e) => {
                e.preventDefault();
                document.getElementById('saveAutomationChanges').click();
            });
        }

        // Save Changes button handler
        const saveChangesBtn = document.getElementById('saveAutomationChanges');
        if (saveChangesBtn && !saveChangesBtn.hasListener) {
            saveChangesBtn.hasListener = true;
            saveChangesBtn.addEventListener('click', () => {
                const nameInput = document.getElementById('editAutomationName');
                const idInput = document.getElementById('editAutomationId');
                const name = nameInput.value.trim();
                const automationId = idInput.value;
                
                if (!name) {
                    alert('Please enter an automation name');
                    return;
                }

                this.updateAutomationName(automationId, name)
                    .then(() => {
                        // Close the modal
                        const modal = bootstrap.Modal.getInstance(document.getElementById('editAutomationModal'));
                        modal.hide();
                    })
                    .catch(error => {
                        console.error('Error:', error);
                        alert('Error updating automation: ' + error.message);
                    });
            });
        }

        // Add click handlers for automation rows
        document.querySelectorAll('.automation-row').forEach(row => {
            if (!row.hasListener) {
                row.hasListener = true;
                row.addEventListener('click', (e) => {
                    if (!e.target.closest('button')) {
                        this.toggleAutomationDetails(row);
                    }
                });
            }
        });

        // Delete Automation button handler
        const deleteBtn = document.getElementById('deleteAutomation');
        if (deleteBtn && !deleteBtn.hasListener) {
            deleteBtn.hasListener = true;
            deleteBtn.addEventListener('click', () => {
                const automationId = document.getElementById('editAutomationId').value;
                
                if (confirm('Are you sure you want to delete this automation? This action cannot be undone.')) {
                    fetch('/delete_automation', {
                        method: 'POST',
                        headers: {
                            'Content-Type': 'application/json',
                        },
                        body: JSON.stringify({ automation_id: automationId })
                    })
                    .then(response => response.json())
                    .then(data => {
                        if (data.error) {
                            throw new Error(data.error);
                        }
                        
                        // Remove both the automation row and its details row
                        const row = document.querySelector(`.automation-row[data-automation-id="${automationId}"]`);
                        if (row) {
                            const detailsRow = row.nextElementSibling;
                            row.remove();
                            if (detailsRow && detailsRow.classList.contains('automation-details')) {
                                detailsRow.remove();
                            }
                        }
                        
                        // Close the modal
                        const modal = bootstrap.Modal.getInstance(document.getElementById('editAutomationModal'));
                        modal.hide();
                    })
                    .catch(error => {
                        console.error('Error:', error);
                        alert('Error deleting automation: ' + error.message);
                    });
                }
            });
        }

        // Add click handlers for edit buttons
        document.querySelectorAll('.edit-automation-name').forEach(button => {
            if (!button.hasListener) {
                button.hasListener = true;
                button.addEventListener('click', (e) => {
                    e.stopPropagation();
                    const automationId = button.dataset.automationId;
                    const automationName = button.dataset.automationName;
                    
                    const modal = new bootstrap.Modal(document.getElementById('editAutomationModal'));
                    const nameInput = document.getElementById('editAutomationName');
                    const idInput = document.getElementById('editAutomationId');
                    
                    nameInput.value = automationName;
                    idInput.value = automationId;
                    
                    modal.show();
                });
            }
        });

        // Add click handlers for status buttons
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