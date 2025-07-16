# app/models/trading.py
from app import db
from datetime import datetime
import uuid
from sqlalchemy.orm import relationship # Explicit import for clarity

# Assuming ExchangeCredentials is in app.models.exchange_credentials
# and User is in app.models.user
# These will be resolved by SQLAlchemy's relationship magic,
# but direct imports are good practice if used for type hinting or direct reference.
# from .exchange_credentials import ExchangeCredentials # If needed for type hints
# from .user import User # If needed for type hints

class TradingStrategy(db.Model):
    __tablename__ = 'trading_strategies'

    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    name = db.Column(db.String(100), nullable=False)
    exchange_credential_id = db.Column(db.Integer, db.ForeignKey('exchange_credentials.id'), nullable=False)
    trading_pair = db.Column(db.String(50), nullable=False)  # e.g., "BTC/USDC"
    base_asset_symbol = db.Column(db.String(20), nullable=False)  # e.g., "BTC"
    quote_asset_symbol = db.Column(db.String(20), nullable=False)  # e.g., "USDC"

    # For SQLite, Numeric might be emulated or use Python's Decimal.
    # If issues arise, Float could be an alternative, but Numeric is preferred for financial data.
    allocated_base_asset_quantity = db.Column(db.Numeric(precision=28, scale=18), nullable=False, default=0.0)
    allocated_quote_asset_quantity = db.Column(db.Numeric(precision=28, scale=18), nullable=False, default=0.0)

    webhook_id = db.Column(db.String(36), unique=True, nullable=False, default=lambda: str(uuid.uuid4()))
    webhook_template = db.Column(db.Text, nullable=True)

    is_active = db.Column(db.Boolean, nullable=False, default=True)
    created_at = db.Column(db.DateTime, nullable=False, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, nullable=False, default=datetime.utcnow, onupdate=datetime.utcnow)

    user = relationship('User', backref=db.backref('trading_strategies', lazy='dynamic'))
    exchange_credential = relationship('ExchangeCredentials', backref=db.backref('trading_strategies', lazy='dynamic'))
    
    value_history = relationship('StrategyValueHistory', backref='strategy', lazy='dynamic', cascade="all, delete-orphan")

    def __repr__(self):
        return f'<TradingStrategy {self.name} ({self.trading_pair}) for User {self.user_id}>'

class StrategyValueHistory(db.Model):
    __tablename__ = 'strategy_value_history'

    id = db.Column(db.Integer, primary_key=True)
    strategy_id = db.Column(db.Integer, db.ForeignKey('trading_strategies.id'), nullable=False)
    timestamp = db.Column(db.DateTime, nullable=False, default=datetime.utcnow)
    value_usd = db.Column(db.Numeric(precision=28, scale=18), nullable=False)
    base_asset_quantity_snapshot = db.Column(db.Numeric(precision=28, scale=18), nullable=False)
    quote_asset_quantity_snapshot = db.Column(db.Numeric(precision=28, scale=18), nullable=False)

    # The relationship back to TradingStrategy is defined by the backref 'strategy'
    # in TradingStrategy.value_history

    def __repr__(self):
        return f'<StrategyValueHistory for Strategy {self.strategy_id} @ {self.timestamp} - ${self.value_usd}>'


class AssetTransferLog(db.Model):
    """Records internal asset transfers between main accounts and trading strategies."""
    __tablename__ = 'asset_transfer_logs'

    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    timestamp = db.Column(db.DateTime, nullable=False, default=datetime.utcnow)

    # Raw identifiers exactly as used by the transfer routine so we can reconstruct context later
    source_identifier = db.Column(db.String(100), nullable=False)
    destination_identifier = db.Column(db.String(100), nullable=False)

    asset_symbol = db.Column(db.String(20), nullable=False)
    amount = db.Column(db.Numeric(precision=28, scale=18), nullable=False)

    # Convenience links to involved strategies (nullable when Main Account is involved)
    strategy_id_from = db.Column(db.Integer, nullable=True)
    strategy_id_to = db.Column(db.Integer, nullable=True)
    # Preserve strategy names at the time of transfer to ensure historical context after deletions
    strategy_name_from = db.Column(db.String(100), nullable=True)
    strategy_name_to = db.Column(db.String(100), nullable=True)

    def __repr__(self):
        return (
            f"<AssetTransferLog {self.id}: {self.amount} {self.asset_symbol} "
            f"{self.source_identifier} → {self.destination_identifier}>"
        )

    def to_dict(self):
        """Return a dict representation aligned with WebhookLog.to_dict()."""
        return {
            'id': self.id,
            'timestamp': self.timestamp.isoformat(),
            'source_identifier': self.source_identifier,
            'destination_identifier': self.destination_identifier,
            'asset_symbol': self.asset_symbol,
            'amount': float(self.amount),
            'strategy_id_from': self.strategy_id_from,
            'strategy_name_from': self.strategy_name_from,
            'strategy_id_to': self.strategy_id_to,
            'strategy_name_to': self.strategy_name_to,
        }
