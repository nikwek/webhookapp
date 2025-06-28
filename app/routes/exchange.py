# app/routes/exchange.py

from flask import Blueprint, render_template, request, flash, redirect, url_for, current_app
from flask_security import login_required, current_user
from app.models.exchange_credentials import ExchangeCredentials
from app.exchanges.ccxt_base_adapter import CcxtBaseAdapter # Needed for issubclass check
from app.exchanges.registry import ExchangeRegistry
from app import db
from app.models.trading import TradingStrategy
import uuid
import logging
import json
from collections import defaultdict
from decimal import Decimal, InvalidOperation
from app.services import allocation_service


logger = logging.getLogger(__name__)

exchange_bp = Blueprint('exchange', __name__, url_prefix='/exchange')

@exchange_bp.route('/<string:exchange_id>') # Path adjusted due to url_prefix
@login_required
def view_exchange(exchange_id: str):
    """Render the specific exchange page."""
    user_id = current_user.id
    all_creds = ExchangeCredentials.query.filter_by(user_id=user_id).all()
    
    # Get all connected exchanges for the dropdown
    connected_exchanges_for_dropdown = []
    unique_exchange_ids = sorted(list(set(cred.exchange for cred in all_creds)))

    for ex_id in unique_exchange_ids:
        adapter_cls_dropdown = ExchangeRegistry.get_adapter(ex_id)
        display_name_dropdown = ex_id # Default
        if adapter_cls_dropdown:
            try:
                if hasattr(adapter_cls_dropdown, 'get_display_name'):
                    display_name_dropdown = adapter_cls_dropdown.get_display_name()
                elif hasattr(adapter_cls_dropdown, 'get_name'):
                    display_name_dropdown = adapter_cls_dropdown.get_name()
            except Exception as e:
                logger.error(f"Error getting display name for {ex_id} in dropdown: {e}")
        connected_exchanges_for_dropdown.append({
            'id': ex_id,
            'display_name': display_name_dropdown
        })

    # Get data for the currently selected exchange
    current_exchange_adapter_cls = ExchangeRegistry.get_adapter(exchange_id)
    current_exchange_display_name = exchange_id # Default
    current_exchange_data = {
        'total_value': 0.0,
        'balances': [],
        'currency': 'USD',
        'pricing_errors': [],
        'success': False,
        'error_message': None
    }

    if not current_exchange_adapter_cls:
        logger.warning(f"No adapter found for selected exchange: {exchange_id}, user: {user_id}")
        flash(f"Could not load data for exchange '{exchange_id}'. Adapter not found.", "danger")
        current_exchange_data['error_message'] = f"Adapter for '{exchange_id}' not found."
        return render_template(
            'exchange.html',
            current_exchange_id=exchange_id,
            current_exchange_display_name=current_exchange_display_name,
            current_exchange_data=current_exchange_data,
            all_connected_exchanges=connected_exchanges_for_dropdown,
            title=f"{current_exchange_display_name} Details"
        )

    try:
        if hasattr(current_exchange_adapter_cls, 'get_display_name'):
            current_exchange_display_name = current_exchange_adapter_cls.get_display_name()
        elif hasattr(current_exchange_adapter_cls, 'get_name'):
            current_exchange_display_name = current_exchange_adapter_cls.get_name()
    except Exception as e:
        logger.error(f"Error getting display name for current exchange {exchange_id}: {e}")

    cred = None # Initialize cred to None
    if issubclass(current_exchange_adapter_cls, CcxtBaseAdapter):
        cred = next((c for c in all_creds if c.exchange == exchange_id), None)
        if cred and hasattr(current_exchange_adapter_cls, 'get_portfolio_value'):
            try:
                portfolio_data = current_exchange_adapter_cls.get_portfolio_value(
                    user_id=user_id,
                    portfolio_id=cred.portfolio_id, 
                    target_currency="USD"
                )
                current_exchange_data['total_value'] = float(portfolio_data.get('total_value', 0.0))
                current_exchange_data['balances'] = portfolio_data.get('balances', [])
                current_exchange_data['currency'] = portfolio_data.get('currency', 'USD')
                current_exchange_data['pricing_errors'] = portfolio_data.get('pricing_errors', [])
                current_exchange_data['success'] = portfolio_data.get('success', True)
                if not current_exchange_data['success']:
                     current_exchange_data['error_message'] = portfolio_data.get('error', 'Failed to retrieve portfolio data.')
                current_exchange_data['current_credential_id'] = cred.id # Pass credential ID
            except Exception as e:
                logger.error(f"Error getting portfolio value for {exchange_id} (user {user_id}): {e}", exc_info=True)
                flash(f"Error retrieving data for {current_exchange_display_name}: {e}", "danger")
                current_exchange_data['error_message'] = f"An error occurred: {e}"
                current_exchange_data['pricing_errors'].append({'asset': 'N/A', 'error': str(e)})
        elif not cred:
            logger.warning(f"No credentials found for {exchange_id} for user {user_id} to fetch portfolio.")
            flash(f"Credentials for {current_exchange_display_name} not found.", "warning")
            current_exchange_data['error_message'] = f"Credentials for {current_exchange_display_name} not found."
            current_exchange_data['current_credential_id'] = None
        else: 
            logger.error(f"Adapter {exchange_id} is CCXT but has no get_portfolio_value method.")
            flash(f"Cannot retrieve portfolio for {current_exchange_display_name}.", "danger")
            current_exchange_data['error_message'] = f"Cannot retrieve portfolio for {current_exchange_display_name} (internal error)."

    # Fetch trading strategies for the current user and exchange credential
    user_strategies = []
    # 'cred' is defined within the CcxtBaseAdapter check block, need to ensure it's accessible
    # Let's re-fetch or ensure 'cred' is defined in this scope if not already.
    # For now, assuming 'cred' might be None if not CCXT or no cred found.
    
    # Re-evaluate where 'cred' is defined. It's inside the 'if issubclass...' block.
    # We need 'cred' to exist to fetch strategies. Let's find the credential first.
    
    final_cred = next((c for c in all_creds if c.exchange == exchange_id), None)

    if final_cred:
        user_strategies = TradingStrategy.query.filter_by(
            user_id=user_id,
            exchange_credential_id=final_cred.id
        ).order_by(TradingStrategy.name).all()

    # Calculate total allocated amounts for each asset across all strategies for this exchange credential
    total_allocated_by_asset = defaultdict(Decimal)
    if user_strategies: # user_strategies is already filtered for the current exchange_credential_id
        for strategy in user_strategies:
            try:
                if strategy.base_asset_symbol and strategy.allocated_base_asset_quantity is not None:
                    total_allocated_by_asset[strategy.base_asset_symbol] += Decimal(str(strategy.allocated_base_asset_quantity))
                if strategy.quote_asset_symbol and strategy.allocated_quote_asset_quantity is not None:
                    total_allocated_by_asset[strategy.quote_asset_symbol] += Decimal(str(strategy.allocated_quote_asset_quantity))
            except InvalidOperation as e_alloc:
                logger.error(f"Invalid decimal value for allocated quantity in strategy {strategy.id} ('{strategy.name}'). Asset: {strategy.base_asset_symbol} or {strategy.quote_asset_symbol}. Error: {e_alloc}. Skipping this allocation.")

    # Update main account balances with allocated and unallocated amounts
    if 'balances' in current_exchange_data and isinstance(current_exchange_data['balances'], list):
        for asset_balance_item in current_exchange_data['balances']:
            asset_symbol = asset_balance_item.get('asset')
            if not asset_symbol: # Should not happen with valid exchange data
                asset_balance_item['total_allocated'] = 0.0
                asset_balance_item['unallocated'] = float(asset_balance_item.get('total', 0.0))
                logger.warning(f"Asset item found without an 'asset' symbol in balances for {exchange_id}. Data: {asset_balance_item}")
                continue

            try:
                total_on_exchange_str = str(asset_balance_item.get('total', '0.0'))
                total_on_exchange = Decimal(total_on_exchange_str)
            except InvalidOperation as e_bal:
                logger.error(f"Invalid 'total' value '{asset_balance_item.get('total')}' for asset {asset_symbol} from exchange {exchange_id}. Error: {e_bal}. Treating as 0.")
                total_on_exchange = Decimal('0.0')

            allocated_for_this_asset = total_allocated_by_asset.get(asset_symbol, Decimal('0.0'))
            unallocated_amount = total_on_exchange - allocated_for_this_asset
            
            asset_balance_item['total_allocated'] = float(allocated_for_this_asset)
            asset_balance_item['unallocated'] = float(max(Decimal('0.0'), unallocated_amount)) # Ensure unallocated is not negative
    elif current_exchange_data.get('balances') is None:
        current_exchange_data['balances'] = [] # Ensure it's an iterable for the template if it was None

    # Prepare strategy data for JavaScript
    # Prepare main account assets data for JavaScript
    main_account_assets_json_data = []
    # Use 'cred' which is defined in the scope above for CCXT adapters
    # Ensure 'cred' is defined and not None before trying to use it.
    # 'cred' would be None if no matching credential was found or if not a CCXT adapter.
    if current_exchange_data.get('balances') and final_cred:
        for asset_balance_item in current_exchange_data['balances']:
            asset_symbol = asset_balance_item.get('asset')
            # Use 'unallocated' as it represents the freely transferable amount from the main account
            available_balance = asset_balance_item.get('unallocated', 0.0) 
            if asset_symbol and float(available_balance) > 0: # Only include assets with some balance
                main_account_assets_json_data.append({
                    "id": f"main::{final_cred.id}::{asset_symbol}", # Unique ID for JS
                    "name": f"Main Account - {asset_symbol}",
                    "asset_symbol": asset_symbol,
                    "exchange_credential_id": final_cred.id,
                    "available_balance": float(available_balance)
                })

    # Prepare strategy data for JavaScript
    strategies_json_data = [
        {
            "id": strategy.id,
            "name": strategy.name,
            "exchange_credential_id": strategy.exchange_credential_id,
            "base_asset_symbol": strategy.base_asset_symbol,
            "quote_asset_symbol": strategy.quote_asset_symbol,
            "allocated_base_asset_quantity": float(strategy.allocated_base_asset_quantity or 0),
            "allocated_quote_asset_quantity": float(strategy.allocated_quote_asset_quantity or 0)
        }
        for strategy in user_strategies
    ]

    return render_template(
        'exchange.html',
        current_exchange_id=exchange_id,
        current_exchange_display_name=current_exchange_display_name,
        current_exchange_data=current_exchange_data,
        all_connected_exchanges=connected_exchanges_for_dropdown,
        user_strategies=user_strategies,  # Pass strategies to template
        strategies_json_data=strategies_json_data,
        main_account_assets_json_data=main_account_assets_json_data,
        current_credential_id=cred.id if cred else None, # Pass JSON-ready strategy data
        title=f"{current_exchange_display_name} Details"
    )


