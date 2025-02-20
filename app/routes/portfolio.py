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
