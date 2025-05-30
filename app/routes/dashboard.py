from flask import (
    Blueprint, render_template, jsonify,
    session, redirect, url_for, request, flash
)
from flask_security import login_required, current_user
from app.models.automation import Automation
from app.models.webhook import WebhookLog
from app.models.exchange_credentials import ExchangeCredentials
from app.models.portfolio import Portfolio 
from app.forms import CoinbaseAPIKeyForm
from app.services.account_service import AccountService
from app import db
import coinbase.rest
import logging

# Add the logger that's missing
logger = logging.getLogger(__name__)

bp = Blueprint('dashboard', __name__)


@bp.route('/dashboard')
@login_required
def dashboard():
    """Render the dashboard page for non-admin users with improved handling of invalid credentials."""
    if current_user.has_role('admin'):
        return redirect(url_for('admin.users'))

    user_id = current_user.id
    
    # Get automations
    db_automations = Automation.query.filter_by(user_id=user_id).all()
    
    # Get portfolios and verify their access
    all_portfolios = Portfolio.query.filter_by(user_id=user_id).all()
    
    # Create a dictionary of verified portfolios
    portfolios = {}
    for p in all_portfolios:
        portfolios[p.id] = p
        
        # Check if portfolio has credentials
        has_credentials = ExchangeCredentials.query.filter_by(
            portfolio_id=p.id,
            exchange='coinbase'
        ).first() is not None
        
        # Store credential status on portfolio object
        p.has_credentials = has_credentials
    
    # Convert automations to dictionaries for template
    automations = []
    for automation in db_automations:
        automation_dict = {
            'id': automation.id,
            'automation_id': automation.automation_id,
            'name': automation.name,
            'is_active': automation.is_active,
            'trading_pair': automation.trading_pair,
            'webhook_url': f"{request.url_root.rstrip('/')}/webhook?automation_id={automation.automation_id}",
            'portfolio_name': None,
            'portfolio_value': None,
            'portfolio_status': 'disconnected'  # Default status
        }
        
        if automation.portfolio_id and automation.portfolio_id in portfolios:
            portfolio = portfolios[automation.portfolio_id]
            automation_dict['portfolio_name'] = portfolio.name
            
            if hasattr(portfolio, 'has_credentials') and portfolio.has_credentials:
                if portfolio.invalid_credentials:
                    automation_dict['portfolio_status'] = 'invalid'
                else:
                    # Only try to get portfolio value if credentials exist and aren't marked invalid
                    try:
                        portfolio_value = AccountService.get_portfolio_value(user_id, portfolio.id)
                        automation_dict['portfolio_value'] = portfolio_value
                        automation_dict['portfolio_status'] = 'connected' if portfolio_value > 0 else 'empty'
                    except Exception as e:
                        logger.error(f"Error getting portfolio value: {str(e)}")
                        automation_dict['portfolio_status'] = 'error'
            else:
                automation_dict['portfolio_status'] = 'disconnected'
        
        automations.append(automation_dict)

    # Check if user has Coinbase API keys
    has_coinbase_keys = ExchangeCredentials.query.filter_by(
        user_id=current_user.id,
        exchange='coinbase',
        portfolio_name='default'
    ).first() is not None

    return render_template('dashboard.html', 
                           automations=automations, 
                           has_coinbase_keys=has_coinbase_keys)

    
@bp.route('/api/coinbase/portfolios')
@login_required
def get_coinbase_portfolios():
    try:
        # Get portfolios from database
        db_portfolios = Portfolio.query.filter_by(
            user_id=current_user.id
        ).all()
        
        # Create portfolio data with connection status and value
        portfolio_data = []
        for p in db_portfolios:
            # Check if portfolio has credentials
            has_credentials = bool(ExchangeCredentials.query.filter_by(
                portfolio_id=p.id,
                exchange='coinbase'
            ).first())
            
            # Get portfolio value if connected
            portfolio_value = None
            if has_credentials:
                portfolio_value = AccountService.get_portfolio_value(current_user.id, p.id)
            
            portfolio_data.append({
                'id': p.id,
                'name': p.name,
                'portfolio_id': p.portfolio_id,
                'exchange': p.exchange,
                'is_connected': has_credentials,
                'value': portfolio_value
            })
        
        return jsonify({
            'has_credentials': True,
            'portfolios': portfolio_data
        })
    except Exception as e:
        return jsonify({
            'has_credentials': False,
            'error': str(e)
        })


