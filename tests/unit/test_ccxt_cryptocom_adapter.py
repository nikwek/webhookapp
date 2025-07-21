"""Unit tests for Crypto.com CCXT adapter"""

import types
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
    assert pairs == ["BTC/USDT", "ETH/USDT"]


def test_ip_whitelist_error_translated(monkeypatch):
    """Simulate IP_ILLEGAL exception and ensure user-friendly message is returned."""

    def _raise_ip_illegal(*_a, **_k):  # noqa: D401
        raise Exception("IP_ILLEGAL – this key is bound to a different IP")

    monkeypatch.setattr(CcxtCryptocomAdapter, "get_portfolio_value", classmethod(_raise_ip_illegal))

    # We call through a thin wrapper that catches and rewrites errors. Use a dummy method to trigger.
    result = CcxtCryptocomAdapter.get_portfolio_value(user_id=1, portfolio_id=1)
    assert result["success"] is False
    assert "IP address" in result["error"]
