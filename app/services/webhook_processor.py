# app/services/webhook_processor.py
import json
import uuid
import logging
from datetime import datetime
from decimal import Decimal
from typing import Dict, Any

from app import db
from app.models import TradingStrategy, Automation, WebhookLog
from app.services.exchange_service import ExchangeService

logger = logging.getLogger(__name__)


class EnhancedWebhookProcessor:
    """
    Handles incoming webhooks for both Automations and Trading Strategies.
    """

    def __init__(self):
        self.exchange_service = ExchangeService()

    def process_webhook(self, identifier: str, payload: Dict[str, Any]):
        """
        Main entry point for processing a webhook.
        Identifies the target (Automation or Strategy) and processes the trade.
        """
        self.identifier = identifier
        logger.info(f"Received webhook for identifier: {identifier}")
        logger.info(f"Webhook Payload:\n{json.dumps(payload, indent=2)}")

        strategy = TradingStrategy.query.filter_by(webhook_id=identifier).first()
        if strategy:
            logger.info(
                f"Identifier matched to Trading Strategy ID: {strategy.id} "
                f"(via webhook_id)"
            )
            return self._process_for_strategy(strategy, payload)

        automation = Automation.query.filter_by(webhook_id=identifier).first()
        if automation:
            logger.info(
                f"Identifier matched to Automation ID: {automation.id} "
                f"(via webhook_id)"
            )
            return self._process_for_automation(automation, payload)

        logger.error(f"No Trading Strategy or Automation found for identifier: {identifier}")
        return {"success": False, "message": "Identifier not found"}, 404

    def _process_for_strategy(self, strategy: TradingStrategy, payload: Dict[str, Any]):
        """Processes a webhook for a Trading Strategy."""
        logger.info(f"Processing webhook for strategy {strategy.id} (name: {strategy.name})")
        logger.info(f"Webhook Payload:\n{json.dumps(payload, indent=2)}")
        
        try:
            action = payload['action']
            ticker = payload.get('ticker')
        except KeyError as e:
            msg = f"Missing required field in JSON payload for strategy {strategy.id}: {e}"
            logger.error(msg)
            self._log_and_commit(strategy_id=strategy.id, status='error', message=msg, payload=payload)
            return {"success": False, "message": msg}, 400

        # Normalize ticker format from payload if present
        if 'ticker' in payload and isinstance(payload['ticker'], str):
            # This ensures that formats like 'BTC-USDC' are converted to 'BTC/USDC'
            payload['ticker'] = payload['ticker'].replace('-', '/').upper()

        # Re-check the payload_ticker after normalization
        payload_ticker = payload.get('ticker')

        # Validate ticker
        if payload_ticker != strategy.trading_pair:
            error_message = f"Ticker mismatch for strategy {strategy.id}. Expected '{strategy.trading_pair}', got '{payload_ticker}'."
            logger.error(error_message)
            self._log_and_commit(strategy_id=strategy.id, status='error', message=error_message, payload=payload)
            return {'error': error_message}, 400

        credentials = strategy.exchange_credential
        if not credentials:
            msg = (
                f"Could not find ExchangeCredentials linked to strategy {strategy.id}. "
                f"Expected a valid 'exchange_credential_id'."
            )
            logger.error(msg)
            self._log_and_commit(strategy_id=strategy.id, status='error', message=msg, payload=payload)
            return {"success": False, "message": msg}, 500


        client_order_id = f"strat_{strategy.id}_{uuid.uuid4()}"

        trade_kwargs = {
            'credentials': credentials,
            'portfolio': None,
            'trading_pair': strategy.trading_pair,
            'action': action,
            'payload': payload,
            'client_order_id': client_order_id,
            'target_type': 'strategy',
            'target_id': strategy.id,
            'target': strategy,
            'webhook_id': strategy.webhook_id,
        }

        return self._execute_and_process_trade(**trade_kwargs)

    def _process_for_automation(self, automation: Automation, payload: Dict[str, Any]):
        """Processes a webhook for an Automation (legacy)."""
        logger.info(f"Processing webhook for automation {automation.id} (name: {automation.name})")
        logger.info(f"Webhook Payload:\n{json.dumps(payload, indent=2)}")
        
        try:
            action = payload['action']
            ticker = payload.get('ticker')
        except KeyError as e:
            msg = f"Missing required field in JSON payload for automation {automation.id}: {e}"
            logger.error(msg)
            self._log_and_commit(automation_id=automation.id, status='error', message=msg, payload=payload)
            return {"success": False, "message": msg}, 400
            
        # Look up the strategy associated with this automation if it exists
        strategy = TradingStrategy.query.filter_by(automation_id=automation.id).first()
        
        if not strategy:
            msg = f"No TradingStrategy found for Automation ID: {automation.id}"
            logger.error(msg)
            self._log_and_commit(automation_id=automation.id, status='error', message=msg, payload=payload)
            return {"success": False, "message": msg}, 404
            
        # Now we have the strategy, process it as a strategy webhook
        return self._process_for_strategy(strategy, payload)

    def _execute_and_process_trade(self, **kwargs):
        """Helper to execute trade and handle logging and session commit."""
        try:
            # Create a clean copy of kwargs for the service call, excluding keys
            # that are for internal use by the processor only.
            service_kwargs = kwargs.copy()
            service_kwargs.pop('target', None)
            service_kwargs.pop('webhook_id', None)

            trade_result = self.exchange_service.execute_trade(**service_kwargs)
            
            # Log that we're about to check for portfolio updates
            logger.info(f"Checking if we should update portfolio. Trade result keys: {list(trade_result.keys())}")
            
            # For strategy trades, update the virtual portfolio
            # Check if trade was successful (either via 'trade_executed' flag or 'success' flag)
            if (trade_result.get('trade_executed', False) or trade_result.get('success', False)) and kwargs.get('target_type') == 'strategy':
                # The order data could be in raw_order, order, or be the trade_result itself
                # Try each in order of preference
                raw_order = trade_result.get("raw_order", {})
                if not raw_order:
                    raw_order = trade_result.get("order", {})
                if not raw_order:
                    raw_order = trade_result
                    
                # Ensure we have the original payload included
                if 'original_payload' not in raw_order and 'payload' in kwargs:
                    raw_order['original_payload'] = kwargs.get('payload')
                
                logger.info(f"Updating portfolio for strategy {kwargs['target'].id} with action {kwargs['action']}")
                self._update_strategy_portfolio(
                    strategy=kwargs['target'],
                    action=kwargs['action'],
                    trade_result=raw_order,
                )

            self._log_and_commit(
                strategy_id=kwargs.get('target_id'),
                status='success',
                message=f"Trade {kwargs.get('action')} for {kwargs.get('trading_pair')}",
                trade_result=trade_result,
                client_order_id=kwargs.get('client_order_id'),
                payload=kwargs.get('payload')  # Include the original payload
            )

            # Log the full trade result for debugging
            logger.info(f"Processing Response / Info:\n{json.dumps(trade_result, indent=2, default=str)}")
            return trade_result, 200

        except Exception as e:
            db.session.rollback()
            logger.error(f"Exception during trade execution: {e}", exc_info=True)
            self._log_and_commit(
                strategy_id=kwargs.get('target_id'),
                status='error',
                message=f"Failed trade {kwargs.get('action')}. Error: {e}",
                trade_result={'error': str(e)},
                payload=kwargs.get('payload'),  # Include the original payload
                client_order_id=kwargs.get('client_order_id')
            )
            return {"success": False, "message": f"An internal error occurred: {e}"}, 500

    def _serialize_decimal(self, obj):
        """Helper method to convert Decimal objects to float for JSON serialization."""
        if isinstance(obj, Decimal):
            return float(obj)
        elif isinstance(obj, dict):
            return {k: self._serialize_decimal(v) for k, v in obj.items()}
        elif isinstance(obj, list):
            return [self._serialize_decimal(item) for item in obj]
        return obj
            
    def _log_and_commit(
        self,
        strategy_id=None,
        automation_id=None,
        target_type="strategy",
        payload=None,
        trading_pair=None,
        status="success",
        message="",
        order_id=None,
        client_order_id=None,
        trade_result=None,
    ):
        """Log webhook event and commit to database."""
        try:
            # First log the original payload for debugging
            logger.info(f"DEBUG - Before serialization - Payload type: {type(payload)}, Content: {payload}")
            
            # Convert any Decimal objects in payload and trade_result to float
            payload_to_store = self._serialize_decimal(payload)
            trade_result_to_store = self._serialize_decimal(trade_result)

            # Convert dictionaries to JSON strings for database storage
            if payload_to_store and isinstance(payload_to_store, dict):
                payload_to_store = json.dumps(payload_to_store)

            if trade_result_to_store and isinstance(trade_result_to_store, dict):
                trade_result_to_store = json.dumps(trade_result_to_store)
                
            # Log the serialized data types before database storage
            logger.info(f"DEBUG - Before WebhookLog creation - Storing payload type: {type(payload_to_store)}, trade_result type: {type(trade_result_to_store)}")
            
            # Look up strategy and exchange names if strategy_id is provided
            strategy_name = "Unknown"
            exchange_name = "Unknown"
            
            if strategy_id:
                # Try to find the strategy and get its name and exchange
                try:
                    from app.models.trading import TradingStrategy
                    from app.models.exchange_credentials import ExchangeCredentials
                    strategy = TradingStrategy.query.get(strategy_id)
                    if strategy:
                        strategy_name = strategy.name
                        
                        # Get the exchange name from the exchange credentials
                        if strategy.exchange_credential_id:
                            exchange_credential = ExchangeCredentials.query.get(strategy.exchange_credential_id)
                            if exchange_credential:
                                exchange_name = exchange_credential.exchange
                except Exception as e:
                    logger.error(f"Error retrieving strategy/exchange info for log: {e}")
            
            # Create the WebhookLog with all information
            webhook_log = WebhookLog(
                strategy_id=strategy_id,
                automation_id=automation_id,
                target_type=target_type,
                payload=payload_to_store,  # Now this should be a JSON string if it was a dict
                trading_pair=trading_pair,
                status=status,
                message=message,
                order_id=order_id,
                client_order_id=client_order_id,
                raw_response=trade_result_to_store,  # Now this should be a JSON string if it was a dict
                timestamp=datetime.utcnow(),
                # Store the names directly in the log
                strategy_name=strategy_name,
                exchange_name=exchange_name
            )
            db.session.add(webhook_log)
            
            # Log the values after creating the WebhookLog
            logger.info(f"DEBUG - After WebhookLog creation - Log payload attribute type: {type(webhook_log.payload)}, Content: {webhook_log.payload}")
            
            db.session.commit()
            identifier = self.identifier or (strategy_id or automation_id)
            logger.info(f"Successfully processed and logged webhook for identifier: {identifier}")
        except Exception as e:
            logger.error(f"Failed to write webhook log or commit session: {e}")
            db.session.rollback()
            # Re-raise the exception to ensure the caller knows the commit failed
            raise

    def _update_strategy_portfolio(
        self, strategy: TradingStrategy, action: str, trade_result: Dict[str, Any]
    ):
        """
        Updates the virtual portfolio of a strategy after a trade.
        This method is designed to be called within an active db.session.
        """
        if not strategy:
            logger.error("Cannot update a null strategy.")
            return
        
        if not trade_result or not isinstance(trade_result, dict):
            logger.error("No valid trade result provided for portfolio update")
            return
            
        # Get original values for logging
        original_base = strategy.allocated_base_asset_quantity
        original_quote = strategy.allocated_quote_asset_quantity
        
        # Extract data from various sources
        filled = None
        cost = None
        ticker = trade_result.get('order', {}).get('symbol')
        order_data = trade_result.get('order', {})
        original_payload = trade_result.get('original_payload', {})
        payload_amount = None
        
        # Check for amount in original payload
        if isinstance(original_payload, dict) and 'amount' in original_payload:
            payload_amount = original_payload.get('amount')
            logger.info(f"Found amount in original payload: {payload_amount}")
        
        logger.info(f"Initial order data - filled: {order_data.get('filled')}, cost: {order_data.get('cost')}")
        
        # ENHANCEMENT: Check for filled amount at top level first (from enhanced adapter)
        if trade_result.get('filled') is not None:
            filled = trade_result.get('filled')
            logger.info(f"Found filled amount at top level of trade_result: {filled}")
        # Fallback to order data
        elif order_data.get('filled') is not None:
            filled = order_data.get('filled')
            logger.info(f"Found filled amount in order data: {filled}")
            
        # ENHANCEMENT: Check for cost at top level first (from enhanced adapter)
        if trade_result.get('cost') is not None:
            cost = trade_result.get('cost')
            logger.info(f"Found cost at top level of trade_result: {cost}")
        # Fallback to order data
        elif order_data.get('cost') is not None:
            cost = order_data.get('cost')
            logger.info(f"Found cost in order data: {cost}")
        
        # If filled is None, try to get it from other sources
        if filled is None:
            # Try amount directly in the trade_result
            if 'amount' in trade_result:
                filled = trade_result.get('amount')
                logger.info(f"Using amount from trade_result as filled: {filled}")
            # Try amount from the original payload
            elif payload_amount is not None:
                filled = payload_amount
                logger.info(f"Using amount from original payload as filled: {payload_amount}")
            # Preferred approach: Use 100% of available assets (all-in/all-out)
            else:
                if action.lower() == 'buy':
                    # For a buy, use all available quote currency (e.g., USD) and calculate how much base we get
                    available_quote = strategy.allocated_quote_asset_quantity
                    if available_quote > Decimal('0'):
                        # Estimate how much base currency we can buy with all our quote currency
                        # In reality, this should use the actual exchange rate from the API
                        estimated_price = Decimal('50000')  # Estimated BTC price
                        filled = available_quote / estimated_price
                        logger.info(f"All-in buy: Using 100% of available {available_quote} quote currency")
                        logger.info(f"Estimated base currency to receive: {filled}")
                    else:
                        logger.warning("No quote currency available for buy. Using minimal amount.")
                        filled = Decimal('0.0001')  # Small default amount
                elif action.lower() == 'sell':
                    # For a sell, use all available base currency (e.g., BTC)
                    available_base = strategy.allocated_base_asset_quantity
                    if available_base > Decimal('0'):
                        filled = available_base
                        logger.info(f"All-out sell: Using 100% of available {filled} base currency")
                    else:
                        logger.warning("No base currency available for sell. Using minimal amount.")
                        filled = Decimal('0.0001')  # Small default amount
                else:
                    # Unknown action
                    ticker_info = ticker or "unknown"
                    logger.warning(f"Unknown action '{action}' for ticker {ticker_info}. Using minimal amount.")
                    filled = Decimal('0.0001')  # Small default amount
        
        # Convert to Decimal safely
        if filled is None:
            logger.error("Cannot update portfolio: filled amount is None")
            return
            
        if not isinstance(filled, Decimal):
            try:
                filled = Decimal(str(filled))
            except Exception as e:
                logger.error(f"Failed to convert filled amount to Decimal: {str(e)}")
                return
            
        # If the filled amount is invalid, stop here
        if filled <= 0:
            logger.error("Cannot update portfolio with zero or negative amount")
            return
            
        # For cost calculation when missing (common with Coinbase)
        if cost is None:
            # Try to extract price from the order if available
            price = order_data.get('price')
            
            if price is not None:
                try:
                    if not isinstance(price, Decimal):
                        price = Decimal(str(price))
                    cost = price * filled
                    logger.info(f"Calculated cost from price and filled: {cost}")
                except Exception as e:
                    logger.error(f"Could not calculate cost from price '{price}': {str(e)}")
                    cost = None
                    
            # Last resort for cost calculation
            if cost is None:
                if action.lower() in ['buy', 'sell']:
                    # For cryptocurrencies, use a reasonable price estimate
                    estimated_price = Decimal('50000')  # Fallback BTC price
                    cost = filled * estimated_price
                    logger.warning(f"Cost not available, using estimate: {cost}")
        
        # Convert cost to Decimal safely
        if cost is not None and not isinstance(cost, Decimal):
            try:
                cost = Decimal(str(cost))
            except Exception as e:
                # Fallback based on filled amount
                estimated_price = Decimal('50000')  # Rough BTC price
                cost = filled * estimated_price
                logger.error(f"Using fallback cost calculation: {cost}, exception: {str(e)}")
        
        # Now update the portfolio
        if action.lower() == 'buy':
            # For buy: Add base asset, subtract quote asset (cost)
            strategy.allocated_base_asset_quantity += filled
            
            # If we're using the 100% approach for buys, we've already calculated the appropriate
            # filled amount based on available quote currency, so we should set quote to 0
            if 'available_quote' in locals():
                strategy.allocated_quote_asset_quantity = Decimal('0.0')
                logger.info("Setting quote asset to zero after 100% buy")
            else:
                # Traditional approach - subtract cost from quote asset
                strategy.allocated_quote_asset_quantity -= cost
                # Ensure we don't go negative
                if strategy.allocated_quote_asset_quantity < 0:
                    logger.warning("Quote asset quantity went negative after buy. Setting to 0.")
                    strategy.allocated_quote_asset_quantity = Decimal('0.0')
        elif action.lower() == 'sell':
            # For sell: Subtract base asset, add quote asset (proceeds)
            
            # If we're using the 100% approach for sells, set base asset to 0
            if 'available_base' in locals() and filled == available_base:
                strategy.allocated_base_asset_quantity = Decimal('0.0')
                logger.info("Setting base asset to zero after 100% sell")
            else:
                # Traditional approach - subtract filled from base asset
                strategy.allocated_base_asset_quantity -= filled
                # Ensure we don't go negative
                if strategy.allocated_base_asset_quantity < 0:
                    logger.warning("Base asset quantity went negative after sell. Setting to 0.")
                    strategy.allocated_base_asset_quantity = Decimal('0.0')
            # Add proceeds to quote asset
            strategy.allocated_quote_asset_quantity += cost
        
        # Log the portfolio changes
        logger.info(
            f"Strategy {strategy.id} {action.upper()} successful. "
            f"Base: {original_base} -> {strategy.allocated_base_asset_quantity}. "
            f"Quote: {original_quote} -> {strategy.allocated_quote_asset_quantity}"
        )