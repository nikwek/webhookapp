// Common utilities for webhook manager
window.WebhookManager = window.WebhookManager || {
    // CSRF token fetch wrapper
    fetchWithCSRF: function(url, options = {}) {
        const csrfToken = document.querySelector('meta[name="csrf-token"]').getAttribute('content');
        return fetch(url, {
            ...options,
            headers: {
                'Content-Type': 'application/json',
                'X-CSRFToken': csrfToken,
                ...options.headers
            }
        });
    },

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
    
        const csrfToken = document.querySelector('meta[name="csrf-token"]').getAttribute('content');
        const endpoint = isAdmin ? 
            `/admin/api/automation/${automationId}/${isActive ? 'deactivate' : 'activate'}` :
            `/automation/${automationId}/status`;
        
        return fetch(endpoint, {
            method: 'PUT',
            headers: {
                'Content-Type': 'application/json',
                'Accept': 'application/json',
                'X-CSRFToken': csrfToken
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
    },

    // Password validation logic
    setupPasswordValidation: function() {
        const password = document.getElementById("password");
        const passwordConfirm = document.getElementById("password_confirm");
        const strengthMessage = document.getElementById("password-strength");
        const matchMessage = document.getElementById("password-match-message");

        if (!password || !strengthMessage || !passwordConfirm || !matchMessage) return;

        function checkPasswordStrength() {
            const value = password.value;
            let strength = "Weak";
            let color = "red";

            if (value.length >= 8) {
                strength = "Medium";
                color = "orange";

                if (/[A-Z]/.test(value) && 
                    /[a-z]/.test(value) && 
                    /\d/.test(value) && 
                    /[^A-Za-z0-9]/.test(value)) {
                    strength = "Strong";
                    color = "green";
                }
            }

            strengthMessage.textContent = `Password Strength: ${strength}`;
            strengthMessage.style.color = color;
        }

        function checkPasswordMatch() {
            if (password.value && passwordConfirm.value) {
                if (password.value === passwordConfirm.value) {
                    matchMessage.textContent = "Passwords match!";
                    matchMessage.style.color = "green";
                } else {
                    matchMessage.textContent = "Passwords do not match!";
                    matchMessage.style.color = "red";
                }
            } else {
                matchMessage.textContent = "";
            }
        }

        // Add event listeners
        password.addEventListener("input", () => {
            checkPasswordStrength();
            checkPasswordMatch();
        });

        passwordConfirm.addEventListener("input", checkPasswordMatch);
    }
};

// Initialize when DOM is loaded
document.addEventListener('DOMContentLoaded', () => {
    WebhookManager.initializeEventListeners();
    WebhookManager.setupPasswordValidation();
});

