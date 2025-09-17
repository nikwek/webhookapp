# app/forms/custom_register_form.py
"""Custom registration form with reCAPTCHA and additional bot protection."""

from flask import current_app, request
from flask_security.forms import ConfirmRegisterForm
from wtforms import PasswordField, SubmitField, HiddenField, ValidationError
from wtforms.validators import DataRequired, EqualTo, Length
import requests


class RecaptchaValidator:
    """Custom validator for reCAPTCHA."""
    
    def __init__(self, message=None):
        self.message = message or 'Please complete the reCAPTCHA verification'
    
    def __call__(self, form, field):
        if not current_app.config.get('RECAPTCHA_ENABLED'):
            return  # Skip validation if reCAPTCHA is disabled
            
        recaptcha_response = request.form.get('g-recaptcha-response')
        
        # Log registration attempt for monitoring
        user_agent = request.headers.get('User-Agent', 'Unknown')
        ip_address = request.remote_addr
        current_app.logger.warning(
            f"Registration attempt - IP: {ip_address}, "
            f"User-Agent: {user_agent}, "
            f"reCAPTCHA response: {'Present' if recaptcha_response else 'Missing'}"
        )
        
        if not recaptcha_response:
            current_app.logger.warning(f"BLOCKED: Registration from {ip_address} - No reCAPTCHA response")
            raise ValidationError(self.message)
            
        secret_key = current_app.config.get('RECAPTCHA_SECRET_KEY')
        if not secret_key:
            return  # Skip validation if no secret key configured
            
        verify_url = 'https://www.google.com/recaptcha/api/siteverify'
        data = {
            'secret': secret_key,
            'response': recaptcha_response,
            'remoteip': request.remote_addr
        }
        
        try:
            response = requests.post(verify_url, data=data, timeout=10)
            result = response.json()
            if not result.get('success', False):
                current_app.logger.warning(f"BLOCKED: Registration from {ip_address} - reCAPTCHA verification failed: {result}")
                raise ValidationError(self.message)
            else:
                current_app.logger.info(f"ALLOWED: Registration from {ip_address} - reCAPTCHA verified successfully")
        except Exception as e:
            current_app.logger.error(f"BLOCKED: Registration from {ip_address} - reCAPTCHA verification error: {e}")
            raise ValidationError('reCAPTCHA verification failed. Please try again.')


class CustomRegisterForm(ConfirmRegisterForm):
    """Custom registration form with reCAPTCHA protection."""
    
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
    
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
    
    # Hidden field to trigger reCAPTCHA validation
    recaptcha = HiddenField('reCAPTCHA', validators=[RecaptchaValidator()])
    
    submit = SubmitField('Create Account')
    
