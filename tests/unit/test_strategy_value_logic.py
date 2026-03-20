"""Unit tests for app/services/strategy_value_service.py.

Tests cover _value_usd_with_prices (pure math), _value_usd (live price fetch),
and snapshot_all_strategies (DB integration with mocked prices).
"""
from __future__ import annotations

import os
import uuid
from decimal import Decimal
from types import SimpleNamespace
from unittest.mock import patch

import pytest

from app import db
from app.models.exchange_credentials import ExchangeCredentials
from app.models.trading import StrategyValueHistory, TradingStrategy
from app.models.user import User
from app.services.strategy_value_service import (
    _value_usd,
    _value_usd_with_prices,
    snapshot_all_strategies,
)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture()
def dummy_cred(app, regular_user):
    with app.app_context():
        from cryptography.fernet import Fernet

        key = Fernet.generate_key().decode()
        os.environ["ENCRYPTION_KEY"] = key

        user = User.query.filter_by(email="testuser@example.com").first()
        cred = ExchangeCredentials(
            user_id=user.id,
            exchange="dummybal",
            portfolio_name="Main",
            api_key="key",
            api_secret="sec",
        )
        db.session.add(cred)
        db.session.commit()
        return cred.id


def _make_db_strategy(app, cred_id, *, base_qty="0", quote_qty="0",
                      base_sym="BTC", quote_sym="USDT"):
    """Create and persist a TradingStrategy; return its id."""
    with app.app_context():
        user = User.query.filter_by(email="testuser@example.com").first()
        strat = TradingStrategy(
            user_id=user.id,
            name="ValTest " + str(uuid.uuid4())[:8],
            exchange_credential_id=cred_id,
            trading_pair=f"{base_sym}/{quote_sym}",
            base_asset_symbol=base_sym,
            quote_asset_symbol=quote_sym,
            allocated_base_asset_quantity=Decimal(base_qty),
            allocated_quote_asset_quantity=Decimal(quote_qty),
        )
        db.session.add(strat)
        db.session.commit()
        return strat.id


def _simple_strategy(base="0", quote="0", base_sym="BTC", quote_sym="USDT"):
    """Return a lightweight mock strategy object (no DB required)."""
    return SimpleNamespace(
        id=99,
        name="MockStrat",
        allocated_base_asset_quantity=Decimal(str(base)),
        allocated_quote_asset_quantity=Decimal(str(quote)),
        base_asset_symbol=base_sym,
        quote_asset_symbol=quote_sym,
    )


# ---------------------------------------------------------------------------
# _value_usd_with_prices tests (pure calculation, no DB)
# ---------------------------------------------------------------------------


def test_value_usd_with_prices_both_assets():
    """Both BTC and USDT are priced; total = 0.1 * 50000 + 500 * 1 = 5500."""
    strat = _simple_strategy(base="0.1", quote="500")
    prices = {"BTC": 50000.0, "USDT": 1.0}
    result = _value_usd_with_prices(strat, prices)
    assert result == Decimal("5500.00")


def test_value_usd_with_prices_only_quote():
    """Zero base quantity: only quote contributes to value."""
    strat = _simple_strategy(base="0", quote="1000")
    prices = {"BTC": 50000.0, "USDT": 1.0}
    result = _value_usd_with_prices(strat, prices)
    assert result == Decimal("1000.00")


def test_value_usd_with_prices_missing_price_for_base():
    """If base price is absent from prices dict, only quote value is counted."""
    strat = _simple_strategy(base="0.5", quote="500")
    prices = {"USDT": 1.0}  # no BTC price
    result = _value_usd_with_prices(strat, prices)
    # Only quote value: 500 * 1.0 = 500
    assert result == Decimal("500.00")


# ---------------------------------------------------------------------------
# _value_usd tests (live price fetch via PriceService)
# ---------------------------------------------------------------------------


def test_value_usd_fetches_live_prices(app):
    """_value_usd calls PriceService.get_price_usd and calculates correctly."""
    strat = _simple_strategy(base="0.1", quote="500")

    def fake_get_price_usd(symbol, force_refresh=False):
        return 50000.0 if symbol.upper() == "BTC" else 1.0

    with app.app_context():
        with patch(
            "app.services.strategy_value_service.PriceService.get_price_usd",
            side_effect=fake_get_price_usd,
        ):
            result = _value_usd(strat)

    assert result == Decimal("5500.00")


# ---------------------------------------------------------------------------
# snapshot_all_strategies tests (DB integration)
# ---------------------------------------------------------------------------


def test_snapshot_all_strategies_writes_history(app, dummy_cred):
    """Snapshot creates a StrategyValueHistory record for a strategy with assets."""
    strat_id = _make_db_strategy(
        app, dummy_cred, base_qty="0.1", quote_qty="500"
    )

    with app.app_context():
        with patch(
            "app.services.strategy_value_service.PriceService.get_prices_usd_batch",
            return_value={"BTC": 50000.0, "USDT": 1.0},
        ):
            snapshot_all_strategies(source="test")

        count = StrategyValueHistory.query.filter_by(strategy_id=strat_id).count()
    assert count >= 1


def test_snapshot_skips_zero_value_with_assets(app, dummy_cred):
    """When calculated value is 0 but strategy has assets, no snapshot is written."""
    strat_id = _make_db_strategy(
        app, dummy_cred, base_qty="1.0", quote_qty="0"
    )

    with app.app_context():
        # Return empty prices so the base asset has no price → value = 0
        with patch(
            "app.services.strategy_value_service.PriceService.get_prices_usd_batch",
            return_value={},  # no prices available
        ):
            # With no prices, the batch fetch will be treated as a partial failure.
            # The service will still try to snapshot but calculated value for
            # the strategy will be 0 and should be skipped.
            # We also need to stub retries to avoid sleeping.
            snapshot_all_strategies(source="test", max_retries=1)

        count = StrategyValueHistory.query.filter_by(strategy_id=strat_id).count()
    # Either the snapshot was skipped due to 0 value, or aborted due to missing prices.
    # Either way, no record with value=0 should exist.
    with app.app_context():
        zero_records = (
            StrategyValueHistory.query.filter_by(strategy_id=strat_id)
            .filter(StrategyValueHistory.value_usd == 0)
            .count()
        )
    assert zero_records == 0


def test_snapshot_does_nothing_with_no_strategies(app):
    """snapshot_all_strategies returns early without error when no strategies exist."""
    with app.app_context():
        # Remove all strategies for this test
        TradingStrategy.query.delete()
        db.session.commit()

        # Should complete without raising
        snapshot_all_strategies(source="test")
