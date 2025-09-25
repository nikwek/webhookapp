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
from app.services.notification_service import NotificationService
from app.exchanges.registry import ExchangeRegistry

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

        logger.error(f"No Trading Strategy found for identifier: {identifier}")
        return {"success": False, "message": "Identifier not found"}, 404

    def _process_for_strategy(self, strategy: TradingStrategy, payload: Dict[str, Any]):
        """Processes a webhook for a Trading Strategy."""
        logger.info(f"Processing webhook for strategy {strategy.id} (name: {strategy.name})")
        logger.info(f"Webhook Payload:\n{json.dumps(payload, indent=2)}")

        # If the strategy is paused/inactive, ignore the webhook gracefully
        if not strategy.is_active:
            msg = f"Strategy {strategy.id} is currently paused – webhook ignored."
            logger.info(msg)
            self._log_and_commit(strategy_id=strategy.id, status='ignored', message=msg, payload=payload)
            # Return 403 Forbidden so the caller knows the strategy is not accepting webhooks
            return {"success": False, "message": msg}, 403
        
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

            # Determine status for logging
            status_value = (
                str(trade_result.get('trade_status') or '')
                or ('success' if trade_result.get('success', False) else 'error')
            )
            
            self._log_and_commit(
                strategy_id=kwargs.get('target_id'),
                status=status_value,
                message=f"Trade {kwargs.get('action')} for {kwargs.get('trading_pair')}",
                trade_result=trade_result,
                client_order_id=kwargs.get('client_order_id'),
                payload=kwargs.get('payload')  # Include the original payload
            )

            # Log the full trade result for debugging
            logger.info(f"Processing Response / Info:\n{json.dumps(trade_result, indent=2, default=str)}")

            # Send user transaction activity email (opt-in)
            try:
                strategy_obj = kwargs.get('target')
                if strategy_obj and getattr(strategy_obj, 'user', None):
                    user = strategy_obj.user
                    # Resolve exchange display name
                    ex_name = strategy_obj.exchange_credential.exchange if strategy_obj.exchange_credential else 'unknown'
                    adapter_cls = ExchangeRegistry.get_adapter(ex_name)
                    if adapter_cls and hasattr(adapter_cls, 'get_display_name'):
                        exchange_display_name = adapter_cls.get_display_name()
                    elif adapter_cls and hasattr(adapter_cls, 'get_name'):
                        exchange_display_name = adapter_cls.get_name()
                    else:
                        exchange_display_name = ex_name.rsplit('-ccxt', 1)[0] if ex_name.endswith('-ccxt') else ex_name
                    information = f"{kwargs.get('action', '').upper()} {kwargs.get('trading_pair', '')}"
                    status_text = status_value.capitalize() if isinstance(status_value, str) else str(status_value)
                    ts = datetime.utcnow().isoformat()
                    coid = kwargs.get('client_order_id')
                    NotificationService.send_user_transaction_activity(
                        user=user,
                        exchange_display_name=exchange_display_name,
                        strategy_name=strategy_obj.name,
                        information=information,
                        status=status_text,
                        timestamp=ts,
                        client_order_id=coid,
                    )
            except Exception as notify_exc:
                logger.error(f"Failed to send transaction email: {notify_exc}")
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
                                # Replace user-unfriendly adapter suffix e.g. 'coinbase-ccxt' → 'coinbase'
                                if exchange_name and exchange_name.endswith('-ccxt'):
                                    exchange_name = exchange_name.rsplit('-ccxt', 1)[0]
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
        
        # Use the correct field names from the TradingStrategy model
        base_asset = strategy.base_asset_symbol
        quote_asset = strategy.quote_asset_symbol
        
        # Store initial balances for adding to the UI
        initial_balances = {
            "base": {
                "asset": base_asset,
                "before": str(original_base)
            },
            "quote": {
                "asset": quote_asset,
                "before": str(original_quote)
            }
        }
        
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
        
        # ------------------------------
        # Calculate total fees (in quote currency)
        # ------------------------------
        total_fees = Decimal('0')
        try:
            fee_entries = []
            # CCXT order format: single fee dict under 'fee' or list under 'fees'
            if 'fee' in order_data and order_data['fee']:
                fee_entries.append(order_data['fee'])
            if 'fees' in order_data and order_data['fees']:
                fee_entries.extend(order_data['fees'])
            # Some exchanges (e.g., Coinbase) expose fee at the top level too
            if 'fee' in trade_result and trade_result['fee']:
                fee_entries.append(trade_result['fee'])
            if 'fees' in trade_result and trade_result['fees']:
                fee_entries.extend(trade_result['fees'])
            # As a last-resort, look for info.total_fees (string) inside order_data.info
            info = order_data.get('info', {}) if isinstance(order_data, dict) else {}
            if isinstance(info, dict) and info.get('total_fees'):
                fee_entries.append({'cost': info.get('total_fees'), 'currency': strategy.quote_asset_symbol})

            for fee_item in fee_entries:
                if not fee_item:
                    continue
                fee_cost = fee_item.get('cost') if isinstance(fee_item, dict) else None
                fee_currency = fee_item.get('currency') if isinstance(fee_item, dict) else None
                # Only count fees denominated in the quote asset
                if fee_cost is None:
                    continue
                if fee_currency is None and strategy.quote_asset_symbol:
                    fee_currency = strategy.quote_asset_symbol  # assume quote
                if (not fee_currency) or (not strategy.quote_asset_symbol):
                    continue
                if fee_currency.upper() == strategy.quote_asset_symbol.upper():
                    total_fees += Decimal(str(fee_cost))
        except Exception as e:
            logger.warning(f"Could not parse fee information from order: {e}")
            total_fees = Decimal('0')

        # ------------------------------
        # Convert cost to Decimal safely
        if cost is not None and not isinstance(cost, Decimal):
            try:
                cost = Decimal(str(cost))
            except Exception as e:
                # Fallback based on filled amount
                estimated_price = Decimal('50000')  # Rough BTC price
                cost = filled * estimated_price
                logger.error(f"Using fallback cost calculation: {cost}, exception: {str(e)}")
        
        # ------------------------------
        # If the exchange returned cost *after* fees, prefer that
        # ------------------------------
        total_after_fees = None
        try:
            info = order_data.get('info', {}) if isinstance(order_data, dict) else {}
            val_after_fees = info.get('total_value_after_fees') if isinstance(info, dict) else None
            if val_after_fees is not None:
                total_after_fees = Decimal(str(val_after_fees))
        except Exception as e:
            logger.debug(f"Could not parse total_value_after_fees: {e}")
            total_after_fees = None

        # Now update the portfolio
        if action.lower() == 'buy':
            # For buy: Add base asset, subtract quote asset (cost)
            strategy.allocated_base_asset_quantity += filled
            
            # Check for Coinbase size_inclusive_of_fees pattern for logging purposes
            info = order_data.get('info', {}) if isinstance(order_data, dict) else {}
            is_size_inclusive = info.get('size_inclusive_of_fees', False) if isinstance(info, dict) else False
            is_size_in_quote = info.get('size_in_quote', False) if isinstance(info, dict) else False
            
            # Log the order properties for debugging
            if is_size_inclusive and is_size_in_quote:
                logger.info(f"Processing Coinbase order with size_inclusive_of_fees={is_size_inclusive} and size_in_quote={is_size_in_quote}")
                
                # Get quote size from order configuration if available (for logging only)
                if isinstance(info, dict) and isinstance(info.get('order_configuration', {}), dict):
                    market_config = info.get('order_configuration', {}).get('market_market_ioc', {})
                    if isinstance(market_config, dict):
                        quote_size = market_config.get('quote_size')
                        if quote_size is not None:
                            try:
                                quote_size = Decimal(str(quote_size))
                                logger.info(f"Original quote_size in order configuration: {quote_size}")
                            except Exception as e:
                                logger.warning(f"Failed to convert quote_size to Decimal: {e}")
            
            # Always use the actual cost+fees rather than zeroing out
            # This fixes the issue with Coinbase's size_inclusive_of_fees orders
            quote_spent = total_after_fees if total_after_fees is not None else (cost + total_fees)
            logger.info(f"Subtracting exact amount spent {quote_spent} from quote asset")
            strategy.allocated_quote_asset_quantity -= quote_spent
            
            # Only zero out in the 'available_quote' case from earlier in the method
            # which is the explicit 100% spending logic from the original implementation
            if 'available_quote' in locals():
                logger.info("Setting quote asset to zero due to 100% allocation flag")
                strategy.allocated_quote_asset_quantity = Decimal('0.0')
            
            # Clamp tiny negatives caused by rounding
            if strategy.allocated_quote_asset_quantity < 0:
                if strategy.allocated_quote_asset_quantity > Decimal('-0.00000001'):
                    strategy.allocated_quote_asset_quantity = Decimal('0.0')
                else:
                    logger.warning("Quote asset quantity went negative after buy. Setting to 0.")
                    strategy.allocated_quote_asset_quantity = Decimal('0.0')
                    
            # Add balance information to trade_result for UI display
            final_base = strategy.allocated_base_asset_quantity
            final_quote = strategy.allocated_quote_asset_quantity
            
            # Update the initial balances with final values
            initial_balances["base"]["after"] = str(final_base)
            initial_balances["base"]["change"] = str(final_base - original_base)
            initial_balances["quote"]["after"] = str(final_quote)
            initial_balances["quote"]["change"] = str(final_quote - original_quote)
            
            # Add to trade_result for display in the UI
            trade_result["balances"] = initial_balances
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
            # Add proceeds to quote asset (net of fees)
            net_proceeds = total_after_fees if total_after_fees is not None else (cost - total_fees)
            strategy.allocated_quote_asset_quantity += net_proceeds
            
            # Add balance information to trade_result for UI display
            final_base = strategy.allocated_base_asset_quantity
            final_quote = strategy.allocated_quote_asset_quantity
            
            # Update the initial balances with final values
            initial_balances["base"]["after"] = str(final_base)
            initial_balances["base"]["change"] = str(final_base - original_base)
            initial_balances["quote"]["after"] = str(final_quote)
            initial_balances["quote"]["change"] = str(final_quote - original_quote)
            
            # Add to trade_result for display in the UI
            trade_result["balances"] = initial_balances
        
        # Log the portfolio changes
        logger.info(
            f"Strategy {strategy.id} {action.upper()} successful. "
            f"Base: {original_base} -> {strategy.allocated_base_asset_quantity}. "
            f"Quote: {original_quote} -> {strategy.allocated_quote_asset_quantity}"
        )

        # After updating portfolio, create an immediate value snapshot so the UI
        # charts update without waiting for the nightly cron job.
        try:
            from datetime import datetime
            from app.models.trading import StrategyValueHistory
            from app.services.strategy_value_service import _value_usd
            snap_val = _value_usd(strategy)
            db.session.add(
                StrategyValueHistory(
                    strategy_id=strategy.id,
                    timestamp=datetime.utcnow(),
                    value_usd=snap_val,
                    base_asset_quantity_snapshot=strategy.allocated_base_asset_quantity,
                    quote_asset_quantity_snapshot=strategy.allocated_quote_asset_quantity,
                )
            )
            logger.info("Snapshot added after trade for strategy %s: $%s", strategy.id, snap_val)
        except Exception as e:
            logger.error("Failed to add immediate strategy snapshot: %s", e, exc_info=True)

        # After updating portfolio, check overall allocations vs actual balances
        try:
            self._check_portfolio_drift(strategy)
        except Exception as e:
            logger.error(f"Error while checking portfolio drift: {e}")

    def _check_portfolio_drift(self, strategy: TradingStrategy):
        """Compare summed strategy allocations with live exchange balances.

        If allocated quantities across all strategies tied to the same
        exchange credentials exceed the actual on-chain balances, log a
        warning so the user can rebalance.  This acts as a guard against
        rounding errors or manual withdrawals performed directly on the
        exchange UI.
        """
        creds = strategy.exchange_credential
        if not creds:
            logger.warning("Drift check skipped – strategy %s has no exchange_credential", strategy.id)
            return

        exchange = creds.exchange
        portfolio_name = creds.portfolio_name or "default"

        # Fetch live balances via the adapter
        client = ExchangeService.get_client(strategy.user_id, exchange, portfolio_name)
        if client is None:
            logger.warning(
                "Drift check skipped – no client for user %s exchange %s portfolio %s",
                strategy.user_id,
                exchange,
                portfolio_name,
            )
            return

        try:
            balances = client.fetch_balance()
        except Exception as exc:
            logger.warning(
                "Drift check: fetch_balance failed for user %s exchange %s – %s",
                strategy.user_id,
                exchange,
                exc,
            )
            return

        total_balances = balances.get("total", {}) or {}

        # Aggregate allocated quantities for *all* strategies using the same credentials
        related_strategies = TradingStrategy.query.filter_by(exchange_credential_id=creds.id).all()
        aggregated: dict[str, Decimal] = {}
        for strat in related_strategies:
            base_sym = (strat.base_asset_symbol or "").upper()
            quote_sym = (strat.quote_asset_symbol or "").upper()
            if base_sym:
                aggregated[base_sym] = aggregated.get(base_sym, Decimal("0")) + Decimal(str(strat.allocated_base_asset_quantity))
            if quote_sym:
                aggregated[quote_sym] = aggregated.get(quote_sym, Decimal("0")) + Decimal(str(strat.allocated_quote_asset_quantity))

        tolerance = Decimal("0.00000001")  # 1e-8 tolerance for float noise
        for asset, allocated_qty in aggregated.items():
            live_qty = Decimal(str(total_balances.get(asset, 0)))
            if allocated_qty - live_qty > tolerance:
                logger.warning(
                    "ALLOCATION DRIFT – User %s asset %s over-allocated. Allocated=%s Live=%s."
                    " Consider rebalancing strategies or transferring funds.",
                    strategy.user_id,
                    asset,
                    allocated_qty,
                    live_qty,
                )