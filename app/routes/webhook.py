# app/routes/webhook.py
from flask import Blueprint, request, jsonify
from app.models.webhook import WebhookLog
from app import db
from datetime import datetime, timezone
import json

bp = Blueprint('webhook', __name__)

@bp.route('/webhook', methods=['POST'])
def webhook():
    receipt_time = datetime.now(timezone.utc)
    
    # Standardize JSON formatting by parsing and re-stringifying
    payload = json.loads(json.dumps(request.json))
    
    log = WebhookLog(
        timestamp=receipt_time,
        payload=payload
    )
    db.session.add(log)
    db.session.commit()
    return jsonify({"message": "Webhook received."})
