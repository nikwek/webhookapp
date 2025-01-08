# app/routes/webhook.py
from flask import Blueprint, request, jsonify
from app.models.webhook import WebhookLog
from app import db
from datetime import datetime, timezone
import json

bp = Blueprint('webhook', __name__)

@bp.route('/webhook', methods=['POST'])
def webhook():
    payload = request.json
    if not payload or 'automation_id' not in payload:
        return jsonify({"error": "Missing automation_id"}), 400

    automation = Automation.query.filter_by(
        automation_id=payload['automation_id'],
        is_active=True
    ).first()
    if not automation:
        return jsonify({"error": "Invalid automation_id"}), 404

    log = WebhookLog(
        timestamp=datetime.now(timezone.utc),
        payload=payload,
        automation_id=automation.automation_id
    )
    db.session.add(log)
    db.session.commit()
    return jsonify({"message": "Webhook received"})