@exchange_bp.route('/<string:exchange_id>/strategy/create', methods=['POST'])
@login_required
def create_trading_strategy(exchange_id: str):
    """Handles the creation of a new trading strategy."""
    if request.method == 'POST':
        strategy_name = request.form.get('strategy_name')
        trading_pair = request.form.get('trading_pair') # e.g., BTC/USDT

        if not strategy_name or not trading_pair:
            flash('Strategy Name and Trading Pair are required.', 'danger')
            return redirect(url_for('exchange.view_exchange', exchange_id=exchange_id))

        # Basic validation for trading_pair format (e.g., SYMBOL/SYMBOL)
        # More robust validation (e.g., checking if pair exists on exchange) can be added later
        if '/' not in trading_pair or len(trading_pair.split('/')) != 2:
            flash('Invalid Trading Pair format. Please use SYMBOL/SYMBOL (e.g., BTC/USDT).', 'danger')
            return redirect(url_for('exchange.view_exchange', exchange_id=exchange_id))

        base_asset_symbol, quote_asset_symbol = trading_pair.upper().split('/')

        # Find the ExchangeCredentials for the user and this exchange_id
        # Assuming one credential per user per exchange for simplicity here.
        # If multiple credentials can exist, logic to select one would be needed.
        credential = ExchangeCredentials.query.filter_by(
            user_id=current_user.id,
            exchange=exchange_id # The exchange_id from the route (e.g., 'binance', 'coinbase')
        ).first()

        if not credential:
            flash(f'No active credentials found for {exchange_id.capitalize()} to associate the strategy with.', 'danger')
            logger.warning(f"User {current_user.id} tried to create strategy for {exchange_id} but has no credentials.")
            return redirect(url_for('exchange.view_exchange', exchange_id=exchange_id))

        try:
            new_strategy = TradingStrategy(
                user_id=current_user.id,
                name=strategy_name,
                exchange_credential_id=credential.id,
                trading_pair=trading_pair.upper(),
                base_asset_symbol=base_asset_symbol,
                quote_asset_symbol=quote_asset_symbol,
                webhook_id=str(uuid.uuid4()) # Generate a unique webhook_id
            )

            # Generate a default webhook template
            ticker_format = new_strategy.trading_pair.replace('/', '-')
            default_webhook_template_dict = {
                "action": "{{strategy.action}}",
                "ticker": ticker_format,
                "timestamp": "{{timenow}}",
                "message": "Optional message"
            }
            new_strategy.webhook_template = json.dumps(default_webhook_template_dict, indent=4)

            db.session.add(new_strategy)
            db.session.commit()
            flash(f'Trading strategy "{strategy_name}" created successfully!', 'success')
            logger.info(f"User {current_user.id} created new strategy '{strategy_name}' ({new_strategy.id}) for exchange {exchange_id} (cred_id: {credential.id})")
        except Exception as e:
            db.session.rollback()
            logger.error(f"Error creating trading strategy for user {current_user.id} on exchange {exchange_id}: {e}", exc_info=True)
            flash(f'Error creating trading strategy: {str(e)}', 'danger')

        return redirect(url_for('exchange.view_exchange', exchange_id=exchange_id))
    
    # Should not be reached if only POST is allowed by the route decorator,
    # but as a fallback:
    return redirect(url_for('exchange.view_exchange', exchange_id=exchange_id))


