from flask import Blueprint, render_template, request, jsonify, flash, redirect, url_for, current_app
from flask_login import login_required, current_user
from app.services.coinbase_service import CoinbaseService
from app.models.exchange_credentials import ExchangeCredentials
from app import db

bp = Blueprint('portfolio', __name__, url_prefix='/portfolio')

@bp.route('/')
@login_required
def index():
    """Portfolio dashboard view"""
    try:
        # Get account credentials
        account_creds = ExchangeCredentials.get_account_credentials(current_user.id)
        if not account_creds:
            flash('Please connect your Coinbase account first.', 'warning')
            return redirect(url_for('settings.index'))
            
        portfolios = CoinbaseService.list_portfolios(account_creds)
        return render_template('portfolio/index.html', portfolios=portfolios)
    except Exception as e:
        flash(f'Failed to fetch portfolios: {str(e)}', 'error')
        return render_template('portfolio/index.html', portfolios=[])

@bp.route('/api/portfolios', methods=['GET'])
@login_required
def list_portfolios():
    """API endpoint to list portfolios"""
    try:
        account_creds = ExchangeCredentials.get_account_credentials(current_user.id)
        if not account_creds:
            return jsonify({"error": "Please connect your Coinbase account first."}), 401
            
        portfolios = CoinbaseService.list_portfolios(account_creds)
        return jsonify({"portfolios": portfolios})
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

        account_creds = ExchangeCredentials.get_account_credentials(current_user.id)
        if not account_creds:
            return jsonify({"error": "Please connect your Coinbase account first."}), 401
            
        portfolio = CoinbaseService.create_portfolio(account_creds, data['name'])
        return jsonify({"portfolio": portfolio})
    except Exception as e:
        current_app.logger.error(f"Error creating portfolio: {str(e)}")
        return jsonify({"error": str(e)}), 500

@bp.route('/api/portfolios/<portfolio_id>/credentials', methods=['POST'])
@login_required
def get_credentials(portfolio_id):
    """API endpoint to save portfolio credentials"""
    try:
        # Get API key and secret from request
        data = request.get_json()
        api_key = data.get('api_key')
        api_secret = data.get('api_secret')
        name = data.get('name', f"Portfolio {portfolio_id} API Key")
        
        if not api_key or not api_secret:
            return jsonify({"error": "API key and secret are required"}), 400
        
        # Get account credentials to verify the portfolio exists
        account_creds = ExchangeCredentials.get_account_credentials(current_user.id)
        if not account_creds:
            return jsonify({"error": "Please connect your Coinbase account first."}), 401
            
        # Verify portfolio exists
        portfolio = CoinbaseService.get_portfolio(account_creds, portfolio_id)
        if not portfolio:
            return jsonify({"error": "Portfolio not found"}), 404
        
        # Test the provided API credentials
        temp_creds = ExchangeCredentials(
            user_id=current_user.id,
            portfolio_id=portfolio_id,
            portfolio_name=portfolio.get('name'),
            exchange='coinbase',
            purpose='trading'
        )
        temp_creds.api_key = api_key
        temp_creds.secret_key = api_secret
        
        # Verify the credentials work by testing access
        test_result = CoinbaseService.list_portfolios(temp_creds)
        if not test_result:
            return jsonify({"error": "Invalid API key or secret"}), 400
        
        # Save the verified credentials
        db.session.add(temp_creds)
        db.session.commit()
        
        return jsonify({
            "success": True,
            "message": "API credentials saved successfully"
        })
    except Exception as e:
        current_app.logger.error(f"Error saving credentials: {str(e)}")
        return jsonify({"error": str(e)}), 500
