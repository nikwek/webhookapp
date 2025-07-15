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


def snapshot_all_strategies() -> None:
    """Create or update today's value snapshot for every strategy."""
    logger.info("Running daily strategy value snapshot …")
    today = date.today()

    strategies = TradingStrategy.query.all()
    for strat in strategies:
        try:
            current_val = _value_usd(strat)
        except Exception:
            continue  # already logged above

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