@exchange_bp.route('/<string:exchange_id>/transfer', methods=['POST'])
@login_required
def transfer_assets(exchange_id: str):
    user_id = current_user.id
    source_account_id_str = request.form.get('source_account_id')
    destination_account_id_str = request.form.get('destination_account_id')
    asset_symbol_from_form = request.form.get('asset_symbol')
    amount_str = request.form.get('amount')

    logger.info(f"Transfer attempt by user {user_id} on exchange {exchange_id}: Source: {source_account_id_str}, Dest: {destination_account_id_str}, Asset: {asset_symbol_from_form}, Amount: {amount_str}")

    if not all([source_account_id_str, destination_account_id_str, asset_symbol_from_form, amount_str]):
        flash('Missing required fields for transfer.', 'danger')
        return redirect(url_for('exchange.view_exchange', exchange_id=exchange_id))

    try:
        amount = Decimal(amount_str)
        if amount <= Decimal('0'): # Amount must be positive
            # Using Decimal('0') for comparison with a Decimal type
            raise ValueError("Transfer amount must be positive.")
    except InvalidOperation:
        flash('Invalid transfer amount format. Please enter a valid number.', 'danger')
        return redirect(url_for('exchange.view_exchange', exchange_id=exchange_id))
    except ValueError as e: # Catches the specific ValueError for non-positive amount
        flash(str(e), 'danger')
        return redirect(url_for('exchange.view_exchange', exchange_id=exchange_id))

    try:
        success, message = allocation_service.execute_internal_asset_transfer(
            user_id=user_id,
            source_identifier=source_account_id_str,
            destination_identifier=destination_account_id_str,
            asset_symbol_to_transfer=asset_symbol_from_form,
            amount=amount
        )
        if success:
            flash(message, 'success')
        else:
            flash(message, 'danger')
    except allocation_service.AllocationError as e:
        logger.warning(f"AllocationError during transfer: {e}. User: {user_id}, Source: {source_account_id_str}, Dest: {destination_account_id_str}, Asset: {asset_symbol_from_form}, Amount: {amount}")
        flash(str(e), 'danger')
    except ValueError as e: # Catch potential errors from int() conversion within service or here
        logger.error(f"Error processing transfer: {e}. Source: {source_account_id_str}, Dest: {destination_account_id_str}, Asset: {asset_symbol_from_form}, Amount: {amount_str}")
        flash(f'Invalid source or destination format for transfer: {e}', 'danger')
    except Exception as e:
        logger.error(f"Unexpected error during transfer: {e}", exc_info=True)
        flash('An unexpected error occurred. Please try again.', 'danger')
    
    return redirect(url_for('exchange.view_exchange', exchange_id=exchange_id))


