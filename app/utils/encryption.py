# app/utils/encryption.py
from cryptography.fernet import Fernet
from flask import current_app
import base64

def get_encryption_key():
    """Get or create encryption key"""
    key = current_app.config.get('ENCRYPTION_KEY')
    if not key:
        raise ValueError('ENCRYPTION_KEY must be set in configuration')
    return base64.urlsafe_b64decode(key)

def encrypt_value(value):
    """Encrypt a string value"""
    if not value:
        return None
    
    key = get_encryption_key()
    f = Fernet(base64.urlsafe_b64encode(key))
    return f.encrypt(value.encode())

def decrypt_value(encrypted_value):
    """Decrypt an encrypted value"""
    if not encrypted_value:
        return None
    
    key = get_encryption_key()
    f = Fernet(base64.urlsafe_b64encode(key))
    return f.decrypt(encrypted_value).decode()