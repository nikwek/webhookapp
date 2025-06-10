# app/services/allocation_service.py

from decimal import Decimal, InvalidOperation
from collections import defaultdict
from app import db
from app.models.trading import TradingStrategy
from app.models.exchange_credentials import ExchangeCredentials
from app.exchanges.registry import ExchangeRegistry
import logging

logger = logging.getLogger(__name__)

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


def allocate_to_strategy(user_id: int, strategy_id: int, asset_symbol: str, amount_to_allocate: Decimal):
    if amount_to_allocate <= Decimal('0'):
        # Raising error instead of returning tuple for consistency in error handling
        raise AllocationError("Allocation amount must be positive.")

    strategy = TradingStrategy.query.filter_by(id=strategy_id, user_id=user_id).first()
    if not strategy:
        raise AllocationError(f"Strategy with ID {strategy_id} not found for user {user_id}.")

    if asset_symbol != strategy.base_asset_symbol and asset_symbol != strategy.quote_asset_symbol:
        raise AllocationError(f"Asset {asset_symbol} is not part of strategy {strategy.name}'s trading pair ({strategy.trading_pair}).")

    # Check against unallocated balance
    unallocated_balance = get_unallocated_balance(user_id, strategy.exchange_credential_id, asset_symbol)
    if amount_to_allocate > unallocated_balance:
        raise AllocationError(
            f"Cannot allocate {amount_to_allocate} {asset_symbol}. "
            f"Unallocated balance is {unallocated_balance:.8f} {asset_symbol}."
        )

    # Perform allocation
    if asset_symbol == strategy.base_asset_symbol:
        strategy.allocated_base_asset_quantity += amount_to_allocate
    elif asset_symbol == strategy.quote_asset_symbol:
        strategy.allocated_quote_asset_quantity += amount_to_allocate
    
    db.session.add(strategy)
    try:
        db.session.commit()
        return True, f"Successfully allocated {amount_to_allocate} {asset_symbol} to {strategy.name}."
    except Exception as e:
        db.session.rollback()
        logger.error(f"Database error during allocation: {e}", exc_info=True)
        raise AllocationError(f"Could not save allocation due to a database error: {str(e)}")


def deallocate_from_strategy(user_id: int, strategy_id: int, asset_symbol: str, amount_to_deallocate: Decimal):
    if amount_to_deallocate <= Decimal('0'):
        raise AllocationError("Deallocation amount must be positive.")

    strategy = TradingStrategy.query.filter_by(id=strategy_id, user_id=user_id).first()
    if not strategy:
        raise AllocationError(f"Strategy with ID {strategy_id} not found for user {user_id}.")

    if asset_symbol != strategy.base_asset_symbol and asset_symbol != strategy.quote_asset_symbol:
        raise AllocationError(f"Asset {asset_symbol} is not part of strategy {strategy.name}'s trading pair ({strategy.trading_pair}).")

    # Perform deallocation
    if asset_symbol == strategy.base_asset_symbol:
        if amount_to_deallocate > strategy.allocated_base_asset_quantity:
            raise AllocationError(
                f"Cannot deallocate {amount_to_deallocate} {asset_symbol}. "
                f"Strategy {strategy.name} only has {strategy.allocated_base_asset_quantity:.8f} {asset_symbol} allocated."
            )
        strategy.allocated_base_asset_quantity -= amount_to_deallocate
    elif asset_symbol == strategy.quote_asset_symbol:
        if amount_to_deallocate > strategy.allocated_quote_asset_quantity:
            raise AllocationError(
                f"Cannot deallocate {amount_to_deallocate} {asset_symbol}. "
                f"Strategy {strategy.name} only has {strategy.allocated_quote_asset_quantity:.8f} {asset_symbol} allocated."
            )
        strategy.allocated_quote_asset_quantity -= amount_to_deallocate
    
    db.session.add(strategy)
    try:
        db.session.commit()
        return True, f"Successfully deallocated {amount_to_deallocate} {asset_symbol} from {strategy.name}."
    except Exception as e:
        db.session.rollback()
        logger.error(f"Database error during deallocation: {e}", exc_info=True)
        raise AllocationError(f"Could not save deallocation due to a database error: {str(e)}")
