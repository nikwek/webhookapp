# app/services/webhook_processor.py

from app.models.automation import Automation
from app.models.exchange_credentials import ExchangeCredentials
from app.models.webhook import WebhookLog
from app.services.coinbase_service import CoinbaseService
from app import db
from flask import current_app
import logging

logger = logging.getLogger(__name__)

class WebhookProcessor:
    def process_webhook(self, automation_id, payload):
        """
        Process an incoming webhook for an automation
        
        Args:
            automation_id (str): ID of the automation
            payload (dict): Webhook payload
            
        Returns:
            dict: Processing result
        """
        try:
            # Get the automation
            automation = Automation.query.filter_by(automation_id=automation_id).first()
            
            if not automation:
                logger.error(f"No automation found with id: {automation_id}")
                return {
                    "success": False,
                    "message": f"No automation found with id: {automation_id}"
                }
            
            if not automation.is_active:
                logger.warning(f"Attempt to process webhook for inactive automation: {automation_id}")
                return {
                    "success": False,
                    "message": "Automation is not active"
                }
            
            # Create a log entry for this webhook
            log_entry = WebhookLog(
                automation_id=automation_id,
                payload=payload
            )
            db.session.add(log_entry)
            db.session.commit()
            
            # Check if automation has a trading pair configured
            if not automation.trading_pair:
                logger.warning(f"Automation {automation_id} does not have a trading pair configured")
                return {
                    "success": False,
                    "message": "Trading pair not configured for this automation"
                }
            
            # Get the API credentials for this automation
            credentials = ExchangeCredentials.query.filter_by(
                automation_id=automation.id,
                exchange='coinbase'
            ).first()
            
            if not credentials:
                logger.error(f"No API credentials found for automation: {automation_id}")
                return {
                    "success": False,
                    "message": "API credentials not found"
                }
            
            # Process the webhook payload
            action = payload.get('action', '').lower()
            
            # Validate action
            if action not in ['buy', 'sell']:
                logger.error(f"Invalid action in payload: {action}")
                return {
                    "success": False,
                    "message": f"Invalid action: {action}. Must be 'buy' or 'sell'."
                }
            
            # Use amount from payload or default to position_size
            amount = payload.get('amount') or payload.get('position_size')
            
            if not amount:
                logger.error("No amount or position_size specified in payload")
                return {
                    "success": False,
                    "message": "No amount or position_size specified in payload"
                }
            
            # TODO: Implement the actual trading logic with Coinbase API
            # This would typically call CoinbaseService to place the order
            
            # For now, just log the trade we would execute
            logger.info(f"Would execute {action} order for {amount} of {automation.trading_pair}")
            
            return {
                "success": True,
                "message": "Webhook processed successfully",
                "action": action,
                "amount": amount,
                "trading_pair": automation.trading_pair
            }
            
        except Exception as e:
            logger.error(f"Error processing webhook: {str(e)}", exc_info=True)
            db.session.rollback()
            return {
                "success": False,
                "message": f"Error processing webhook: {str(e)}"
            }
