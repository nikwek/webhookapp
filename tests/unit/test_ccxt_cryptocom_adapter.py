"""Unit tests for Crypto.com CCXT adapter"""

import pytest

from app.exchanges.ccxt_cryptocom_adapter import CcxtCryptocomAdapter


class _FakeClient:
    """Light-weight stub mimicking ccxt exchange client"""

    def load_markets(self):
        # Return three markets; only *active* spot pairs should be accepted.
        return {
            "BTC/USDT": {"symbol": "BTC/USDT", "active": True},
            "ETH/USDT": {"symbol": "ETH/USDT", "active": True},
            # Include an inactive market to ensure it is ignored
            "LTC/USDT": {"symbol": "LTC/USDT", "active": False},
        }


@pytest.fixture(name="patched_client")
def _patched_client(monkeypatch):
    """Patch the adapter's internal get_client() helper to return a fake ccxt client."""

    def _fake_get_client(*_args, **_kwargs):  # noqa: D401
        return _FakeClient()

    # Patch get_client (classmethod) to return fake client regardless of args
    monkeypatch.setattr(
        CcxtCryptocomAdapter,
        "get_client",
        classmethod(lambda *a, **k: _FakeClient()),
    )


def test_get_trading_pairs_returns_active_pairs(patched_client):  # noqa: D401
    pairs = CcxtCryptocomAdapter.get_trading_pairs(user_id=1)
    expected = [
        {
            "id": "BTC/USDT",
            "product_id": "BTC/USDT",
            "base_currency": None,
            "quote_currency": None,
            "display_name": "BTC/USDT",
        },
        {
            "id": "ETH/USDT",
            "product_id": "ETH/USDT",
            "base_currency": None,
            "quote_currency": None,
            "display_name": "ETH/USDT",
        },
    ]
    assert pairs == expected


def test_ip_whitelist_error_translated(monkeypatch):
    """Simulate IP_ILLEGAL exception and ensure user-friendly message is returned."""
    
    # Mock the base class method to raise IP_ILLEGAL error
    def _mock_super_get_portfolio_value(*_a, **_k):
        raise Exception("IP_ILLEGAL – this key is bound to a different IP")
    
    # Patch the parent class method that gets called by super()
    from app.exchanges.ccxt_base_adapter import CcxtBaseAdapter
    monkeypatch.setattr(CcxtBaseAdapter, "get_portfolio_value", classmethod(_mock_super_get_portfolio_value))
    
    # Call the Crypto.com adapter which should catch and translate the error
    result = CcxtCryptocomAdapter.get_portfolio_value(user_id=1, portfolio_id=1)
    assert result["success"] is False
    assert "IP address" in result["error"]
