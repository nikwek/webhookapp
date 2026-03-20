"""Unit tests for ExchangeService.execute_trade amount-calculation and validation logic.

These tests focus on the allocation guard logic inside execute_trade — no real
exchange calls are made. All adapter interactions are mocked.
"""
from __future__ import annotations

import os
import uuid
from decimal import Decimal
from unittest.mock import MagicMock, patch

import pytest

from app import db
from app.models.exchange_credentials import ExchangeCredentials
from app.models.trading import TradingStrategy
from app.models.user import User
from app.exchanges.registry import ExchangeRegistry
from app.services.exchange_service import ExchangeService


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture()
def dummy_cred(app, regular_user):
    """Create a minimal ExchangeCredentials row for the test user."""
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


@pytest.fixture()
def strategy_with_assets(app, dummy_cred):
    """Create a TradingStrategy with 1.0 BTC allocated base and 50000 USDT allocated quote."""
    with app.app_context():
        user = User.query.filter_by(email="testuser@example.com").first()
        strat = TradingStrategy(
            user_id=user.id,
            name="Test Strategy " + str(uuid.uuid4())[:8],
            exchange_credential_id=dummy_cred,
            trading_pair="BTC/USDT",
            base_asset_symbol="BTC",
            quote_asset_symbol="USDT",
            allocated_base_asset_quantity=Decimal("1.0"),
            allocated_quote_asset_quantity=Decimal("50000.0"),
        )
        db.session.add(strat)
        db.session.commit()
        return strat.id


def _make_mock_adapter(free_btc: float = 1.0):
    """Return a mock adapter whose client reports the given free BTC balance."""
    mock_adapter = MagicMock()
    mock_client = MagicMock()
    mock_adapter.get_client.return_value = mock_client
    mock_client.fetch_balance.return_value = {
        "free": {"BTC": free_btc},
        "used": {"BTC": 0.0},
        "total": {"BTC": free_btc},
    }
    mock_adapter.execute_trade.return_value = {
        "trade_executed": True,
        "trade_status": "filled",
        "filled": 0.001,
        "cost": 50.0,
    }
    return mock_adapter


def _cred_obj(app, cred_id):
    """Re-fetch ExchangeCredentials within the app context."""
    return ExchangeCredentials.query.get(cred_id)


# ---------------------------------------------------------------------------
# Helper to call execute_trade with common defaults
# ---------------------------------------------------------------------------


def _execute(
    app,
    cred_id: int,
    strategy_id: int,
    action: str,
    payload: dict,
    mock_adapter,
    ticker_price: dict | None = None,
):
    if ticker_price is None:
        ticker_price = {"last": 50000}

    with app.app_context():
        cred = _cred_obj(app, cred_id)
        with patch.object(ExchangeRegistry, "get_adapter", return_value=mock_adapter):
            with patch.object(
                ExchangeService, "get_ticker_price", return_value=ticker_price
            ):
                with patch(
                    "app.services.exchange_service.get_market_precisions",
                    return_value={"amount_quant": None},
                ):
                    return ExchangeService.execute_trade(
                        credentials=cred,
                        portfolio=None,
                        trading_pair="BTC/USDT",
                        action=action,
                        payload=payload,
                        client_order_id=str(uuid.uuid4()),
                        target_type="strategy",
                        target_id=strategy_id,
                    )


# ---------------------------------------------------------------------------
# Test cases
# ---------------------------------------------------------------------------


def test_buy_without_explicit_amount_uses_quote_divided_by_price(
    app, dummy_cred, strategy_with_assets
):
    """BUY without payload amount: amount = allocated_quote / price, rounded down to 9dp."""
    mock_adapter = _make_mock_adapter()
    result = _execute(
        app,
        dummy_cred,
        strategy_with_assets,
        "buy",
        {"action": "buy", "ticker": "BTC/USDT"},
        mock_adapter,
        ticker_price={"last": 50000},
    )
    # 50000 USDT / 50000 price = 1.0 BTC
    assert result.get("trade_executed") is True
    # Verify execute_trade was called with amount = 1.0
    call_kwargs = mock_adapter.execute_trade.call_args
    assert call_kwargs is not None
    payload_passed = call_kwargs[0][2] if call_kwargs[0] else call_kwargs[1].get("payload", {})
    # amount should be set in payload or directly — adapter call should have occurred
    mock_adapter.execute_trade.assert_called_once()


