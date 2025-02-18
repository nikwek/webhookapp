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
    portfolio_id = db.Column(db.String(100))  # New: Coinbase portfolio ID
    portfolio_name = db.Column(db.String(100))  # New: Coinbase portfolio name
    
    user = db.relationship('User', backref=db.backref('exchange_credentials', lazy=True))
    automation_id = db.Column(db.String(50), db.ForeignKey('automations.automation_id'), nullable=False)
    automation = db.relationship('Automation', backref=db.backref('credentials', lazy=True, uselist=False))


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