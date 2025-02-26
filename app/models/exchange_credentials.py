# app/models/exchange_credentials.py
from app import db
from datetime import datetime, timezone
from cryptography.fernet import Fernet
import os

class ExchangeCredentials(db.Model):
    __tablename__ = 'exchange_credentials'
    
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    name = db.Column(db.String(100), nullable=False)
    exchange = db.Column(db.String(50), nullable=False)  # e.g., 'coinbase'
    encrypted_api_key = db.Column(db.LargeBinary, nullable=False)
    encrypted_secret_key = db.Column(db.LargeBinary, nullable=False)
    created_at = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc))
    last_used = db.Column(db.DateTime)
    is_active = db.Column(db.Boolean, default=True)
    portfolio_id = db.Column(db.String(100), nullable=True)  # Can be null for account-level credentials
    portfolio_name = db.Column(db.String(100), nullable=True)
    purpose = db.Column(db.String(20), default='trading')  # 'read_only' or 'trading'
    
    user = db.relationship('User', back_populates='exchange_credentials', lazy=True)
    automation_id = db.Column(db.String(50), db.ForeignKey('automations.automation_id'), nullable=True)  # Can be null for account-level credentials
    automation = db.relationship('Automation', backref=db.backref('credentials', lazy=True, uselist=False))

    # Encryption methods remain the same
    @staticmethod
    def get_encryption_key():
        key = os.environ.get('ENCRYPTION_KEY')
        if not key:
            raise ValueError("ENCRYPTION_KEY environment variable not set")
        return key.encode()

    def encrypt_value(self, value):
        f = Fernet(self.get_encryption_key())
        return f.encrypt(value.encode())

    def decrypt_value(self, encrypted_value):
        f = Fernet(self.get_encryption_key())
        return f.decrypt(encrypted_value).decode()

    @property
    def api_key(self):
        return self.decrypt_value(self.encrypted_api_key)

    @api_key.setter
    def api_key(self, value):
        self.encrypted_api_key = self.encrypt_value(value)

    @property
    def secret_key(self):
        return self.decrypt_value(self.encrypted_secret_key)

    @secret_key.setter
    def secret_key(self, value):
        self.encrypted_secret_key = self.encrypt_value(value)

    # Add to app/models/exchange_credentials.py
    @classmethod
    def get_account_credentials(cls, user_id):
        """Get account-level credentials for a user"""
        return cls.query.filter_by(
            user_id=user_id,
            purpose='read_only',
            automation_id=None,
            is_active=True
        ).first()
