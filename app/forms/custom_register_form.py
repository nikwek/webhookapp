# app/forms/custom_register_form.py
"""Custom registration form with reCAPTCHA and additional bot protection."""

from flask import current_app, request
from flask_security.forms import ConfirmRegisterForm
from wtforms import PasswordField, SubmitField
from wtforms.validators import DataRequired, EqualTo, Length
import requests


class CustomRegisterForm(ConfirmRegisterForm):
    """Custom registration form with reCAPTCHA protection."""
    
    # Don't override email field - let Flask-Security handle email validation
    # including duplicate email checking
    
    password = PasswordField('Password', validators=[
        DataRequired(message='Password is required'),
        Length(min=8, message='Password must be at least 8 characters long')
    ])
    
    password_confirm = PasswordField('Confirm Password', validators=[
        DataRequired(message='Please confirm your password'),
        EqualTo('password', message='Passwords must match')
    ])
    
    submit = SubmitField('Create Account')
    
    def validate_recaptcha(self):
        """Validate reCAPTCHA response."""
        if not current_app.config.get('RECAPTCHA_ENABLED'):
            return True
            
        recaptcha_response = request.form.get('g-recaptcha-response')
        if not recaptcha_response:
            return False
            
        secret_key = current_app.config.get('RECAPTCHA_SECRET_KEY')
        if not secret_key:
            return True  # Skip validation if no secret key configured
            
        verify_url = 'https://www.google.com/recaptcha/api/siteverify'
        data = {
            'secret': secret_key,
            'response': recaptcha_response,
            'remoteip': request.remote_addr
        }
        
        try:
            response = requests.post(verify_url, data=data, timeout=10)
            result = response.json()
            return result.get('success', False)
        except Exception:
            return False
    
    def validate(self, **kwargs):
        """Custom validation including reCAPTCHA check."""
        # Run standard form validation first
        if not super().validate(**kwargs):
            return False
        
        # Check reCAPTCHA if enabled
        if current_app.config.get('RECAPTCHA_ENABLED'):
            if not self.validate_recaptcha():
                self.form_errors.append('Please complete the reCAPTCHA verification')
                return False
        
        return True
