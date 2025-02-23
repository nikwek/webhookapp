# config.py
from dotenv import load_dotenv
import os

basedir = os.path.abspath(os.path.dirname(__file__))

load_dotenv()

class Config:
    SECRET_KEY = os.environ.get('SECRET_KEY') or 'your-secret-key'
    ENCRYPTION_KEY = os.environ.get('ENCRYPTION_KEY')  # Must be a 32-url-safe-base64-encoded key
    SQLALCHEMY_DATABASE_URI = os.environ.get('DATABASE_URL') or \
        'sqlite:///' + os.path.join(basedir, 'instance', 'webhook.db')
    SQLALCHEMY_TRACK_MODIFICATIONS = False
    COINBASE_CLIENT_ID = os.environ.get('COINBASE_CLIENT_ID')
    COINBASE_CLIENT_SECRET = os.environ.get('COINBASE_CLIENT_SECRET')
    OAUTH_REDIRECT_URI = os.environ.get('OAUTH_REDIRECT_URI')

    # Email notifications (optional - set these if you want email notifications)
    ENABLE_EMAIL_NOTIFICATIONS = os.environ.get('ENABLE_EMAIL_NOTIFICATIONS', 'False').lower() == 'true'
    MAIL_SERVER = os.environ.get('MAIL_SERVER', 'smtp.gmail.com')
    MAIL_PORT = int(os.environ.get('MAIL_PORT', 587))
    MAIL_USE_TLS = os.environ.get('MAIL_USE_TLS', 'True').lower() == 'true'
    MAIL_USERNAME = os.environ.get('MAIL_USERNAME')
    MAIL_PASSWORD = os.environ.get('MAIL_PASSWORD')
    MAIL_DEFAULT_SENDER = os.environ.get('MAIL_DEFAULT_SENDER')
    
    # Application URL for notifications
    APPLICATION_URL = os.environ.get('APPLICATION_URL', 'http://localhost:5001')