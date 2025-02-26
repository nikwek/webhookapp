# app/routes/api_keys.py
from flask import Blueprint, render_template, redirect, url_for, request, flash, jsonify, current_app
from flask_login import login_required, current_user
from app.models.exchange_credentials import ExchangeCredentials
from app.models.automation import Automation
from app.services.coinbase_service import CoinbaseService
from app import db

bp = Blueprint('api_keys', __name__, url_prefix='/api-keys')

@bp.route('/connect/<automation_id>', methods=['GET', 'POST'])
@login_required
def connect(automation_id):
    """Connect an automation to Coinbase via API keys"""
    automation = Automation.query.filter_by(
        automation_id=automation_id,
        user_id=current_user.id
    ).first_or_404()
    
    # Check if credentials already exist
    existing_creds = ExchangeCredentials.query.filter_by(
        automation_id=automation_id,
        user_id=current_user.id,
        exchange='coinbase'
    ).first()
    
    if request.method == 'POST':
        api_key = request.form.get('api_key')
        api_secret = request.form.get('api_secret')
        name = request.form.get('credential_name')
        
        if not all([api_key, api_secret, name]):
            flash('All fields are required', 'danger')
            return redirect(url_for('api_keys.connect', automation_id=automation_id))
        
        # Create temporary credentials to test
        temp_creds = ExchangeCredentials(
            user_id=current_user.id,
            automation_id=automation_id,
            exchange='coinbase',
            name=name
        )
        
        # Set API key and secret
        temp_creds.api_key = api_key
        temp_creds.secret_key = api_secret
        
        # Test credentials
        test_result = CoinbaseService.list_portfolios(temp_creds)
        
        if not test_result:
            flash('Invalid API key or secret', 'danger')
            return redirect(url_for('api_keys.connect', automation_id=automation_id))
        
        if existing_creds:
            existing_creds.name = name
            existing_creds.api_key = api_key
            existing_creds.secret_key = api_secret
        else:
            db.session.add(temp_creds)
        
        db.session.commit()
        flash('Coinbase API credentials saved successfully', 'success')
        return redirect(url_for('api_keys.select_portfolio', automation_id=automation_id))
        
    return render_template('api_keys/connect.html', automation=automation)

@bp.route('/select-portfolio/<automation_id>', methods=['GET', 'POST'])
@login_required
def select_portfolio(automation_id):
    """Select a portfolio to use with an automation"""
    automation = Automation.query.filter_by(
        automation_id=automation_id,
        user_id=current_user.id
    ).first_or_404()
    
    credentials = ExchangeCredentials.query.filter_by(
        automation_id=automation_id,
        user_id=current_user.id,
        exchange='coinbase'
    ).first_or_404()
    
    if request.method == 'POST':
        portfolio_id = request.form.get('portfolio_id')
        portfolio_name = request.form.get('portfolio_name')
        
        credentials.portfolio_id = portfolio_id
        credentials.portfolio_name = portfolio_name
        db.session.commit()
        
        flash('Portfolio selected successfully', 'success')
        return redirect(url_for('automation.view_automation', automation_id=automation_id))
    
    # Get portfolios from Coinbase
    portfolios = CoinbaseService.list_portfolios(credentials)
    
    return render_template(
        'api_keys/select_portfolio.html',
        automation=automation,
        portfolios=portfolios
    )