from flask import (
    Blueprint, render_template, jsonify,
    redirect, url_for, request, flash
)
from flask_security import login_required, current_user
from app.models.automation import Automation
from app.models.webhook import WebhookLog
from app.models.exchange_credentials import ExchangeCredentials
from app.models.portfolio import Portfolio
from app.forms.api_key_form import CoinbaseAPIKeyForm, CcxtApiKeyForm
from app.exchanges.coinbase_adapter import CoinbaseAdapter
from app.exchanges.registry import ExchangeRegistry
from app.services.account_service import AccountService
from app import db
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

    logger.info(f"Dashboard loaded for user: {current_user.email}, Admin: {current_user.has_role('admin')}")

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
    """Render the settings page and handle API key form submissions."""
    # Imports moved to top-level
    coinbase_native_form = CoinbaseAPIKeyForm(prefix='cb_native')
    ccxt_form = CcxtApiKeyForm(prefix='ccxt')

    if request.method == 'POST':
        logger.info(f"--- SETTINGS POST REQUEST ---")
        logger.info(f"Raw form data: {request.form.to_dict(flat=False)}")
        submitted_form_name = request.form.get('form_name')
        logger.info(f"Submitted form_name: '{submitted_form_name}'")

        if submitted_form_name == 'coinbase_native_form':
            logger.info("Attempting to validate coinbase_native_form")
            if coinbase_native_form.validate_on_submit():
                logger.info("coinbase_native_form validation SUCCESSFUL.")
                api_key = coinbase_native_form.api_key.data
                api_secret = coinbase_native_form.api_secret.data
                try:
                    # Validate the new keys from the form directly
                    is_valid, validation_message = CoinbaseAdapter.validate_api_keys(api_key, api_secret)
                    if not is_valid:
                        raise Exception(f"Coinbase key validation error: {validation_message}")
                    logger.info("Coinbase API keys successfully validated via direct check.")
                    existing_creds = ExchangeCredentials.query.filter_by(user_id=current_user.id, exchange='coinbase').first()
                    if existing_creds:
                        existing_creds.api_key = api_key
                        existing_creds.api_secret = existing_creds.encrypt_secret(api_secret)
                        existing_creds.updated_at = db.func.now()
                    else:
                        is_new_default = not ExchangeCredentials.query.filter_by(user_id=current_user.id, is_default=True).first()
                        new_creds = ExchangeCredentials(user_id=current_user.id, exchange='coinbase',
                                                       api_key=api_key, api_secret=api_secret,
                                                       portfolio_name='default', is_default=is_new_default)
                        db.session.add(new_creds)
                    db.session.commit()
                    flash('Coinbase API keys saved successfully!', 'success')
                    return redirect(url_for('dashboard.settings'))
                except Exception as e:
                    logger.error(f"Error validating/saving Coinbase API keys: {str(e)}", exc_info=True)
                    db.session.rollback()
                    flash(f'Error validating/saving Coinbase API keys: {str(e)}', 'danger')
            else:
                logger.error(f"Coinbase Native form validation FAILED. Errors: {coinbase_native_form.errors}")
                flash(f"Error processing Coinbase Native form. Please check inputs: {coinbase_native_form.errors}", "danger")
        
        elif submitted_form_name == 'ccxt_form':
            exchange_name_from_form = request.form.get('exchange')
            logger.info(f"Attempting to validate ccxt_form for exchange: {exchange_name_from_form}")
            if ccxt_form.validate_on_submit():
                logger.info(f"ccxt_form validation SUCCESSFUL for exchange: {exchange_name_from_form}.")
                api_key = ccxt_form.api_key.data
                api_secret = ccxt_form.api_secret.data
                # Ensure exchange_name is captured from the form for the try block
                exchange_name = exchange_name_from_form 
                logger.info(f"Attempting to save API keys for {exchange_name.capitalize()}.")
                try:
                    existing_creds = ExchangeCredentials.query.filter_by(user_id=current_user.id, exchange=exchange_name).first()
                    if existing_creds:
                        existing_creds.api_key = api_key
                        existing_creds.api_secret = existing_creds.encrypt_secret(api_secret)
                        existing_creds.updated_at = db.func.now()
                        logger.info(f"Updating existing API keys for {exchange_name.capitalize()}. API Key: {api_key[:5]}...")
                    else:
                        is_new_default = not ExchangeCredentials.query.filter_by(user_id=current_user.id, is_default=True).first()
                        new_creds = ExchangeCredentials(
                            user_id=current_user.id,
                            exchange=exchange_name,
                            api_key=api_key,
                            api_secret=api_secret,
                            portfolio_name='default',  # Added for CCXT exchanges
                            is_default=is_new_default
                        )
                        db.session.add(new_creds)
                        logger.info(f"Adding new API keys for {exchange_name.capitalize()}. API Key: {api_key[:5]}...")
                    db.session.commit()
                    logger.info(f"Successfully saved/updated API keys for {exchange_name.capitalize()} in the database.")
                    flash(f'{exchange_name.capitalize()} API keys saved successfully!', 'success')
                    return redirect(url_for('dashboard.settings'))
                except Exception as e:
                    db.session.rollback()
                    logger.error(f"Error saving {exchange_name.capitalize()} API keys: {str(e)}", exc_info=True)
                    flash(f'Error saving {exchange_name.capitalize()} API keys: {str(e)}', 'danger')
            else:
                logger.error(f"CCXT form validation FAILED for exchange {exchange_name_from_form}. Errors: {ccxt_form.errors}")
                flash(f"Error processing CCXT form for {exchange_name_from_form}. Please check inputs: {ccxt_form.errors}", "danger")
        
        else:
            logger.warning(f"POST to /settings with unhandled or missing form_name: '{submitted_form_name}'. Check form (HTML & JS) and route logic.")
            if not submitted_form_name:
                flash("An error occurred: Form type not identified.", "danger")
            else:
                flash(f"An error occurred processing the '{submitted_form_name}' form. Please contact support.", "danger")

    # Gather data for template display (GET request or after POST processing)
    logger.info(f"Settings GET: current_user.id = {current_user.id}")
    user_creds = ExchangeCredentials.query.filter_by(user_id=current_user.id).all()
    logger.info(f"Settings GET: Found {len(user_creds)} credentials for user.")
    for cred_log_idx, cred_log_item in enumerate(user_creds):
        logger.info(f"  Cred {cred_log_idx}: id={cred_log_item.id}, exchange='{cred_log_item.exchange}', portfolio='{cred_log_item.portfolio_name}', key_present={bool(cred_log_item.api_key)}")
    exchange_creds_map = {}
    # Prioritize 'coinbase' with 'default' portfolio for native display
    coinbase_default_cred = next((c for c in user_creds if c.exchange == 'coinbase' and c.portfolio_name == 'default'), None)

    if coinbase_default_cred:
        exchange_creds_map['coinbase'] = coinbase_default_cred

    # Populate other credentials, avoiding overwrite if coinbase default was already set by priority
    for cred in user_creds:
        if cred.exchange not in exchange_creds_map:
            exchange_creds_map[cred.exchange] = cred
    logger.info(f"Settings GET: exchange_creds_map before passing to template: { {k: v.id for k,v in exchange_creds_map.items()} }")
    available_exchange_adapters = ExchangeRegistry.get_all_adapter_classes()
    logger.info(f"Settings GET: Names from available_exchange_adapters: {[adapter.get_name() for adapter in available_exchange_adapters]}")

    # Pre-fill Coinbase native form if keys exist and not a POST submission that failed validation
    if request.method == 'GET' and 'coinbase' in exchange_creds_map:
        coinbase_native_form.api_key.data = exchange_creds_map['coinbase'].api_key
        # Do not pre-fill secret

    return render_template(
        'settings.html',
        coinbase_native_form=coinbase_native_form,
        ccxt_form=ccxt_form,
        form=coinbase_native_form, 
        available_exchange_adapters=available_exchange_adapters,
        exchange_credentials=exchange_creds_map,
        has_coinbase_keys=bool(exchange_creds_map.get('coinbase')),
    )

# ... (rest of the code remains the same)
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
