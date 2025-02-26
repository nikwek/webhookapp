# app/routes/settings.py
from flask import Blueprint, render_template, redirect, request, url_for, flash, current_app
from flask_login import login_required, current_user
from app.models.exchange_credentials import ExchangeCredentials
from app.services.coinbase_service import CoinbaseService
from app import db
from datetime import datetime, timezone

bp = Blueprint('settings', __name__, url_prefix='/settings')

@bp.route('/', methods=['GET'])
@login_required
def index():
    # Get account-level credentials
    account_credentials = ExchangeCredentials.get_account_credentials(current_user.id)
    
    # Get portfolios if credentials exist
    portfolios = []
    if account_credentials:
        try:
            portfolios = CoinbaseService.list_portfolios(account_credentials)
        except Exception as e:
            current_app.logger.error(f"Error fetching portfolios: {str(e)}")
            flash("Could not fetch portfolios. Please check your API credentials.", "warning")
    
    return render_template('settings.html', 
                          account_credentials=account_credentials,
                          portfolios=portfolios)

@bp.route('/connect-coinbase', methods=['POST'])
@login_required
def connect_coinbase():
    api_key = request.form.get('api_key')
    api_secret = request.form.get('api_secret')
    name = request.form.get('credential_name', 'My Coinbase Account')
    
    if not all([api_key, api_secret]):
        flash('API Key and Secret are required', 'danger')
        return redirect(url_for('settings.index'))
    
    # Check if account credentials already exist
    existing = ExchangeCredentials.get_account_credentials(current_user.id)
    if existing:
        flash('You already have Coinbase credentials. Please disconnect first.', 'warning')
        return redirect(url_for('settings.index'))
    
    # Create and test credentials
    try:
        credentials = ExchangeCredentials(
            user_id=current_user.id,
            name=name,
            exchange='coinbase',
            purpose='read_only',
            automation_id=None
        )
        credentials.api_key = api_key
        credentials.secret_key = api_secret
        
        # Test if credentials work by listing portfolios
        test_result = CoinbaseService.list_portfolios(credentials)
        if not test_result:
            flash('Invalid API key or secret. Please check your credentials.', 'danger')
            return redirect(url_for('settings.index'))
        
        # Save credentials
        db.session.add(credentials)
        db.session.commit()
        
        flash('Successfully connected to Coinbase!', 'success')
    except Exception as e:
        current_app.logger.error(f"Error connecting to Coinbase: {str(e)}")
        flash(f'Error connecting to Coinbase: {str(e)}', 'danger')
    
    return redirect(url_for('settings.index'))

@bp.route('/disconnect-coinbase', methods=['POST'])
@login_required
def disconnect_coinbase():
    # Find and remove account credentials
    creds = ExchangeCredentials.get_account_credentials(current_user.id)
    if creds:
        db.session.delete(creds)
        db.session.commit()
        flash('Successfully disconnected from Coinbase.', 'success')
    else:
        flash('No Coinbase connection found.', 'info')
    
    return redirect(url_for('settings.index'))