from flask import Blueprint, render_template, request, jsonify, flash, redirect, url_for, current_app
from flask_login import login_required, current_user
from app.services.coinbase_service import CoinbaseService
from app.models.exchange_credentials import ExchangeCredentials
from app import db
import time
import hmac
import hashlib
import base64
import requests

bp = Blueprint('portfolio', __name__, url_prefix='/portfolio')

@bp.route('/')
@login_required
def index():
    """Portfolio dashboard view"""
    try:
        coinbase = CoinbaseService(current_user.id)
        portfolios = coinbase.list_portfolios()
        return render_template('portfolio/index.html', portfolios=portfolios)
    except ValueError as e:
        flash('Please connect your Coinbase account first.', 'warning')
        return redirect(url_for('oauth.exchange_authorize'))
    except Exception as e:
        flash(f'Failed to fetch portfolios: {str(e)}', 'error')
        return render_template('portfolio/index.html', portfolios=[])

@bp.route('/api/portfolios', methods=['GET'])
@login_required
def list_portfolios():
    """API endpoint to list portfolios"""
    try:
        coinbase = CoinbaseService(current_user.id)
        portfolios = coinbase.list_portfolios()
        return jsonify({"portfolios": portfolios})
    except ValueError as e:
        return jsonify({"error": "Please connect your Coinbase account first."}), 401
    except Exception as e:
        current_app.logger.error(f"Error fetching portfolios: {str(e)}")
        return jsonify({"error": str(e)}), 500

@bp.route('/api/portfolios', methods=['POST'])
@login_required
def create_portfolio():
    """API endpoint to create a portfolio"""
    try:
        data = request.get_json()
        if not data or 'name' not in data:
            return jsonify({"error": "Portfolio name is required"}), 400

        coinbase = CoinbaseService(current_user.id)
        portfolio = coinbase.create_portfolio(data['name'])
        return jsonify({"portfolio": portfolio})
    except Exception as e:
        current_app.logger.error(f"Error creating portfolio: {str(e)}")
        return jsonify({"error": str(e)}), 500

@bp.route('/api/portfolios/<portfolio_id>/credentials', methods=['POST'])
@login_required
def get_credentials(portfolio_id):
    """API endpoint to generate and save portfolio credentials"""
    try:
        coinbase = CoinbaseService(current_user.id)
        credentials = coinbase.get_portfolio_api_credentials(portfolio_id)
        
        # Save credentials securely
        exchange_creds = ExchangeCredentials(
            user_id=current_user.id,
            portfolio_id=portfolio_id,
            api_key=credentials['api_key'],
            api_secret=credentials['api_secret']
        )
        db.session.add(exchange_creds)
        db.session.commit()
        
        return jsonify({
            "success": True,
            "message": "API credentials generated and saved successfully"
        })
    except Exception as e:
        current_app.logger.error(f"Error generating credentials: {str(e)}")
        return jsonify({"error": str(e)}), 500


