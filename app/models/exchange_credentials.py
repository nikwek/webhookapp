# app/models/exchange_credentials.py

from datetime import datetime
from app import db
from cryptography.fernet import Fernet
import base64
import os
import logging

class ExchangeCredentials(db.Model):
    __tablename__ = 'exchange_credentials'
    
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    automation_id = db.Column(db.Integer, db.ForeignKey('automations.id'), nullable=True)
    portfolio_id = db.Column(db.Integer, db.ForeignKey('portfolios.id'), nullable=True)
    exchange = db.Column(db.String(50), nullable=False)
    portfolio_name = db.Column(db.String(100), nullable=False)
    api_key = db.Column(db.String(255), nullable=False)
    api_secret = db.Column(db.String(255), nullable=False)
    is_default = db.Column(db.Boolean, default=False)  # Flag for read-only default credentials
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    
    # Add relationships
    user = db.relationship('User', backref=db.backref('credentials', lazy=True))
    automation = db.relationship('Automation', backref=db.backref('credentials', lazy=True))
    portfolio = db.relationship('Portfolio', backref=db.backref('credentials', lazy=True))
    
    def __init__(self, user_id, exchange, portfolio_name, api_key, api_secret, 
                 automation_id=None, portfolio_id=None, is_default=False):
        self.user_id = user_id
        self.exchange = exchange
        self.portfolio_name = portfolio_name
        self.api_key = api_key
        self.api_secret = self.encrypt_secret(api_secret)
        self.automation_id = automation_id
        self.portfolio_id = portfolio_id
        self.is_default = is_default
    
    def encrypt_secret(self, secret):
        """Encrypt the API secret before storing in database"""
        key = os.environ.get('ENCRYPTION_KEY')
        fernet = Fernet(key)
        encrypted_secret = fernet.encrypt(secret.encode())
        return base64.urlsafe_b64encode(encrypted_secret).decode('utf-8')
    
    def decrypt_secret(self):
        """Decrypt the API secret for use in API calls"""
        key = os.environ.get('ENCRYPTION_KEY')
        fernet = Fernet(key)
        encrypted_secret = base64.urlsafe_b64decode(self.api_secret.encode('utf-8'))
        decrypted_secret = fernet.decrypt(encrypted_secret).decode('utf-8')
        return decrypted_secret

    @classmethod
    def get_user_default_credentials(cls, user_id, exchange='coinbase'):
        """Get the default credentials for a user for a specific exchange"""
        return cls.query.filter_by(
            user_id=user_id,
            exchange=exchange,
            portfolio_name='default',
            is_default=True
        ).first()
        
    @classmethod
    def get_automation_credentials(cls, automation_id):
        """Get credentials for a specific automation"""
        return cls.query.filter_by(
            automation_id=automation_id,
            is_default=False
        ).first()
