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
    try:
        base_px = Decimal(str(PriceService.get_price_usd(strategy.base_asset_symbol)))
        quote_px = Decimal(str(PriceService.get_price_usd(strategy.quote_asset_symbol)))
    except Exception as exc:  # noqa: BLE001
        logger.warning("Could not fetch prices for strategy %s – skipping. %s", strategy.id, exc)
        raise

    val = (
        (strategy.allocated_base_asset_quantity or Decimal("0")) * base_px
        + (strategy.allocated_quote_asset_quantity or Decimal("0")) * quote_px
    )
    return val.quantize(Decimal("0.01"))


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
