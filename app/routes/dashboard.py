from flask import (
    Blueprint, render_template, jsonify,
    redirect, url_for, request, flash,
    request
)
from flask_security import login_required, current_user
from app.models.automation import Automation
from app.models.webhook import WebhookLog
from app.models.exchange_credentials import ExchangeCredentials
from app.models.portfolio import Portfolio
from app.forms.api_key_form import CoinbaseAPIKeyForm, CcxtApiKeyForm
from app.exchanges.coinbase_adapter import CoinbaseAdapter
from app.exchanges.ccxt_base_adapter import CcxtBaseAdapter
from app.exchanges.registry import ExchangeRegistry
from app.services.account_service import AccountService
from typing import List, Dict, Any
from app import db
import logging

# Add the logger that's missing
logger = logging.getLogger(__name__)

def flash_form_errors(form):
    """Flashes form errors to the user."""
    for field, errors in form.errors.items():
        for error in errors:
            flash(f"Error in the {getattr(form, field).label.text} field - {error}", 'danger')




bp = Blueprint('dashboard', __name__)


@bp.route('/dashboard')
@login_required
def dashboard():
    """Render the dashboard page for non-admin users."""
    if current_user.has_role('admin'):
        return redirect(url_for('admin.users'))

    logger.info(
        f"Dashboard loaded for user: {current_user.email}, "
        f"Admin: {current_user.has_role('admin')}"
    )
    user_id = current_user.id

    # Get automations
    db_automations = Automation.query.filter_by(user_id=user_id).all()

    # Get portfolios (used for automations linking to Coinbase Native portfolios)
    all_user_portfolios = Portfolio.query.filter_by(user_id=user_id).all()

    portfolios_map = {}
    for p_model in all_user_portfolios:
        portfolios_map[p_model.id] = p_model
        # Check if this Portfolio model instance has Coinbase Native credentials
        has_native_creds = ExchangeCredentials.query.filter_by(
            portfolio_id=p_model.id,  # Links Portfolio.id
            exchange=CoinbaseAdapter.get_name()  # For Coinbase native
        ).first() is not None
        p_model.has_credentials = has_native_creds

    automations_list = []
    for item in db_automations:
        url_root = request.url_root.rstrip('/')
        webhook_url = f"{url_root}/webhook?automation_id={item.automation_id}"
        automation_dict = {
            'id': item.id,
            'automation_id': item.automation_id,
            'name': item.name,
            'is_active': item.is_active,
            'trading_pair': item.trading_pair,
            'webhook_url': webhook_url,
            'portfolio_name': None,
            'portfolio_value': None,
            'portfolio_status': 'disconnected'
        }

        if item.portfolio_id and item.portfolio_id in portfolios_map:
            linked_model = portfolios_map[item.portfolio_id]
            automation_dict['portfolio_name'] = linked_model.name

            if getattr(linked_model, 'has_credentials', False):
                if getattr(linked_model, 'invalid_credentials', False):
                    automation_dict['portfolio_status'] = 'invalid'
                else:
                    try:
                        # Coinbase-specific via CoinbaseService
                        value = AccountService.get_portfolio_value(
                            user_id, linked_model.id
                        )
                        automation_dict['portfolio_value'] = value
                        is_positive = value and float(value) > 0
                        status = 'connected' if is_positive else 'empty'
                        automation_dict['portfolio_status'] = status
                    except Exception as e:
                        logger.error(
                            f"Error getting portfolio value for automation "
                            f"{item.id} (portfolio {linked_model.id}): {e}",
                            exc_info=True
                        )
                        automation_dict['portfolio_status'] = 'error'
            else:
                automation_dict['portfolio_status'] = 'disconnected'

        automations_list.append(automation_dict)

    # --- New logic for Exchange Balances ---
    connected_exchanges_display_data: List[Dict[str, Any]] = []
    all_creds = ExchangeCredentials.query.filter_by(user_id=user_id).all()

    unique_names = sorted(list(set(cred.exchange for cred in all_creds)))

    for ex_name in unique_names:
        adapter_cls = ExchangeRegistry.get_adapter(ex_name)
        if not adapter_cls:
            logger.warning(
                f"No adapter for exchange: {ex_name}, user: {user_id}"
            )
            continue

        logger.debug(f"Dashboard: ----- START Processing ex_name: {ex_name}, adapter_cls: {adapter_cls} -----")
        
        _resolved_display_name = None
        if hasattr(adapter_cls, 'get_display_name'):
            logger.debug(f"Dashboard: adapter_cls '{adapter_cls.__name__}' for '{ex_name}' HAS get_display_name method.")
            try:
                _resolved_display_name = adapter_cls.get_display_name()
                logger.debug(f"Dashboard: Called {adapter_cls.__name__}.get_display_name() for '{ex_name}'. Result: '{_resolved_display_name}'")
            except Exception as e_gdn:
                logger.error(f"Dashboard: Error calling {adapter_cls.__name__}.get_display_name() for '{ex_name}': {e_gdn}", exc_info=True)
                if hasattr(adapter_cls, 'get_name'):
                    logger.warning(f"Dashboard: Falling back to {adapter_cls.__name__}.get_name() for '{ex_name}' due to error in get_display_name.")
                    try:
                        _resolved_display_name = adapter_cls.get_name()
                        logger.debug(f"Dashboard: Called fallback {adapter_cls.__name__}.get_name() for '{ex_name}'. Result: '{_resolved_display_name}'")
                    except Exception as e_gn_fallback:
                        logger.error(f"Dashboard: Error calling fallback {adapter_cls.__name__}.get_name() for '{ex_name}': {e_gn_fallback}", exc_info=True)
                        _resolved_display_name = ex_name
                        logger.warning(f"Dashboard: Ultimate fallback to ex_name for '{ex_name}'. Result: '{_resolved_display_name}'")
                else:
                    _resolved_display_name = ex_name
                    logger.warning(f"Dashboard: Ultimate fallback to ex_name for '{ex_name}' (get_name missing after get_display_name error). Result: '{_resolved_display_name}'")
        else:
            logger.warning(f"Dashboard: adapter_cls '{adapter_cls.__name__}' for '{ex_name}' DOES NOT have get_display_name. Attempting get_name.")
            if hasattr(adapter_cls, 'get_name'):
                try:
                    _resolved_display_name = adapter_cls.get_name()
                    logger.debug(f"Dashboard: Called {adapter_cls.__name__}.get_name() for '{ex_name}'. Result: '{_resolved_display_name}'")
                except Exception as e_gn:
                    logger.error(f"Dashboard: Error calling {adapter_cls.__name__}.get_name() for '{ex_name}': {e_gn}", exc_info=True)
                    _resolved_display_name = ex_name
                    logger.warning(f"Dashboard: Ultimate fallback to ex_name for '{ex_name}' after error in get_name. Result: '{_resolved_display_name}'")
            else:
                logger.error(f"Dashboard: adapter_cls '{adapter_cls.__name__}' for '{ex_name}' also DOES NOT have get_name. This is highly unexpected. Falling back to ex_name.")
                _resolved_display_name = ex_name
                logger.warning(f"Dashboard: Ultimate fallback to ex_name for '{ex_name}' (get_name missing). Result: '{_resolved_display_name}'")
        
        display_name = _resolved_display_name
        logger.debug(f"Dashboard: ----- END Processing ex_name: {ex_name}. Final display_name: '{display_name}' -----")
        total_value = 0.0
        pricing_errors: List[Dict[str, Any]] = []
        processed_ok = False
        currency = "USD"

        if adapter_cls and issubclass(adapter_cls, CcxtBaseAdapter):
            ccxt_cred = next(
                (c for c in all_creds if c.exchange == ex_name), None
            )
            if ccxt_cred and hasattr(adapter_cls, 'get_portfolio_value'):
                try:
                    val_data = adapter_cls.get_portfolio_value(
                        user_id=user_id,
                        portfolio_id=ccxt_cred.portfolio_id,
                        target_currency="USD"
                    )
                    total_value = float(val_data.get('total_value', 0.0))
                    pricing_errors.extend(
                        val_data.get('pricing_errors', [])
                    )
                    currency = val_data.get('currency', 'USD')
                    processed_ok = True
                except Exception as e:
                    logger.error(
                        f"Error CCXT value for {ex_name} (user {user_id}): {e}",
                        exc_info=True
                    )
                    pricing_errors.append({'asset': 'N/A', 'error': f'{e}'})

        elif ex_name == CoinbaseAdapter.get_name():
            cb_creds = [
                c for c in all_creds if c.exchange == CoinbaseAdapter.get_name()
                and c.portfolio_id is not None
            ]
            if not cb_creds:
                logger.info(
                    f"No Coinbase portfolio creds for user {user_id}"
                )

            for cred_item in cb_creds:
                if hasattr(adapter_cls, 'get_portfolio_value'):
                    try:
                        val_data = adapter_cls.get_portfolio_value(
                            user_id=user_id,
                            portfolio_id=cred_item.portfolio_id,
                            currency="USD"
                        )
                        if val_data.get('success'):
                            total_value += float(val_data.get('value', 0.0))
                        else:
                            err_msg = val_data.get(
                                'error', 'Unknown Coinbase error'
                            )
                            logger.warning(
                                f"Could not get Coinbase portfolio value "
                                f"{cred_item.portfolio_id} (user {user_id}): "
                                f"{err_msg}"
                            )
                            asset_id = cred_item.portfolio_name or \
                                cred_item.portfolio_id
                            pricing_errors.append(
                                {'asset': f'{asset_id}', 'error': err_msg}
                            )
                        processed_ok = True
                    except Exception as e:
                        logger.error(
                            f"Error Coinbase portfolio value "
                            f"{cred_item.portfolio_id} (user {user_id}): {e}",
                            exc_info=True
                        )
                        asset_id = cred_item.portfolio_name or \
                            cred_item.portfolio_id
                        pricing_errors.append(
                            {'asset': f'{asset_id}', 'error': f'{e}'}
                        )
        else:
            logger.info(
                f"Adapter for {ex_name} (user {user_id}) not recognized."
            )
            pricing_errors.append({'asset': 'N/A', 'error': 'Not supported'})

        if processed_ok or pricing_errors:
            connected_exchanges_display_data.append({
                'name': ex_name, 
                'display_name': display_name, 
                'value': round(total_value, 2),
                'currency': currency,
                'errors': pricing_errors,
                'logo': f"{ex_name}.svg"
            })

    # Check if the user has credentials for ANY exchange
    has_any_exchange_keys = ExchangeCredentials.query.filter_by(
        user_id=user_id
    ).first() is not None

    return render_template(
        'dashboard.html',
        automations=automations_list,
        exchanges=connected_exchanges_display_data,
        has_any_exchange_keys=has_any_exchange_keys
    )


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
    coinbase_native_form = CoinbaseAPIKeyForm(prefix='cb_native')
    ccxt_form = CcxtApiKeyForm(prefix='ccxt')

    if request.method == 'POST':
        logger.info("--- SETTINGS POST REQUEST ---")  
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
                    is_valid, val_msg = CoinbaseAdapter.validate_api_keys(
                        api_key, api_secret
                    )
                    if not is_valid:
                        raise Exception(f"Coinbase key error: {val_msg}")
                    logger.info("Coinbase API keys validated.")

                    existing = ExchangeCredentials.query.filter_by(
                        user_id=current_user.id, exchange='coinbase'
                    ).first()
                    if existing:
                        existing.api_key = api_key
                        existing.api_secret = existing.encrypt_secret(api_secret)
                        existing.updated_at = db.func.now()
                    else:
                        is_default = not ExchangeCredentials.query.filter_by(
                            user_id=current_user.id, is_default=True
                        ).first()
                        new = ExchangeCredentials(
                            user_id=current_user.id, exchange='coinbase',
                            api_key=api_key, portfolio_name='default',
                            is_default=is_default
                        )
                        new.api_secret = new.encrypt_secret(api_secret)
                        db.session.add(new)
                    db.session.commit()
                    flash('Coinbase API keys saved successfully!', 'success')
                    return redirect(url_for('dashboard.settings'))
                except Exception as e:
                    db.session.rollback()
                    logger.error(f"Error saving Coinbase keys: {e}", exc_info=True)
                    flash(f'Error saving Coinbase API keys: {e}', 'danger')
            else:
                logger.warning(
                    f"Native form validation FAILED: {coinbase_native_form.errors}"
                )
                flash_form_errors(coinbase_native_form)

        elif submitted_form_name == 'ccxt_form':
            exchange_id = request.form.get('exchange')
            logger.info(f"Validating ccxt_form for exchange: {exchange_id}")
            if ccxt_form.validate_on_submit():
                logger.info(f"ccxt_form for {exchange_id} valid.")
                api_key = ccxt_form.api_key.data
                api_secret = ccxt_form.api_secret.data
                password = getattr(ccxt_form, 'password', None)
                password = password.data if password else None
                uid = getattr(ccxt_form, 'uid', None)
                uid = uid.data if uid else None

                adapter_cls = ExchangeRegistry.get_adapter(exchange_id)
                if not adapter_cls:
                    flash(f"Unknown exchange: {exchange_id}", 'danger')
                    return redirect(url_for('dashboard.settings'))

                try:
                    is_valid, val_msg = adapter_cls.validate_api_keys(
                        api_key, api_secret, password=password, uid=uid
                    )
                    if not is_valid:
                        disp_name = adapter_cls.get_display_name()
                        raise Exception(f"{disp_name} key error: {val_msg}")
                    logger.info(f"{adapter_cls.get_display_name()} API keys validated.")

                    existing = ExchangeCredentials.query.filter_by(
                        user_id=current_user.id, exchange=exchange_id
                    ).first()

                    if existing:
                        existing.api_key = api_key
                        existing.api_secret = existing.encrypt_secret(api_secret) # Re-encrypt on update
                        existing.passphrase = password # Update passphrase (stored as is)
                        # uid is not a field in ExchangeCredentials model
                        existing.updated_at = db.func.now()
                        logger.info(f"Updated credentials for {exchange_id}")
                    else:
                        new = ExchangeCredentials(
                            user_id=current_user.id,
                            exchange=exchange_id,
                            api_key=api_key,
                            api_secret=api_secret,  # Pass to __init__ for encryption
                            passphrase=password,    # Pass to __init__ (stored as is)
                            portfolio_name='default'
                        )
                        # uid is not a field in ExchangeCredentials model
                        db.session.add(new)
                        logger.info(f"Added new credentials for {exchange_id}")

                    db.session.commit()
                    disp_name = adapter_cls.get_display_name()
                    flash(f'{disp_name} API keys saved!', 'success')
                    return redirect(url_for('dashboard.settings'))
                except Exception as e:
                    db.session.rollback()
                    disp_name = adapter_cls.get_display_name() if adapter_cls else exchange_id
                    logger.error(f"Error saving {disp_name} keys: {e}", exc_info=True)
                    flash(f'Error saving {disp_name} API keys: {e}', 'danger')
            else:
                logger.warning(
                    f"ccxt_form for {exchange_id} FAILED: {ccxt_form.errors}"
                )
                flash_form_errors(ccxt_form)
        else:
            logger.warning(f"Unknown form_name: '{submitted_form_name}'")
            flash('Invalid form submission.', 'danger')

    user_creds = ExchangeCredentials.query.filter_by(user_id=current_user.id).all()
    exchange_creds_map = {cred.exchange: cred for cred in user_creds}
    logger.info(
        f"Settings GET: exchange_creds_map before passing to template: "
        f"{ {k: v.id for k,v in exchange_creds_map.items()} }"
    )
    available_exchange_adapters = ExchangeRegistry.get_all_adapter_classes()
    logger.info(
        f"Settings GET: Names from available_exchange_adapters: "
        f"{[adapter.get_name() for adapter in available_exchange_adapters]}"
    )

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
    # Using existing local import for request to avoid potential circular issues
    # from flask import request

    exchange_name_to_delete = request.form.get('exchange') # Renamed for clarity
    if not exchange_name_to_delete:
        flash('Exchange not specified for deletion.', 'danger')
        return redirect(url_for('dashboard.settings'))

    # Fetch all credentials for the given exchange and user
    credentials_to_delete = ExchangeCredentials.query.filter_by(
        user_id=current_user.id,
        exchange=exchange_name_to_delete
    ).all()

    if credentials_to_delete:
        for cred in credentials_to_delete:
            db.session.delete(cred)
        db.session.commit()
        flash(f'All API keys for {exchange_name_to_delete.capitalize()} have been deleted successfully!', 'success')
        log_message = "Del %s creds for user %s, exch '%s'."
        logger.info(log_message, len(credentials_to_delete), current_user.id, exchange_name_to_delete)
    else:
        logger.warning(
            f"No API keys found for user {current_user.id}, "
            f"exchange '{exchange_name_to_delete}' to delete."
        )
        flash(f'No API keys found for {exchange_name_to_delete.capitalize()} to delete.', 'warning')

    return redirect(url_for('dashboard.settings'))
