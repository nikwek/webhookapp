# app/forms/custom_login_form.py
from flask_security.forms import LoginForm
from flask import current_app, flash

class CustomLoginForm(LoginForm):
    """Custom login form with explicit error handling"""
    
    def validate(self, extra_validators=None):
        # Call parent validation
        result = super().validate(extra_validators=extra_validators)
        
        # Create explicit error messages for authentication failures
        if not result:
            # Check if email is not found or password is wrong
            if 'email' in self.errors or 'password' in self.errors:
                flash("Authentication failed. Please check your email and password.", "error")
        
        return result