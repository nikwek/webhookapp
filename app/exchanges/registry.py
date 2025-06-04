# app/exchanges/registry.py

from typing import Dict, Type, List, Optional
from app.exchanges.base_adapter import ExchangeAdapter
import logging

logger = logging.getLogger(__name__)


class ExchangeRegistry:
    """Registry for exchange adapters."""

    _adapters: Dict[str, Type[ExchangeAdapter]] = {}

    @classmethod
    def register(cls, adapter_class: Type[ExchangeAdapter]) -> None:
        """Register an exchange adapter"""
        exchange_name = adapter_class.get_name()
        cls._adapters[exchange_name] = adapter_class
        logger.info(f"Registered exchange adapter: {exchange_name}")

    @classmethod
    def get_adapter(cls, exchange_name: str) -> Optional[Type[ExchangeAdapter]]:
        """Get adapter for a specific exchange by name"""
        adapter = cls._adapters.get(exchange_name)
        if not adapter:
            logger.warning(f"No adapter found for exchange: {exchange_name}")
        return adapter

    @classmethod
    def get_all_exchanges(cls) -> List[str]:
        """Get a list of all registered exchange names"""
        return list(cls._adapters.keys())

    @classmethod
    def get_default_exchange(cls) -> Optional[str]:
        """Get the default exchange name (first one registered)"""
        if not cls._adapters:
            return None
        return next(iter(cls._adapters.keys()))

    @classmethod
    def get_all_adapter_classes(cls) -> List[Type[ExchangeAdapter]]:
        """Get a list of all registered exchange adapter classes."""
        return list(cls._adapters.values())
