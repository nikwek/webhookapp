# app/routes/coinbase.py

from flask import Blueprint, jsonify, current_app, session
from flask_login import login_required, current_user
from app.services.coinbase_service import CoinbaseService
from app.models.exchange_credentials import ExchangeCredentials
import logging

logger = logging.getLogger(__name__)

bp = Blueprint('coinbase', __name__, url_prefix='/api/coinbase')

@bp.route('/account-info')
@login_required
def get_account_info():
    """Get Coinbase account information"""
    # Check if user has Coinbase API keys
    has_credentials = ExchangeCredentials.query.filter_by(
        user_id=current_user.id,
        exchange='coinbase',
        portfolio_name='default'
    ).first() is not None
    
    if not has_credentials:
        return jsonify({
            'error': 'No Coinbase API keys found',
            'has_credentials': False
        }), 400
    
    # Get account information
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
def get_market_data(product_id):
    """Get market data for a specific product"""
    # Check if user has Coinbase API keys
    has_credentials = ExchangeCredentials.query.filter_by(
        user_id=current_user.id,
        exchange='coinbase',
        portfolio_name='default'
    ).first() is not None
    
    if not has_credentials:
        return jsonify({
            'error': 'No Coinbase API keys found',
            'has_credentials': False
        }), 400
    
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
def get_portfolios():
    """Get Coinbase portfolios"""
    # Check if user has Coinbase API keys
    has_credentials = ExchangeCredentials.query.filter_by(
        user_id=current_user.id,
        exchange='coinbase',
        portfolio_name='default'
    ).first() is not None
    
    if not has_credentials:
        return jsonify({
            'error': 'No Coinbase API keys found',
            'has_credentials': False
        }), 400
    
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
def get_trading_pairs():
    """Get all available trading pairs from Coinbase"""
    logger.info("Trading pairs endpoint called")
    
    # Check if user has Coinbase API keys
    credentials = ExchangeCredentials.query.filter_by(
        user_id=current_user.id,
        exchange='coinbase',
        portfolio_name='default'
    ).first()
    
    if not credentials:
        logger.warning(f"No API credentials found for user {current_user.id}")
        return jsonify({
            'success': False,
            'message': 'API credentials not found',
            'trading_pairs': []
        }), 400
    
    # Get trading pairs
    user_id = session.get('user_id', current_user.id)
    trading_pairs = CoinbaseService.get_trading_pairs(user_id)
    
    if not trading_pairs:
        logger.warning(f"No trading pairs found for user {user_id}")
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
