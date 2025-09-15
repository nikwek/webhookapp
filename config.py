# config.py
import os
import secrets
from pathlib import Path
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
        # --- Stable SECRET_KEY -------------------------------------------------
    # If SECRET_KEY not provided via environment, generate it once and store
    # it under instance/.flask_secret_key so that subsequent application
    # restarts use the same key. This prevents CSRF/session invalidation that
    # occurs when a new random key is created each time the server starts.
    _secret_key_env = os.environ.get('SECRET_KEY')
    if _secret_key_env:
        SECRET_KEY = _secret_key_env
    else:
        _secret_file = Path(basedir) / 'instance' / '.flask_secret_key'
        if _secret_file.exists():
            SECRET_KEY = _secret_file.read_text().strip()
        else:
            _secret_file.parent.mkdir(parents=True, exist_ok=True)
            SECRET_KEY = secrets.token_hex(32)
            _secret_file.write_text(SECRET_KEY)
    SECURITY_REGISTER_URL = '/register'
    SECURITY_REGISTER_USER_TEMPLATE = 'security/register_user.html'

    # Flask-Security specific settings
    SECURITY_REGISTERABLE = True
    SECURITY_CONFIRMABLE = True
    SECURITY_RECOVERABLE = True
    SECURITY_CHANGEABLE = True
    SECURITY_CONFIRM_EMAIL_WITHIN = '5 days'
    SECURITY_LOGIN_WITHOUT_CONFIRMATION = False  # Force email confirmation
    SECURITY_PASSWORD_COMPLEXITY_CHECKER = 'zxcvbn'
    SECURITY_CSRF_PROTECT_MECHANISMS = ('session',)
    SECURITY_CSRF_IGNORE_UNAUTH_ENDPOINTS = True
    SECURITY_PASSWORD_CONFIRM_REQUIRED = True
    WTF_CSRF_CHECK_DEFAULT = False
    SECURITY_FLASH_MESSAGES = True
    # Custom error messages
    SECURITY_MSG_USER_DOES_NOT_EXIST = ("We couldn't find an account with that email. Need to create an account?", "error")
    SECURITY_MSG_INVALID_PASSWORD = ("Invalid password. Forgot your password?", "error")
    SECURITY_MSG_LOGIN_EXPIRED = ("Your login has expired. Please log in again.", "error")
    SECURITY_MSG_TWO_FACTOR_INVALID_TOKEN = ("Invalid authentication code. Please try again.", "error") 
    SECURITY_MSG_TWO_FACTOR_METHOD_NOT_AVAILABLE = ("Requested method not available.", "error")
    SECURITY_MSG_TWO_FACTOR_PERMISSION_DENIED = ("Permission denied.", "error")
    
    # Template path configurations
    SECURITY_TWO_FACTOR_VERIFY_CODE_TEMPLATE = "security/two_factor_verify_code.html"

    # Two-factor settings
    SECURITY_TWO_FACTOR = True
    SECURITY_TOTP_SECRETS = {
        "1": os.environ.get("SECURITY_TWO_FACTOR_SECRET_KEY")
    }
    SECURITY_TOTP_ISSUER = "WebhookApp"
    SECURITY_TWO_FACTOR_ENABLED_METHODS = ["totp"]  # only Google-Auth style
    SECURITY_TWO_FACTOR_REQUIRED = False            # user may opt-in
    SECURITY_TWO_FACTOR_RESCUE_EMAIL = False          # allow e-mail rescue
    SECURITY_TWO_FACTOR_VALIDITY = 120              # seconds
    SECURITY_TWO_FACTOR_REG_VALIDITY = 3600
    SECURITY_TWO_FACTOR_QR_VERSION = 1
    SECURITY_TWO_FACTOR_QR_QUALITY = 1
    # Enable recovery-code endpoints
    SECURITY_MULTI_FACTOR_RECOVERY_CODES = True

    # Security redirects
    SECURITY_POST_LOGIN_VIEW = '/login-redirect'
    SECURITY_POST_LOGOUT_VIEW = '/login'
    SECURITY_POST_REGISTER_VIEW = '/login'  # Redirect to login page after registration

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
    
    # Flask-Security-Too email sender configuration
    SECURITY_EMAIL_SENDER = os.environ.get('MAIL_DEFAULT_SENDER')
    SECURITY_TWO_FACTOR_RESCUE_MAIL = os.environ.get('MAIL_DEFAULT_SENDER')
    
    # reCAPTCHA settings for bot protection
    # Temporary hardcoded values for production testing
    RECAPTCHA_SITE_KEY = '6LdNrcorAAAAAJF9v5MF-OztU7OwqqNWX7Jj1f7p'
    RECAPTCHA_SECRET_KEY = '6LdNrcorAAAAAFXiFgz7SMWsGMwbbEYDwkt-L25-'
    RECAPTCHA_ENABLED = True


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
    
    # Absolute paths for Pi deployment
    if os.environ.get('ABSOLUTE_CERT_PATH'):
        SSL_CERT = os.environ.get('ABSOLUTE_CERT_PATH')
        SSL_KEY = os.environ.get('ABSOLUTE_KEY_PATH')
    else:
        SSL_CERT = os.path.join(basedir, 'certificates', 'fullchain.pem')
        SSL_KEY = os.path.join(basedir, 'certificates', 'privkey.pem')
    
    # Log certificate paths to help with debugging
    import logging
    logging.getLogger(__name__).info(f"SSL certificate path: {SSL_CERT}")
    logging.getLogger(__name__).info(f"SSL key path: {SSL_KEY}")
    
    # Enhance security in production
    SESSION_COOKIE_SECURE = True


# Function to get the appropriate config
def get_config():
    env = os.environ.get('FLASK_ENV', 'development').lower()
    if env == 'production':
        return ProductionConfig()
    return DevelopmentConfig()