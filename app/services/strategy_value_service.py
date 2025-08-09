"""Service that snapshots the USD value of every trading strategy daily."""
from __future__ import annotations

import logging
from datetime import date, datetime
from decimal import Decimal

from sqlalchemy import func

from app import db
from app.models.trading import StrategyValueHistory, TradingStrategy
from app.services.price_service import PriceService

logger = logging.getLogger(__name__)


def _value_usd(strategy: TradingStrategy) -> Decimal:
    """Calculate the current USD value for *strategy* using live prices."""
    base_value = Decimal("0")
    quote_value = Decimal("0")
    calculated_values = False  # Track if we successfully calculated at least one asset value
    
    # Log the actual values for debugging
    logger.info(
        "Calculating value for strategy %s (%s): base=%s %s, quote=%s %s", 
        strategy.id, strategy.name,
        strategy.allocated_base_asset_quantity, strategy.base_asset_symbol,
        strategy.allocated_quote_asset_quantity, strategy.quote_asset_symbol
    )
    
    # Calculate base asset value if there's any quantity
    if strategy.allocated_base_asset_quantity is not None and strategy.allocated_base_asset_quantity > 0:
        try:
            if not strategy.base_asset_symbol:
                logger.error("Missing base asset symbol for strategy %s", strategy.id)
            else:
                base_px = Decimal(str(PriceService.get_price_usd(strategy.base_asset_symbol, force_refresh=True)))
                base_value = Decimal(str(strategy.allocated_base_asset_quantity)) * base_px
                logger.info("Base asset %s price: $%s, value: $%s", 
                          strategy.base_asset_symbol, base_px, base_value)
                calculated_values = True
        except Exception as exc:  # noqa: BLE001
            logger.error("Could not calculate base asset value for %s: %s", 
                        strategy.base_asset_symbol, exc)
    
    # Calculate quote asset value if there's any quantity
    if strategy.allocated_quote_asset_quantity is not None and strategy.allocated_quote_asset_quantity > 0:
        try:
            if not strategy.quote_asset_symbol:
                logger.error("Missing quote asset symbol for strategy %s", strategy.id)
            else:
                quote_px = Decimal(str(PriceService.get_price_usd(strategy.quote_asset_symbol, force_refresh=True)))
                quote_value = Decimal(str(strategy.allocated_quote_asset_quantity)) * quote_px
                logger.info("Quote asset %s price: $%s, value: $%s", 
                           strategy.quote_asset_symbol, quote_px, quote_value)
                calculated_values = True
        except Exception as exc:  # noqa: BLE001
            logger.error("Could not calculate quote asset value for %s: %s", 
                        strategy.quote_asset_symbol, exc)

    # Calculate total value
    val = base_value + quote_value
    formatted_val = val.quantize(Decimal("0.01"))
    logger.info("Total value for strategy %s: $%s (calculated_values=%s)", 
               strategy.id, formatted_val, calculated_values)
    
    return formatted_val


def _value_usd_with_prices(strategy: TradingStrategy, asset_prices: dict[str, float]) -> Decimal:
    """Calculate the current USD value for *strategy* using pre-fetched prices.
    
    This is more efficient than _value_usd() as it uses batched price data
    instead of making individual API calls for each strategy.
    """
    base_value = Decimal("0")
    quote_value = Decimal("0")
    calculated_values = False
    
    # Log the actual values for debugging
    logger.info(
        "Calculating value for strategy %s (%s): base=%s %s, quote=%s %s",
        strategy.id, strategy.name,
        strategy.allocated_base_asset_quantity, strategy.base_asset_symbol,
        strategy.allocated_quote_asset_quantity, strategy.quote_asset_symbol
    )
    
    # Calculate base asset value if there's any quantity
    if (strategy.allocated_base_asset_quantity is not None and 
            strategy.allocated_base_asset_quantity > 0 and 
            strategy.base_asset_symbol):
        symbol = strategy.base_asset_symbol.upper()
        if symbol in asset_prices:
            base_px = Decimal(str(asset_prices[symbol]))
            base_value = Decimal(str(strategy.allocated_base_asset_quantity)) * base_px
            logger.info("Base asset %s price: $%s, value: $%s", symbol, base_px, base_value)
            calculated_values = True
        else:
            logger.warning("No price available for base asset %s", symbol)
    
    # Calculate quote asset value if there's any quantity
    if (strategy.allocated_quote_asset_quantity is not None and 
            strategy.allocated_quote_asset_quantity > 0 and 
            strategy.quote_asset_symbol):
        symbol = strategy.quote_asset_symbol.upper()
        if symbol in asset_prices:
            quote_px = Decimal(str(asset_prices[symbol]))
            quote_value = Decimal(str(strategy.allocated_quote_asset_quantity)) * quote_px
            logger.info("Quote asset %s price: $%s, value: $%s", symbol, quote_px, quote_value)
            calculated_values = True
        else:
            logger.warning("No price available for quote asset %s", symbol)

    # Calculate total value
    val = base_value + quote_value
    formatted_val = val.quantize(Decimal("0.01"))
    logger.info("Total value for strategy %s: $%s (calculated_values=%s)",
                strategy.id, formatted_val, calculated_values)
    
    return formatted_val


