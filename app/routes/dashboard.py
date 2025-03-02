from flask import (
    Blueprint, render_template, jsonify,
    session, redirect, url_for, request, flash
)
from flask_login import login_required, current_user
from app.models.automation import Automation
from app.models.webhook import WebhookLog
from app.models.exchange_credentials import ExchangeCredentials
from app.models.portfolio import Portfolio 
from app.forms import CoinbaseAPIKeyForm
from app import db
import coinbase.rest

bp = Blueprint('dashboard', __name__)


@bp.route('/dashboard')
@login_required
def dashboard():
    """Render the dashboard page for non-admin users."""
    if session.get('is_admin'):
        return redirect(url_for('admin.users'))

    user_id = current_user.id
    
    # Get automations with portfolio details using a join
    automations_query = (
        Automation.query
        .outerjoin(Portfolio, Automation.portfolio_id == Portfolio.id)
        .filter(Automation.user_id == user_id)
        .add_columns(
            Portfolio.name.label('portfolio_name'),
            Automation.trading_pair
        )
        .all()
    )
    
    # Process the results into a format suitable for the template
    automations = []
    for result in automations_query:
        automation = result[0]  # The Automation object
        automation.webhook_url = f"{request.url_root.rstrip('/')}/webhook?automation_id={automation.automation_id}"
        automation.portfolio_name = result[1]  # The Portfolio.name value
        automation.trading_pair = result[0].trading_pair  # Get trading_pair from Automation object
        automations.append(automation)

    # Check if user has Coinbase API keys
    has_coinbase_keys = ExchangeCredentials.query.filter_by(
        user_id=current_user.id,
        exchange='coinbase',
        portfolio_name='default'
    ).first() is not None

    return render_template('dashboard.html', 
                           automations=automations, 
                           has_coinbase_keys=has_coinbase_keys)


@bp.route('/api/logs')
@login_required
def get_logs():
    """Get webhook logs for the current user."""
    try:
        logs = WebhookLog.query.join(Automation).filter(
            Automation.user_id == current_user.id
        ).order_by(WebhookLog.timestamp.desc()).limit(100).all()
        
        return jsonify([log.to_dict() for log in logs])
    except Exception as e:
        print(f"Error getting logs: {str(e)}")
        return jsonify({"error": str(e)}), 500
    
@bp.route('/api/coinbase/portfolios')
@login_required
def get_coinbase_portfolios():
    try:
        # Get portfolios from database
        db_portfolios = Portfolio.query.filter_by(
            user_id=current_user.id
        ).all()
        
        # Create portfolio data with connection status
        portfolio_data = [{
            'id': p.id,
            'name': p.name,
            'portfolio_id': p.portfolio_id,
            'exchange': p.exchange,
            'is_connected': bool(ExchangeCredentials.query.filter_by(
                portfolio_id=p.id,
                exchange='coinbase'
            ).first())
        } for p in db_portfolios]
        
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
        print(f"Error clearing logs: {e}")
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
    
    return render_template('settings.html', 
                          form=form, 
                          has_coinbase_keys=bool(coinbase_creds))


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
