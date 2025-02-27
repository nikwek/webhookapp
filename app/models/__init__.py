# app/models/__init__.py

# Import all models to ensure they're registered with SQLAlchemy
from app.models.user import User
from app.models.automation import Automation
from app.models.webhook import WebhookLog
from app.models.exchange_credentials import ExchangeCredentials
from app.models.portfolio import Portfolio
