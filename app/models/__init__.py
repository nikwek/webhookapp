# app/models/__init__.py

from .. import db  # Import the SQLAlchemy instance from the app package

# Import all models to ensure they're registered with SQLAlchemy
from app.models.user import User, Role
from app.models.automation import Automation
from app.models.webhook import WebhookLog
from app.models.exchange_credentials import ExchangeCredentials
from app.models.portfolio import Portfolio
from .account_cache import AccountCache
from app.models.trading import TradingStrategy, StrategyValueHistory

# Update __all__ if you're using it
__all__ = [
    'User',
    'Role',
    'Automation',
    'WebhookLog',
    'ExchangeCredentials',
    'Portfolio',
    'AccountCache',
    'TradingStrategy',
    'StrategyValueHistory'
]
