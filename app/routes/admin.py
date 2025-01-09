from flask import Blueprint, jsonify, session, render_template
from app.models.user import User
from app.models.automation import Automation
from app.models.webhook import WebhookLog
from app import db
from datetime import datetime, timezone
from functools import wraps

bp = Blueprint('admin', __name__, url_prefix='/admin')

def admin_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if not session.get('is_admin'):
            return jsonify({"error": "Unauthorized"}), 403
        return f(*args, **kwargs)
    return decorated_function

@bp.route('/users')
@admin_required
def users():
    users = User.query.all()
    return render_template('users.html', users=users)

@bp.route('/logs/<automation_id>')
@admin_required
def get_logs(automation_id):
    logs = WebhookLog.query\
        .filter_by(automation_id=automation_id)\
        .order_by(WebhookLog.timestamp.desc())\
        .all()
    
    return jsonify({
        "logs": [{
            "timestamp": log.timestamp.strftime("%Y-%m-%d %H:%M:%S"),
            "payload": log.payload
        } for log in logs]
    })

@bp.route('/deactivate-automation/<automation_id>', methods=['POST'])
@admin_required
def deactivate_automation(automation_id):
    automation = Automation.query.filter_by(automation_id=automation_id).first()
    if not automation:
        return jsonify({"error": "Automation not found"}), 404
    
    automation.is_active = False
    db.session.commit()
    return jsonify({"success": True})

@bp.route('/reset-user/<int:user_id>', methods=['POST'])
@admin_required
def reset_user(user_id):
    user = User.query.get(user_id)
    if not user or user.is_admin:
        return jsonify({"error": "User not found or cannot reset admin"}), 404
    
    # Deactivate all user's automations
    Automation.query.filter_by(user_id=user_id)\
        .update({"is_active": False})
    
    db.session.commit()
    return jsonify({"success": True})