# test_webhook_processor.py
# Run this script to test webhook processing without actually triggering a webhook

import os
import sys
from flask import Flask
from flask_sqlalchemy import SQLAlchemy
from datetime import datetime, timezone
import json
import logging

# Set up logging
logging.basicConfig(level=logging.INFO, 
                   format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

# Add app directory to path so we can import from app
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

# Import after setting path
from app import create_app, db
from app.models.automation import Automation
from app.services.webhook_processor import WebhookProcessor

def test_webhook_processor():
    """Test the webhook processor with a sample payload"""
    app = create_app()
    
    with app.app_context():
        # Get an existing automation ID from the database
        automation = Automation.query.filter_by(is_active=True).first()
        
        if not automation:
            logger.error("No active automations found in the database.")
            return
        
        automation_id = automation.automation_id
        logger.info(f"Using automation: {automation.name} (ID: {automation_id})")
        
        # Check if the automation has a portfolio and trading pair
        if not automation.portfolio_id:
            logger.error(f"Automation {automation_id} has no portfolio connected.")
            return
            
        if not automation.trading_pair:
            logger.error(f"Automation {automation_id} has no trading pair set.")
            return
        
        # Sample payload for a buy signal
        buy_payload = {
            "action": "buy",
            "timestamp": datetime.now(timezone.utc).isoformat()
        }
        
        # Sample payload for a sell signal
        sell_payload = {
            "action": "sell",
            "timestamp": datetime.now(timezone.utc).isoformat()
        }
        
        # Choose which action to test
        test_action = "sell"  # Change to "sell" to test sell orders
        test_payload = buy_payload if test_action == "buy" else sell_payload
        
        logger.info(f"Testing {test_action.upper()} webhook with payload:")
        logger.info(json.dumps(test_payload, indent=2))
        
        # Process the webhook
        processor = WebhookProcessor()
        result = processor.process_webhook(automation_id, test_payload)
        
        logger.info("Webhook processing result:")
        logger.info(json.dumps(result, indent=2))

if __name__ == "__main__":
    test_webhook_processor()
