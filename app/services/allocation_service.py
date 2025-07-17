# app/services/allocation_service.py

from decimal import Decimal, InvalidOperation
from collections import defaultdict
from app import db
from app.models.trading import TradingStrategy, AssetTransferLog, StrategyValueHistory
from app.models.exchange_credentials import ExchangeCredentials
from app.exchanges.registry import ExchangeRegistry
import logging
from datetime import datetime, timedelta
from app.services.strategy_value_service import _value_usd

logger = logging.getLogger(__name__)

def _snapshot_strategy_value(strategy: TradingStrategy, *, ts: datetime | None = None) -> None:
    """Insert a StrategyValueHistory row reflecting *strategy*'s current value.

    *ts* allows the caller to supply an explicit timestamp so we can guarantee a
    strict ordering relative to a just-logged ``AssetTransferLog``.  When *ts*
    is *None* the current UTC time is used.
    """
    try:
        val = _value_usd(strategy)
        snap_ts = ts or datetime.utcnow()
        db.session.add(
            StrategyValueHistory(
                strategy_id=strategy.id,
                timestamp=snap_ts,
                value_usd=val,
                base_asset_quantity_snapshot=strategy.allocated_base_asset_quantity,
                quote_asset_quantity_snapshot=strategy.allocated_quote_asset_quantity,
            )
        )
    except Exception as exc:
        # Do not fail the transfer if snapshotting fails – just log.
        logger.error("Failed to snapshot strategy %s after transfer: %s", strategy.id, exc)

class AllocationError(Exception):
    """Custom exception for allocation errors."""
    pass

def get_unallocated_balance(user_id: int, credential_id: int, asset_symbol: str) -> Decimal:
    """Helper function to calculate unallocated balance for a specific asset on an exchange credential."""
    credential = ExchangeCredentials.query.filter_by(id=credential_id, user_id=user_id).first()
    if not credential:
        raise AllocationError(f"Exchange credential with ID {credential_id} not found for user {user_id}.")

    # 1. Sum all allocations for this asset across all strategies using this credential
    total_allocated_for_asset = Decimal('0')
    strategies_on_credential = TradingStrategy.query.filter_by(
        user_id=user_id,
        exchange_credential_id=credential.id
    ).all()

    for s in strategies_on_credential:
        if s.base_asset_symbol == asset_symbol:
            total_allocated_for_asset += s.allocated_base_asset_quantity
        if s.quote_asset_symbol == asset_symbol:
            total_allocated_for_asset += s.allocated_quote_asset_quantity

    # 2. Fetch total live balance from the exchange
    live_total_balance_for_asset = Decimal('0')
    adapter_cls = ExchangeRegistry.get_adapter(credential.exchange)
    if not adapter_cls:
        raise AllocationError(f"No adapter found for exchange: {credential.exchange}")

    try:
        # Assuming get_portfolio_value is the method that returns balances
        # This might need adjustment based on actual adapter capabilities
        portfolio_data = adapter_cls.get_portfolio_value(
            user_id=user_id, 
            portfolio_id=credential.portfolio_id, # portfolio_id might not always be used by adapter
            target_currency="USD" # target_currency might not be relevant for raw balances
        )
        if portfolio_data.get('success', False):
            for balance_item in portfolio_data.get('balances', []):
                if balance_item.get('asset') == asset_symbol:
                    live_total_balance_for_asset = Decimal(str(balance_item.get('total', '0')))
                    break
        else:
            error_msg = portfolio_data.get('error', 'Failed to retrieve portfolio data from exchange.')
            logger.error(f"Failed to fetch balance for {asset_symbol} from {credential.exchange}: {error_msg}")
            raise AllocationError(f"Could not verify balance on {credential.exchange}: {error_msg}")
    except Exception as e:
        logger.error(f"Exception fetching balance for {asset_symbol} from {credential.exchange}: {e}", exc_info=True)
        raise AllocationError(f"Error communicating with {credential.exchange} to verify balance: {str(e)}")

    unallocated = live_total_balance_for_asset - total_allocated_for_asset
    return max(Decimal('0'), unallocated) # Ensure it's not negative due to sync issues or errors


