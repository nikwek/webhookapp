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