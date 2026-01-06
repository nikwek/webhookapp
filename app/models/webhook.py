from app import db
from sqlalchemy import Column, Integer, String, Text, DateTime, ForeignKey
from sqlalchemy.orm import relationship
from datetime import datetime
import json


def normalize_trade_status(status, trade_result=None):
    """
    Normalize trade status for consistent display across UI and emails.
    
    CCXT returns 'closed' for successfully filled orders, but we want to show 'success'
    for better user understanding. Coinbase returns 'open' for market orders that
    are effectively complete but still settling.
    
    Args:
        status: Raw status string from exchange/trade result
        trade_result: Optional trade result dict to check for completion indicators
        
    Returns:
        Normalized status string ('success', 'error', or original status)
    """
    if not status:
        return status
    
    status_lower = str(status).lower()
    
    # Normalize 'closed' to 'success' (CCXT unified status for filled orders)
    if status_lower == 'closed':
        return 'success'
    
    # Handle Coinbase 'open' status for effectively completed market orders
    if status_lower == 'open' and trade_result:
        # Check if trade has significant fill percentage (>95%) indicating completion
        if isinstance(trade_result, dict):
            raw_order = trade_result.get('raw_order', {})
            info = raw_order.get('info', {})
            
            # Check completion percentage from Coinbase
            completion_pct = info.get('completion_percentage')
            if completion_pct:
                try:
                    completion_float = float(completion_pct)
                    if completion_float > 95.0:  # >95% filled = effectively complete
                        return 'success'
                except (ValueError, TypeError):
                    pass
            
            # Also check if we have filled amount and it's substantial
            filled = raw_order.get('filled')
            if filled and float(filled) > 0:
                return 'success'
    
    # Keep other statuses as-is
    return status

class WebhookLog(db.Model):
    idempotency_hash = Column(String(64), index=True, nullable=True)  # Hash of the payload for idempotency
    """Model for storing webhook execution logs"""
    __tablename__ = 'webhook_logs'
    
    id = Column(Integer, primary_key=True)
    
    # A log can belong to an old Automation or a new Trading Strategy
    automation_id = db.Column(db.String(36), db.ForeignKey('automations.automation_id'), nullable=True, index=True)
    strategy_id = db.Column(db.Integer, db.ForeignKey('trading_strategies.id'), nullable=True, index=True)
    target_type = db.Column(db.String(20), nullable=True, index=True) # 'automation' or 'strategy'

    payload = db.Column(db.JSON, nullable=True)
    timestamp = db.Column(db.DateTime, default=datetime.utcnow, nullable=False, index=True)
    
    # Fields to store trade execution results
    trading_pair = db.Column(db.String(20), nullable=True)
    status = db.Column(db.String(20), nullable=True)  # 'success' or 'error'
    message = db.Column(db.Text, nullable=True)
    order_id = db.Column(db.String(50), nullable=True)
    client_order_id = db.Column(db.String(36), nullable=True)
    raw_response = db.Column(db.Text, nullable=True)
    
    # Store strategy and exchange names directly for better historical tracking
    strategy_name = db.Column(db.String(100), nullable=True)
    exchange_name = db.Column(db.String(50), nullable=True)
    
    # Relationships - using passive_deletes to preserve logs when strategies/automations are deleted
    automation = db.relationship('Automation', backref=db.backref('webhook_logs', lazy=True), passive_deletes=True)
    strategy = db.relationship('TradingStrategy', backref=db.backref('webhook_logs', lazy=True), passive_deletes=True)

    def __repr__(self):
        if self.automation_id:
            return f'<WebhookLog {self.id} for automation {self.automation_id}>'
        elif self.strategy_id:
            return f'<WebhookLog {self.id} for strategy {self.strategy_id}>'
        return f'<WebhookLog {self.id}>'
    
    @property
    def formatted_payload(self):
        """Return a formatted string of the payload for display"""
        if isinstance(self.payload, dict):
            return json.dumps(self.payload, indent=2)
        return str(self.payload)
    
    def to_dict(self):
        """Convert webhook log to dictionary for API response"""
        source_name = "Unknown"
        if self.automation:
            source_name = self.automation.name
        elif self.strategy:
            source_name = self.strategy.name
        payload_dict = {}
        if self.payload and isinstance(self.payload, str):
            try:
                payload_dict = json.loads(self.payload)
            except json.JSONDecodeError:
                payload_dict = {'error': 'Invalid JSON in payload'}
        elif self.payload:
            payload_dict = self.payload

        response_dict = {}
        if self.raw_response and isinstance(self.raw_response, str):
            try:
                response_dict = json.loads(self.raw_response)
            except json.JSONDecodeError:
                response_dict = {'error': 'Invalid JSON in response'}
        elif self.raw_response:
            response_dict = self.raw_response
        action = payload_dict.get('action')
        ticker = payload_dict.get('ticker')
        message = payload_dict.get('message')
        
        # Use model fields as fallbacks
        if not ticker and self.trading_pair:
            ticker = self.trading_pair
            
        if not message and self.message:
            message = self.message
        
        # Debug output for exchange name
        actual_exchange = self.exchange_name if self.exchange_name else 'None'
        
        result = {
            'id': self.id,
            'automation_id': self.automation_id,
            'strategy_id': self.strategy_id,
            'source_name': source_name,
            # Store raw exchange name plus debug information
            'strategy_name': self.strategy_name if self.strategy_name else 'Unknown',
            'exchange_name': actual_exchange,  # Return the actual value, not 'Unknown'
            'payload': payload_dict,
            'timestamp': self.timestamp.isoformat() if self.timestamp else None,
            'action': action,
            'ticker': ticker,
            'information': message,
            'status': normalize_trade_status(self.status),
            'order_id': self.order_id,
            'client_order_id': self.client_order_id,
            'raw_response': response_dict,
            # Add debug information
            '_debug': {
                'raw_exchange_name': actual_exchange,
                'id': self.id
            }
        }
        return result