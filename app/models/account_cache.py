from app import db
from datetime import datetime, timezone
from sqlalchemy.dialects.postgresql import JSONB
import logging

logger = logging.getLogger(__name__)

class AccountCache(db.Model):
    """Cache for exchange account data"""
    __tablename__ = 'account_caches'
    
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    portfolio_id = db.Column(db.Integer, db.ForeignKey('portfolios.id'))
    exchange = db.Column(db.String(50), default='coinbase')  # Exchange identifier
    
    # Account identifiers
    account_id = db.Column(db.String(255), nullable=False)
    name = db.Column(db.String(255))
    is_primary = db.Column(db.Boolean, default=False)
    account_type = db.Column(db.String(50))  # 'fiat' or 'wallet'
    
    # Balance information
    balance_amount = db.Column(db.Float)
    balance_currency = db.Column(db.String(10))
    hold_amount = db.Column(db.Float, default=0.0)
    available_amount = db.Column(db.Float)
    
    # Currency details
    currency_code = db.Column(db.String(10))
    currency_name = db.Column(db.String(255))
    currency_type = db.Column(db.String(50))
    currency_exponent = db.Column(db.Integer)
    
    # Additional details
    allows_deposits = db.Column(db.Boolean)
    allows_withdrawals = db.Column(db.Boolean)
    rewards_apy = db.Column(db.Float)
    resource_path = db.Column(db.String(255))
    
    # Timestamps
    created_at = db.Column(db.DateTime(timezone=True))
    updated_at = db.Column(db.DateTime(timezone=True))
    last_cached_at = db.Column(db.DateTime(timezone=True), 
                              default=datetime.now(timezone.utc))
    
    # Relationships
    portfolio = db.relationship('Portfolio', backref='account_caches')
    user = db.relationship('User', backref='account_caches')
    
    def to_dict(self):
        """Convert account cache to dictionary"""
        return {
            'id': self.id,
            'account_id': self.account_id,
            'name': self.name,
            'type': self.account_type,
            'balance': {
                'amount': self.balance_amount,
                'currency': self.balance_currency
            },
            'available': {
                'amount': self.available_amount,
                'currency': self.balance_currency
            },
            'hold': {
                'amount': self.hold_amount,
                'currency': self.balance_currency
            },
            'currency': {
                'code': self.currency_code,
                'name': self.currency_name,
                'type': self.currency_type,
                'exponent': self.currency_exponent
            },
            'rewards_apy': self.rewards_apy,
            'permissions': {
                'allows_deposits': self.allows_deposits,
                'allows_withdrawals': self.allows_withdrawals
            },
            'portfolio_id': self.portfolio_id,
            'updated_at': self.updated_at.isoformat() if self.updated_at else None,
            'last_cached_at': self.last_cached_at.isoformat()
        }
    
    @classmethod
    def create_from_exchange_account(cls, account_data, user_id, portfolio_id=None, exchange='coinbase'):
        """Create account cache from exchange account data"""
        try:
            # Check if account_data is None
            if account_data is None:
                logger.error("Account data is None")
                return None
                
            logger.debug(f"Creating account cache from account data: {type(account_data)}")
                
            # Handle string data (try to parse as JSON)
            if isinstance(account_data, str):
                try:
                    import json
                    account_data = json.loads(account_data)
                    logger.debug("Parsed account data from string")
                except Exception as e:
                    logger.error(f"Could not parse account string: {account_data[:100]}, error: {str(e)}")
                    return None
                
            # Handle different possible data structures
            if isinstance(account_data, dict):
                # It's a dictionary
                logger.debug(f"Account data is a dictionary with keys: {list(account_data.keys())}")
                
                # Extract nested dictionaries safely
                balance_dict = account_data.get('balance', {}) if isinstance(account_data.get('balance'), dict) else {}
                currency_dict = account_data.get('currency', {}) if isinstance(account_data.get('currency'), dict) else {}
                hold_dict = account_data.get('hold', {}) if isinstance(account_data.get('hold'), dict) else {}
                available_dict = account_data.get('available', {}) if isinstance(account_data.get('available'), dict) else {}
                
                return cls(
                    user_id=user_id,
                    portfolio_id=portfolio_id,
                    exchange=exchange,
                    account_id=account_data.get('uuid') or account_data.get('id') or 'unknown',
                    name=account_data.get('name', 'Unnamed Account'),
                    is_primary=account_data.get('primary', False),
                    account_type=account_data.get('type', 'unknown'),
                    balance_amount=float(balance_dict.get('amount', 0)),
                    balance_currency=balance_dict.get('currency', 'USD'),
                    hold_amount=float(hold_dict.get('amount', 0)),
                    available_amount=float(available_dict.get('amount', 0)),
                    currency_code=currency_dict.get('code', account_data.get('currency_code', 'USD')),
                    currency_name=currency_dict.get('name', 'US Dollar'),
                    currency_type=currency_dict.get('type', 'fiat'),
                    currency_exponent=currency_dict.get('exponent', 2),
                    allows_deposits=account_data.get('allow_deposits', True),
                    allows_withdrawals=account_data.get('allow_withdrawals', True),
                    rewards_apy=account_data.get('rewards_apy', 0.0),
                    resource_path=account_data.get('resource_path', ''),
                    created_at=account_data.get('created_at', datetime.now(timezone.utc)),
                    updated_at=account_data.get('updated_at', datetime.now(timezone.utc)),
                    last_cached_at=datetime.now(timezone.utc)
                )
            else:
                # It's an object with attributes
                logger.debug("Account data is an object with attributes")
                
                # Use getattr with safe defaults
                balance_obj = getattr(account_data, 'balance', None)
                currency_obj = getattr(account_data, 'currency', None)
                hold_obj = getattr(account_data, 'hold', None)
                available_obj = getattr(account_data, 'available', None)
                
                return cls(
                    user_id=user_id,
                    portfolio_id=portfolio_id,
                    account_id=getattr(account_data, 'uuid', getattr(account_data, 'id', 'unknown')),
                    name=getattr(account_data, 'name', 'Unnamed Account'),
                    is_primary=getattr(account_data, 'primary', False),
                    account_type=getattr(account_data, 'type', 'unknown'),
                    balance_amount=float(getattr(balance_obj, 'amount', 0)),
                    balance_currency=getattr(balance_obj, 'currency', 'USD'),
                    hold_amount=float(getattr(hold_obj, 'amount', 0)),
                    available_amount=float(getattr(available_obj, 'amount', 0)),
                    currency_code=getattr(currency_obj, 'code', getattr(account_data, 'currency_code', 'USD')),
                    currency_name=getattr(currency_obj, 'name', 'US Dollar'),
                    currency_type=getattr(currency_obj, 'type', 'fiat'),
                    currency_exponent=getattr(currency_obj, 'exponent', 2),
                    allows_deposits=getattr(account_data, 'allow_deposits', True),
                    allows_withdrawals=getattr(account_data, 'allow_withdrawals', True),
                    rewards_apy=getattr(account_data, 'rewards_apy', 0.0),
                    resource_path=getattr(account_data, 'resource_path', ''),
                    created_at=getattr(account_data, 'created_at', datetime.now(timezone.utc)),
                    updated_at=getattr(account_data, 'updated_at', datetime.now(timezone.utc)),
                    last_cached_at=datetime.now(timezone.utc)
                )
        except Exception as e:
            logger.error(f"Error creating account cache from account data: {str(e)}")
            logger.debug(f"Account data: {account_data}")
            return None
