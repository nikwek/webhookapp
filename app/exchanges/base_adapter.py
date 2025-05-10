# app/exchanges/base_adapter.py

from abc import ABC, abstractmethod
from typing import Dict, List, Any, Tuple
from app.models.exchange_credentials import ExchangeCredentials
from app.models.portfolio import Portfolio


class ExchangeAdapter(ABC):
    """
    Base abstract class for exchange adapters.
    All exchange implementations must extend this class and implement its methods.
    """

    @classmethod
    @abstractmethod
    def get_name(cls) -> str:
        """Return the name of the exchange"""
        pass

    @classmethod
    @abstractmethod
    def get_client(cls, user_id: int, portfolio_name: str = 'default'):
        """
        Get an API client for the exchange

        Args:
            user_id: The user ID
            portfolio_name: The portfolio name

        Returns:
            The exchange client object
        """
        pass

    @classmethod
    @abstractmethod
    def get_portfolios(cls, user_id: int, include_default: bool = False) -> List[str]:
        """
        Get user's portfolios from the exchange

        Args:
            user_id: User ID
            include_default: Whether to include the Default portfolio

        Returns:
            List of portfolio names
        """
        pass

    @classmethod
    @abstractmethod
    def get_trading_pairs(cls, user_id: int) -> List[Dict[str, Any]]:
        """
        Get all available trading pairs from the exchange

        Args:
            user_id: User ID

        Returns:
            List of trading pairs as dictionaries
        """
        pass

    @classmethod
    @abstractmethod
    def get_portfolio_value(cls, user_id: int, portfolio_id: int,
                            currency: str = 'USD') -> Dict[str, Any]:
        """
        Get portfolio value and breakdown

        Args:
            user_id: User ID
            portfolio_id: Portfolio ID
            currency: Currency for valuation

        Returns:
            Portfolio value information
        """
        pass

    @classmethod
    @abstractmethod
    def refresh_account_data(cls, user_id: int, portfolio_id: int) -> bool:
        """
        Refresh account data for a portfolio

        Args:
            user_id: User ID
            portfolio_id: Portfolio ID

        Returns:
            Success status
        """
        pass

    @classmethod
    @abstractmethod
    def execute_trade(cls, credentials: ExchangeCredentials, portfolio: Portfolio,
                      trading_pair: str, action: str, payload: Dict[str, Any],
                      client_order_id: str) -> Dict[str, Any]:
        """
        Execute a trade on the exchange

        Args:
            credentials: The ExchangeCredentials object
            portfolio: The Portfolio object
            trading_pair: Trading pair string (e.g. 'BTC-USD')
            action: 'buy' or 'sell'
            payload: Original webhook payload
            client_order_id: Generated UUID for this order

        Returns:
            Result of the trade execution
        """
        pass

    @classmethod
    @abstractmethod
    def validate_api_keys(cls, api_key: str, api_secret: str) -> Tuple[bool, str]:
        """
        Validate API keys with the exchange

        Args:
            api_key: API key
            api_secret: API secret

        Returns:
            Tuple of (is_valid, message)
        """
        pass
