from flask import Blueprint, jsonify, session, render_template, redirect, url_for
from app.models.user import User
from app.models.automation import Automation
from app.models.webhook import WebhookLog
from app import db
from functools import wraps
from datetime import datetime, timezone

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

@bp.route('/activate-automation/<automation_id>', methods=['POST'])
@admin_required
def activate_automation(automation_id):
    try:
        automation = Automation.query.filter_by(automation_id=automation_id).first()
        if not automation:
            return jsonify({"error": "Automation not found"}), 404
        
        automation.is_active = True
        db.session.commit()
        return jsonify({"success": True})
    except Exception as e:
        db.session.rollback()
        return jsonify({"error": str(e)}), 500

@bp.route('/deactivate-automation/<automation_id>', methods=['POST'])
@admin_required
def deactivate_automation(automation_id):
    try:
        automation = Automation.query.filter_by(automation_id=automation_id).first()
        if not automation:
            return jsonify({"error": "Automation not found"}), 404
        
        automation.is_active = False
        db.session.commit()
        return jsonify({"success": True})
    except Exception as e:
        db.session.rollback()
        return jsonify({"error": str(e)}), 500

@bp.route('/purge-logs/<automation_id>', methods=['POST'])
@admin_required
def purge_logs(automation_id):
    try:
        print(f"Purging logs for automation {automation_id}")  # Debug line
        result = WebhookLog.query.filter_by(automation_id=automation_id).delete()
        print(f"Deleted {result} logs")  # Debug line
        db.session.commit()
        return jsonify({"success": True})
    except Exception as e:
        print(f"Error purging logs: {e}")  # Debug line
        db.session.rollback()
        return jsonify({"error": str(e)}), 500

@bp.route('/delete-automation/<automation_id>', methods=['POST'])
@admin_required
def delete_automation(automation_id):
    try:
        print(f"Deleting automation {automation_id}")  # Debug line
        # First delete all logs
        log_result = WebhookLog.query.filter_by(automation_id=automation_id).delete()
        print(f"Deleted {log_result} logs")  # Debug line
        
        # Then delete the automation
        automation = Automation.query.filter_by(automation_id=automation_id).first()
        if automation:
            db.session.delete(automation)
            db.session.commit()
            print(f"Successfully deleted automation")  # Debug line
            return jsonify({"success": True})
        return jsonify({"error": "Automation not found"}), 404
    except Exception as e:
        print(f"Error deleting automation: {e}")  # Debug line
        db.session.rollback()
        return jsonify({"error": str(e)}), 500

@bp.route('/reset-user/<int:user_id>', methods=['POST'])
@admin_required
def reset_user(user_id):
    try:
        user = User.query.get(user_id)
        if not user:
            return jsonify({"error": "User not found"}), 404
        
        # Get all automation IDs for this user
        automation_ids = [a.automation_id for a in user.automations]
        
        # Delete all logs for all automations
        if automation_ids:
            WebhookLog.query.filter(WebhookLog.automation_id.in_(automation_ids)).delete()
        
        db.session.commit()
        return jsonify({"success": True})
    except Exception as e:
        db.session.rollback()
        return jsonify({"error": str(e)}), 500

@bp.route('/suspend-user/<int:user_id>', methods=['POST'])
@admin_required
def suspend_user(user_id):
    try:
        user = User.query.get(user_id)
        if not user:
            return jsonify({"error": "User not found"}), 404
        
        user.is_suspended = True
        db.session.commit()
        return jsonify({"success": True})
    except Exception as e:
        db.session.rollback()
        return jsonify({"error": str(e)}), 500

@bp.route('/unsuspend-user/<int:user_id>', methods=['POST'])
@admin_required
def unsuspend_user(user_id):
    try:
        user = User.query.get(user_id)
        if not user:
            return jsonify({"error": "User not found"}), 404
        
        user.is_suspended = False
        db.session.commit()
        return jsonify({"success": True})
    except Exception as e:
        db.session.rollback()
        return jsonify({"error": str(e)}), 500
    
