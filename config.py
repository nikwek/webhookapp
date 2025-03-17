# config.py
import os
import secrets
from datetime import timedelta
from dotenv import load_dotenv

load_dotenv()

basedir = os.path.abspath(os.path.dirname(__file__))

class Config:
    SQLALCHEMY_DATABASE_URI = os.environ.get('DATABASE_URL') or \
        'sqlite:///' + os.path.join(basedir, 'instance', 'webhook.db')
        # Database connection pool settings
    SQLALCHEMY_ENGINE_OPTIONS = {
        'pool_pre_ping': True,  # Enables automatic reconnection
        'pool_recycle': 300,    # Recycle connections every 5 minutes
        'pool_size': 10         # Maximum number of connections to keep
    }
    SQLALCHEMY_TRACK_MODIFICATIONS = False

    # Security settings
    SECURITY_PASSWORD_SALT = os.environ.get('SECURITY_PASSWORD_SALT')
    SECRET_KEY = os.environ.get('SECRET_KEY') or secrets.token_hex(32)
    SECURITY_REGISTER_URL = '/register'
    SECURITY_REGISTER_USER_TEMPLATE = 'security/register_user.html'

    # Flask-Security specific settings
    SECURITY_REGISTERABLE = True
    SECURITY_CONFIRMABLE = True
    SECURITY_RECOVERABLE = True
    SECURITY_CHANGEABLE = True
    SECURITY_PASSWORD_COMPLEXITY_CHECKER = 'zxcvbn'
    SECURITY_CSRF_PROTECT_MECHANISMS = ('session',)
    SECURITY_CSRF_IGNORE_UNAUTH_ENDPOINTS = True
    SECURITY_PASSWORD_CONFIRM_REQUIRED = True
    WTF_CSRF_CHECK_DEFAULT = False
    
    # Security redirects
    SECURITY_POST_LOGIN_VIEW = '/login-redirect'
    SECURITY_POST_LOGOUT_VIEW = '/login'
    SECURITY_POST_REGISTER_VIEW = '/dashboard'

    # Password requirements
    SECURITY_PASSWORD_RULES = [
        {'min': 8},
        {'uppercase': 1},
        {'lowercase': 1},
        {'numbers': 1},
        {'special': 1}
    ]

    # Session settings - needed for Raspberry Pi
    SESSION_TYPE = 'filesystem'
    SESSION_FILE_DIR = '/tmp/flask_session'
    SESSION_PERMANENT = True
    PERMANENT_SESSION_LIFETIME = timedelta(hours=24)
    SESSION_COOKIE_SECURE = False
    SESSION_COOKIE_HTTPONLY = True
    SESSION_COOKIE_SAMESITE = 'Lax'

    # Add a warning if no salt is set
    if not os.environ.get('SECURITY_PASSWORD_SALT'):
        import warnings
        warnings.warn('SECURITY_PASSWORD_SALT not set. Using default value.')

    # Email settings
    MAIL_SERVER = os.environ.get('MAIL_SERVER')
    MAIL_PORT = int(os.environ.get('MAIL_PORT', 587))
    MAIL_USE_TLS = os.environ.get('MAIL_USE_TLS', 'True').lower() == 'true'
    MAIL_USERNAME = os.environ.get('MAIL_USERNAME')
    MAIL_PASSWORD = os.environ.get('MAIL_PASSWORD')
    MAIL_DEFAULT_SENDER = os.environ.get('MAIL_DEFAULT_SENDER')
    
    # Application URL
    APPLICATION_URL = os.environ.get('APPLICATION_URL')
    
class DevelopmentConfig(Config):
    DEBUG = True
    FLASK_ENV = 'development'
    # Use development URL for webhooks
    APPLICATION_URL = os.environ.get('DEV_APPLICATION_URL') or os.environ.get('APPLICATION_URL')
    # No SSL in development
    SSL_ENABLED = False


class ProductionConfig(Config):
    DEBUG = False
    FLASK_ENV = 'production'
    # Use production URL for webhooks
    APPLICATION_URL = os.environ.get('PROD_APPLICATION_URL') or os.environ.get('APPLICATION_URL')
    # Enable SSL in production
    SSL_ENABLED = True
    SSL_CERT = '/etc/letsencrypt/live/app.wekwerth.services/fullchain.pem'
    SSL_KEY = '/etc/letsencrypt/live/app.wekwerth.services/privkey.pem'
    # Enhance security in production
    SESSION_COOKIE_SECURE = True


# Function to get the appropriate config
def get_config():
    env = os.environ.get('FLASK_ENV', 'development').lower()
    if env == 'production':
        return ProductionConfig()
    return DevelopmentConfig()