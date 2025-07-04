#!/usr/bin/env python
# Script to check webhook logs for strategy and exchange names

import os
import sys
from datetime import datetime
from app import create_app, db
from app.models.webhook import WebhookLog

# Create the Flask app with the development configuration
app = create_app()

# Use the application context
with app.app_context():
    # Query the most recent 10 webhook logs
    logs = WebhookLog.query.order_by(WebhookLog.timestamp.desc()).limit(10).all()
    
    print(f"Found {len(logs)} recent webhook logs\n")
    
    # Print header
    print(f"{'ID':<5} | {'Timestamp':<25} | {'Strategy Name':<30} | {'Exchange Name':<20}")
    print("-" * 85)
    
    # Print each log
    for log in logs:
        timestamp = log.timestamp.strftime('%Y-%m-%d %H:%M:%S') if log.timestamp else 'None'
        strategy_name = log.strategy_name or 'None'
        exchange_name = log.exchange_name or 'None'
        print(f"{log.id:<5} | {timestamp:<25} | {strategy_name:<30} | {exchange_name:<20}")
