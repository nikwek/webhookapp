from app import db
from app.models.webhook import WebhookLog
from app.models.automation import Automation
from app.services.coinbase_service import CoinbaseService
import json

def process_webhook(payload, automation_id):
    """
    Process incoming webhook data according to automation rules
    
    Args:
        payload (dict): The webhook payload to process
        automation_id (int): ID of the automation to use for processing
        
    Returns:
        tuple: (success, message)
    """
    try:
        # Get the automation
        automation = Automation.query.get(automation_id)
        if not automation:
            return False, "Automation not found"
            
        # Validate payload
        if not isinstance(payload, dict) or 'action' not in payload:
            return False, "Invalid payload format"
            
        # Log the webhook
        log = WebhookLog(
            automation_id=automation_id,
            payload=json.dumps(payload)
        )
        db.session.add(log)
        
        # Get trading parameters
        action = payload.get('action')
        amount = payload.get('amount')
        
        if action not in ['buy', 'sell']:
            return False, "Invalid action type"
            
        if not amount or not isinstance(amount, (int, float)):
            return False, "Invalid amount"
            
        # Execute trade
        client = CoinbaseService.get_client()
        order = client.create_market_order(
            product_id=automation.trading_pair,
            side=action,
            size=amount
        )
        
        db.session.commit()
        return True, f"Webhook processed successfully. Order ID: {order['order_id']}"
        
    except Exception as e:
        db.session.rollback()
        return False, str(e)