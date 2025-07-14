from datetime import datetime  # Ensure datetime is imported for logging
from flask import (
    Blueprint, render_template, jsonify,
    redirect, url_for, request, flash
)
from flask_security import login_required, current_user
from app.models.automation import Automation
from app.models.webhook import WebhookLog
from app.models.exchange_credentials import ExchangeCredentials
from app.forms.api_key_form import CcxtApiKeyForm
from app.exchanges.ccxt_base_adapter import CcxtBaseAdapter
from app.exchanges.registry import ExchangeRegistry
from typing import List, Dict, Any
from app import db
import logging

from app.models.trading import TradingStrategy # Added for trading strategies
import uuid # Added for generating unique webhook IDs for strategies

# Add the logger that's missing
logger = logging.getLogger(__name__)

def flash_form_errors(form):
    """Flashes form errors to the user."""
    for field, errors in form.errors.items():
        for error in errors:
            field_label = getattr(form, field).label.text
            flash(f"Error in {field_label} field - {error}", 'danger')

bp = Blueprint('dashboard', __name__)

@bp.route('/')
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
            'portfolio_name': 'N/A (linking needs review)',  # Placeholder
            'portfolio_value': None,
            'portfolio_status': 'unknown'  # Placeholder
        }
        # TODO: If automations need to link to CCXT exchanges, adapt the logic here.
        # This might involve looking up ExchangeCredentials by a portfolio_id or another mechanism.
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

        # Count trading strategies associated with this exchange for the current user
        strategy_count = TradingStrategy.query.join(
            ExchangeCredentials,
            TradingStrategy.exchange_credential_id == ExchangeCredentials.id
        ).filter(
            TradingStrategy.user_id == user_id,
            ExchangeCredentials.exchange == ex_name
        ).count()

        if adapter_cls and issubclass(adapter_cls, CcxtBaseAdapter):
            ccxt_cred = next(
                (c for c in all_creds if c.exchange == ex_name), None
            )
            if ccxt_cred and hasattr(adapter_cls, 'get_portfolio_value'):
                try:
                    logger.info(f"Dashboard: START get_portfolio_value for CCXT {ex_name} at {datetime.now()}") # Log start
                    val_data = adapter_cls.get_portfolio_value(
                        user_id=user_id,
                        portfolio_id=ccxt_cred.portfolio_id,
                        target_currency="USD"
                    )
                    logger.info(f"Dashboard: END get_portfolio_value for CCXT {ex_name} at {datetime.now()}. Success: {val_data.get('success', True)}") # Log end
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

        if processed_ok or pricing_errors:
            connected_exchanges_display_data.append({
                'name': ex_name, 
                'display_name': display_name, 
                'value': round(total_value, 2),
                'currency': currency,
                'errors': pricing_errors,
                'logo': f"{ex_name}.svg",
                'investment_strategy_count': strategy_count
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
    ccxt_form = CcxtApiKeyForm(prefix='ccxt')

    if request.method == 'POST':
        logger.info("--- SETTINGS POST REQUEST ---")
        raw_form_data_log = "Raw form data: %s"
        logger.info(raw_form_data_log, request.form.to_dict(flat=False))
        
        submitted_form_name = request.form.get('form_name')
        logger.info("Submitted form_name: '%s'", submitted_form_name)

        if submitted_form_name == 'timezone_form':
            tz_value = request.form.get('timezone')
            logger.info("Updating timezone preference to %s", tz_value)
            try:
                current_user.timezone = tz_value
                db.session.commit()
                flash('Timezone preference saved.', 'success')
                return redirect(url_for('dashboard.settings'))
            except Exception as e:
                logger.error("Error saving timezone: %s", e, exc_info=True)
                db.session.rollback()
                flash(f'Error saving timezone: {e}', 'danger')
        elif submitted_form_name == 'ccxt_form':
            form_exchange = request.form.get('exchange')
            logger.info("Validating ccxt_form for exchange: %s", form_exchange)
            if ccxt_form.validate_on_submit():
                logger.info("ccxt_form valid.")
                api_key = ccxt_form.api_key.data
                api_secret = ccxt_form.api_secret.data
                password_field = getattr(ccxt_form, 'password', None)
                password = password_field.data if password_field else None
                uid_field = getattr(ccxt_form, 'uid', None)
                uid = uid_field.data if uid_field else None

                adapter_cls = ExchangeRegistry.get_adapter(form_exchange)
                if not adapter_cls:
                    flash(f"Unknown exchange: {form_exchange}", 'danger')
                    return redirect(url_for('dashboard.settings'))

                disp_name_try = "Unknown Exchange"
                try:
                    disp_name_try = adapter_cls.get_display_name()
                    is_valid, val_msg = adapter_cls.validate_api_keys(
                        api_key, api_secret, password=password, uid=uid
                    )
                    if not is_valid:
                        raise Exception(f"{disp_name_try} key error: {val_msg}")
                    logger.info("%s API keys validated.", disp_name_try)

                    existing = ExchangeCredentials.query.filter_by(
                        user_id=current_user.id, exchange=form_exchange
                    ).first()

                    if existing:
                        existing.api_key = api_key
                        existing.api_secret = existing.encrypt_secret(api_secret)
                        existing.passphrase = password
                        existing.updated_at = db.func.now()
                        logger.info("Updated credentials for %s", form_exchange)
                    else:
                        new = ExchangeCredentials(
                            user_id=current_user.id,
                            exchange=form_exchange,
                            api_key=api_key,
                            api_secret=api_secret,
                            passphrase=password,
                            portfolio_name='default' # Ensure this is appropriate
                        )
                        db.session.add(new)
                        logger.info("Added new credentials for %s", form_exchange)

                    db.session.commit()
                    flash(f'{disp_name_try} API keys saved!', 'success')
                    return redirect(url_for('dashboard.settings'))
                except Exception as e:
                    db.session.rollback()
                    # Use disp_name_try if adapter_cls was resolved, else fallback
                    disp_name_catch = disp_name_try if adapter_cls else form_exchange
                    logger.error("Error saving %s keys: %s", disp_name_catch, e, exc_info=True)
                    flash(f'Error saving {disp_name_catch} API keys: {e}', 'danger')
            else:
                logger.warning("ccxt_form FAILED: %s", ccxt_form.errors)
                flash_form_errors(ccxt_form)
        else:
            logger.warning("Unknown form_name: '%s'", submitted_form_name)
            flash('Invalid form submission.', 'danger')
        # Fall through to GET logic if POST doesn't redirect

    # --- GET Request Logic (or fall-through from POST) ---
    user_id = current_user.id
    user_creds = ExchangeCredentials.query.filter_by(user_id=user_id).all()
    exchange_creds_map = {cred.exchange: cred for cred in user_creds}
    
    log_creds_map_str = "Settings GET: exchange_creds_map: %s"
    logger.info(log_creds_map_str, {k: v.id for k, v in exchange_creds_map.items()})

    # Expose only user-facing adapters in Settings (hide legacy technical ids)
    available_exchange_adapters = [
        cls for cls in ExchangeRegistry.get_all_adapter_classes()
        if not cls.get_name().endswith("-ccxt")
    ]
    log_adapters_str = "Settings GET: Available adapter names: %s"
    logger.info(log_adapters_str, [adapter.get_name() for adapter in available_exchange_adapters])

    connected_exchanges_display_data: List[Dict[str, Any]] = []
    unique_exchange_names_with_creds = sorted(list(set(cred.exchange for cred in user_creds)))

    for ex_name_get in unique_exchange_names_with_creds:
        adapter_cls_get = ExchangeRegistry.get_adapter(ex_name_get)
        display_name_get = ex_name_get
        logo_filename_get = f"{ex_name_get.lower()}.svg"

        if adapter_cls_get:
            try:
                display_name_get = adapter_cls_get.get_display_name()
            except AttributeError:
                try:
                    display_name_get = adapter_cls_get.get_name()
                except AttributeError:
                    logger.warning(
                        "Settings: Adapter for %s has neither get_display_name nor get_name.", ex_name_get
                    )
            except Exception as e_disp_name_get:
                logger.error("Settings: Error getting display name for %s: %s", ex_name_get, e_disp_name_get)
            
            if hasattr(adapter_cls_get, 'get_logo_filename'):
                try:
                    logo_filename_get = adapter_cls_get.get_logo_filename()
                except Exception as e_logo_get:
                    logger.warning(
                        "Settings: Error getting logo for %s from adapter: %s. Using default.",
                        ex_name_get, e_logo_get
                    )
        
        connected_exchanges_display_data.append({
            'name': ex_name_get,
            'display_name': display_name_get,
            'logo': logo_filename_get,
        })

    from zoneinfo import available_timezones
    timezones_list = sorted(available_timezones())

    return render_template(
        'settings.html',
        ccxt_form=ccxt_form,
        connected_exchanges=connected_exchanges_display_data,
        user_creds_map=exchange_creds_map,
        available_exchange_adapters=available_exchange_adapters,
        user=current_user,
        timezones=timezones_list
    )


# ... (rest of the code remains the same)

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
        capitalized_exchange_name = exchange_name_to_delete.capitalize()
        message = (
            f"All API keys for {capitalized_exchange_name} "
            "have been deleted successfully!"
        )
        flash(message, 'success')
        log_message = "Del %s creds for user %s, exch '%s'."
        logger.info(
            log_message,
            len(credentials_to_delete),
            current_user.id,
            exchange_name_to_delete
        )
    else:
        warning_msg_user = f"No API keys found for user {current_user.id}, "
        warning_msg_exchange = f"exchange '{exchange_name_to_delete}' to delete."
        logger.warning(warning_msg_user + warning_msg_exchange)
        message = f'No API keys found for {exchange_name_to_delete.capitalize()} to delete.'
        flash(message, 'warning')

    return redirect(url_for('dashboard.settings'))

