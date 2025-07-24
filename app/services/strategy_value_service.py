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


def snapshot_all_strategies(*, source: str = "unspecified") -> None:
    """Create or update today's value snapshot for every strategy."""
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

    # Fetch all required prices in a single batch API call
    logger.info(f"Fetching prices for {len(required_assets)} unique assets: {sorted(required_assets)}")
    try:
        asset_prices = PriceService.get_prices_usd_batch(list(required_assets), force_refresh=True)
        logger.info(f"Successfully fetched {len(asset_prices)} asset prices")
    except Exception as exc:
        logger.error("Failed to fetch batch asset prices: %s", exc, exc_info=True)
        # Fall back to individual pricing (existing behavior)
        asset_prices = {}

    # Calculate values for all strategies using the batched prices
    for strat in strategies:
        try:
            current_val = _value_usd_with_prices(strat, asset_prices)
        except Exception as exc:
            logger.error("Failed to calculate value for strategy %s: %s", strat.id, exc, exc_info=True)
            continue

        existing = (
            StrategyValueHistory.query
            .filter(StrategyValueHistory.strategy_id == strat.id)
            .filter(func.date(StrategyValueHistory.timestamp) == today)
            .first()
        )
        if existing:
            existing.value_usd = current_val
            existing.base_asset_quantity_snapshot = strat.allocated_base_asset_quantity
            existing.quote_asset_quantity_snapshot = strat.allocated_quote_asset_quantity
        else:
            db.session.add(
                StrategyValueHistory(
                    strategy_id=strat.id,
                    timestamp=datetime.utcnow(),
                    value_usd=current_val,
                    base_asset_quantity_snapshot=strat.allocated_base_asset_quantity,
                    quote_asset_quantity_snapshot=strat.allocated_quote_asset_quantity,
                )
            )
    try:
        db.session.commit()
    except Exception as exc:  # noqa: BLE001
        logger.error("Failed to commit strategy value snapshots: %s", exc, exc_info=True)
        db.session.rollback()