@exchange_bp.route('/<string:exchange_id>/strategy/<int:strategy_id>')
@login_required
def view_strategy_details(exchange_id: str, strategy_id: int):
    """Render the specific trading strategy details page."""
    strategy = TradingStrategy.query.filter_by(id=strategy_id, user_id=current_user.id).first_or_404()

    # Fetch exchange display name for breadcrumbs and titles
    current_exchange_adapter_cls = ExchangeRegistry.get_adapter(exchange_id)
    current_exchange_display_name = exchange_id  # Default
    if current_exchange_adapter_cls:
        try:
            if hasattr(current_exchange_adapter_cls, 'get_display_name'):
                current_exchange_display_name = current_exchange_adapter_cls.get_display_name()
            elif hasattr(current_exchange_adapter_cls, 'get_name'): # Fallback
                current_exchange_display_name = current_exchange_adapter_cls.get_name()
        except Exception as e:
            logger.error(f"Error getting display name for {exchange_id} on strategy page: {e}")

    # Get the base application URL from config, fallback to request URL
    # Use .get() to avoid KeyError if not set, and provide a sensible fallback.
    application_url = current_app.config.get('APPLICATION_URL', request.host_url)

    return render_template(
        'strategy_details.html',
        strategy=strategy,
        exchange_id=exchange_id,
        current_exchange_display_name=current_exchange_display_name,
        application_url=application_url,
        title=f"Strategy: {strategy.name}"
    )


