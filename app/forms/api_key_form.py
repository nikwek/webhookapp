# app/forms/api_key_form.py

from flask_wtf import FlaskForm
from wtforms import StringField, PasswordField, SubmitField
from wtforms.validators import DataRequired, Length


class CcxtApiKeyForm(FlaskForm):
    """Form for CCXT-based Exchange API Keys"""
    api_key = StringField(
        'API Key',
        validators=[
            DataRequired(),
            Length(
                min=10, max=128,
                message="API Key must be between 10 and 128 characters"
            )  # Adjusted min length
        ]
    )
    api_secret = PasswordField(
        'API Secret',
        validators=[
            DataRequired(),
            Length(
                min=10, max=256,
                message="API Secret must be between 10 and 256 characters"
            )  # Adjusted min length
        ]
    )
    submit = SubmitField('Save API Keys')