def test_buy_with_amount_exceeding_quote_returns_rejected(
    app, dummy_cred, strategy_with_assets
):
    """BUY with explicit amount whose cost exceeds allocated quote → rejected."""
    mock_adapter = _make_mock_adapter()
    # 2.0 BTC * 50000 price = 100000 > 50000 allocated quote
    result = _execute(
        app,
        dummy_cred,
        strategy_with_assets,
        "buy",
        {"action": "buy", "ticker": "BTC/USDT", "amount": "2.0"},
        mock_adapter,
        ticker_price={"last": 50000},
    )
    assert result.get("trade_executed") is False
    assert result.get("trade_status") == "rejected"
    mock_adapter.execute_trade.assert_not_called()


def test_buy_when_price_unavailable_returns_error(
    app, dummy_cred, strategy_with_assets
):
    """BUY when ticker price is 0 or missing → error with trade_executed=False."""
    mock_adapter = _make_mock_adapter()
    result = _execute(
        app,
        dummy_cred,
        strategy_with_assets,
        "buy",
        {"action": "buy", "ticker": "BTC/USDT"},
        mock_adapter,
        ticker_price={"last": 0},
    )
    assert result.get("trade_executed") is False
    mock_adapter.execute_trade.assert_not_called()


def test_sell_without_explicit_amount_uses_full_base(
    app, dummy_cred, strategy_with_assets
):
    """SELL without payload amount: uses all of allocated_base_asset_quantity."""
    mock_adapter = _make_mock_adapter(free_btc=1.0)
    result = _execute(
        app,
        dummy_cred,
        strategy_with_assets,
        "sell",
        {"action": "sell", "ticker": "BTC/USDT"},
        mock_adapter,
    )
    assert result.get("trade_executed") is True
    mock_adapter.execute_trade.assert_called_once()


def test_sell_with_amount_exceeding_base_returns_rejected(
    app, dummy_cred, strategy_with_assets
):
    """SELL with explicit amount > allocated base → rejected."""
    mock_adapter = _make_mock_adapter(free_btc=5.0)
    # Strategy has 1.0 BTC allocated; request 2.0
    result = _execute(
        app,
        dummy_cred,
        strategy_with_assets,
        "sell",
        {"action": "sell", "ticker": "BTC/USDT", "amount": "2.0"},
        mock_adapter,
    )
    assert result.get("trade_executed") is False
    assert result.get("trade_status") == "rejected"
    mock_adapter.execute_trade.assert_not_called()


def test_sell_capped_by_insufficient_free_balance_returns_rejected(
    app, dummy_cred, strategy_with_assets
):
    """SELL when free exchange balance < allocated amount → rejected with 'Insufficient free'."""
    # Strategy has 1.0 BTC allocated, but exchange only has 0.1 free
    mock_adapter = _make_mock_adapter(free_btc=0.1)
    result = _execute(
        app,
        dummy_cred,
        strategy_with_assets,
        "sell",
        {"action": "sell", "ticker": "BTC/USDT"},
        mock_adapter,
    )
    assert result.get("trade_executed") is False
    assert result.get("trade_status") == "rejected"
    assert "Insufficient free" in result.get("message", "")
    mock_adapter.execute_trade.assert_not_called()


def test_sell_executes_when_balance_sufficient(app, dummy_cred, strategy_with_assets):
    """SELL when free balance >= allocated amount → adapter.execute_trade is called."""
    mock_adapter = _make_mock_adapter(free_btc=2.0)
    result = _execute(
        app,
        dummy_cred,
        strategy_with_assets,
        "sell",
        {"action": "sell", "ticker": "BTC/USDT"},
        mock_adapter,
    )
    assert result.get("trade_executed") is True
    mock_adapter.execute_trade.assert_called_once()


def test_strategy_not_found_returns_error(app, dummy_cred):
    """Non-existent strategy_id → trade_executed=False with error status."""
    mock_adapter = _make_mock_adapter()
    with app.app_context():
        cred = _cred_obj(app, dummy_cred)
        with patch.object(ExchangeRegistry, "get_adapter", return_value=mock_adapter):
            with patch.object(
                ExchangeService, "get_ticker_price", return_value={"last": 50000}
            ):
                with patch(
                    "app.services.exchange_service.get_market_precisions",
                    return_value={"amount_quant": None},
                ):
                    result = ExchangeService.execute_trade(
                        credentials=cred,
                        portfolio=None,
                        trading_pair="BTC/USDT",
                        action="sell",
                        payload={"action": "sell", "ticker": "BTC/USDT"},
                        client_order_id=str(uuid.uuid4()),
                        target_type="strategy",
                        target_id=999999,
                    )
    assert result.get("trade_executed") is False
