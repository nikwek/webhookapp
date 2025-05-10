# app/exchanges/init_exchanges.py

from app.exchanges.registry import ExchangeRegistry
from app.exchanges.coinbase_adapter import CoinbaseAdapter
import logging

logger = logging.getLogger(__name__)


def initialize_exchange_adapters():
    """
    Initialize and register all exchange adapters.
    This function should be called during application startup.
    """
    logger.info("Initializing exchange adapters...")

    # Register the Coinbase adapter
    ExchangeRegistry.register(CoinbaseAdapter)

    # Log registered exchanges
    registered_exchanges = ExchangeRegistry.get_all_exchanges()
    exchanges_str = ', '.join(registered_exchanges)
    logger.info(f"Registered exchange adapters: {exchanges_str}")

    return registered_exchanges
