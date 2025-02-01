from flask import current_app, Blueprint, render_template, jsonify, session, redirect, url_for, Response, request
from flask_login import login_required, current_user
from app.models.automation import Automation
from app.models.webhook import WebhookLog
from app import db
from flask_sse import sse
import json

# Temporary for testing
from redis import Redis
import os
# END Temporary for testing

bp = Blueprint('dashboard', __name__)

# Temporary for testing

@bp.route('/test-redis')
@login_required
def test_redis():
    redis_url = os.getenv('REDIS_URL', 'redis://localhost:6379')
    r = Redis.from_url(redis_url)
    try:
        r.ping()
        return "Redis connection successful!"
    except Exception as e:
        current_app.logger.error(f"Redis test error: {str(e)}")
        return f"Redis connection failed: {str(e)}"

@bp.route('/test-sse')
@login_required
def test_sse():
    try:
        # Test message through SSE
        sse.publish(
            {"test": "message"},
            type='test',
            channel=f'user_{current_user.id}'
        )
        return "SSE test message sent! Check browser console for incoming message."
    except Exception as e:
        current_app.logger.error(f"SSE test error: {str(e)}")
        return f"SSE publish failed: {str(e)}"
    
# END Temporary for testing

@bp.route('/dashboard')
@login_required
def dashboard():
    """Render the dashboard page for non-admin users."""
    if session.get('is_admin'):
        return redirect(url_for('admin.users'))

    user_id = current_user.id
    automations = Automation.query.filter_by(user_id=user_id).all()

    # Generate webhook URLs for each automation
    base_url = request.url_root.rstrip('/')
    for automation in automations:
        automation.webhook_url = f"{base_url}/webhook?automation_id={automation.automation_id}"

    return render_template('dashboard.html', automations=automations)

@bp.route('/api/logs')
@login_required
def get_logs():
    """Get initial logs for the current user"""
    logs = WebhookLog.query.join(Automation).filter(
        Automation.user_id == current_user.id
    ).order_by(WebhookLog.timestamp.desc()).limit(100).all()
    
    return jsonify([log.to_dict() for log in logs])

@bp.route('/clear-logs', methods=['POST'])
@login_required
def clear_logs():
    """Clear webhook logs for the current user."""
    try:
        user_id = current_user.id
        WebhookLog.query.join(Automation).filter(
            Automation.user_id == user_id
        ).delete(synchronize_session=False)
        
        db.session.commit()

        # Notify clients about the cleared logs
        sse.publish(
            {"logs": []},
            type='webhook_update',
            channel=f'user_{user_id}'
        )

        return jsonify({"success": True})
    except Exception as e:
        print(f"Error clearing logs: {e}")
        db.session.rollback()
        return jsonify({"error": str(e)}), 500

@bp.route('/settings')
@login_required
def settings():
    """Render the settings page."""
    return render_template('settings.html')