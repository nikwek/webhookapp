# app/models/automation.py
import secrets
from app import db
from datetime import datetime, timezone
from app.models.user import User

class Automation(db.Model):
    __tablename__ = 'automations'
    
    id = db.Column(db.Integer, primary_key=True)
    automation_id = db.Column(db.String(32), unique=True, nullable=False)
    name = db.Column(db.String(100), nullable=False)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    is_active = db.Column(db.Boolean, default=True)
    last_run = db.Column(db.DateTime, default=None)
    created_at = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc))
    template = db.Column(db.JSON, default={})

    # Add the relationship
    user = db.relationship('User', backref=db.backref('automations', lazy=True))

    @staticmethod
    def generate_automation_id():
        while True:
            automation_id = secrets.token_urlsafe(6)[:8]
            if not Automation.query.filter_by(automation_id=automation_id).first():
                return automation_id
