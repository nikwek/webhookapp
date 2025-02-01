# app/routes/webhook.py
from flask import Blueprint, request, jsonify, current_app
from flask_sse import sse
from app.models.webhook import WebhookLog
from app.models.automation import Automation
from app import db
from datetime import datetime
import json

bp = Blueprint('webhook', __name__)

@bp.route('/webhook', methods=['POST'])
def receive_webhook():
    try:
        automation_id = request.args.get('automation_id')
        if not automation_id:
            return jsonify({"error": "Missing automation_id parameter"}), 400

        automation = Automation.query.filter_by(automation_id=automation_id).first()
        if not automation:
            return jsonify({"error": "Automation not found"}), 404

        if not automation.is_active:
            return jsonify({"error": "Automation is inactive"}), 403

        payload = request.get_json()
        
        # Create webhook log
        log = WebhookLog(
            automation_id=automation.id,
            payload=payload,
            timestamp=datetime.utcnow()
        )
        db.session.add(log)
        db.session.commit()

        # Get updated logs for this user and emit event
        logs = WebhookLog.query.join(Automation).filter(
            Automation.user_id == automation.user_id
        ).order_by(WebhookLog.timestamp.desc()).limit(100).all()

        # Emit event with updated logs
        with current_app.app_context():
            sse.publish(
                {
                    "logs": [log.to_dict() for log in logs]
                },
                type='webhook_update',
                channel=f'user_{automation.user_id}'
            )

        return jsonify({"status": "success"}), 200

    except Exception as e:
        current_app.logger.error(f"Error processing webhook: {str(e)}")
        db.session.rollback()
        return jsonify({"error": "Internal server error"}), 500