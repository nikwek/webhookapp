from flask import Blueprint, render_template, request, jsonify, flash, redirect, url_for
from flask_login import login_required, current_user
from app.services.coinbase_service import CoinbaseService
from app.models.exchange_credentials import ExchangeCredentials
from app import db

bp = Blueprint('portfolio', __name__, url_prefix='/portfolio')

@bp.route('/')
@login_required
def index():
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

@bp.route('/create', methods=['POST'])
@login_required
def create_portfolio():
    name = request.form.get('name')
    if not name:
        flash('Portfolio name is required', 'error')
        return redirect(url_for('portfolio.index'))

    try:
        coinbase = CoinbaseService(current_user.id)
        portfolio = coinbase.create_portfolio(name)
        flash(f'Portfolio "{name}" created successfully', 'success')
        return redirect(url_for('portfolio.index'))
    except Exception as e:
        flash(f'Failed to create portfolio: {str(e)}', 'error')
        return redirect(url_for('portfolio.index'))

@bp.route('/<portfolio_id>/credentials', methods=['POST'])
@login_required
def get_credentials(portfolio_id):
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
        
        flash('API credentials generated and saved successfully', 'success')
        return redirect(url_for('automation.index'))
    except Exception as e:
        flash(f'Failed to generate API credentials: {str(e)}', 'error')
        return redirect(url_for('portfolio.index'))