def snapshot_all_strategies(*, source: str = "unspecified", max_retries: int = 3) -> None:
    """Create or update today's value snapshot for every strategy.
    
    Args:
        source: Source of the snapshot request (e.g., "scheduled_daily", "manual")
        max_retries: Maximum number of retry attempts if price fetching fails
    """
    import time
    
    logger.info("Running strategy value snapshot (source=%s) …", source)
    today = date.today()

    strategies = TradingStrategy.query.all()
    if not strategies:
        logger.info("No strategies found, skipping snapshot")
        return

    # Collect all unique assets needed for pricing
    required_assets = set()
    for strat in strategies:
        if (strat.allocated_base_asset_quantity is not None and
                strat.allocated_base_asset_quantity > 0 and
                strat.base_asset_symbol):
            required_assets.add(strat.base_asset_symbol.upper())
        if (strat.allocated_quote_asset_quantity is not None and
                strat.allocated_quote_asset_quantity > 0 and
                strat.quote_asset_symbol):
            required_assets.add(strat.quote_asset_symbol.upper())

    if not required_assets:
        logger.info("No assets to price, skipping snapshot")
        return

    # Retry logic for price fetching with exponential backoff
    asset_prices = None
    for attempt in range(max_retries):
        try:
            logger.info(f"Fetching prices for {len(required_assets)} unique assets (attempt {attempt + 1}/{max_retries}): {sorted(required_assets)}")
            asset_prices = PriceService.get_prices_usd_batch(list(required_assets), force_refresh=True)
            
            # Validate that we got prices for the critical assets
            missing_prices = required_assets - set(asset_prices.keys())
            if missing_prices:
                logger.warning(f"Missing prices for {len(missing_prices)} assets: {sorted(missing_prices)}")
                # If we're missing more than 50% of required prices, consider this a failure
                if len(missing_prices) > len(required_assets) * 0.5:
                    raise ValueError(f"Too many missing prices: {len(missing_prices)}/{len(required_assets)}")
            
            logger.info(f"Successfully fetched {len(asset_prices)} asset prices")
            break  # Success, exit retry loop
            
        except Exception as exc:
            logger.error(f"Price fetch attempt {attempt + 1} failed: %s", exc, exc_info=True)
            if attempt < max_retries - 1:
                # Exponential backoff: 30s, 60s, 120s
                wait_time = 30 * (2 ** attempt)
                logger.info(f"Retrying in {wait_time} seconds...")
                time.sleep(wait_time)
            else:
                logger.error("All price fetch attempts failed. Aborting snapshot to prevent recording 0 values.")
                return  # Exit completely - do not record any values

    # Double-check we have valid prices before proceeding
    if not asset_prices:
        logger.error("No asset prices available. Aborting snapshot to prevent recording 0 values.")
        return

    # Calculate values for all strategies using the batched prices
    successful_snapshots = 0
    failed_snapshots = 0
    
    for strat in strategies:
        try:
            current_val = _value_usd_with_prices(strat, asset_prices)
            
            # Critical check: Never record 0 values unless the strategy actually has 0 assets
            has_assets = ((strat.allocated_base_asset_quantity or 0) > 0 or 
                         (strat.allocated_quote_asset_quantity or 0) > 0)
            
            if current_val == 0 and has_assets:
                logger.error(f"Strategy {strat.id} ({strat.name}) calculated as $0 but has assets. Skipping to prevent bad data.")
                failed_snapshots += 1
                continue
                
        except Exception as exc:
            logger.error("Failed to calculate value for strategy %s: %s", strat.id, exc, exc_info=True)
            failed_snapshots += 1
            continue

        try:
            # Delete all existing records for this strategy on this date to ensure clean state
            # This handles the case where multiple concurrent workers created duplicate records
            deleted_count = StrategyValueHistory.query.filter(
                StrategyValueHistory.strategy_id == strat.id,
                func.date(StrategyValueHistory.timestamp) == today
            ).delete()
            
            if deleted_count > 0:
                logger.info(f"Deleted {deleted_count} existing snapshot(s) for strategy {strat.id}")
            
            # Create a fresh record with the current calculated value
            db.session.add(
                StrategyValueHistory(
                    strategy_id=strat.id,
                    timestamp=datetime.utcnow(),
                    value_usd=current_val,
                    base_asset_quantity_snapshot=strat.allocated_base_asset_quantity,
                    quote_asset_quantity_snapshot=strat.allocated_quote_asset_quantity,
                )
            )
            successful_snapshots += 1
            logger.info(f"Prepared snapshot for strategy {strat.id} ({strat.name}): ${current_val}")
            
        except Exception as exc:
            logger.error(f"Failed to prepare snapshot for strategy {strat.id}: %s", exc, exc_info=True)
            failed_snapshots += 1
            continue
    
    # Only commit if we have at least some successful snapshots
    if successful_snapshots > 0:
        try:
            db.session.commit()
            logger.info(f"Successfully committed {successful_snapshots} strategy snapshots. Failed: {failed_snapshots}")
        except Exception as exc:
            logger.error("Failed to commit strategy value snapshots: %s", exc, exc_info=True)
            db.session.rollback()
            raise
    else:
        logger.error(f"No successful snapshots to commit. All {failed_snapshots} strategies failed.")
        db.session.rollback()
        db.session.rollback()
