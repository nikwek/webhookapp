# app/models/webhook.py
from app import db
from datetime import datetime, timezone

class WebhookLog(db.Model):
    __tablename__ = 'webhook_logs'
    
    id = db.Column(db.Integer, primary_key=True)
    automation_id = db.Column(db.String(32), db.ForeignKey('automations.automation_id'))
    payload = db.Column(db.JSON)
    timestamp = db.Column(db.DateTime(timezone=True), nullable=False)
    
    # Add relationship to get automation details
    automation = db.relationship('Automation', backref='webhook_logs')

    def to_dict(self):
        return {
            "id": self.id,
            "timestamp": self.timestamp.strftime("%Y-%m-%d %H:%M:%S"),
            "automation_name": self.automation.name if self.automation else "Unknown",
            "automation_id": self.automation_id,
            "payload": self.payload
        }