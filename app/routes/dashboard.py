# app/routes/dashboard.py
from flask import Blueprint, render_template, jsonify, session, redirect, url_for
from flask_login import login_required
from app.models.webhook import WebhookLog
from app.models.automation import Automation
from app import db

bp = Blueprint('dashboard', __name__)

@bp.route('/')
@login_required
def dashboard():
    """Render the dashboard page for non-admin users."""
    if session.get('is_admin'):
        return redirect(url_for('admin.users'))

    user_id = session.get('user_id')
    automations = Automation.query.filter_by(user_id=user_id).all()
    logs = WebhookLog.query.join(Automation).filter(
        Automation.user_id == user_id
    ).order_by(WebhookLog.timestamp.desc()).limit(100).all()

    return render_template('dashboard.html', automations=automations, logs=logs)

@bp.route('/clear-logs', methods=['POST'])
@login_required
def clear_logs():
    """Clear webhook logs for the current user."""
    try:
        user_id = session.get('user_id')
        if not user_id:
            return jsonify({"error": "Unauthorized"}), 403
            
        # Delete logs for all automations owned by the user
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