def execute_internal_asset_transfer(user_id: int, source_identifier: str, destination_identifier: str, asset_symbol_to_transfer: str, amount: Decimal):
    """
    Executes an internal transfer of assets between a user's main account and their trading strategies,
    or between two trading strategies.

    The function handles three types of transfers:
    1. Main Account -> Trading Strategy
    2. Trading Strategy -> Main Account
    3. Trading Strategy -> Trading Strategy

    Identifiers are used to specify the source and destination:
    - Main Account: 'main::{credential_id}::{asset_symbol}' (e.g., 'main::11::BTC')
    - Trading Strategy: 'strategy::{strategy_id}' (e.g., 'strategy::3')

    Args:
        user_id (int): The ID of the user performing the transfer.
        source_identifier (str): The identifier for the source account/strategy.
        destination_identifier (str): The identifier for the destination account/strategy.
        asset_symbol_to_transfer (str): The symbol of the asset being transferred (e.g., 'BTC').
        amount (Decimal): The amount of the asset to transfer.

    Returns:
        tuple[bool, str]: A tuple containing a boolean indicating success and a message.

    Raises:
        AllocationError: If the transfer is invalid for any reason (e.g., insufficient funds,
                         invalid identifiers, mismatched assets).
    """
    logger.debug(f"Executing transfer: user_id={user_id}, source='{source_identifier}', dest='{destination_identifier}', asset='{asset_symbol_to_transfer}', amount={amount}")
    source_parts = source_identifier.split('::')
    dest_parts = destination_identifier.split('::')

    # --- Validate and parse source ---
    source_type, source_id = None, None
    if len(source_parts) == 3 and source_parts[0] == 'main':
        source_type, source_credential_id_str, source_asset_symbol = source_parts
        source_id = int(source_credential_id_str)
        # The asset in the identifier must match the asset being transferred.
        if source_asset_symbol.upper() != asset_symbol_to_transfer.upper():
            raise AllocationError(f"Asset symbol in source identifier ('{source_asset_symbol}') does not match asset being transferred ('{asset_symbol_to_transfer}').")
    elif (len(source_parts) == 2 or len(source_parts) == 3) and source_parts[0] == 'strategy':
        source_type = source_parts[0]  # 'strategy'
        source_strategy_id_str = source_parts[1] # The actual ID string
        source_id = int(source_strategy_id_str)
        # The third part (source_parts[2]), if present, is an asset symbol.
        # asset_symbol_to_transfer is the definitive asset for the transaction.
    else:
        raise AllocationError(f"Invalid source identifier format: '{source_identifier}'")

    # --- Validate and parse destination ---
    dest_type, dest_id = None, None
    if len(dest_parts) == 3 and dest_parts[0] == 'main':
        dest_type, dest_credential_id_str, dest_asset_symbol = dest_parts
        dest_id = int(dest_credential_id_str)
        # The asset in the identifier must match the asset being transferred.
        if dest_asset_symbol.upper() != asset_symbol_to_transfer.upper():
            raise AllocationError(f"Asset symbol in destination identifier ('{dest_asset_symbol}') does not match asset being transferred ('{asset_symbol_to_transfer}').")
    elif (len(dest_parts) == 2 or len(dest_parts) == 3) and dest_parts[0] == 'strategy':
        dest_type = dest_parts[0]  # 'strategy'
        dest_strategy_id_str = dest_parts[1] # The actual ID string
        dest_id = int(dest_strategy_id_str)
        # The third part (dest_parts[2]), if present, is an asset symbol.
    else:
        raise AllocationError(f"Invalid destination identifier format: '{destination_identifier}'")


    try:
        # --- Case 1: Main Account -> Trading Strategy --- 
        if source_type == 'main' and dest_type == 'strategy':
            source_credential_id = source_id
            destination_strategy_id = dest_id

            if amount <= Decimal('0'):
                raise AllocationError("Transfer amount must be positive.")

            strategy = TradingStrategy.query.filter_by(id=destination_strategy_id, user_id=user_id).first()
            if not strategy:
                raise AllocationError(f"Strategy with ID {destination_strategy_id} not found for user {user_id}.")

            if strategy.exchange_credential_id != source_credential_id:
                raise AllocationError(f"Strategy's associated credential ID ({strategy.exchange_credential_id}) does not match the source main account's credential ID ({source_credential_id}).")

            if asset_symbol_to_transfer != strategy.base_asset_symbol and asset_symbol_to_transfer != strategy.quote_asset_symbol:
                raise AllocationError(f"Asset {asset_symbol_to_transfer} is not part of strategy {strategy.name}'s trading pair ({strategy.trading_pair}).")

            unallocated_balance = get_unallocated_balance(user_id, source_credential_id, asset_symbol_to_transfer)
            if amount > unallocated_balance:
                raise AllocationError(
                    f"Cannot transfer {amount} {asset_symbol_to_transfer}. "
                    f"Unallocated balance is {unallocated_balance:.8f} {asset_symbol_to_transfer} on the specified main account."
                )

            if asset_symbol_to_transfer == strategy.base_asset_symbol:
                current_base_allocated = strategy.allocated_base_asset_quantity if strategy.allocated_base_asset_quantity is not None else Decimal('0.0')
                strategy.allocated_base_asset_quantity = current_base_allocated + amount
            elif asset_symbol_to_transfer == strategy.quote_asset_symbol:
                current_quote_allocated = strategy.allocated_quote_asset_quantity if strategy.allocated_quote_asset_quantity is not None else Decimal('0.0')
                strategy.allocated_quote_asset_quantity = current_quote_allocated + amount
            
            db.session.add(strategy)

            # Record transfer log with an explicit timestamp so we can guarantee ordering
            now_ts = datetime.utcnow()
            log_entry = AssetTransferLog(
                user_id=user_id,
                timestamp=now_ts,
                source_identifier=source_identifier,
                destination_identifier=destination_identifier,
                asset_symbol=asset_symbol_to_transfer,
                amount=amount,
                strategy_id_from=None,
                strategy_name_from=None,
                strategy_id_to=destination_strategy_id,
                strategy_name_to=strategy.name,
            )
            db.session.add(log_entry)
            # Snapshot strategy *after* logging the transfer. Use a timestamp *after* the transfer
            # by a micro-second to maintain strict ordering.
            _snapshot_strategy_value(strategy, ts=now_ts + timedelta(microseconds=1))
            db.session.commit()
            logger.info(f"Successfully transferred {amount} {asset_symbol_to_transfer} from main account (cred ID: {source_credential_id}) to strategy {strategy.name} (ID: {destination_strategy_id}) for user {user_id}.")
            return True, f"Successfully transferred {amount} {asset_symbol_to_transfer} to {strategy.name}."

        # --- Case 2: Trading Strategy -> Main Account --- 
        elif source_type == 'strategy' and dest_type == 'main':
            source_strategy_id = source_id # Use already parsed integer ID
            destination_credential_id = dest_id # Use already parsed integer ID

            if amount <= Decimal('0'):
                raise AllocationError("Transfer amount must be positive.")

            strategy = TradingStrategy.query.filter_by(id=source_strategy_id, user_id=user_id).first()
            if not strategy:
                raise AllocationError(f"Source strategy with ID {source_strategy_id} not found for user {user_id}.")

            if strategy.exchange_credential_id != destination_credential_id:
                raise AllocationError(f"Strategy's associated credential ID ({strategy.exchange_credential_id}) does not match the destination main account's credential ID ({destination_credential_id}). Funds can only be transferred back to the strategy's parent main account.")

            if asset_symbol_to_transfer == strategy.base_asset_symbol:
                current_base_allocated = strategy.allocated_base_asset_quantity if strategy.allocated_base_asset_quantity is not None else Decimal('0.0')
                if amount > current_base_allocated:
                    raise AllocationError(f"Cannot transfer {amount} {asset_symbol_to_transfer}. Strategy {strategy.name} only has {current_base_allocated:.8f} {asset_symbol_to_transfer} allocated.")
                strategy.allocated_base_asset_quantity = current_base_allocated - amount
            elif asset_symbol_to_transfer == strategy.quote_asset_symbol:
                current_quote_allocated = strategy.allocated_quote_asset_quantity if strategy.allocated_quote_asset_quantity is not None else Decimal('0.0')
                if amount > current_quote_allocated:
                    raise AllocationError(f"Cannot transfer {amount} {asset_symbol_to_transfer}. Strategy {strategy.name} only has {current_quote_allocated:.8f} {asset_symbol_to_transfer} allocated.")
                strategy.allocated_quote_asset_quantity = current_quote_allocated - amount
            else:
                raise AllocationError(f"Asset {asset_symbol_to_transfer} is not part of strategy {strategy.name}'s trading pair ({strategy.trading_pair}).")
            
            db.session.add(strategy)

            # Record transfer log first so its timestamp precedes the snapshot
            log_entry = AssetTransferLog(
                user_id=user_id,
                source_identifier=source_identifier,
                destination_identifier=destination_identifier,
                asset_symbol=asset_symbol_to_transfer,
                amount=amount,
                strategy_id_from=source_strategy_id,
                strategy_name_from=strategy.name,
                strategy_id_to=None,
                strategy_name_to=None,
            )
            db.session.add(log_entry)
            # Snapshot strategy after logging
            _snapshot_strategy_value(strategy)
            db.session.commit()
            logger.info(f"Successfully transferred {amount} {asset_symbol_to_transfer} from strategy {strategy.name} (ID: {source_strategy_id}) to main account (cred ID: {destination_credential_id}) for user {user_id}.")
            return True, f"Successfully transferred {amount} {asset_symbol_to_transfer} from {strategy.name} to Main Account."

        # --- Case 3: Trading Strategy -> Trading Strategy --- 
        elif source_type == 'strategy' and dest_type == 'strategy':
            source_strategy_id = source_id
            destination_strategy_id = dest_id

            if amount <= Decimal('0'):
                raise AllocationError("Transfer amount must be positive.")

            if source_strategy_id == destination_strategy_id:
                raise AllocationError("Source and destination strategies cannot be the same.")

            source_strategy = TradingStrategy.query.filter_by(id=source_strategy_id, user_id=user_id).first()
            destination_strategy = TradingStrategy.query.filter_by(id=destination_strategy_id, user_id=user_id).first()

            if not source_strategy:
                raise AllocationError(f"Source strategy with ID {source_strategy_id} not found for user {user_id}.")
            if not destination_strategy:
                raise AllocationError(f"Destination strategy with ID {destination_strategy_id} not found for user {user_id}.")

            if source_strategy.exchange_credential_id != destination_strategy.exchange_credential_id:
                raise AllocationError(f"Strategies must belong to the same main exchange account. Source: {source_strategy.exchange_credential_id}, Destination: {destination_strategy.exchange_credential_id}.")

            # Validate asset compatibility for source strategy
            if not (asset_symbol_to_transfer == source_strategy.base_asset_symbol or asset_symbol_to_transfer == source_strategy.quote_asset_symbol):
                raise AllocationError(f"Asset {asset_symbol_to_transfer} is not part of source strategy {source_strategy.name}'s trading pair ({source_strategy.trading_pair}).")

            # Validate asset compatibility for destination strategy
            if not (asset_symbol_to_transfer == destination_strategy.base_asset_symbol or asset_symbol_to_transfer == destination_strategy.quote_asset_symbol):
                raise AllocationError(f"Asset {asset_symbol_to_transfer} is not part of destination strategy {destination_strategy.name}'s trading pair ({destination_strategy.trading_pair}).")

            # Decrease from source strategy
            if asset_symbol_to_transfer == source_strategy.base_asset_symbol:
                current_source_base_allocated = source_strategy.allocated_base_asset_quantity if source_strategy.allocated_base_asset_quantity is not None else Decimal('0.0')
                if amount > current_source_base_allocated:
                    raise AllocationError(f"Cannot transfer {amount} {asset_symbol_to_transfer}. Source strategy {source_strategy.name} only has {current_source_base_allocated:.8f} {asset_symbol_to_transfer} allocated.")
                source_strategy.allocated_base_asset_quantity = current_source_base_allocated - amount
            elif asset_symbol_to_transfer == source_strategy.quote_asset_symbol: # Must be quote if not base, due to earlier validation
                current_source_quote_allocated = source_strategy.allocated_quote_asset_quantity if source_strategy.allocated_quote_asset_quantity is not None else Decimal('0.0')
                if amount > current_source_quote_allocated:
                    raise AllocationError(f"Cannot transfer {amount} {asset_symbol_to_transfer}. Source strategy {source_strategy.name} only has {current_source_quote_allocated:.8f} {asset_symbol_to_transfer} allocated.")
                source_strategy.allocated_quote_asset_quantity = current_source_quote_allocated - amount
            
            # Increase for destination strategy
            if asset_symbol_to_transfer == destination_strategy.base_asset_symbol:
                current_dest_base_allocated = destination_strategy.allocated_base_asset_quantity if destination_strategy.allocated_base_asset_quantity is not None else Decimal('0.0')
                destination_strategy.allocated_base_asset_quantity = current_dest_base_allocated + amount
            elif asset_symbol_to_transfer == destination_strategy.quote_asset_symbol: # Must be quote if not base, due to earlier validation
                current_dest_quote_allocated = destination_strategy.allocated_quote_asset_quantity if destination_strategy.allocated_quote_asset_quantity is not None else Decimal('0.0')
                destination_strategy.allocated_quote_asset_quantity = current_dest_quote_allocated + amount


            log_entry = AssetTransferLog(
                user_id=user_id,
                source_identifier=source_identifier,
                destination_identifier=destination_identifier,
                asset_symbol=asset_symbol_to_transfer,
                amount=amount,
                strategy_id_from=source_strategy_id,
                strategy_name_from=source_strategy.name,
                strategy_id_to=destination_strategy_id,
                strategy_name_to=destination_strategy.name,
            )
            db.session.add(log_entry)
            # Snapshot both strategies since both allocations changed
            _snapshot_strategy_value(source_strategy)
            _snapshot_strategy_value(destination_strategy)
            db.session.add(source_strategy)
            db.session.add(destination_strategy)
            db.session.commit()
            logger.info(f"Successfully transferred {amount} {asset_symbol_to_transfer} from strategy {source_strategy.name} (ID: {source_strategy_id}) to strategy {destination_strategy.name} (ID: {destination_strategy_id}) for user {user_id}.")
            return True, f"Successfully transferred {amount} {asset_symbol_to_transfer} from {source_strategy.name} to {destination_strategy.name}."
        
        else:
            raise AllocationError("Unsupported transfer combination.")

    except InvalidOperation: # Catches errors from Decimal conversion if IDs are not numeric
        db.session.rollback()
        raise AllocationError("Invalid ID format in source or destination identifier.")
    except ValueError: # Catches errors from int() conversion if IDs are not numeric
        db.session.rollback()
        raise AllocationError("Invalid ID format in source or destination identifier.")
    except AllocationError as e:
        db.session.rollback()
        raise e # Re-raise known allocation errors
    except Exception as e:
        db.session.rollback()
        logger.error(f"Unexpected error during internal asset transfer: {e}", exc_info=True)
        raise AllocationError(f"An unexpected error occurred: {str(e)}")
