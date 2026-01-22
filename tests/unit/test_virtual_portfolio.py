"""Unit tests for EnhancedWebhookProcessor._update_strategy_portfolio

These tests focus purely on the in-memory math – no real DB persistence or
exchange calls required. We monkey-patch the drift-check to isolate the logic.
"""

from decimal import Decimal
from types import SimpleNamespace

import pytest

from app.services.webhook_processor import EnhancedWebhookProcessor


# ---------------------------------------------------------------------------
# Helper fixtures & builders
# ---------------------------------------------------------------------------


def make_strategy(*, base="0", quote="0"):
    """Return a lightweight stand-in for TradingStrategy."""
    return SimpleNamespace(
        id=1,
        # Portfolio quantities stored as Decimals in the real model
        allocated_base_asset_quantity=Decimal(str(base)),
        allocated_quote_asset_quantity=Decimal(str(quote)),
        base_asset_symbol="BTC",
        quote_asset_symbol="USDC",
        # Drift check expects an attribute – keep it None for these unit tests
        exchange_credential=None,
    )


@pytest.fixture()
def processor(monkeypatch):
    proc = EnhancedWebhookProcessor()
    # Disable drift check to avoid hitting adapters / DB. Patch on the CLASS so
    # the lambda binds correctly and receives `self`.
    monkeypatch.setattr(EnhancedWebhookProcessor, "_check_portfolio_drift", lambda self, strategy: None)
    return proc


# ---------------------------------------------------------------------------
# Test cases
# ---------------------------------------------------------------------------


def test_buy_uses_total_after_fees(processor):
    """If total_value_after_fees is supplied, that figure dictates quote debit."""
    strat = make_strategy(base="0", quote="1000")

    trade_result = {
        "filled": Decimal("0.02"),
        "cost": Decimal("1000"),  # before fees (should be ignored)
        "order": {
            "filled": Decimal("0.02"),
            "cost": Decimal("1000"),
            "info": {"total_value_after_fees": "990"},
        },
    }

    processor._update_strategy_portfolio(strat, "buy", trade_result)

    assert strat.allocated_base_asset_quantity == Decimal("0.02")
    # 1000 USDC – 990 = 10 left
    assert strat.allocated_quote_asset_quantity == Decimal("10")


def test_buy_fallback_cost_plus_fees(processor):
    """When total_after_fees absent, cost + fee is used."""
    strat = make_strategy(base="0", quote="1000")

    trade_result = {
        "filled": Decimal("0.02"),
        "order": {
            "filled": Decimal("0.02"),
            "cost": Decimal("1000"),
            "fee": {"cost": "5", "currency": "USDC"},
        },
    }

    processor._update_strategy_portfolio(strat, "buy", trade_result)

    assert strat.allocated_base_asset_quantity == Decimal("0.02")
    # 1000 – (1000 + 5) = ‑5 ⇒ clamped to 0.00
    assert strat.allocated_quote_asset_quantity == Decimal("0")


def test_sell_net_proceeds(processor):
    """Sell should add net proceeds (after fees) to quote and zero out base."""
    strat = make_strategy(base="0.02", quote="0")

    trade_result = {
        "filled": Decimal("0.02"),
        "order": {
            "filled": Decimal("0.02"),
            "cost": Decimal("1000"),
            "info": {"total_value_after_fees": "995"},
        },
    }

    processor._update_strategy_portfolio(strat, "sell", trade_result)

    assert strat.allocated_base_asset_quantity == Decimal("0")
    assert strat.allocated_quote_asset_quantity == Decimal("995")


def test_rounding_negative_clamp(processor):
    """Tiny negative quote balance should clamp to zero."""
    strat = make_strategy(base="0", quote="0.00000002")

    trade_result = {
        "filled": Decimal("0.00000001"),
        "order": {
            "filled": Decimal("0.00000001"),
            "cost": Decimal("0.00000002"),
        },
    }

    processor._update_strategy_portfolio(strat, "buy", trade_result)

    assert strat.allocated_quote_asset_quantity == Decimal("0")


def test_buy_preserves_quote_remainder(processor):
    """Buy should not zero out quote; it must subtract exact total_after_fees and keep remainder."""
    strat = make_strategy(base="0", quote="4114.398096986165910494")

    trade_result = {
        "filled": Decimal("1.0"),
        "order": {
            "filled": Decimal("1.0"),
            "cost": Decimal("4114.2488814879"),
            "info": {"total_value_after_fees": "4114.2488814879"},
        },
    }

    processor._update_strategy_portfolio(strat, "buy", trade_result)

    # Expect exact remainder after subtracting total_after_fees
    assert strat.allocated_quote_asset_quantity == Decimal("0.149215498265910494")


def test_sell_fallback_cost_minus_fees(processor):
    """When total_after_fees missing on SELL, use cost - fees."""
    strat = make_strategy(base="1.0", quote="0")

    trade_result = {
        "filled": Decimal("1.0"),
        "order": {
            "filled": Decimal("1.0"),
            "cost": Decimal("4100"),
            "fee": {"cost": "28", "currency": "USDC"},
        },
    }

    processor._update_strategy_portfolio(strat, "sell", trade_result)

    assert strat.allocated_base_asset_quantity == Decimal("0")
    assert strat.allocated_quote_asset_quantity == Decimal("4072")
