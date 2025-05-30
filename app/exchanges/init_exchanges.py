# app/exchanges/init_exchanges.py

from app.exchanges.registry import ExchangeRegistry
from app.exchanges.coinbase_adapter import CoinbaseAdapter
from app.exchanges.ccxt_base_adapter import CcxtBaseAdapter
import logging
import os

logger = logging.getLogger(__name__)


def initialize_exchange_adapters():
    """
    Initialize and register all exchange adapters.
    This function should be called during application startup.
    """
    logger.info("Initializing exchange adapters...")

    # List of ccxt exchanges we want to expose. You can override via the
    # environment variable `CCXT_EXCHANGES` (comma-separated ids) or a Flask
    # config entry ``CCXT_EXCHANGES``.
    DEFAULT_CCXT_EXCHANGES = [
        "binance",
        "kraken",
        "kucoin",
    ]

    # 1. Register the native Coinbase adapter (non-ccxt)
    ExchangeRegistry.register(CoinbaseAdapter)

    # 2. Dynamically generate and register CCXT adapters
    # ---------------------------------------------------
    # Determine which exchanges to expose
    from flask import current_app  # imported here to avoid circular deps

    cfg_exchanges = []
    if current_app and current_app.config.get("CCXT_EXCHANGES"):
        cfg_exchanges = current_app.config["CCXT_EXCHANGES"]
    env_exchanges = os.getenv("CCXT_EXCHANGES", "")
    if env_exchanges:
        cfg_exchanges = [e.strip() for e in env_exchanges.split(",") if e.strip()]

    exchange_ids = cfg_exchanges or DEFAULT_CCXT_EXCHANGES

    for exch_id in exchange_ids:
        try:
            # Dynamically create subclass
            AdapterCls = type(  # noqa: N806
                f"{exch_id.capitalize()}CcxtAdapter",
                (CcxtBaseAdapter,),
                {"_exchange_id": exch_id},
            )
            ExchangeRegistry.register(AdapterCls)
        except Exception as exc:  # noqa: BLE001
            logger.error("Failed to register CCXT adapter for %s: %s", exch_id, exc)

    # Log final registry
    registered_exchanges = ExchangeRegistry.get_all_exchanges()
    logger.info("Registered exchange adapters: %s", ", ".join(registered_exchanges))
    return registered_exchanges
