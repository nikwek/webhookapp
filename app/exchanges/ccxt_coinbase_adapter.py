# app/exchanges/ccxt_coinbase_adapter.py

import logging
import time
from typing import Dict, Any, Optional

import ccxt

from app.exchanges.ccxt_base_adapter import CcxtBaseAdapter
from app.models.exchange_credentials import ExchangeCredentials
from app.models.portfolio import Portfolio

logger = logging.getLogger(__name__)

class CcxtCoinbaseAdapter(CcxtBaseAdapter):
    """
    Coinbase-specific implementation of the CCXT adapter.
    Handles Coinbase-specific API requirements and behaviors.
    """
    _exchange_id = "coinbase-ccxt"
    
    @classmethod
    def _get_exchange_class(cls):
        # Coinbase now uses the 'coinbase' exchange ID in CCXT
        return ccxt.coinbase
    
    @classmethod
    def execute_trade(
        cls,
        credentials: ExchangeCredentials,
        portfolio: Optional[Portfolio],
        trading_pair: str,
        action: str,
        payload: Dict[str, Any],
        client_order_id: str,
    ):
        """
        Overrides the base execute_trade method to handle Coinbase-specific trading requirements,
        particularly for market buy orders which need special handling.
        """
        # Get common parameters for all orders
        side = action.lower()
        amount = payload.get("size") or payload.get("amount") or payload.get("quantity")
        if not amount:
            return {
                "trade_executed": False,
                "message": "No trade size specified in payload",
                "trade_status": "error",
                "client_order_id": client_order_id,
            }

        order_type = (payload.get("order_type") or payload.get("type") or "market").lower()
        price = payload.get("price") if order_type == "limit" else None
        
        # Get the client - same as in base class
        client = cls.get_client(
            credentials.user_id,
            credentials.portfolio_name,
        )
        
        # Coinbase requires a minimum order size ($10 USD minimum)
        min_order_value = 10.0  
        
        # Special handling for Coinbase market buy orders using cost-based approach
        if order_type == "market" and side == "buy":
            try:
                # Fetch the current price to ensure we meet min order requirements
                ticker = client.fetch_ticker(trading_pair)
                current_price = float(
                    ticker.get('last')
                    or ticker.get('close')
                    or ticker.get('ask')
                    or ticker.get('bid')
                )
                logger.info(f"Current price for {trading_pair}: {current_price}")
                
                # Calculate the cost (quote currency amount)
                cost = float(amount) * current_price
                
                # Enforce Coinbase minimum order size – abort if below
                if cost < min_order_value:
                    error_msg = (
                        f"Order cost ${cost:.2f} below Coinbase minimum ${min_order_value:.2f}. "
                        "Trade aborted."
                    )
                    logger.warning(error_msg)
                    return {
                        "trade_executed": False,
                        "message": error_msg,
                        "trade_status": "rejected",
                        "client_order_id": client_order_id,
                        "exchange_order_id": None,
                    }
                
                # Coinbase requires costs to have at most 2 decimal places
                cost = round(cost, 2)
                
                logger.info(f"Using createMarketBuyOrderWithCost with USD amount: ${cost:.2f}")
                
                # Use the specialized Coinbase method for cost-based market buy orders
                initial_order = client.create_market_buy_order_with_cost(trading_pair, cost)
                
                # Log the successful order
                logger.info(f"Placed Coinbase market BUY order for {trading_pair} with cost ${cost:.2f}")
                
                # Get the order ID for follow-up
                order_id = initial_order.get("id")
                
                # Now fetch the complete order details with filled amount
                # Market orders execute quickly, but we'll add a small retry mechanism
                max_retries = 3
                retry_delay = 1.0  # seconds
                complete_order = None
                
                for attempt in range(max_retries):
                    try:
                        logger.info(f"Fetching complete order details for order ID {order_id} (attempt {attempt+1}/{max_retries})")
                        complete_order = client.fetch_order(order_id, trading_pair)
                        
                        # Check if we have the filled amount
                        if complete_order.get('filled') is not None:
                            logger.info(f"Successfully retrieved filled amount: {complete_order.get('filled')}")
                            break
                            
                        logger.info(f"Order not yet filled, retrying in {retry_delay} seconds...")
                        time.sleep(retry_delay)
                        retry_delay *= 1.5  # Increase delay for next attempt
                    except Exception as fetch_error:
                        logger.error(f"Error fetching order details: {fetch_error}")
                        time.sleep(retry_delay)
                        retry_delay *= 1.5  # Increase delay for next attempt
                
                # Use the complete order if available, otherwise fall back to initial order
                final_order = complete_order if complete_order else initial_order
                
                # If we still don't have filled amount, calculate it from cost and price
                if final_order.get('filled') is None and final_order.get('cost') is None:
                    logger.info("Order details incomplete, using calculated values")
                    # We know the cost because we set it
                    final_order['cost'] = cost
                    # Estimate filled amount (will be slightly off due to fees)
                    estimated_filled = cost / current_price
                    final_order['filled'] = estimated_filled
                    logger.info(f"Estimated filled amount: {estimated_filled} from cost ${cost:.2f}")
                
                # Return structure consistent with base adapter
                return {
                    "trade_executed": True,
                    "message": "success",
                    "trade_status": final_order.get("status", "closed"),
                    "client_order_id": client_order_id,
                    "exchange_order_id": order_id,
                    "raw_order": final_order,
                }
            except Exception as exc:
                logger.error(f"Error using create_market_buy_order_with_cost for {trading_pair}: {exc}")
                # Robust fallback: use create_order with cost and option override
                try:
                    fallback_initial = client.create_order(
                        trading_pair,
                        "market",
                        "buy",
                        cost,  # pass cost as amount when option disabled
                        None,
                        params={"createMarketBuyOrderRequiresPrice": False},
                    )
                    order_id = fallback_initial.get("id")
                    final_order = fallback_initial
                    try:
                        final_order = client.fetch_order(order_id, trading_pair)
                    except Exception:
                        pass
                    return {
                        "trade_executed": True,
                        "message": "success",
                        "trade_status": final_order.get("status"),
                        "client_order_id": client_order_id,
                        "exchange_order_id": order_id,
                        "raw_order": final_order,
                    }
                except Exception as fallback_exc:
                    logger.error(
                        f"Fallback market buy by cost failed for {trading_pair}: {fallback_exc}"
                    )
                    return {
                        "trade_executed": False,
                        "message": str(fallback_exc),
                        "trade_status": "error",
                        "client_order_id": client_order_id,
                    }
        
        # For all other order types (and fallback for market buy if the specialized method fails),
        # delegate to the parent class implementation
        return super().execute_trade(
            credentials, portfolio, trading_pair, action, payload, client_order_id
        )
