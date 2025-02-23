# app/routes/dashboard.py
from flask import (
    Blueprint, render_template, jsonify,
    session, redirect, url_for, request, current_app
)
from flask_login import login_required, current_user
from app.models.automation import Automation
from app.models.webhook import WebhookLog
from app.services.oauth_service import get_oauth_credentials
from app.services.coinbase_service import CoinbaseService
from app import db

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
        automation.webhook_url = f"{base_url}/webhook?automation_id={automation.automation_id}"

    # Get detailed OAuth connection status
    from app.services.oauth_service import get_connection_status
    connection_status = get_connection_status(user_id)
    
    # Only try to fetch portfolios if OAuth is properly connected
    portfolios = []
    if connection_status['is_connected']:
        try:
            coinbase_service = CoinbaseService(user_id)
            portfolios = coinbase_service.list_portfolios()
        except Exception as e:
            current_app.logger.error(f"Error fetching portfolios: {str(e)}")

    return render_template(
        'dashboard.html',
        automations=automations,
        oauth_status=connection_status,
        portfolios=portfolios
    )


@bp.route('/settings')
@login_required
def settings():
    """Render the settings page."""
    from app.services.oauth_service import get_connection_status
    
    # Get detailed connection status
    connection_status = get_connection_status(current_user.id)
    
    return render_template(
        'settings.html',
        oauth_connected=connection_status['is_connected'],
        connection_status=connection_status
    )


@bp.route('/api/logs')
@login_required
def get_logs():
    """Get webhook logs for the current user."""
    try:
        logs = WebhookLog.query.outerjoin(Automation).filter(
            db.or_(
                Automation.user_id == current_user.id,
                Automation.id.is_(None)
            )
        ).order_by(WebhookLog.timestamp.desc()).limit(100).all()
        
        return jsonify([log.to_dict() for log in logs])
    except Exception as e:
        print(f"Error getting logs: {str(e)}")
        return jsonify({"error": str(e)}), 500


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
