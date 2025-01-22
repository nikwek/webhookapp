from flask import Blueprint, jsonify, session, render_template, redirect, url_for, request
from app.models.user import User
from app.models.automation import Automation
from app.models.webhook import WebhookLog
from app import db
from functools import wraps
from datetime import datetime, timezone
from flask_login import login_required

bp = Blueprint('admin', __name__, url_prefix='/admin')


def admin_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if not session.get('is_admin'):
            return jsonify({"error": "Unauthorized"}), 403

        # Get the current user
        user = User.query.get(session.get('user_id'))
        if user and user.require_password_change:
            return redirect(url_for('auth.change_password'))

        return f(*args, **kwargs)
    return decorated_function


@bp.route('/')
@admin_required
def index():
    return redirect(url_for('admin.users'))


@bp.route('/users')
@admin_required
def users():
    search = request.args.get('search', '')
    query = User.query
    if search:
        query = query.filter(User.username.ilike(f'%{search}%'))
    users = query.all()
    return render_template('admin/users.html', users=users)


@bp.route('/automations')
@admin_required
def automations():
    automations = Automation.query.join(User).all()
    return render_template('admin/automations.html', automations=automations)

@bp.route('/settings')
@admin_required
def settings():
    return render_template('admin/settings.html')

# API endpoints for user management
@bp.route('/api/user/<int:user_id>/reset', methods=['POST'])
@admin_required
def reset_user(user_id):
    try:
        user = User.query.get_or_404(user_id)
        # Delete all logs for user's automations
        automation_ids = [a.automation_id for a in user.automations]
        if automation_ids:
            WebhookLog.query.filter(WebhookLog.automation_id.in_(automation_ids)).delete()
        db.session.commit()
        return jsonify({"success": True})
    except Exception as e:
        db.session.rollback()
        return jsonify({"error": str(e)}), 500

@bp.route('/api/user/<int:user_id>/suspend', methods=['POST'])
@admin_required
def suspend_user(user_id):
    try:
        user = User.query.get_or_404(user_id)
        user.is_suspended = not user.is_suspended
        db.session.commit()
        return jsonify({"success": True})
    except Exception as e:
        db.session.rollback()
        return jsonify({"error": str(e)}), 500

@bp.route('/api/user/<int:user_id>/delete', methods=['POST'])
@admin_required
def delete_user(user_id):
    try:
        user = User.query.get_or_404(user_id)
        # Delete all associated logs and automations
        automation_ids = [a.automation_id for a in user.automations]
        if automation_ids:
            WebhookLog.query.filter(WebhookLog.automation_id.in_(automation_ids)).delete()
        for automation in user.automations:
            db.session.delete(automation)
        db.session.delete(user)
        db.session.commit()
        return jsonify({"success": True})
    except Exception as e:
        db.session.rollback()
        return jsonify({"error": str(e)}), 500

from app import db
from app.models.automation import Automation
from flask import Blueprint, jsonify, session, render_template, redirect, url_for, request
@admin_required
def toggle_automation(automation_id):
    try:
        automation = Automation.query.filter_by(automation_id=automation_id).first()
        if not automation:
            return jsonify({"error": "Automation not found"}), 404

        automation.is_active = not automation.is_active
        db.session.commit()

        # Add a log entry for the status change
        log_message = f"Automation '{automation.name}' has been {'activated' if automation.is_active else 'deactivated'}."
        current_app.logger.info(log_message)

        return jsonify({"success": True, "is_active": automation.is_active})
    except Exception as e:
        db.session.rollback()
        current_app.logger.error(f"Error toggling automation: {str(e)}")
        return jsonify({"error": str(e)}), 500

@bp.route('/api/automation/<automation_id>/purge', methods=['POST'])
@admin_required
def purge_automation_logs(automation_id):
    try:
        WebhookLog.query.filter_by(automation_id=automation_id).delete()
        db.session.commit()
        return jsonify({"success": True})
    except Exception as e:
        db.session.rollback()
        return jsonify({"error": str(e)}), 500

@bp.route('/api/automation/<automation_id>/delete', methods=['POST'])
@admin_required
def delete_automation(automation_id):
    try:
        # First delete all logs
        WebhookLog.query.filter_by(automation_id=automation_id).delete()
        # Then delete the automation
        automation = Automation.query.filter_by(automation_id=automation_id).first()
        if automation:
            db.session.delete(automation)
            db.session.commit()
            return jsonify({"success": True})
        return jsonify({"error": "Automation not found"}), 404
    except Exception as e:
        db.session.rollback()
        return jsonify({"error": str(e)}), 500
    

@bp.route('/admin/dashboard')
@login_required
@admin_required
def admin_dashboard():
    """Redirect admin users directly to the users page."""
    return redirect(url_for('admin.users'))

@bp.route('/admin/users')
@login_required
@admin_required
def admin_users():
    search = request.args.get('search', '')
    query = User.query
    if search:
        query = query.filter(User.username.ilike(f'%{search}%'))
    users = query.all()
    return render_template('admin/users.html', users=users)

@bp.route('/admin/automations')
@login_required
@admin_required
def admin_automations():
    automations = Automation.query.join(User).all()
    return render_template('admin/automations.html', automations=automations)
    
