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
            button.disabled = true; // Prevent multiple clicks
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
        const chevron = row.querySelector('.chevron-icon');
        const detailsDiv = row.querySelector('.automation-details');
        if (detailsDiv) {
            const isHidden = detailsDiv.style.display === 'none';
            detailsDiv.style.display = isHidden ? 'block' : 'none';
            chevron.classList.toggle('fa-chevron-down', isHidden);
            chevron.classList.toggle('fa-chevron-right', !isHidden);
        }
    },

    initializeEventListeners: function() {
        const self = this;  // Store reference to WebhookManager

        // Create New Automation button
        const createBtn = document.getElementById('createAutomationBtn');
        if (createBtn) {
            createBtn.onclick = function() {
                const modal = new bootstrap.Modal(document.getElementById('createAutomationModal'));
                modal.show();
            };
        }

        // JSON toggle buttons
        document.querySelectorAll('.toggle-json').forEach(button => {
            button.onclick = function(e) {
                e.stopPropagation();
                self.toggleJson(e);
            };
        });

        // Automation header click handlers
        document.querySelectorAll('.automation-header').forEach(header => {
            header.onclick = function(e) {
                if (!e.target.closest('button')) {  // Ignore clicks on buttons
                    const row = this.closest('.automation-row');
                    self.toggleAutomationDetails(row);
                }
            };
        });

        // Status toggle buttons
        document.querySelectorAll('.status-button').forEach(button => {
            button.onclick = function(e) {
                e.stopPropagation();
                const automationId = this.dataset.automationId;
                const isActive = JSON.parse(this.dataset.isActive);
                const isAdmin = this.dataset.isAdmin === 'true';

                self.toggleAutomationStatus(automationId, isActive, isAdmin)
                    .catch(error => alert('Error: ' + error.message));
            };
        });

        // Edit buttons
        document.querySelectorAll('.edit-automation-name').forEach(button => {
            button.onclick = function(e) {
                e.stopPropagation();
                const automationId = this.dataset.automationId;
                const automationName = this.dataset.automationName;
                
                // Set up edit modal
                const modal = new bootstrap.Modal(document.getElementById('editAutomationModal'));
                const nameInput = document.getElementById('editAutomationName');
                const idInput = document.getElementById('editAutomationId');
                
                nameInput.value = automationName;
                idInput.value = automationId;
                
                modal.show();
            };
        });

        // Create Automation form
        const createForm = document.getElementById('createAutomationForm');
        if (createForm) {
            createForm.addEventListener('submit', function(e) {
                e.preventDefault();
                const nameInput = document.getElementById('automationName');
                const name = nameInput.value.trim();
                
                if (!name) {
                    alert('Please enter an automation name');
                    return;
                }

                // Disable submit button to prevent double submission
                const submitButton = createForm.querySelector('button[type="submit"]');
                submitButton.disabled = true;

                fetch('/create-automation', {
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
                    
                    // Add the new automation to the DOM at the top
                    const container = document.getElementById('automations-container');
                    
                    // Remove any existing automation with the same ID (prevent duplicates)
                    const existingAutomation = container.querySelector(`[data-automation-id="${data.automation_id}"]`);
                    if (existingAutomation) {
                        existingAutomation.remove();
                    }
                    
                    const newAutomationHtml = `
                        <div class="automation-row" data-automation-id="${data.automation_id}">
                            <div class="automation-header">
                                <div class="d-flex justify-content-between align-items-center">
                                    <span>
                                        <i class="fas fa-chevron-right chevron-icon me-2"></i>
                                        ${name}
                                    </span>
                                    <div>
                                        <button class="btn btn-sm btn-secondary edit-automation-name" 
                                                data-automation-id="${data.automation_id}" 
                                                data-automation-name="${name}">
                                            Edit
                                        </button>
                                        <button class="btn btn-sm status-button btn-success" 
                                                data-automation-id="${data.automation_id}" 
                                                data-is-active="true">
                                            Active
                                        </button>
                                    </div>
                                </div>
                            </div>
                            <div class="automation-details" style="display: none;">
                                <div class="mb-3">
                                    <strong>Webhook URL:</strong>
                                    <input type="text" class="form-control" value="${data.webhook_url}" readonly>
                                </div>
                                <div class="mb-3">
                                    <strong>Template JSON:</strong>
                                    <pre class="bg-light p-3 mb-2"><code id="template-${data.automation_id}">${JSON.stringify(data.template, null, 2)}</code></pre>
                                </div>
                            </div>
                        </div>
                    `;
                    container.insertAdjacentHTML('afterbegin', newAutomationHtml);
                    
                    // Close the modal and reset the form
                    const modal = bootstrap.Modal.getInstance(document.getElementById('createAutomationModal'));
                    modal.hide();
                    createForm.reset();
                    
                    // Re-enable the submit button
                    submitButton.disabled = false;
                    
                    // Clean up modal artifacts
                    document.body.classList.remove('modal-open');
                    document.body.style.overflow = '';
                    document.body.style.paddingRight = '';
                    const modalBackdrop = document.querySelector('.modal-backdrop');
                    if (modalBackdrop) {
                        modalBackdrop.remove();
                    }
                    
                    // Remove any existing event listeners from the new automation
                    const newAutomation = container.querySelector(`[data-automation-id="${data.automation_id}"]`);
                    const newHeader = newAutomation.querySelector('.automation-header');
                    const newButtons = newAutomation.querySelectorAll('button');
                    
                    // Add event listeners specifically to the new automation
                    newHeader.onclick = function(e) {
                        if (!e.target.closest('button')) {
                            self.toggleAutomationDetails(newAutomation);
                        }
                    };
                    
                    // Add event listeners to the new automation's buttons
                    newButtons.forEach(button => {
                        if (button.classList.contains('status-button')) {
                            button.onclick = function(e) {
                                e.stopPropagation();
                                const automationId = this.dataset.automationId;
                                const isActive = JSON.parse(this.dataset.isActive);
                                const isAdmin = this.dataset.isAdmin === 'true';
                                self.toggleAutomationStatus(automationId, isActive, isAdmin)
                                    .catch(error => alert('Error: ' + error.message));
                            };
                        } else if (button.classList.contains('edit-automation-name')) {
                            button.onclick = function(e) {
                                e.stopPropagation();
                                const automationId = this.dataset.automationId;
                                const automationName = this.dataset.automationName;
                                
                                const modal = new bootstrap.Modal(document.getElementById('editAutomationModal'));
                                const nameInput = document.getElementById('editAutomationName');
                                const idInput = document.getElementById('editAutomationId');
                                
                                nameInput.value = automationName;
                                idInput.value = automationId;
                                
                                modal.show();
                            };
                        }
                    });
                })
                
                .catch(error => {
                    console.error('Error:', error);
                    alert('Error creating automation: ' + error.message);
                    submitButton.disabled = false;
                })
                .finally(() => {
                    // Ensure modal cleanup happens even on error
                    document.body.classList.remove('modal-open');
                    document.body.style.overflow = '';
                    document.body.style.paddingRight = '';
                    const modalBackdrop = document.querySelector('.modal-backdrop');
                    if (modalBackdrop) {
                        modalBackdrop.remove();
                    }
                });
            });
        }

        // Save Changes button handler
        const saveChangesBtn = document.getElementById('saveAutomationChanges');
        if (saveChangesBtn) {
            saveChangesBtn.addEventListener('click', function() {
                const nameInput = document.getElementById('editAutomationName');
                const idInput = document.getElementById('editAutomationId');
                const name = nameInput.value.trim();
                const automationId = idInput.value;
                
                if (!name) {
                    alert('Please enter an automation name');
                    return;
                }

                fetch('/update_automation_name', {
                    method: 'POST',
                    headers: {
                        'Content-Type': 'application/json',
                    },
                    body: JSON.stringify({ 
                        automation_id: automationId,
                        name: name 
                    })
                })
                .then(response => response.json())
                .then(data => {
                    if (data.error) {
                        throw new Error(data.error);
                    }
                    
                    // Update the automation name in the DOM
                    const row = document.querySelector(`.automation-row[data-automation-id="${automationId}"]`);
                    const nameSpan = row.querySelector('.automation-header span');
                    const editButton = row.querySelector('.edit-automation-name');
                    
                    nameSpan.innerHTML = `
                        <i class="fas fa-chevron-right chevron-icon me-2"></i>
                        ${name}
                    `;
                    editButton.dataset.automationName = name;
                    
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

        // Delete Automation button handler
        const deleteBtn = document.getElementById('deleteAutomation');
        if (deleteBtn) {
            deleteBtn.addEventListener('click', function() {
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
                        
                        // Remove the automation from the DOM
                        const row = document.querySelector(`.automation-row[data-automation-id="${automationId}"]`);
                        if (row) {
                            row.remove();
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
    }
};

// Initialize when DOM is loaded
document.addEventListener('DOMContentLoaded', () => {
    WebhookManager.initializeEventListeners();
});
