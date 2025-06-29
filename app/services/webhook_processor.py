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
        msg = (
            f"Processing for legacy Automations (ID: {automation.id}) "
            f"is not fully implemented in this flow."
        )
        logger.warning(msg)
        self._log_and_commit(automation_id=automation.id, status='error', message=msg, payload=payload)
        return {"success": False, "message": msg}, 501

    def _execute_and_process_trade(self, **kwargs):
        """Helper to execute trade and handle logging and session commit."""
        try:
            # Create a clean copy of kwargs for the service call, excluding keys
            # that are for internal use by the processor only.
            service_kwargs = kwargs.copy()
            service_kwargs.pop('target', None)
            service_kwargs.pop('webhook_id', None)

            trade_result = self.exchange_service.execute_trade(**service_kwargs)

            if trade_result.get('trade_executed') and kwargs.get('target_type') == 'strategy':
                raw_order = trade_result.get("raw_order", {})
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
                timestamp=datetime.utcnow()
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

        filled = Decimal(str(trade_result.get('filled', '0')))
        cost = Decimal(str(trade_result.get('cost', '0')))

        logger.info(
            f"Updating strategy {strategy.id} portfolio after {action} trade. "
            f"Filled: {filled}, Cost: {cost}"
        )

        if filled <= 0 or cost <= 0:
            logger.warning(
                f"Trade for strategy {strategy.id} resulted in no change or invalid "
                f"amounts (filled: {filled}, cost: {cost}). Skipping portfolio update."
            )
            return

        original_base = strategy.allocated_base_asset_quantity
        original_quote = strategy.allocated_quote_asset_quantity

        if action.lower() == 'buy':
            strategy.allocated_base_asset_quantity = filled
            strategy.allocated_quote_asset_quantity = Decimal('0.0')
        elif action.lower() == 'sell':
            strategy.allocated_base_asset_quantity = Decimal('0.0')
            strategy.allocated_quote_asset_quantity = cost
        else:
            logger.error(f"Unknown action '{action}' for strategy {strategy.id}.")
            return

        logger.info(
            f"Strategy {strategy.id} {action.upper()} successful. "
            f"Base: {original_base} -> {strategy.allocated_base_asset_quantity}. "
            f"Quote: {original_quote} -> {strategy.allocated_quote_asset_quantity}"
        )