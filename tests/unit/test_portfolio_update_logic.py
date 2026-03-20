"""Unit tests for EnhancedWebhookProcessor._update_strategy_portfolio.

All tests use a lightweight SimpleNamespace stand-in for TradingStrategy so no
DB round-trips are required. _check_portfolio_drift and _defer_snapshot_creation
are patched out to isolate the math.
"""
from __future__ import annotations

from decimal import Decimal
from types import SimpleNamespace
from unittest.mock import patch

import pytest

from app.services.webhook_processor import EnhancedWebhookProcessor


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def make_strategy(*, base="0", quote="0", base_sym="BTC", quote_sym="USDT"):
    return SimpleNamespace(
        id=1,
        name="Test",
        allocated_base_asset_quantity=Decimal(str(base)),
        allocated_quote_asset_quantity=Decimal(str(quote)),
        base_asset_symbol=base_sym,
        quote_asset_symbol=quote_sym,
        exchange_credential=None,
    )


def run_update(strategy, action, trade_result):
    """Call _update_strategy_portfolio with both side-effects patched out."""
    processor = EnhancedWebhookProcessor()
    with patch.object(processor, "_check_portfolio_drift"):
        with patch.object(processor, "_defer_snapshot_creation"):
            processor._update_strategy_portfolio(strategy, action, trade_result)


# ---------------------------------------------------------------------------
# BUY tests
# ---------------------------------------------------------------------------


def test_buy_increments_base_decrements_quote():
    """Basic buy: base increases by filled, quote decreases by cost (no fees)."""
    strat = make_strategy(base="0", quote="50000")
    trade_result = {
        "filled": Decimal("1.0"),
        "cost": Decimal("50000"),
    }
    run_update(strat, "buy", trade_result)

    assert strat.allocated_base_asset_quantity == Decimal("1.0")
    # quote = 50000 - 50000 = 0
    assert strat.allocated_quote_asset_quantity == Decimal("0")


def test_sell_decrements_base_increments_quote():
    """Basic sell: base decreases by filled, quote increases by cost (no fees)."""
    strat = make_strategy(base="1.0", quote="0")
    trade_result = {
        "filled": Decimal("1.0"),
        "cost": Decimal("50000"),
    }
    run_update(strat, "sell", trade_result)

    assert strat.allocated_base_asset_quantity == Decimal("0")
    assert strat.allocated_quote_asset_quantity == Decimal("50000")


def test_buy_applies_total_value_after_fees():
    """BUY with info.total_value_after_fees: quote deducted by that figure, not cost."""
    strat = make_strategy(base="0", quote="50000")
    trade_result = {
        "filled": Decimal("1.0"),
        "cost": Decimal("50000"),
        "info": {"total_value_after_fees": "49900"},
    }
    run_update(strat, "buy", trade_result)

    assert strat.allocated_base_asset_quantity == Decimal("1.0")
    assert strat.allocated_quote_asset_quantity == Decimal("100")


def test_sell_applies_total_value_after_fees():
    """SELL with info.total_value_after_fees: quote credited by that figure."""
    strat = make_strategy(base="1.0", quote="0")
    trade_result = {
        "filled": Decimal("1.0"),
        "cost": Decimal("50000"),
        "info": {"total_value_after_fees": "49900"},
    }
    run_update(strat, "sell", trade_result)

    assert strat.allocated_base_asset_quantity == Decimal("0")
    assert strat.allocated_quote_asset_quantity == Decimal("49900")


def test_fee_parsed_from_fee_dict():
    """Fees from trade_result['fee'] dict are applied on BUY."""
    strat = make_strategy(base="0", quote="50000")
    trade_result = {
        "filled": Decimal("1.0"),
        "cost": Decimal("50000"),
        "fee": {"cost": 10.0, "currency": "USDT"},
    }
    run_update(strat, "buy", trade_result)

    assert strat.allocated_base_asset_quantity == Decimal("1.0")
    # quote = 50000 - (50000 + 10) = -10, clamped to 0
    assert strat.allocated_quote_asset_quantity == Decimal("0")


def test_fee_parsed_from_fees_list():
    """Fees from trade_result['fees'] list are summed and applied on BUY."""
    strat = make_strategy(base="0", quote="60000")
    trade_result = {
        "filled": Decimal("1.0"),
        "cost": Decimal("50000"),
        "fees": [
            {"cost": 5.0, "currency": "USDT"},
            {"cost": 5.0, "currency": "USDT"},
        ],
    }
    run_update(strat, "buy", trade_result)

    assert strat.allocated_base_asset_quantity == Decimal("1.0")
    # quote = 60000 - (50000 + 10) = 9990
    assert strat.allocated_quote_asset_quantity == Decimal("9990")


def test_fee_in_base_currency_ignored():
    """Fees denominated in the base asset (BTC) are not counted against quote."""
    strat = make_strategy(base="0", quote="50000", base_sym="BTC", quote_sym="USDT")
    trade_result = {
        "filled": Decimal("1.0"),
        "cost": Decimal("50000"),
        "fee": {"cost": 0.001, "currency": "BTC"},  # fee in base, not quote
    }
    run_update(strat, "buy", trade_result)

    assert strat.allocated_base_asset_quantity == Decimal("1.0")
    # BTC fee is ignored — quote decremented by cost only = 50000 - 50000 = 0
    assert strat.allocated_quote_asset_quantity == Decimal("0")


def test_missing_fee_data_treated_as_zero():
    """trade_result with no fee fields: total_fees = 0, amounts unaffected by fees."""
    strat = make_strategy(base="0", quote="50000")
    trade_result = {
        "filled": Decimal("1.0"),
        "cost": Decimal("40000"),
        # no 'fee', no 'fees', no 'info'
    }
    run_update(strat, "buy", trade_result)

    assert strat.allocated_base_asset_quantity == Decimal("1.0")
    assert strat.allocated_quote_asset_quantity == Decimal("10000")
