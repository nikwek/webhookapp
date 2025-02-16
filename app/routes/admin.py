# app/routes/admin.py
from flask import Blueprint, jsonify, session, render_template, redirect, url_for, request, current_app
from app.models.user import User
from app.models.automation import Automation
from app.models.webhook import WebhookLog
from app.models.exchange_credentials import ExchangeCredentials
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
@bp.route('/api/users/<int:user_id>/reset', methods=['POST'])
@admin_required
def reset_user(user_id):
    try:
        user = User.query.get_or_404(user_id)
        
        # Delete all logs and automations but keep the user
        automation_ids = [a.automation_id for a in user.automations]
        if automation_ids:
            # Delete associated credentials
            ExchangeCredentials.query.filter(
                ExchangeCredentials.automation_id.in_(automation_ids)
            ).delete(synchronize_session=False)
            
            # Delete logs
            WebhookLog.query.filter(
                WebhookLog.automation_id.in_(automation_ids)
            ).delete(synchronize_session=False)
            
            # Delete automations
            Automation.query.filter(
                Automation.automation_id.in_(automation_ids)
            ).delete(synchronize_session=False)
            
        db.session.commit()
        return jsonify({"success": True})
    except Exception as e:
        db.session.rollback()
        current_app.logger.error(f"Error resetting user: {str(e)}")
        return jsonify({"error": str(e)}), 500

@bp.route('/api/users/<int:user_id>/suspend', methods=['POST'])
@admin_required
def suspend_user(user_id):
    try:
        user = User.query.get_or_404(user_id)
        user.is_suspended = not user.is_suspended
        db.session.commit()
        return jsonify({"success": True, "is_suspended": user.is_suspended})
    except Exception as e:
        db.session.rollback()
        current_app.logger.error(f"Error suspending user: {str(e)}")
        return jsonify({"error": str(e)}), 500

@bp.route('/api/users/<int:user_id>/delete', methods=['POST'])
@admin_required
def delete_user(user_id):
    try:
        user = User.query.get_or_404(user_id)
        
        # Delete all associated data
        automation_ids = [a.automation_id for a in user.automations]
        if automation_ids:
            # Delete credentials
            ExchangeCredentials.query.filter(
                ExchangeCredentials.automation_id.in_(automation_ids)
            ).delete(synchronize_session=False)
            
            # Delete logs
            WebhookLog.query.filter(
                WebhookLog.automation_id.in_(automation_ids)
            ).delete(synchronize_session=False)
            
            # Delete automations
            Automation.query.filter(
                Automation.automation_id.in_(automation_ids)
            ).delete(synchronize_session=False)
        
        # Finally delete the user
        db.session.delete(user)
        db.session.commit()
        return jsonify({"success": True})
    except Exception as e:
        db.session.rollback()
        current_app.logger.error(f"Error deleting user: {str(e)}")
        return jsonify({"error": str(e)}), 500

@bp.route('/api/automations/<automation_id>/toggle', methods=['POST'])
@admin_required
def toggle_automation(automation_id):
    try:
        automation = Automation.query.filter_by(automation_id=automation_id).first()
        if not automation:
            return jsonify({"error": "Automation not found"}), 404

        automation.is_active = not automation.is_active
        db.session.commit()

        log_message = f"Automation '{automation.name}' has been {'activated' if automation.is_active else 'deactivated'} by admin."
        current_app.logger.info(log_message)

        return jsonify({"success": True, "is_active": automation.is_active})
    except Exception as e:
        db.session.rollback()
        current_app.logger.error(f"Error toggling automation: {str(e)}")
        return jsonify({"error": str(e)}), 500

@bp.route('/api/automations/<automation_id>/purge', methods=['POST'])
@admin_required
def purge_automation_logs(automation_id):
    try:
        WebhookLog.query.filter_by(automation_id=automation_id).delete()
        db.session.commit()
        return jsonify({"success": True})
    except Exception as e:
        db.session.rollback()
        current_app.logger.error(f"Error purging logs: {str(e)}")
        return jsonify({"error": str(e)}), 500

@bp.route('/api/automations/<automation_id>/delete', methods=['POST'])
@admin_required
def delete_automation(automation_id):
    try:
        # Delete associated credentials first
        ExchangeCredentials.query.filter_by(automation_id=automation_id).delete()
        
        # Delete the automation (logs will remain)
        automation = Automation.query.filter_by(automation_id=automation_id).first()
        if automation:
            db.session.delete(automation)
            db.session.commit()
            return jsonify({"success": True})
        return jsonify({"error": "Automation not found"}), 404
    except Exception as e:
        db.session.rollback()
        current_app.logger.error(f"Error deleting automation: {str(e)}")
        return jsonify({"error": str(e)}), 500