"""Unit tests for dynamically generated Kraken CCXT adapter."""

from __future__ import annotations

import pytest
from flask import Flask

from app.exchanges.init_exchanges import initialize_exchange_adapters
from app.exchanges.registry import ExchangeRegistry


class _FakeKrakenClient:  # noqa: D401
    """Stub mimicking ccxt.kraken client for load_markets only."""

    def load_markets(self):  # noqa: D401
        # Active and inactive markets to test filtering logic in CcxtBaseAdapter
        return {
            "BTC/USD": {"symbol": "BTC/USD", "active": True},
            "ETH/USD": {"symbol": "ETH/USD", "active": True},
            "DOGE/USD": {"symbol": "DOGE/USD", "active": False},
        }


@pytest.fixture(name="kraken_adapter")
def _fixture_kraken_adapter(monkeypatch):  # noqa: D401
    """Return Kraken adapter with _get_client patched to fake client."""
    app = Flask(__name__)
    with app.app_context():
        initialize_exchange_adapters()
        AdapterCls = ExchangeRegistry.get_adapter("kraken")
        assert AdapterCls is not None, "Kraken adapter not registered"

        # Patch get_client to avoid real ccxt usage
        monkeypatch.setattr(
            AdapterCls,
            "get_client",
            classmethod(lambda *_a, **_k: _FakeKrakenClient()),
        )
        return AdapterCls


def test_get_trading_pairs_returns_active_pairs(kraken_adapter):  # noqa: D401
    pairs = kraken_adapter.get_trading_pairs(user_id=1)
    # Adapter returns list of dicts sorted by display_name
    pair_ids = [p["id"] for p in pairs]
    assert pair_ids == ["BTC/USD", "ETH/USD"]
