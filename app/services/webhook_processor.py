# app/services/webhook_processor.py

from app.models.automation import Automation
from app.models.exchange_credentials import ExchangeCredentials
from app.models.webhook import WebhookLog
from app.models.portfolio import Portfolio
from app.services.exchange_service import ExchangeService
from app.services.account_service import AccountService
from datetime import datetime, timezone, timedelta
from app import db
from flask import current_app
import logging
import uuid
import math
import json
import hashlib
import time
from sqlalchemy import and_, func
from app.utils.circuit_breaker import circuit_breaker

logger = logging.getLogger(__name__)

class EnhancedWebhookProcessor:
    IDEMPOTENCY_WINDOW = timedelta(hours=24)  # Consider webhooks unique for 24 hours
    
    def __init__(self):
        self.webhook_cache = {}  # In-memory cache for recent webhooks
    
    def get_webhook_hash(self, automation_id, payload):
        """Generate a unique hash for this webhook to prevent duplicate processing"""
        # Create a string combining automation ID and payload content
        webhook_str = f"{automation_id}:{json.dumps(payload, sort_keys=True)}"
        # Create a hash of this string
        return hashlib.sha256(webhook_str.encode()).hexdigest()

    def is_duplicate_webhook(self, automation_id, payload):
        """Check if this webhook was recently processed"""
        webhook_hash = self.get_webhook_hash(automation_id, payload)
        
        # First check the in-memory cache
        current_time = datetime.now(timezone.utc)
        if webhook_hash in self.webhook_cache:
            cache_time = self.webhook_cache[webhook_hash]
            if current_time - cache_time < self.IDEMPOTENCY_WINDOW:
                return True
        
        # Then check the database (with a simplified approach compatible with SQLite)
        # Instead of using json_contains, we store and compare the hash
        existing_log = WebhookLog.query.filter(
            WebhookLog.automation_id == automation_id,
            WebhookLog.client_order_id == webhook_hash,  # Use the hash as a unique identifier
            WebhookLog.timestamp > current_time - self.IDEMPOTENCY_WINDOW
        ).first()
        
        # If a matching webhook was found, update the cache and return True
        if existing_log:
            self.webhook_cache[webhook_hash] = existing_log.timestamp
            return True
            
        # No matching webhook found
        return False
    
    def process_webhook(self, automation_id, payload):
        """Process an incoming webhook for an automation with idempotency check"""
        try:
            # Generate client_order_id at the start
            client_order_id = str(uuid.uuid4())
            logger.info(f"Processing webhook with client_order_id: {client_order_id}")
            
            # Check if this is a duplicate webhook
            if self.is_duplicate_webhook(automation_id, payload):
                logger.info(f"Duplicate webhook detected for automation {automation_id}")
                return {
                    "success": True,
                    "trade_executed": False,
                    "duplicate_webhook": True,
                    "client_order_id": client_order_id,
                    "message": "Webhook already processed (duplicate request)"
                }
            
            # Get the automation
            automation = Automation.query.filter_by(automation_id=automation_id).first()
            
            if not automation:
                logger.error(f"No automation found with id: {automation_id}")
                return {
                    "success": True,  # Webhook received successfully
                    "trade_executed": False,
                    "client_order_id": client_order_id,
                    "message": f"No automation found with id: {automation_id}"
                }
            
            # Create a log entry for this webhook immediately
            webhook_hash = self.get_webhook_hash(automation_id, payload)
            log_entry = WebhookLog(
                automation_id=automation_id,
                payload=payload,
                timestamp=datetime.now(timezone.utc),
                trading_pair=automation.trading_pair,
                client_order_id=webhook_hash  # Use the hash instead of a random UUID
            )
            db.session.add(log_entry)
            db.session.commit()
            
            # Add to in-memory cache
            self.webhook_cache[webhook_hash] = log_entry.timestamp
            
            # Standard validation checks
            if not automation.trading_pair:
                logger.warning(f"Automation {automation_id} does not have a trading pair configured")
                return {
                    "success": False,
                    "message": "Trading pair not configured for this automation"
                }
            
            # Check if portfolio is connected
            if not automation.portfolio_id:
                logger.error(f"No portfolio connected to automation: {automation_id}")
                return {
                    "success": False, 
                    "message": "No portfolio connected to this automation"
                }
            
            # Get portfolio details
            portfolio = Portfolio.query.get(automation.portfolio_id)
            if not portfolio:
                logger.error(f"Portfolio not found for automation {automation_id}")
                return {
                    "success": False,
                    "message": "Portfolio not found"
                }
            
            # Get the API credentials for this automation
            credentials = ExchangeCredentials.query.filter_by(
                portfolio_id=automation.portfolio_id,
                exchange='coinbase'
            ).first()
            
            if not credentials:
                logger.error(f"No API credentials found for automation: {automation_id}")
                return {
                    "success": False,
                    "message": "API credentials not found"
                }
            
            # Process the webhook payload
            # Use action from payload, ignore any trading pair in the webhook
            action = payload.get('action', '').lower()
            
            # Validate action
            if action not in ['buy', 'sell']:
                logger.error(f"Invalid action in payload: {action}")
                return {
                    "success": False,
                    "message": f"Invalid action: {action}. Must be 'buy' or 'sell'."
                }
            
            # Always use the trading pair defined in the automation
            trading_pair = automation.trading_pair
            logger.info(f"Using trading pair from automation: {trading_pair}")
            
            # Extract base and quote currencies from trading pair
            try:
                base_currency, quote_currency = trading_pair.split('-')
                logger.info(f"Base currency: {base_currency}, Quote currency: {quote_currency}")
            except ValueError:
                logger.error(f"Invalid trading pair format: {trading_pair}")
                return {
                    "success": False,
                    "message": f"Invalid trading pair format: {trading_pair}. Expected format: BTC-USD"
                }
            
            # Execute the trade using the exchange service
            trade_result = ExchangeService.execute_trade(
                credentials=credentials,
                portfolio=portfolio,
                trading_pair=trading_pair,
                action=action,
                payload=payload,
                client_order_id=client_order_id
            )
            
            # Update the log entry with the trade result
            try:
                log_entry.status = trade_result.get('trade_status', 'error')
                log_entry.message = trade_result.get('message', '')
                log_entry.order_id = trade_result.get('order_id', '')
                log_entry.raw_response = trade_result.get('raw_response', '')
                db.session.commit()
                logger.info(f"Updated webhook log {log_entry.id} with trade result")
            except Exception as e:
                logger.error(f"Error updating webhook log: {str(e)}")
                db.session.rollback()
            
            # Update the automation's last_run timestamp
            try:
                automation.last_run = datetime.now(timezone.utc)
                db.session.commit()
            except Exception as e:
                logger.error(f"Error updating automation last_run: {str(e)}")
                db.session.rollback()
            
            # Return combined result
            return {
                "success": True,  # Webhook was received and processed
                "trade_executed": trade_result.get('trade_executed', False),
                "client_order_id": client_order_id,
                "order_id": trade_result.get('order_id'),
                "message": trade_result.get('message'),
                "trading_pair": trading_pair,
                "action": action,
                "size": trade_result.get('size'),
                "raw_response": trade_result.get('raw_response')
            }
            
        except Exception as e:
            logger.error(f"Error processing webhook: {str(e)}", exc_info=True)
            # Create a failed log entry if one hasn't been created yet
            try:
                db.session.rollback()  # Roll back any pending transactions
                
                # Check if a log entry exists for this client_order_id
                existing_log = WebhookLog.query.filter_by(client_order_id=client_order_id).first()
                if not existing_log:
                    error_log = WebhookLog(
                        automation_id=automation_id,
                        payload=payload,
                        timestamp=datetime.now(timezone.utc),
                        status="error",
                        message=f"Error: {str(e)}",
                        client_order_id=client_order_id
                    )
                    db.session.add(error_log)
                    db.session.commit()
            except Exception as log_err:
                logger.error(f"Failed to create error log: {str(log_err)}")
                
            return {
                "success": True,  # Webhook received, but processing failed
                "trade_executed": False,
                "client_order_id": client_order_id,
                "message": f"Error processing webhook: {str(e)}"
            }
            
            # Error handling for API responses
            if hasattr(e, 'response'):
                try:
                    error_response = e.response.json()
                    message = error_response.get('message', str(e))
                    response_dict = error_response
                except:
                    response_dict = {"error": str(e)}
            else:
                message = str(e)
                response_dict = {"error": str(e)}
            
            return {
                "trade_executed": False,
                "message": f"Error: {message}",
                "client_order_id": client_order_id,
                "trade_status": "error",
                "raw_response": str(response_dict)
            }