"""Simple price retrieval service using CoinGecko public API.

Prices are stored in the shared Flask-Caching FileSystemCache so that all
Gunicorn workers read and write the same cached values, avoiding redundant
API calls and staying well within CoinGecko's rate limits.
"""

from __future__ import annotations

import logging
from typing import Dict, Optional

import requests

logger = logging.getLogger(__name__)

_API_BASE = "https://api.coingecko.com/api/v3"
_PRICE_TTL = 300  # seconds (5 minutes)
_CACHE_KEY_PREFIX = "price_usd_"


class PriceService:
    """Fetches USD prices for crypto asset symbols via CoinGecko.

    This class is intentionally *very* small.  If you later migrate to a
    dedicated pricing provider or an internal micro-service you can keep
    the same public interface and replace the internals.
    """

    # Static fallback mapping for the most commonly traded symbols.
    _STATIC_SYMBOL_MAP: Dict[str, str] = {
        "BTC": "bitcoin",
        "ETH": "ethereum",
        "LTC": "litecoin",
        "DOGE": "dogecoin",
        "SOL": "solana",
        "ADA": "cardano",
        "BNB": "binancecoin",
        "XRP": "ripple",
        "DOT": "polkadot",
        "MATIC": "matic-network",
        "AVAX": "avalanche-2",
    }

    # Symbol→CoinGecko-id map kept in-memory per process (just ID lookups, not prices)
    _symbol_to_id: Dict[str, str] = _STATIC_SYMBOL_MAP.copy()

    @classmethod
    def _cache(cls):
        from app import cache
        return cache

    @classmethod
    def _load_symbol_map(cls) -> None:
        """Populate the symbol→id map from CoinGecko (once per process)."""
        try:
            logger.debug("Fetching coin list from CoinGecko for symbol map …")
            r = requests.get(f"{_API_BASE}/coins/list", timeout=20)
            r.raise_for_status()
            for coin in r.json():
                symbol = coin["symbol"].upper()
                if symbol not in cls._symbol_to_id:
                    cls._symbol_to_id[symbol] = coin["id"]
            logger.info("Loaded %s coin symbols from CoinGecko", len(cls._symbol_to_id))
        except Exception as exc:  # noqa: BLE001
            logger.error("Unable to fetch symbol map from CoinGecko: %s", exc, exc_info=True)

    @classmethod
    def _resolve_id(cls, symbol: str) -> Optional[str]:
        """Return CoinGecko id for *symbol* (BTC -> bitcoin)."""
        symbol = symbol.upper()
        if symbol in cls._symbol_to_id:
            return cls._symbol_to_id[symbol]
        # Lazily load the full symbol map once per process if needed
        if len(cls._symbol_to_id) == len(cls._STATIC_SYMBOL_MAP):
            cls._load_symbol_map()
        return cls._symbol_to_id.get(symbol)

    @classmethod
    def get_price_usd(cls, symbol: str, *, force_refresh: bool = False) -> float:
        """Return the latest USD price for *symbol* (e.g. "BTC").

        Results are cached in the shared FileSystemCache for 5 minutes so all
        Gunicorn workers benefit from a single fetch.
        """
        symbol = symbol.upper()
        cache = cls._cache()
        key = f"{_CACHE_KEY_PREFIX}{symbol}"

        if not force_refresh:
            cached = cache.get(key)
            if cached is not None and cached > 1e-4:
                return cached

        coin_id = cls._resolve_id(symbol)
        if not coin_id:
            raise ValueError(f"PriceService: Unknown symbol '{symbol}'.")

        params = {"ids": coin_id, "vs_currencies": "usd"}
        try:
            r = requests.get(f"{_API_BASE}/simple/price", params=params, timeout=15)
            r.raise_for_status()
            price = float(r.json()[coin_id]["usd"])
            cache.set(key, price, timeout=_PRICE_TTL)
            return price
        except Exception as exc:  # noqa: BLE001
            logger.error("Error fetching price for %s: %s", symbol, exc, exc_info=True)
            raise

    @classmethod
    def get_prices_usd_batch(cls, symbols: list[str], *, force_refresh: bool = False) -> dict[str, float]:
        """Return USD prices for multiple symbols in a single CoinGecko API call.

        Checks the shared cache first; only fetches symbols whose price is
        missing or stale, keeping API usage minimal across all workers.

        Returns:
            Dict mapping symbol -> USD price. Symbols whose price could not be
            fetched are omitted (callers should treat missing keys as unknown).
        """
        if not symbols:
            return {}

        symbols = [s.upper() for s in symbols]
        cache = cls._cache()
        prices: dict[str, float] = {}
        symbols_to_fetch: list[str] = []

        for symbol in symbols:
            if not force_refresh:
                cached = cache.get(f"{_CACHE_KEY_PREFIX}{symbol}")
                if cached is not None and cached > 1e-4:
                    prices[symbol] = cached
                    continue
            symbols_to_fetch.append(symbol)

        if not symbols_to_fetch:
            return prices

        # Resolve CoinGecko IDs for uncached symbols
        coin_ids: list[str] = []
        coin_id_to_symbol: dict[str, str] = {}
        for symbol in symbols_to_fetch:
            coin_id = cls._resolve_id(symbol)
            if coin_id:
                coin_ids.append(coin_id)
                coin_id_to_symbol[coin_id] = symbol
            else:
                logger.warning("PriceService: Unknown symbol '%s', skipping", symbol)

        if not coin_ids:
            return prices

        params = {
            "ids": ",".join(coin_ids),
            "vs_currencies": "usd",
        }

        try:
            logger.debug("Fetching batch prices for %d assets: %s", len(coin_ids), coin_ids)
            r = requests.get(f"{_API_BASE}/simple/price", params=params, timeout=15)
            r.raise_for_status()

            for coin_id, data in r.json().items():
                if "usd" in data:
                    symbol = coin_id_to_symbol[coin_id]
                    price = float(data["usd"])
                    prices[symbol] = price
                    cache.set(f"{_CACHE_KEY_PREFIX}{symbol}", price, timeout=_PRICE_TTL)
                    logger.debug("Cached price for %s: $%s", symbol, price)

            return prices

        except Exception as exc:  # noqa: BLE001
            logger.error("Batch price fetch failed for %s: %s", coin_ids, exc, exc_info=True)
            # Fall back to individual fetches for any still-missing symbols
            for symbol in symbols_to_fetch:
                if symbol not in prices:
                    try:
                        prices[symbol] = cls.get_price_usd(symbol)
                    except Exception:
                        logger.warning("Failed individual fallback price fetch for %s", symbol)
            return prices
