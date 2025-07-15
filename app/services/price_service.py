"""Simple price retrieval service using CoinGecko public API.

NOTE: This is deliberately lightweight – it avoids adding any new heavy
external dependencies beyond the already-present ``requests`` package
and keeps an in-memory cache so that a single daily snapshot run does
not trigger dozens of HTTP requests for the same symbol.
"""

from __future__ import annotations

import logging
from datetime import datetime, timedelta
from typing import Dict, Optional

import requests

logger = logging.getLogger(__name__)

_API_BASE = "https://api.coingecko.com/api/v3"


class PriceService:
    """Fetches USD prices for crypto asset symbols via CoinGecko.

    This class is intentionally *very* small.  If you later migrate to a
    dedicated pricing provider or an internal micro-service you can keep
    the same public interface and replace the internals.
    """

    # Map of symbol (upper-case) -> coinGecko id (lower-case)
    _symbol_to_id: Dict[str, str] = {}
    # Map of symbol -> {"price": float, "ts": datetime}
    _price_cache: Dict[str, Dict[str, object]] = {}
    _TTL = timedelta(minutes=5)  # cache freshness window

    @classmethod
    def _load_symbol_map(cls) -> None:
        """Populate the symbol→id cache from CoinGecko.

        This call fetches ~10 kB JSON once and then keeps the result in
        memory for the entire process lifetime.
        """
        try:
            logger.debug("Fetching coin list from CoinGecko for symbol map …")
            r = requests.get(f"{_API_BASE}/coins/list", timeout=20)
            r.raise_for_status()
            for coin in r.json():
                symbol = coin["symbol"].upper()
                if symbol not in cls._symbol_to_id:
                    cls._symbol_to_id[symbol] = coin["id"]
            logger.info("Loaded %s coin symbols from CoinGecko", len(cls._symbol_to_id))
        except Exception as exc:  # noqa: BLE001 – want broad catch for logging
            logger.error("Unable to fetch symbol map from CoinGecko: %s", exc, exc_info=True)

    @classmethod
    def _resolve_id(cls, symbol: str) -> Optional[str]:
        """Return CoinGecko id for *symbol* (BTC -> bitcoin)."""
        symbol = symbol.upper()
        if symbol in cls._symbol_to_id:
            return cls._symbol_to_id[symbol]
        # If cache empty, attempt to load once.
        if not cls._symbol_to_id:
            cls._load_symbol_map()
        return cls._symbol_to_id.get(symbol)

    # List of known USD stablecoins that should always be valued at $1
    _USD_STABLECOINS = {
        'USDT',    # Tether
        'USDC',    # USD Coin
        'DAI',     # Dai
        'PYUSD',   # PayPal USD
        'FDUSD',   # First Digital USD
        'USDE',    # Ethena USDe
        'TUSD',    # TrueUSD
        'BUSD',    # Binance USD
        'USDP',    # Pax Dollar
    }
    @classmethod
    def get_price_usd(cls, symbol: str) -> float:
        """Return the latest *USD* price for *symbol* (e.g. "BTC")."""
        # Special handling for USD stablecoins
        symbol = symbol.upper()
        if symbol in cls._USD_STABLECOINS:
            logger.debug(f"Using fixed $1.00 price for stablecoin {symbol}")
            return 1.00
        symbol = symbol.upper()
        now = datetime.utcnow()

        # short-lived cache
        cached = cls._price_cache.get(symbol)
        if cached and now - cached["ts"] < cls._TTL:
            return cached["price"]  # type: ignore[return-value]

        coin_id = cls._resolve_id(symbol)
        if not coin_id:
            raise ValueError(f"PriceService: Unknown symbol '{symbol}'.")

        params = {"ids": coin_id, "vs_currencies": "usd"}
        try:
            r = requests.get(f"{_API_BASE}/simple/price", params=params, timeout=15)
            r.raise_for_status()
            price = float(r.json()[coin_id]["usd"])
            cls._price_cache[symbol] = {"price": price, "ts": now}
            return price
        except Exception as exc:  # noqa: BLE001
            logger.error("Error fetching price for %s: %s", symbol, exc, exc_info=True)
            raise
