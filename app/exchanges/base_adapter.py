# app/exchanges/base_adapter.py

from abc import ABC, abstractmethod
from typing import Dict, List, Any, Tuple # Added Any
from app.models.exchange_credentials import ExchangeCredentials
from app.models.portfolio import Portfolio


class ExchangeAdapter(ABC):
    """
    Base abstract class for exchange adapters.
    All exchange implementations must extend this class
    and implement its methods.  # noqa: E501
    """

    @classmethod
    @abstractmethod
    def get_name(cls) -> str:
        """
        Return the internal name/key of the exchange
        (e.g., 'coinbase', 'kraken').
        """
        pass

    @classmethod
    @abstractmethod
    def get_display_name(cls) -> str:
        """
        Return the user-facing display name of the exchange
        (e.g., 'Coinbase', 'Kraken').
        """
        pass

    @classmethod
    @abstractmethod
    def get_client(cls, user_id: int, portfolio_name: str = 'default') -> Any: # Added -> Any
        """
        Get an API client for the exchange.

        Args:
            user_id: The user ID.
            portfolio_name: The portfolio name.

        Returns:
            The exchange client object.
        """
        pass

    @classmethod
    @abstractmethod
    def get_portfolios(cls, user_id: int, include_default: bool = False) -> List[str]:  # noqa: E501
        """
        Get user's portfolios from the exchange.

        Args:
            user_id: User ID.
            include_default: Whether to include the Default portfolio.

        Returns:
            List of portfolio names.
        """
        pass

    @classmethod
    @abstractmethod
    def get_trading_pairs(cls, user_id: int) -> List[Dict[str, Any]]:
        """
        Get all available trading pairs from the exchange.

        Args:
            user_id: User ID.

        Returns:
            List of trading pairs as dictionaries (e.g.,
            [{'symbol': 'BTC/USD', 'base': 'BTC',
              'quote': 'USD', ...}]).
        """
        pass

    @classmethod
    @abstractmethod
    def get_portfolio_value(cls, user_id: int, portfolio_id: int,
                            currency: str = 'USD') -> Dict[str, Any]:
        """
        Get portfolio value and breakdown.

        Args:
            user_id: User ID.
            portfolio_id: Portfolio ID.
            currency: Currency for valuation.

        Returns:
            Portfolio value information.
        """
        pass

    @classmethod
    @abstractmethod
    def refresh_account_data(cls, user_id: int, portfolio_id: int) -> bool:
        """
        Refresh account data for a portfolio.

        Args:
            user_id: User ID.
            portfolio_id: Portfolio ID.

        Returns:
            Success status.
        """
        pass

    @classmethod
    @abstractmethod  # noqa: E501
    def execute_trade(cls, credentials: ExchangeCredentials, portfolio: Portfolio,
                      trading_pair: str, action: str, payload: Dict[str, Any],
                      client_order_id: str) -> Dict[str, Any]:
        """
        Execute a trade on the exchange.

        Args:
            credentials: Exchange credentials.
            portfolio: Portfolio object.
            trading_pair: Trading pair (e.g., 'BTC/USD').
            action: Trade action (e.g., 'buy', 'sell').
            payload: Trade parameters (e.g., amount, price).
            client_order_id: Client-generated order ID for idempotency.

        Returns:
            Trade execution result.
        """
        pass

    @classmethod
    @abstractmethod  # noqa: E501
    def validate_api_keys(
        cls,
        api_key: str,
        api_secret: str,
        **kwargs,
    ) -> \
        Tuple[
            bool,
            str,
        ]:
        """
        Validate API keys.

        Args:
            api_key: API key.
            api_secret: API secret.
            **kwargs: Additional parameters (e.g., passphrase for some
                      exchanges).

        Returns:
            Tuple (is_valid, message).
        """
        pass

    @classmethod
    def get_default_portfolio_name(cls) -> str:
        """
        Return the default portfolio name for this exchange, if applicable.
        For most exchanges, this will be 'Default'.
        Coinbase (Native) might use something like 'default' (lowercase).
        """
        return "Default" # Default implementation
