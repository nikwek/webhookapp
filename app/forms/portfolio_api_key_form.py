# app/forms/portfolio_api_key_form.py

from flask_wtf import FlaskForm
from wtforms import StringField, PasswordField, SubmitField, HiddenField
from wtforms.validators import DataRequired, Length

class PortfolioAPIKeyForm(FlaskForm):
    """Form for Portfolio-specific API Keys"""
    portfolio_id = HiddenField('Portfolio ID', validators=[DataRequired()])
    portfolio_name = HiddenField('Portfolio Name', validators=[DataRequired()])
    api_key = StringField('API Key', validators=[
        DataRequired(), 
        Length(min=16, max=128, message="API Key must be between 16 and 128 characters")
    ])
    api_secret = PasswordField('API Secret', validators=[
        DataRequired(),
        Length(min=32, max=256, message="API Secret must be between 32 and 256 characters")
    ])
    submit = SubmitField('Save and Connect')