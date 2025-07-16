# app/services/exchange_service.py

import logging
from decimal import Decimal
from typing import Any, Dict, List, Optional, Tuple

from app.exchanges.registry import ExchangeRegistry
from app.models import ExchangeCredentials, Portfolio, TradingStrategy

logger = logging.getLogger(__name__)


class ExchangeService:
    """
    Service for interacting with exchanges through the adapter system.

    This provides a consistent interface to access different exchange
    functionality.
    """

    @staticmethod
    def get_client(user_id: int, exchange: str, portfolio_name: str = "default") -> Any:
        """
        Get a client for the specified exchange.

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
        Get portfolios for the specified exchange.

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
    def get_ticker_price(user_id: int, exchange: str, trading_pair: str) -> Dict[str, Any]:
        """
        Get the latest ticker price for a trading pair.

        Args:
            user_id: The ID of the user to authenticate with.
            exchange: The name of the exchange.
            trading_pair: The trading pair to fetch the price for.

        Returns:
            A dictionary containing the ticker information.
        """
        adapter = ExchangeRegistry.get_adapter(exchange)
        if not adapter:
            logger.error(f"No adapter registered for exchange: {exchange}")
            return {
                "success": False,
                "error": f"No adapter for exchange: {exchange}",
            }

        return adapter.get_ticker(user_id, trading_pair)

    @staticmethod
    def get_trading_pairs(user_id: int, exchange: str) -> List[Dict[str, Any]]:
        """
        Get trading pairs for the specified exchange.

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
    def get_portfolio_value(user_id: int, portfolio_id: int, currency: str = "USD") -> Dict[str, Any]:
        """
        Get portfolio value for the specified portfolio.

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
                "value": 0.0,
            }

        exchange = portfolio.exchange
        adapter = ExchangeRegistry.get_adapter(exchange)
        if not adapter:
            logger.error(f"No adapter registered for exchange: {exchange}")
            return {
                "success": False,
                "error": f"No adapter for exchange: {exchange}",
                "value": 0.0,
            }

        return adapter.get_portfolio_value(user_id, portfolio_id, currency)

    @staticmethod
    def refresh_account_data(user_id: int, portfolio_id: int) -> bool:
        """
        Refresh account data for the specified portfolio.

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
    def execute_trade(
        credentials: ExchangeCredentials,
        portfolio: Optional[Portfolio],
        trading_pair: str,
        action: str,
        payload: Dict[str, Any],
        client_order_id: str,
        target_type: str,
        target_id: int,
    ) -> Dict[str, Any]:
        """
        Execute a trade on the appropriate exchange.

        Handles trades for both Portfolios (automations) and main accounts
        (strategies).

        Args:
            credentials: The ExchangeCredentials object.
            portfolio: The Portfolio object (can be None for strategies).
            trading_pair: Trading pair string.
            action: 'buy' or 'sell'.
            payload: Original webhook payload.
            client_order_id: Generated UUID for this order.
            target_type: 'automation' or 'strategy'.
            target_id: The ID of the automation or strategy.

        Returns:
            Result of the trade execution.
        """
        exchange = None
        if portfolio:
            exchange = portfolio.exchange
        elif credentials:
            exchange = credentials.exchange
        else:
            logger.error("execute_trade called without portfolio or credentials.")
            return {
                "trade_executed": False,
                "message": "Internal error: Missing portfolio and credentials.",
                "client_order_id": client_order_id,
                "trade_status": "error",
            }

        adapter = ExchangeRegistry.get_adapter(exchange)
        if not adapter:
            logger.error(f"No adapter registered for exchange: {exchange}")
            return {
                "trade_executed": False,
                "message": f"No adapter for exchange: {exchange}",
                "client_order_id": client_order_id,
                "trade_status": "error",
            }

        if target_type == "strategy":
            strategy = TradingStrategy.query.get(target_id)
            if not strategy:
                logger.error(f"Strategy with id {target_id} not found.")
                return {
                    "trade_executed": False,
                    "message": f"Strategy not found: {target_id}",
                    "client_order_id": client_order_id,
                    "trade_status": "error",
                }

            # ---------------- Allocation safeguard & determine amount ----------------
            requested_amount = payload.get("amount")

            if action.lower() == "buy":
                # For BUY we need latest market price first
                ticker_info = ExchangeService.get_ticker_price(
                    credentials.user_id, exchange, trading_pair
                )
                last_price = ticker_info.get("last")
                if not last_price or last_price <= 0:
                    return {
                        "trade_executed": False,
                        "message": f"Could not fetch a valid price for {trading_pair}.",
                        "client_order_id": client_order_id,
                        "trade_status": "error",
                    }
                price_dec = Decimal(str(last_price))

                if requested_amount is not None:
                    try:
                        requested_amount_dec = Decimal(str(requested_amount))
                    except Exception:
                        return {
                            "trade_executed": False,
                            "message": "Invalid amount format in payload.",
                            "client_order_id": client_order_id,
                            "trade_status": "error",
                        }
                    cost_required = requested_amount_dec * price_dec
                    if cost_required > strategy.allocated_quote_asset_quantity:
                        return {
                            "trade_executed": False,
                            "message": (
                                "Insufficient allocated quote assets for this BUY. "
                                f"Cost {cost_required} exceeds allocation "
                                f"{strategy.allocated_quote_asset_quantity}. Trade aborted."
                            ),
                            "client_order_id": client_order_id,
                            "trade_status": "rejected",
                        }
                    amount = requested_amount_dec
                else:
                    # Use all allocated quote assets
                    amount = strategy.allocated_quote_asset_quantity / price_dec

            elif action.lower() == "sell":
                if requested_amount is not None:
                    try:
                        requested_amount_dec = Decimal(str(requested_amount))
                    except Exception:
                        return {
                            "trade_executed": False,
                            "message": "Invalid amount format in payload.",
                            "client_order_id": client_order_id,
                            "trade_status": "error",
                        }
                    if requested_amount_dec > strategy.allocated_base_asset_quantity:
                        return {
                            "trade_executed": False,
                            "message": (
                                "Insufficient allocated base assets for this SELL. "
                                f"Requested {requested_amount_dec} exceeds allocation "
                                f"{strategy.allocated_base_asset_quantity}. Trade aborted."
                            ),
                            "client_order_id": client_order_id,
                            "trade_status": "rejected",
                        }
                    amount = requested_amount_dec
                else:
                    # Sell 100% of the base asset
                    amount = strategy.allocated_base_asset_quantity
            else:
                amount = Decimal("0")


            # Update payload with the calculated or validated amount
            payload["amount"] = float(amount)
            payload["type"] = "market"  # Strategies use market orders

        # The adapter's execute_trade method may need to be updated to handle a
        # null portfolio and to know about strategies vs automations.
        return adapter.execute_trade(
            credentials=credentials,
            portfolio=portfolio,  # Can be None for strategies
            trading_pair=trading_pair,
            action=action,
            payload=payload,
            client_order_id=client_order_id,
        )

    @staticmethod
    def validate_api_keys(
        exchange: str, api_key: str, api_secret: str
    ) -> Tuple[bool, str]:
        """
        Validate API keys with the specified exchange.

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
        """Get a list of all available exchanges."""
        return ExchangeRegistry.get_all_exchanges()