@exchange_bp.route('/<string:exchange_id>/strategy/<int:strategy_id>/delete', methods=['POST'])
@login_required
def delete_trading_strategy(exchange_id: str, strategy_id: int):
    strategy = TradingStrategy.query.get_or_404(strategy_id)
    
    # Verify that the strategy belongs to the current user and the correct exchange
    if strategy.exchange_credential.user_id != current_user.id or strategy.exchange_credential.exchange != exchange_id:
        flash('Unauthorized access to strategy.', 'danger')
        return redirect(url_for('dashboard.dashboard'))

    try:
        # By deleting the strategy, its previously allocated assets are now considered unallocated.
        strategy_name = strategy.name # Store name before deletion for the flash message
        db.session.delete(strategy)
        db.session.commit()
        flash(f'Successfully deleted strategy "{strategy_name}". Its assets are now part of your unallocated balance.', 'success')
    except Exception as e:
        db.session.rollback()
        logger.error(f"Error deleting strategy {strategy.id}: {e}")
        flash('An error occurred while deleting the strategy. Please try again.', 'danger')

    return redirect(url_for('exchange.view_exchange', exchange_id=exchange_id))


@exchange_bp.route('/<string:exchange_id>/strategy/<int:strategy_id>/edit_name', methods=['POST'])
@login_required
def edit_strategy_name(exchange_id: str, strategy_id: int):
    strategy = TradingStrategy.query.get_or_404(strategy_id)

    # Verify that the strategy belongs to the current user and the correct exchange credential
    if not strategy.exchange_credential or strategy.exchange_credential.user_id != current_user.id or strategy.exchange_credential.exchange != exchange_id:
        flash('Unauthorized to edit this strategy.', 'danger')
        return redirect(url_for('dashboard.dashboard'))

    new_name = request.form.get('new_strategy_name')
    if not new_name or len(new_name.strip()) == 0:
        flash('Strategy name cannot be empty.', 'danger')
        return redirect(url_for('exchange.view_strategy_details', exchange_id=exchange_id, strategy_id=strategy_id))
    
    if len(new_name) > 100: # Assuming a max length for strategy name, adjust if necessary
        flash('Strategy name is too long (maximum 100 characters).', 'danger')
        return redirect(url_for('exchange.view_strategy_details', exchange_id=exchange_id, strategy_id=strategy_id))

    # Check if another strategy with the same name already exists for this user and exchange credential
    existing_strategy_with_name = TradingStrategy.query.filter(
        TradingStrategy.user_id == current_user.id,
        TradingStrategy.exchange_credential_id == strategy.exchange_credential_id,
        TradingStrategy.name == new_name.strip(),
        TradingStrategy.id != strategy_id # Exclude the current strategy itself
    ).first()

    if existing_strategy_with_name:
        flash(f'Another strategy with the name "{new_name.strip()}" already exists for this exchange account.', 'danger')
        return redirect(url_for('exchange.view_strategy_details', exchange_id=exchange_id, strategy_id=strategy_id))

    try:
        original_name = strategy.name
        strategy.name = new_name.strip()
        db.session.commit()
        flash(f'Successfully updated strategy name from "{original_name}" to "{strategy.name}".', 'success')
        logger.info(f"User {current_user.id} updated strategy name for strategy {strategy.id} from '{original_name}' to '{strategy.name}' on exchange {exchange_id}.")
    except Exception as e:
        db.session.rollback()
        logger.error(f"Error updating strategy name for strategy {strategy.id}: {e}", exc_info=True)
        flash('An error occurred while updating the strategy name. Please try again.', 'danger')

    return redirect(url_for('exchange.view_strategy_details', exchange_id=exchange_id, strategy_id=strategy_id))
