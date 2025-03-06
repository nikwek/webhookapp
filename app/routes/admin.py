# app/routes/admin.py
from flask import Blueprint, jsonify, session, render_template, redirect, url_for, request
from app.models.user import User
from app.models.automation import Automation
from app.models.webhook import WebhookLog
from app import db
from functools import wraps
from datetime import datetime, timezone
from flask_security import roles_required, login_required

bp = Blueprint('admin', __name__, url_prefix='/admin')


@bp.route('/')
@roles_required('admin') 
def index():
    return redirect(url_for('admin.users'))


@bp.route('/users')
@roles_required('admin') 
def users():
    search = request.args.get('search', '')
    query = User.query
    if search:
        query = query.filter(User.username.ilike(f'%{search}%'))
    users = query.all()
    return render_template('admin/users.html', users=users)


@bp.route('/automations')
@roles_required('admin')
def automations():
    # Join with explicit conditions
    automations = db.session.query(Automation, User).\
        join(User, Automation.user_id == User.id).all()
    
    # Process results to include user information
    formatted_automations = []
    for automation, user in automations:
        automation.user = user  # Attach user object
        formatted_automations.append(automation)
    
    return render_template('admin/automations.html', automations=formatted_automations)


@bp.route('/settings')
@roles_required('admin') 
def settings():
    return render_template('admin/settings.html')

# API endpoints for user management
@bp.route('/api/user/<int:user_id>/reset', methods=['POST'])
@roles_required('admin') 
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
@roles_required('admin') 
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
@roles_required('admin') 
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


@bp.route('/api/automation/<int:automation_id>/toggle', methods=['POST'])
@roles_required('admin') 
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
@roles_required('admin') 
def purge_automation_logs(automation_id):
    try:
        WebhookLog.query.filter_by(automation_id=automation_id).delete()
        db.session.commit()
        return jsonify({"success": True})
    except Exception as e:
        db.session.rollback()
        return jsonify({"error": str(e)}), 500

@bp.route('/api/automation/<automation_id>/delete', methods=['POST'])
@roles_required('admin')  # Use roles_required instead of admin_required
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
@roles_required('admin') 
def admin_dashboard():
    """Redirect admin users directly to the users page."""
    return redirect(url_for('admin.users'))

@bp.route('/admin/users')
@login_required
@roles_required('admin') 
def admin_users():
    search = request.args.get('search', '')
    query = User.query
    if search:
        query = query.filter(User.username.ilike(f'%{search}%'))
    users = query.all()
    return render_template('admin/users.html', users=users)

@bp.route('/admin/automations')
@login_required
@roles_required('admin') 
def admin_automations():
    automations = Automation.query.join(User).all()
    return render_template('admin/automations.html', automations=automations)
    