@bp.route('/api/trading-pairs', methods=['GET'])
@login_required
def get_trading_pairs():
    """API endpoint to get trading pairs using application API keys"""
    try:
        # Use application API keys instead of user's OAuth token
        api_key = current_app.config['COINBASE_API_KEY']
        private_key = current_app.config['COINBASE_API_SECRET']
        
        if api_key and private_key:
            current_app.logger.debug("Fetching trading pairs using API keys")
            
            # Prepare for API authentication
            timestamp = str(int(time.time()))
            method = 'GET'
            request_path = '/api/v3/brokerage/products'
            
            # Create the prehash string
            message = timestamp + method + request_path
            
            # Prepare private key
            # Remove headers and newlines from the private key
            private_key = private_key.replace('-----BEGIN EC PRIVATE KEY-----', '')
            private_key = private_key.replace('-----END EC PRIVATE KEY-----', '')
            private_key = private_key.replace('\\n', '') # Note: double backslash for .env file format
            private_key = private_key.strip()
            
            # Create signature
            key_bytes = base64.b64decode(private_key)
            signature = hmac.new(key_bytes, message.encode(), hashlib.sha256).hexdigest()
            
            # Build headers
            headers = {
                'CB-ACCESS-KEY': api_key.split('/')[-1],  # Extract the key ID from the full path
                'CB-ACCESS-SIGN': signature,
                'CB-ACCESS-TIMESTAMP': timestamp,
                'Content-Type': 'application/json'
            }
            
            current_app.logger.debug(f"Making request to Coinbase API with headers: {headers}")
            
            response = requests.get(
                'https://api.coinbase.com/api/v3/brokerage/products',
                headers=headers
            )
            
            if response.status_code == 200:
                data = response.json()
                
                # Filter only active products
                active_products = [
                    product for product in data.get('products', []) 
                    if product.get('status') == 'online' and 
                    not product.get('trading_disabled') and
                    not product.get('is_disabled')
                ]
                
                # Format for frontend
                formatted_pairs = [
                    {
                        'id': product.get('product_id'),
                        'display_name': product.get('display_name') or product.get('product_id'),
                        'base_currency': product.get('base_currency_id'),
                        'quote_currency': product.get('quote_currency_id'),
                        'base_name': product.get('base_name') or product.get('base_currency_id'),
                        'quote_name': product.get('quote_name') or product.get('quote_currency_id'),
                        'status': product.get('status')
                    }
                    for product in active_products
                ]
                
                current_app.logger.info(f"Successfully fetched {len(formatted_pairs)} trading pairs")
                return jsonify(formatted_pairs)
            else:
                current_app.logger.error(f"API request failed with status {response.status_code}: {response.text}")
                raise ValueError(f"API request failed with status {response.status_code}")
        
        # If we can't fetch from API, use the fallback list
        raise ValueError("Unable to fetch trading pairs from API")
    
    except Exception as e:
        current_app.logger.error(f"Error fetching trading pairs: {str(e)}")
        
        # Use the hardcoded list as a fallback
        current_app.logger.info("Using fallback list of trading pairs")
        
        # This is a shortened version of your list - you can add more pairs as needed
        pair_ids = [
            "BTC-USD", "BTC-USDC", "BTC-USDT","ETH-USD", "ETH-USDC", "ETH-USDT",
            "ADA-USD", "ADA-USDC", "ADA-USDT","SOL-USD", "SOL-USDC", "SOL-USDT"
        ]
        
        formatted_pairs = []
        for pair_id in pair_ids:
            parts = pair_id.split('-')
            if len(parts) == 2:
                base, quote = parts
                
                # Get friendly names for common currencies
                base_name = get_currency_name(base)
                quote_name = get_currency_name(quote)
                
                pair = {
                    'id': pair_id,
                    'display_name': pair_id,
                    'base_currency': base,
                    'quote_currency': quote,
                    'base_name': base_name,
                    'quote_name': quote_name
                }
                
                formatted_pairs.append(pair)
        
        return jsonify(formatted_pairs)

def get_currency_name(symbol):
    """Get full name for currency symbol"""
    names = {
        'BTC': 'Bitcoin',
        'ETH': 'Ethereum',
        'USDC': 'USD Coin',
        'USD': 'US Dollar',
        'USDT': 'Tether',
        'SOL': 'Solana',
        'XRP': 'XRP',
        'EUR': 'Euro',
        'GBP': 'British Pound',
        'DOGE': 'Dogecoin',
        'ADA': 'Cardano',
        'LINK': 'Chainlink',
        'AVAX': 'Avalanche',
        'MATIC': 'Polygon',
        'DOT': 'Polkadot',
        'UNI': 'Uniswap',
        'SHIB': 'Shiba Inu',
        'ATOM': 'Cosmos',
        'LTC': 'Litecoin',
        'DAI': 'Dai',
        'HBAR': 'Hedera',
        'SUI': 'Sui'
    }
    
    return names.get(symbol, symbol)