@bp.route('/clear-logs', methods=['POST'])
@login_required
def clear_logs():
    """Clear webhook logs for the current user."""
    try:
        user_id = current_user.id
        WebhookLog.query.join(Automation).filter(
            Automation.user_id == user_id
        ).delete(synchronize_session=False)

        db.session.commit()
        return jsonify({"success": True})
    except Exception as e:
        logger.error(f"Error clearing logs: {e}")
        db.session.rollback()
        return jsonify({"error": str(e)}), 500


@bp.route('/settings', methods=['GET', 'POST'])
@login_required
def settings():
    """Render the settings page."""
    # Get existing Coinbase API credentials if any
    coinbase_creds = ExchangeCredentials.query.filter_by(
        user_id=current_user.id,
        exchange='coinbase',
        portfolio_name='default'
    ).first()
    
    form = CoinbaseAPIKeyForm()
    
    # Pre-fill API Key if exists (but not secret)
    if coinbase_creds and not form.is_submitted():
        form.api_key.data = coinbase_creds.api_key
    
    if form.validate_on_submit():
        api_key = form.api_key.data
        api_secret = form.api_secret.data
        
        # Verify the API keys by making a simple request
        try:
            # Create a client to test the connection
            client = coinbase.rest.RESTClient(
                api_key=api_key,
                api_secret=api_secret
            )
            
            # Test the connection with a simple account request
            client.get_accounts()
            
            # Check if credentials already exist
            if coinbase_creds:
                # Update existing credentials
                coinbase_creds.api_key = api_key
                coinbase_creds.api_secret = coinbase_creds.encrypt_secret(api_secret)
                coinbase_creds.updated_at = db.func.now()
            else:
                # Create new credentials
                coinbase_creds = ExchangeCredentials(
                    user_id=current_user.id,
                    exchange='coinbase',
                    portfolio_name='default',
                    api_key=api_key,
                    api_secret=api_secret,
                    is_default=True
                )
                db.session.add(coinbase_creds)
            
            db.session.commit()
            flash('Coinbase API keys saved successfully!', 'success')
            return redirect(url_for('dashboard.settings'))
            
        except Exception as e:
            flash(f'Error validating Coinbase API keys: {str(e)}', 'danger')
    
    # Gather credentials for all exchanges for display in template
    user_creds = ExchangeCredentials.query.filter_by(user_id=current_user.id).all()
    exchange_creds_map = {c.exchange: c for c in user_creds}

    return render_template(
        'settings.html',
        form=form,
        exchange_credentials=exchange_creds_map,
        has_coinbase_keys=bool(exchange_creds_map.get('coinbase'))
    )


@bp.route('/settings/coinbase/delete', methods=['POST'])
@login_required
def delete_coinbase_api_keys():
    """Delete Coinbase API keys"""
    creds = ExchangeCredentials.query.filter_by(
        user_id=current_user.id,
        exchange='coinbase',
        portfolio_name='default'
    ).first()
    
    if creds:
        db.session.delete(creds)
        db.session.commit()
        flash('Coinbase API keys deleted successfully!', 'success')
    
    return redirect(url_for('dashboard.settings'))


# ------------------------------------------------------------------
# Generic delete API keys endpoint (works for any exchange)
# ------------------------------------------------------------------

@bp.route('/settings/api-keys/delete', methods=['POST'])
@login_required
def delete_api_keys():
    """Delete API keys for the exchange provided in the form."""
    from flask import request  # local import to avoid circular issues

    exchange = request.form.get('exchange')
    if not exchange:
        flash('Exchange not specified', 'danger')
        return redirect(url_for('dashboard.settings'))

    creds = ExchangeCredentials.query.filter_by(
        user_id=current_user.id,
        exchange=exchange,
        portfolio_name='default',
    ).first()

    if creds:
        db.session.delete(creds)
        db.session.commit()
        flash(f'{exchange.capitalize()} API keys deleted successfully!', 'success')
    else:
        flash('No credentials found', 'warning')

    return redirect(url_for('dashboard.settings'))
