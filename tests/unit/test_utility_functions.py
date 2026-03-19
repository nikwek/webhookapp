"""Tests for utility functions and helpers."""
from decimal import Decimal
from app.routes.api import _trim_decimal, _friendly_exchange


class TestTrimDecimal:
    """Test the _trim_decimal utility function."""

    def test_trim_decimal_removes_trailing_zeros(self):
        """_trim_decimal should remove trailing zeros."""
        assert _trim_decimal(Decimal("1.50000")) == "1.5"
        assert _trim_decimal(Decimal("1.00000")) == "1"
        assert _trim_decimal(Decimal("1.23456")) == "1.23456"

    def test_trim_decimal_handles_integers(self):
        """_trim_decimal should handle integer values."""
        assert _trim_decimal(Decimal("100")) == "100"
        assert _trim_decimal(Decimal("0")) == "0"

    def test_trim_decimal_handles_large_numbers(self):
        """_trim_decimal should handle large numbers."""
        assert _trim_decimal(Decimal("1000000.50000")) == "1000000.5"
        assert _trim_decimal(Decimal("999999999.1")) == "999999999.1"

    def test_trim_decimal_handles_small_numbers(self):
        """_trim_decimal should handle very small numbers."""
        assert _trim_decimal(Decimal("0.00001")) == "0.00001"
        assert _trim_decimal(Decimal("0.000010")) == "0.00001"


class TestFriendlyExchange:
    """Test the _friendly_exchange utility function."""

    def test_friendly_exchange_strips_ccxt_suffix(self):
        """_friendly_exchange should strip -ccxt suffix."""
        assert _friendly_exchange("binance-ccxt") == "binance"
        assert _friendly_exchange("coinbase-ccxt") == "coinbase"
        assert _friendly_exchange("kraken-ccxt") == "kraken"

    def test_friendly_exchange_handles_non_ccxt(self):
        """_friendly_exchange should handle non-ccxt exchanges."""
        assert _friendly_exchange("binance") == "binance"
        assert _friendly_exchange("coinbase") == "coinbase"

    def test_friendly_exchange_handles_none(self):
        """_friendly_exchange should handle None."""
        assert _friendly_exchange(None) is None

    def test_friendly_exchange_handles_empty_string(self):
        """_friendly_exchange should handle empty string."""
        assert _friendly_exchange("") == ""

    def test_friendly_exchange_multiple_ccxt_suffixes(self):
        """_friendly_exchange should only strip last -ccxt suffix."""
        assert _friendly_exchange("exchange-ccxt-ccxt") == "exchange-ccxt"
