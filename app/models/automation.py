# app/models/automation.py
import uuid
from datetime import datetime
from app import db
import json

class Automation(db.Model):
    __tablename__ = 'automations'
    
    id = db.Column(db.Integer, primary_key=True)
    # Add default value for automation_id
    automation_id = db.Column(db.String(40), unique=True, index=True, 
                              default=lambda: str(uuid.uuid4()))
    user_id = db.Column(db.Integer)
    name = db.Column(db.String(100), nullable=False)
    is_active = db.Column(db.Boolean, default=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    last_run = db.Column(db.DateTime, nullable=True)
    portfolio_id = db.Column(db.Integer, nullable=True)
    # Add trading pair field
    trading_pair = db.Column(db.String(20), nullable=True)
    _template = db.Column(db.Text, default='{}')
    
    @staticmethod
    def generate_automation_id():
        return str(uuid.uuid4())
    
    @property
    def template(self):
        if self._template:
            return json.loads(self._template)
        return {}
    
    @template.setter
    def template(self, template):
        self._template = json.dumps(template)


# Alias for backward compatibility with tests
AutomationStrategy = Automation