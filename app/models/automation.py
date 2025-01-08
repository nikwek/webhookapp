# app/models/automation.py
import secrets
from app import db
from datetime import datetime, timezone

class Automation(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    automation_id = db.Column(db.String(8), unique=True, nullable=False)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    created_at = db.Column(db.DateTime(timezone=True), default=datetime.now(timezone.utc))
    is_active = db.Column(db.Boolean, default=True)

    @staticmethod
    def generate_automation_id():
        while True:
            automation_id = secrets.token_urlsafe(6)[:8]
            if not Automation.query.filter_by(automation_id=automation_id).first():
                return automation_id