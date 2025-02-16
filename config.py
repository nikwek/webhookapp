# config.py
import os

basedir = os.path.abspath(os.path.dirname(__file__))

class Config:
    SECRET_KEY = os.environ.get('SECRET_KEY') or 'your-secret-key'
    ENCRYPTION_KEY = os.environ.get('ENCRYPTION_KEY')  # Must be a 32-url-safe-base64-encoded key
    SQLALCHEMY_DATABASE_URI = os.environ.get('DATABASE_URL') or \
        'sqlite:///' + os.path.join(basedir, 'instance', 'webhook.db')
    SQLALCHEMY_TRACK_MODIFICATIONS = False