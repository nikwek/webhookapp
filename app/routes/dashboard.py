from flask import (
    Blueprint, render_template, jsonify, session,
    redirect, url_for, Response, request
)
from flask_login import login_required, current_user
from app.models.automation import Automation
from app.models.webhook import WebhookLog
from app import db
import time

bp = Blueprint('dashboard', __name__)


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
        automation.webhook_url = (
            f"{base_url}/webhook?automation_id={automation.automation_id}"
        )

    # Fetch the latest logs
    logs = WebhookLog.query.join(Automation).filter(
        Automation.user_id == user_id
    ).order_by(WebhookLog.timestamp.desc()).limit(100).all()

    # Convert logs to dictionary format
    initial_logs = [log.to_dict() for log in logs]

    return render_template('dashboard.html', 
                           automations=automations, 
                           initial_logs=initial_logs)


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