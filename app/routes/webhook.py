# app/routes/webhook.py
from flask import Blueprint, request, jsonify, Response, stream_with_context, session, send_from_directory
from flask_login import login_required
from app.models.webhook import WebhookLog
from app.models.automation import Automation
from app.services.webhook_processor import WebhookProcessor
from app import db, csrf
from datetime import datetime, timezone
import json
import time
import os
import logging

logger = logging.getLogger(__name__)

bp = Blueprint('webhook', __name__)

@bp.route('/webhook', methods=['POST'])
@csrf.exempt 
def webhook():
    automation_id = request.args.get('automation_id')
    logger.info(f"Received webhook for automation_id: {automation_id}")
    
    if not automation_id:
        return jsonify({'error': 'Missing automation_id parameter'}), 400

    automation = Automation.query.filter_by(automation_id=automation_id).first()
    logger.info(f"Found automation: {automation}")
    
    if not automation:
        return jsonify({'error': 'Automation not found'}), 404

    if not automation.is_active:
        return jsonify({'error': 'Automation is not active'}), 403

    # Parse the webhook payload
    try:
        payload = request.get_json(force=True)
        logger.info(f"Webhook payload: {payload}")
    except Exception as e:
        logger.error(f"Failed to parse JSON payload: {e}")
        return jsonify({'error': 'Invalid JSON payload'}), 400
    
    # Process the webhook using the WebhookProcessor
    processor = WebhookProcessor()
    result = processor.process_webhook(automation_id, payload)
    
    # Update last_run timestamp
    automation.last_run = datetime.now(timezone.utc)
    try:
        db.session.commit()
    except Exception as e:
        logger.error(f"Error updating last_run timestamp: {e}")
        db.session.rollback()
    
    return jsonify(result)

@bp.route('/webhook-stream')
@login_required
def webhook_stream():
    def event_stream():
        last_id = 0
        while True:
            logs = (WebhookLog.query
                   .join(Automation)
                   .filter(Automation.user_id == session['user_id'])
                   .order_by(WebhookLog.timestamp.desc())
                   .limit(100)
                   .all())
            
            if logs:
                data = [log.to_dict() for log in logs]
                yield f"data: {json.dumps(data)}\n\n"
            
            time.sleep(1)

    return Response(
        stream_with_context(event_stream()),
        mimetype='text/event-stream'
    )

@bp.route('/static/js/components/WebhookLogs.jsx')
def serve_component():
    component_dir = os.path.join(os.path.dirname(os.path.dirname(__file__)), 'static', 'js', 'components')
    return send_from_directory(component_dir, 'WebhookLogs.jsx', mimetype='text/javascript')
