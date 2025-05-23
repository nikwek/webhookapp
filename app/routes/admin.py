# app/routes/admin.py
from flask import Blueprint, jsonify, render_template, redirect, url_for, request, current_app
from app.models.user import User
from app.models.automation import Automation
from app.models.webhook import WebhookLog
from sqlalchemy import func
from app import db
from flask_security import roles_required, current_user

bp = Blueprint('admin', __name__, url_prefix='/admin')

# Role check helper
def get_user_roles():
    return [role.name for role in current_user.roles]

@bp.route('/')
@roles_required('admin') 
def index():
    return redirect(url_for('admin.users'))


@bp.route('/users')
@roles_required('admin')
def users():
    search = request.args.get('search', '')
    
    # Query users with automation count
    query = db.session.query(User, func.count(Automation.id).label('automation_count'))\
        .outerjoin(Automation, User.id == Automation.user_id)\
        .group_by(User.id)
    
    if search:
        query = query.filter(User.email.ilike(f'%{search}%'))
    
    # Returns tuple of (user, automation_count)
    results = query.all()
    
    # Transform results for template
    users = []
    for user, count in results:
        user.automation_count = count
        users.append(user)
    
    return render_template('admin/users.html', users=users)


@bp.route('/automations')
@roles_required('admin')
def automations():
    search = request.args.get('search', '')
    
    # Start with a query that joins Automation with User
    query = db.session.query(Automation, User).join(User, Automation.user_id == User.id)
    
    # Apply search filter if provided
    if search:
        # Search by automation name, ID, or user email
        query = query.filter(
            db.or_(
                Automation.name.ilike(f'%{search}%'),
                Automation.automation_id.ilike(f'%{search}%'),
                User.email.ilike(f'%{search}%')
            )
        )
    
    # Execute the query
    results = query.all()
    current_app.logger.info(f"Found {len(results)} automations for admin page")
    
    # Process results to include user information
    formatted_automations = []
    for automation, user in results:
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
        
        # Get automation IDs directly from the Automation table
        automations = Automation.query.filter_by(user_id=user.id).all()
        automation_ids = [a.automation_id for a in automations]
        
        # 1. Delete webhook logs first
        if automation_ids:
            WebhookLog.query.filter(WebhookLog.automation_id.in_(automation_ids)).delete(synchronize_session='fetch')
        
        # 2. Delete account caches
        from app.models.account_cache import AccountCache
        AccountCache.query.filter_by(user_id=user.id).delete()
        
        # 3. Delete exchange credentials (before portfolios and automations to avoid FK constraint issues)
        from app.models.exchange_credentials import ExchangeCredentials
        ExchangeCredentials.query.filter_by(user_id=user.id).delete()
        
        # 4. Delete user's automations
        Automation.query.filter_by(user_id=user.id).delete()
        
        # 5. Delete user's portfolios (if the relationship exists)
        if hasattr(user, 'portfolios'):
            for portfolio in user.portfolios:
                db.session.delete(portfolio)
        
        # 6. Clear the user's roles
        user.roles = []
        
        # 7. Finally delete the user
        db.session.delete(user)
        db.session.commit()
        
        current_app.logger.info(f"User {user_id} deleted successfully")
        return jsonify({"success": True})
    except Exception as e:
        db.session.rollback()
        current_app.logger.error(f"Error deleting user: {str(e)}")
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

@bp.route('/api/automation/<int:automation_id>/delete', methods=['POST'])
@roles_required('admin')
def delete_automation(automation_id):
    try:
        # First fetch the automation
        automation = Automation.query.get(automation_id)
        if not automation:
            return jsonify({"error": "Automation not found"}), 404
        
        # 1. Delete all logs for this automation
        WebhookLog.query.filter_by(automation_id=automation.automation_id).delete()
        
        # 2. Delete associated exchange credentials
        from app.models.exchange_credentials import ExchangeCredentials
        ExchangeCredentials.query.filter_by(automation_id=automation.id).delete()
        
        # 3. Then delete the automation itself
        db.session.delete(automation)
        db.session.commit()
        current_app.logger.info(f"Automation {automation_id} deleted successfully")
        return jsonify({"success": True})
    except Exception as e:
        db.session.rollback()
        current_app.logger.error(f"Error deleting automation: {str(e)}")
        return jsonify({"error": str(e)}), 500
    
