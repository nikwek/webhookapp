# app/models/webhook.py
from app import db
from datetime import datetime, timezone

class WebhookLog(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    timestamp = db.Column(db.DateTime(timezone=True), nullable=False)
    payload = db.Column(db.JSON)