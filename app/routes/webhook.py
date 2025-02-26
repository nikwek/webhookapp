# app/routes/webhook.py
from flask import Blueprint, request, jsonify, Response, stream_with_context, session, send_from_directory
from flask_login import login_required
from app.models.webhook import WebhookLog
from app.models.automation import Automation
from app import db
from datetime import datetime, timezone
import json
import time
import os


bp = Blueprint('webhook', __name__)

# app/routes/webhook.py
@bp.route('/webhook', methods=['POST'])
def webhook():
    automation_id = request.args.get('automation_id')
    logger.debug(f"Received webhook for automation_id: {automation_id}")
    
    if not automation_id:
        return jsonify({'error': 'Missing automation_id parameter'}), 400

    automation = Automation.query.filter_by(automation_id=automation_id).first()
    logger.debug(f"Found automation: {automation}")
    
    if not automation:
        return jsonify({'error': 'Automation not found'}), 404

    if not automation.is_active:
        return jsonify({'error': 'Automation is not active'}), 403

    # Store the webhook payload
    payload = request.get_json(force=True)
    logger.debug(f"Webhook payload: {payload}")
    
    log = WebhookLog(
        automation_id=automation_id,
        payload=payload,
        timestamp=datetime.now(timezone.utc)
    )
    db.session.add(log)
    
    # Update last_run timestamp
    automation.last_run = datetime.now(timezone.utc)
    
    try:
        db.session.commit()
        logger.debug("Successfully stored webhook")
        
        # Process the webhook to extract trading parameters
        from app.services.webhook_processor import WebhookProcessor
        from app.services.trading_service import TradingService
        
        processed_data, status_code = WebhookProcessor.process_webhook(automation_id, payload)
        
        if status_code != 200:
            return jsonify(processed_data), status_code
            
        # Execute the trade
        result, status_code = TradingService.execute_trade(processed_data)
        
        return jsonify(result), status_code
        
    except Exception as e:
        logger.error(f"Error handling webhook: {str(e)}")
        db.session.rollback()
        return jsonify({'error': str(e)}), 500

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