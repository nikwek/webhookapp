# app/models/webhook.py
from app import db
from datetime import datetime
import json

class WebhookLog(db.Model):
    """Model for storing webhook execution logs"""
    __tablename__ = 'webhook_logs'
    
    id = db.Column(db.Integer, primary_key=True)
    automation_id = db.Column(db.String(36), db.ForeignKey('automations.automation_id'), nullable=False, index=True)
    payload = db.Column(db.JSON, nullable=True)
    timestamp = db.Column(db.DateTime, default=datetime.utcnow, nullable=False, index=True)
    
    # Fields to store trade execution results
    trading_pair = db.Column(db.String(20), nullable=True)
    status = db.Column(db.String(20), nullable=True)  # 'success' or 'error'
    message = db.Column(db.Text, nullable=True)
    order_id = db.Column(db.String(50), nullable=True)
    client_order_id = db.Column(db.String(36), nullable=True)
    raw_response = db.Column(db.Text, nullable=True)
    
    # Relationships
    automation = db.relationship('Automation', backref=db.backref('webhook_logs', lazy=True))
    
    def __repr__(self):
        return f'<WebhookLog {self.id} for automation {self.automation_id}>'
    
    @property
    def formatted_payload(self):
        """Return a formatted string of the payload for display"""
        if isinstance(self.payload, dict):
            return json.dumps(self.payload, indent=2)
        return str(self.payload)
    
    def to_dict(self):
        """Convert webhook log to dictionary for API response"""
        automation_name = self.automation.name if self.automation else "Unknown"
        
        # Extract values from payload if available
        action = None
        ticker = None
        message = None
        
        if self.payload:
            action = self.payload.get('action')
            ticker = self.payload.get('ticker')
            message = self.payload.get('message')
        
        # Use model fields as fallbacks
        if not ticker and self.trading_pair:
            ticker = self.trading_pair
            
        if not message and self.message:
            message = self.message
        
        return {
            'id': self.id,
            'automation_id': self.automation_id,
            'automation_name': automation_name,
            'payload': self.payload,
            'timestamp': self.timestamp.isoformat() if self.timestamp else None,
            'action': action,
            'ticker': ticker,
            'message': message,
            'status': self.status,
            'order_id': self.order_id,
            'client_order_id': self.client_order_id,  # Add this
            'raw_response': self.raw_response  # Add this
        }