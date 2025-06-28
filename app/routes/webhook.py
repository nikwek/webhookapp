# app/routes/webhook.py
from flask import Blueprint, request, jsonify, send_from_directory
from flask_security import login_required, current_user
from flask_limiter import Limiter
from flask_limiter.util import get_remote_address
from app.models.webhook import WebhookLog
from app.models.automation import Automation
from app.models.trading import TradingStrategy
from app.services.webhook_processor import EnhancedWebhookProcessor as WebhookProcessor
from app import db, csrf
from sqlalchemy import or_
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

    # The identifier is passed as a query parameter, historically named 'automation_id'
    # but now used for both automations and strategies via their webhook_id.
    webhook_identifier = request.args.get('automation_id')
    
    if not webhook_identifier:
        logger.warning("Webhook request received without 'automation_id' parameter.")
        # The parameter is still named 'automation_id' for backward compatibility
        return jsonify({'error': 'Missing automation_id parameter'}), 400

    logger.info(f"Received webhook for identifier: {webhook_identifier}")

    # Parse the webhook payload
    try:
        payload = request.get_json(force=True)
        logger.info(f"Webhook payload for identifier {webhook_identifier}: {payload}")
    except Exception as e:
        logger.error(f"Failed to parse JSON payload for identifier {webhook_identifier}: {e}")
        return jsonify({'error': 'Invalid JSON payload'}), 400
    
    # Process the webhook using the updated WebhookProcessor
    processor = WebhookProcessor()
    # The processor now handles identifying the target (strategy or automation)
    # and returns a tuple of (response_dict, status_code)
    result, status_code = processor.process_webhook(identifier=webhook_identifier, payload=payload)
    
    return jsonify(result), status_code


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
    # Corrected query: Fetch logs for EITHER automations OR strategies owned by the user
    pagination = (WebhookLog.query
                 .outerjoin(Automation, WebhookLog.automation_id == Automation.automation_id)
                 .outerjoin(TradingStrategy, WebhookLog.strategy_id == TradingStrategy.id)
                 .filter(
                     or_(
                         Automation.user_id == current_user.id,
                         TradingStrategy.user_id == current_user.id
                     )
                 )
                 .order_by(WebhookLog.timestamp.desc())
                 .paginate(page=page, per_page=per_page, error_out=False, max_per_page=max_per_page))
    
    # The to_dict() method now provides a generic 'source_name'
    logs_data = [log.to_dict() for log in pagination.items]

    return jsonify({
        'logs': logs_data,
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