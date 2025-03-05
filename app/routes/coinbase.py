# app/routes/coinbase.py

from flask import Blueprint, jsonify, current_app, session
from flask_security import login_required, current_user 
from app.services.coinbase_service import CoinbaseService
from app.models.exchange_credentials import ExchangeCredentials
import logging
from functools import wraps

logger = logging.getLogger(__name__)

bp = Blueprint('coinbase', __name__, url_prefix='/api/coinbase')

def has_coinbase_credentials(user_id):
    """Check if user has default Coinbase API credentials"""
    return ExchangeCredentials.query.filter_by(
        user_id=user_id,
        exchange='coinbase',
        portfolio_name='default'
    ).first() is not None

def coinbase_credentials_required(f):
    """Decorator to check if user has Coinbase API credentials"""
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if not has_coinbase_credentials(current_user.id):
            return jsonify({
                'error': 'No Coinbase API keys found',
                'has_credentials': False
            }), 400
        return f(*args, **kwargs)
    return decorated_function


@bp.route('/account-info')
@login_required
@coinbase_credentials_required
def get_account_info():
    # Get Coinbase account information
    account_info = CoinbaseService.get_account_info(current_user.id)
    
    if not account_info:
        return jsonify({
            'error': 'Failed to retrieve account information',
            'has_credentials': True
        }), 500
    
    return jsonify({
        'has_credentials': True,
        'account_info': account_info
    })

@bp.route('/market/<product_id>')
@login_required
@coinbase_credentials_required
def get_market_data(product_id):
    # Get market data
    market_data = CoinbaseService.get_market_data(current_user.id, product_id)
    
    if not market_data:
        return jsonify({
            'error': f'Failed to retrieve market data for {product_id}',
            'has_credentials': True
        }), 500
    
    return jsonify({
        'has_credentials': True,
        'market_data': market_data
    })

@bp.route('/portfolios')
@login_required
@coinbase_credentials_required
def get_portfolios():    
    # Get portfolio information
    portfolios = CoinbaseService.get_portfolios(current_user.id)
    
    if not portfolios:
        return jsonify({
            'error': 'Failed to retrieve portfolio information',
            'has_credentials': True
        }), 500
    
    return jsonify({
        'has_credentials': True,
        'portfolios': portfolios
    })

@bp.route('/trading-pairs')
@login_required
@coinbase_credentials_required
def get_trading_pairs():
    # Get trading pairs
    user_id = session.get('user_id', current_user.id)
    trading_pairs = CoinbaseService.get_trading_pairs(current_user.id)
    
    if not trading_pairs:
        logger.warning(f"No trading pairs found for user {current_user.id}")
        return jsonify({
            'success': False,
            'message': 'Failed to retrieve trading pairs',
            'trading_pairs': []
        }), 500
    
    logger.info(f"Successfully retrieved {len(trading_pairs)} trading pairs")
    return jsonify({
        'success': True,
        'message': 'Trading pairs retrieved successfully',
        'trading_pairs': trading_pairs
    })
