# app/routes/webhook.py
from flask import Blueprint, request, jsonify
from app.models.webhook import WebhookLog
from app.models.automation import Automation
from app import db
from datetime import datetime, timezone
import json

bp = Blueprint('webhook', __name__)

@bp.route('/webhook', methods=['POST'])
def webhook():
    print("Received webhook:", request.json)
    automation_id = request.json.get('automation_id')
    
    automation = Automation.query.filter_by(
        automation_id=automation_id,
        is_active=True
    ).first()
    
    if not automation:
        print(f"Automation {automation_id} not found or inactive")
        return jsonify({"error": "Invalid or inactive automation"}), 404

    # Convert payload to string with sorted keys and no spaces
    payload_str = json.dumps(request.json, sort_keys=True, separators=(',', ':'))
    # Convert back to dict to ensure consistent formatting
    payload = json.loads(payload_str)

    log = WebhookLog(
        timestamp=datetime.now(timezone.utc),
        payload=payload,
        automation_id=automation_id
    )
    db.session.add(log)
    db.session.commit()
    print(f"Webhook logged with id: {log.id}")
    return jsonify({"message": "Webhook received"})