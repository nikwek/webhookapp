# app/services/exchange_service.py

from app.exchanges.registry import ExchangeRegistry
from app.models.exchange_credentials import ExchangeCredentials
from app.models.portfolio import Portfolio
from typing import Dict, List, Any, Optional, Tuple
import logging

logger = logging.getLogger(__name__)

class ExchangeService:
    """
    Service for interacting with exchanges through the adapter system.
    This provides a consistent interface to access different exchange functionality.
    """
    
    @staticmethod
    def get_client(user_id: int, exchange: str, portfolio_name: str = 'default'):
        """
        Get a client for the specified exchange
        
        Args:
            user_id: User ID
            exchange: Exchange name
            portfolio_name: Portfolio name
            
        Returns:
            Exchange client
        """
        adapter = ExchangeRegistry.get_adapter(exchange)
        if not adapter:
            logger.error(f"No adapter registered for exchange: {exchange}")
            return None
            
        return adapter.get_client(user_id, portfolio_name)
    
    @staticmethod
    def get_portfolios(user_id: int, exchange: str, include_default: bool = False) -> List[str]:
        """
        Get portfolios for the specified exchange
        
        Args:
            user_id: User ID
            exchange: Exchange name
            include_default: Whether to include default portfolio
            
        Returns:
            List of portfolio names
        """
        adapter = ExchangeRegistry.get_adapter(exchange)
        if not adapter:
            logger.error(f"No adapter registered for exchange: {exchange}")
            return []
            
        return adapter.get_portfolios(user_id, include_default)
    
    @staticmethod
    def get_trading_pairs(user_id: int, exchange: str) -> List[Dict[str, Any]]:
        """
        Get trading pairs for the specified exchange
        
        Args:
            user_id: User ID
            exchange: Exchange name
            
        Returns:
            List of trading pairs
        """
        adapter = ExchangeRegistry.get_adapter(exchange)
        if not adapter:
            logger.error(f"No adapter registered for exchange: {exchange}")
            return []
            
        return adapter.get_trading_pairs(user_id)
    
    @staticmethod
    def get_portfolio_value(user_id: int, portfolio_id: int, currency: str = 'USD') -> Dict[str, Any]:
        """
        Get portfolio value for the specified portfolio
        
        Args:
            user_id: User ID
            portfolio_id: Portfolio ID
            currency: Currency for valuation
            
        Returns:
            Portfolio value information
        """
        # Get the portfolio to determine the exchange
        portfolio = Portfolio.query.get(portfolio_id)
        if not portfolio:
            logger.error(f"Portfolio {portfolio_id} not found")
            return {
                "success": False,
                "error": "Portfolio not found",
                "value": 0.0
            }
            
        exchange = portfolio.exchange
        adapter = ExchangeRegistry.get_adapter(exchange)
        if not adapter:
            logger.error(f"No adapter registered for exchange: {exchange}")
            return {
                "success": False,
                "error": f"No adapter for exchange: {exchange}",
                "value": 0.0
            }
            
        return adapter.get_portfolio_value(user_id, portfolio_id, currency)
    
    @staticmethod
    def refresh_account_data(user_id: int, portfolio_id: int) -> bool:
        """
        Refresh account data for the specified portfolio
        
        Args:
            user_id: User ID
            portfolio_id: Portfolio ID
            
        Returns:
            Success status
        """
        # Get the portfolio to determine the exchange
        portfolio = Portfolio.query.get(portfolio_id)
        if not portfolio:
            logger.error(f"Portfolio {portfolio_id} not found")
            return False
            
        exchange = portfolio.exchange
        adapter = ExchangeRegistry.get_adapter(exchange)
        if not adapter:
            logger.error(f"No adapter registered for exchange: {exchange}")
            return False
            
        return adapter.refresh_account_data(user_id, portfolio_id)
    
    @staticmethod
    def execute_trade(credentials: ExchangeCredentials, portfolio: Portfolio, 
                     trading_pair: str, action: str, payload: Dict[str, Any], 
                     client_order_id: str) -> Dict[str, Any]:
        """
        Execute a trade on the appropriate exchange
        
        Args:
            credentials: The ExchangeCredentials object
            portfolio: The Portfolio object
            trading_pair: Trading pair string
            action: 'buy' or 'sell'
            payload: Original webhook payload
            client_order_id: Generated UUID for this order
            
        Returns:
            Result of the trade execution
        """
        exchange = portfolio.exchange
        adapter = ExchangeRegistry.get_adapter(exchange)
        if not adapter:
            logger.error(f"No adapter registered for exchange: {exchange}")
            return {
                "trade_executed": False,
                "message": f"No adapter for exchange: {exchange}",
                "client_order_id": client_order_id,
                "trade_status": "error"
            }
            
        return adapter.execute_trade(
            credentials=credentials,
            portfolio=portfolio,
            trading_pair=trading_pair,
            action=action,
            payload=payload,
            client_order_id=client_order_id
        )
    
    @staticmethod
    def validate_api_keys(exchange: str, api_key: str, api_secret: str) -> Tuple[bool, str]:
        """
        Validate API keys with the specified exchange
        
        Args:
            exchange: Exchange name
            api_key: API key
            api_secret: API secret
            
        Returns:
            Tuple of (is_valid, message)
        """
        adapter = ExchangeRegistry.get_adapter(exchange)
        if not adapter:
            logger.error(f"No adapter registered for exchange: {exchange}")
            return False, f"Exchange '{exchange}' not supported"
            
        return adapter.validate_api_keys(api_key, api_secret)
    
    @staticmethod
    def get_available_exchanges() -> List[str]:
        """Get a list of all available exchanges"""
        return ExchangeRegistry.get_all_exchanges()
