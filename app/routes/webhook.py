# app/routes/webhook.py
from flask import Blueprint, request, jsonify, send_from_directory
from flask_security import login_required, current_user
from flask_limiter import Limiter
from flask_limiter.util import get_remote_address
from app.models.webhook import WebhookLog
from app.models.automation import Automation
from app.services.webhook_processor import EnhancedWebhookProcessor as WebhookProcessor
from app import db, csrf
from datetime import datetime, timezone
import os
import logging

logger = logging.getLogger(__name__)
limiter = Limiter(key_func=get_remote_address, default_limits=["200 per day", "50 per hour"])
bp = Blueprint('webhook', __name__)

@bp.route('/webhook', methods=['POST'])
@limiter.limit("60/minute", key_func=lambda: request.args.get('automation_id'))
@csrf.exempt 
def webhook():
    if request.content_length > 10 * 1024:  # 10KB limit
        return jsonify({'error': 'Payload too large'}), 413
    
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


@bp.route('/static/js/components/WebhookLogs.jsx')
def serve_component():
    component_dir = os.path.join(os.path.dirname(os.path.dirname(__file__)), 'static', 'js', 'components')
    return send_from_directory(component_dir, 'WebhookLogs.jsx', mimetype='text/javascript')

@bp.route('/api/logs')
@login_required
def get_logs():
    """API endpoint to get webhook logs with pagination"""
    page = request.args.get('page', 1, type=int)
    per_page = request.args.get('per_page', 20, type=int)
    max_per_page = 100  # Limit maximum number of items per page
    
    # Apply limits to prevent excessive resource usage
    per_page = min(per_page, max_per_page)
    
    # Get logs with pagination and optimize query
    pagination = (WebhookLog.query
                 .join(Automation)
                 .filter(Automation.user_id == current_user.id)
                 .order_by(WebhookLog.timestamp.desc())
                 .paginate(page=page, per_page=per_page, error_out=False, max_per_page=max_per_page))
    
    return jsonify({
        'logs': [log.to_dict() for log in pagination.items],
        'pagination': {
            'page': pagination.page,
            'per_page': pagination.per_page,
            'total': pagination.total,
            'pages': pagination.pages,
            'has_next': pagination.has_next,
            'has_prev': pagination.has_prev,
            'next_num': pagination.next_num,
            'prev_num': pagination.prev_num
        }
    })