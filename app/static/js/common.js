// Common utilities for webhook manager
window.WebhookManager = window.WebhookManager || {
    // Disable a submit button and optionally show a loading indicator
    setButtonLoading: function(button, processingText = 'Working...') {
        if (!button) return;
        button.disabled = true;
        // If it's a <button>, we can embed spinner HTML; if it's <input>, fall back to text swap
        if (button.tagName === 'BUTTON') {
            // Preserve original html for potential restore
            if (!button.dataset.originalContent) {
                button.dataset.originalContent = button.innerHTML;
            }
            button.innerHTML = `<span class="spinner-border spinner-border-sm me-1" role="status" aria-hidden="true"></span> ${processingText}`;
        } else if (button.tagName === 'INPUT') {
            if (!button.dataset.originalValue) {
                button.dataset.originalValue = button.value;
            }
            button.value = processingText;
        }
    },
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


    // Utility to pretty-print JSON objects or strings in logs
    formatJsonDisplay: function(data) {
        if (data === null || data === undefined) {
            return '';
        }
        let obj = data;
        // If the incoming value is a string, attempt to parse as JSON to indent it
        if (typeof obj === 'string') {
            try {
                obj = JSON.parse(obj);
            } catch (e) {
                // leave as is if not valid JSON
                return obj;
            }
        }
        try {
            return JSON.stringify(obj, null, 2);
        } catch (e) {
            return String(obj);
        }
    },

    initializeEventListeners: function() {
        // Global form submit handler to prevent double-submits
        document.querySelectorAll('form').forEach(form => {
            if (form.dataset.preventDoubleSubmit) return; // guard against double wiring
            form.dataset.preventDoubleSubmit = 'true';
            form.addEventListener('submit', () => {
                const submitButtons = form.querySelectorAll('button[type="submit"], input[type="submit"]');
                submitButtons.forEach(btn => {
                    const loadingText = btn.dataset.loadingText || (btn.value || btn.innerText || 'Processing...');
                    WebhookManager.setButtonLoading(btn, loadingText);
                });
            }, { once: true });
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

// Expose helper globally for convenience
window.formatJsonDisplay = window.WebhookManager.formatJsonDisplay.bind(window.WebhookManager);

// Initialize when DOM is loaded
document.addEventListener('DOMContentLoaded', () => {
    WebhookManager.initializeEventListeners();
    WebhookManager.setupPasswordValidation();
});

