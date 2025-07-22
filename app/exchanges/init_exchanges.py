# app/exchanges/init_exchanges.py

from app.exchanges.registry import ExchangeRegistry
from app.exchanges.ccxt_base_adapter import CcxtBaseAdapter
from app.exchanges.ccxt_coinbase_adapter import CcxtCoinbaseAdapter
from app.exchanges.ccxt_cryptocom_adapter import CcxtCryptocomAdapter
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
        "kraken",
        "cryptocom",
        "coinbase-ccxt",
    ]

    # 2. Dynamically generate and register CCXT adapters
    # ---------------------------------------------------
    # Determine which exchanges to expose
    from flask import current_app  # imported here to avoid circular deps

    cfg_exchanges = []
    if current_app and current_app.config.get("CCXT_EXCHANGES"):
        cfg_exchanges = current_app.config["CCXT_EXCHANGES"]
    env_exchanges = os.getenv("CCXT_EXCHANGES", "")
    if env_exchanges:
        cfg_exchanges = [  # noqa: E501
            e.strip() for e in env_exchanges.split(",") if e.strip()
        ]

    exchange_ids = cfg_exchanges or DEFAULT_CCXT_EXCHANGES

    # Register Coinbase adapters
    # Technical adapter (internal id with '-ccxt')
    ExchangeRegistry.register(CcxtCoinbaseAdapter)

    # User-facing alias adapter without the suffix
    class CoinbaseAliasAdapter(CcxtCoinbaseAdapter):
        _exchange_id = "coinbase"

    ExchangeRegistry.register(CoinbaseAliasAdapter)


    # Register our custom Coinbase adapter first
    # Register the rest of the exchanges dynamically
    for exch_id in exchange_ids:
        # Skip Coinbase as we have a custom implementation
        if exch_id in ["coinbase", "coinbase-ccxt"]:
            continue

        try:
            # Dynamically create subclass for other exchanges
            AdapterCls = type(  # noqa: N806
                f"{exch_id.capitalize()}CcxtAdapter",
                (CcxtBaseAdapter,),
                {"_exchange_id": exch_id},
            )
            ExchangeRegistry.register(AdapterCls)
        except Exception as exc:  # noqa: BLE001
            logger.error(  # noqa: E501
                "Failed to register CCXT adapter for %s: %s", exch_id, exc
            )

    # Register our custom cryptocom adapter last so it overrides any generated one
    ExchangeRegistry.register(CcxtCryptocomAdapter)

    # Log final registry
    registered_exchanges = ExchangeRegistry.get_all_exchanges()
    logger.info(  # noqa: E501
        "Registered exchange adapters: %s", ", ".join(registered_exchanges)
    )
    return registered_exchanges
