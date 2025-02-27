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
    exchange = db.Column(db.String(50), nullable=False)
    portfolio_name = db.Column(db.String(100), nullable=False)
    api_key = db.Column(db.String(255), nullable=False)
    api_secret = db.Column(db.String(255), nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    
    def __init__(self, user_id, exchange, portfolio_name, api_key, api_secret):
        self.user_id = user_id
        self.exchange = exchange
        self.portfolio_name = portfolio_name
        self.api_key = api_key
        self.api_secret = self.encrypt_secret(api_secret)
    
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
        logging.info(f"Decrypted secret: {decrypted_secret}")
        return decrypted_secret

    @classmethod
    def get_user_default_credentials(cls, user_id):
        """Get the default Coinbase credentials for a user"""
        return cls.query.filter_by(
            user_id=user_id,
            exchange='coinbase',
            portfolio_name='default'
        ).first()