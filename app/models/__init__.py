# app/models/__init__.py

# Import all models to ensure they're registered with SQLAlchemy
from app.models.user import User, Role
from app.models.automation import Automation
from app.models.webhook import WebhookLog
from app.models.exchange_credentials import ExchangeCredentials
from app.models.portfolio import Portfolio
from .account_cache import AccountCache

# Update __all__ if you're using it
__all__ = [
    'User',
    'Role',
    'Automation',
    'WebhookLog',
    'ExchangeCredentials',
    'Portfolio',
    'AccountCache'
]
