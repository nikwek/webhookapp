# app/services/webhook_processor.py
from app.models.automation import Automation
from app.models.webhook import WebhookLog
from app import db
import logging
from datetime import datetime, timezone

logger = logging.getLogger(__name__)

class WebhookProcessor:
    @staticmethod
    def process_webhook(automation_id, payload):
        """
        Process incoming webhook from TradingView
        
        Args:
            automation_id (str): The automation ID
            payload (dict): The webhook payload
            
        Returns:
            tuple: (processed_data, status_code)
        """
        # Find the automation
        automation = Automation.query.filter_by(automation_id=automation_id).first()
        if not automation:
            logger.error(f"Automation not found: {automation_id}")
            return {"error": "Automation not found"}, 404
        
        # Extract trading parameters from payload
        try:
            # Assuming payload has something like:
            # {"action": "buy", "symbol": "BTC-USD", "amount": 100}
            action = payload.get('action', '').lower()  # 'buy' or 'sell'
            symbol = payload.get('symbol')
            amount = payload.get('amount')
            
            # Validate the extracted parameters
            if not action or action not in ['buy', 'sell']:
                logger.error(f"Invalid action in payload: {action}")
                return {"error": "Invalid action. Must be 'buy' or 'sell'"}, 400
                
            if not symbol:
                logger.error("Missing symbol in payload")
                return {"error": "Missing symbol parameter"}, 400
                
            if not amount:
                logger.error("Missing amount in payload")
                return {"error": "Missing amount parameter"}, 400
                
            try:
                amount = float(amount)
                if amount <= 0:
                    raise ValueError("Amount must be positive")
            except ValueError as e:
                logger.error(f"Invalid amount in payload: {amount}")
                return {"error": f"Invalid amount: {str(e)}"}, 400
            
            # Create processed data structure
            processed_data = {
                "automation_id": automation_id,
                "action": action,
                "symbol": symbol,
                "amount": amount,
                "timestamp": datetime.now(timezone.utc).isoformat()
            }
            
            return processed_data, 200
            
        except Exception as e:
            logger.error(f"Error processing webhook: {str(e)}")
            return {"error": f"Error processing webhook: {str(e)}"}, 500