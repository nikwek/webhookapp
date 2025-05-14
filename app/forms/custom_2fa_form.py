# app/forms/custom_2fa_form.py
from flask_security.forms import TwoFactorVerifyCodeForm
from flask import current_app, flash
import re


class Custom2FACodeForm(TwoFactorVerifyCodeForm):
    """Custom two-factor authentication form with explicit error handling"""
    
    def validate(self, extra_validators=None):
        """
        Custom validation logic to catch and handle errors at the right stage:
        1. Check for empty code
        2. Check code format (must be 6 digits)
        3. Pass to Flask-Security-Too validation for actual token verification
        """
        # Pre-process the code
        if not hasattr(self, 'code') or not self.code.data:
            flash("Please enter your authentication code.", "error")
            return False
        
        # Strip whitespace and check format
        code = self.code.data.strip()
        if not code:
            flash("Please enter your authentication code.", "error")
            return False
        
        # Validate format: must be exactly 6 digits
        if not re.match(r'^\d{6}$', code):
            flash("Invalid authentication code format. Must be 6 digits.", "error")
            current_app.logger.debug(f"Bad format: '{code}'")
            return False
            
        # Code format is good, proceed with token validation logic
        result = super().validate(extra_validators=extra_validators)
        
        # If the code format is valid but value is wrong
        if not result:
            current_app.logger.debug("2FA validation failed for code with valid format")
            flash("Invalid authentication code. Please try again.", "error")
            
        return result
