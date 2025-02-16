# app/routes/automation.py
from flask import Blueprint, request, jsonify, session, send_from_directory, render_template, current_app
from flask_login import current_user
from functools import wraps
from app import db
from app.models.automation import Automation
from app.models.webhook import WebhookLog
from app.models.exchange_credentials import ExchangeCredentials
from datetime import datetime, timezone
import os

bp = Blueprint('automation', __name__)

# Decorators
def api_login_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        auth_header = request.environ.get('HTTP_AUTHORIZATION')
        if not auth_header and not session.get('user_id'):
            return jsonify({"error": "Unauthorized"}), 403
        return f(*args, **kwargs)
    return decorated_function

# Helper Functions
def get_user_automation(automation_id):
    """Helper function to get an automation for the current user"""
    return Automation.query.filter_by(
        automation_id=automation_id,
        user_id=session['user_id']
    ).first()

# Static File Routes
@bp.route('/static/js/components/WebhookLogs.jsx')
def serve_component(filename):
    root_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    static_dir = os.path.join(root_dir, 'static', 'js', 'components')
    return send_from_directory(static_dir, filename, mimetype='text/jsx')

# UI Routes
@bp.route('/automation/new', methods=['GET'])
@api_login_required
def new_automation():
    return render_template('automation.html', automation=None)

@bp.route('/automation/<automation_id>', methods=['GET'])
@api_login_required
def view_automation(automation_id):
    automation = get_user_automation(automation_id)
    if not automation:
        return render_template('404.html'), 404
    return render_template('automation.html', automation=automation)

# Automation API Routes
@bp.route('/automation', methods=['POST'])
@api_login_required
def create_automation():
    try:
        data = request.get_json()
        if not data or 'name' not in data:
            return jsonify({"error": "Missing required field: name"}), 400
            
        automation = Automation(
            automation_id=Automation.generate_automation_id(),
            name=data.get('name'),
            user_id=session['user_id']
        )
        db.session.add(automation)
        
        template = {
            "action": "{{strategy.order.action}}",
            "ticker": "{{ticker}}",
            "order_size": "100%",
            "position_size": "{{strategy.position_size}}",
            "schema": "2",
            "timestamp": "{{time}}"
        }
        
        automation.template = template
        db.session.commit()
        
        return jsonify({
            "automation_id": automation.automation_id,
            "webhook_url": f"{request.url_root}webhook?automation_id={automation.automation_id}",
            "template": template
        })
    except Exception as e:
        print(f"Error creating automation: {e}")
        db.session.rollback()
        return jsonify({"error": "Failed to create automation"}), 500

@bp.route('/automation/<automation_id>', methods=['PUT'])
@api_login_required
def update_automation(automation_id):
    try:
        automation = get_user_automation(automation_id)
        if not automation:
            return jsonify({"error": "Automation not found"}), 404
            
        data = request.get_json()
        if 'name' in data:
            automation.name = data['name']
            
        db.session.commit()
        return jsonify({"success": True})
    except Exception as e:
        db.session.rollback()
        return jsonify({"error": str(e)}), 500

@bp.route('/automation/<automation_id>/status', methods=['PUT'])
@api_login_required
def update_automation_status(automation_id):
    try:
        automation = get_user_automation(automation_id)
        if not automation:
            return jsonify({"error": "Automation not found"}), 404
            
        data = request.get_json()
        if 'is_active' in data:
            automation.is_active = data['is_active']
            
        db.session.commit()
        return jsonify({"success": True})
    except Exception as e:
        db.session.rollback()
        return jsonify({"error": str(e)}), 500

@bp.route('/automation/<automation_id>', methods=['DELETE'])
@api_login_required
def delete_automation(automation_id):
    try:
        automation = get_user_automation(automation_id)
        if not automation:
            return jsonify({"error": "Automation not found"}), 404
            
        db.session.delete(automation)
        db.session.commit()
        return jsonify({"success": True})
    except Exception as e:
        db.session.rollback()
        return jsonify({"error": str(e)}), 500

# Webhook Log Routes
@bp.route('/automation/<automation_id>/logs')
@api_login_required
def get_automation_logs(automation_id):
    """Get webhook logs for a specific automation."""
    try:
        automation = get_user_automation(automation_id)
        if not automation:
            return jsonify({"error": "Automation not found"}), 404
        
        logs = WebhookLog.query.filter_by(
            automation_id=automation_id
        ).order_by(WebhookLog.timestamp.desc()).limit(100).all()
        
        return jsonify([log.to_dict() for log in logs])
    except Exception as e:
        print(f"Error fetching automation logs: {e}")
        return jsonify({"error": str(e)}), 500

# Credential Management Routes
@bp.route('/automation/<automation_id>/credentials', methods=['GET'])
@api_login_required
def get_credentials(automation_id):
    """Get all credentials for a user."""
    try:
        automation = get_user_automation(automation_id)
        if not automation:
            return jsonify({"error": "Automation not found"}), 404
            
        credentials = ExchangeCredentials.query.filter_by(
            user_id=session['user_id']
        ).order_by(ExchangeCredentials.created_at.desc()).all()
        
        return jsonify({
            "credentials": [{
                "id": cred.id,
                "name": cred.name,
                "exchange": cred.exchange,
                "last_used": cred.last_used.isoformat() if cred.last_used else None,
                "created_at": cred.created_at.isoformat(),
                "is_active": cred.is_active
            } for cred in credentials]
        })
    except Exception as e:
        print(f"Error fetching credentials: {e}")
        return jsonify({"error": str(e)}), 500

@bp.route('/automation/<automation_id>/credentials', methods=['POST'])
@api_login_required
def create_credentials(automation_id):
    """Create new API credentials."""
    try:
        automation = get_user_automation(automation_id)
        if not automation:
            return jsonify({"error": "Automation not found"}), 404
            
        data = request.get_json()
        if not all(k in data for k in ['name', 'api_key', 'secret_key']):
            return jsonify({"error": "Missing required fields"}), 400
            
        # Validate input
        if not data['name'].strip():
            return jsonify({"error": "Name cannot be empty"}), 400
        if not data['api_key'].strip() or not data['secret_key'].strip():
            return jsonify({"error": "API key and secret key cannot be empty"}), 400
            
        credentials = ExchangeCredentials(
            user_id=session['user_id'],
            name=data['name'].strip(),
            exchange='coinbase',  # Hardcoded for now
            is_active=True
        )
        
        credentials.api_key = data['api_key'].strip()
        credentials.secret_key = data['secret_key'].strip()
        
        db.session.add(credentials)
        db.session.commit()
        
        return jsonify({
            "id": credentials.id,
            "name": credentials.name,
            "exchange": credentials.exchange,
            "created_at": credentials.created_at.isoformat(),
            "is_active": credentials.is_active
        })
    except ValueError as e:
        db.session.rollback()
        print(f"Encryption error: {e}")
        return jsonify({"error": "Configuration error: encryption key not set up correctly"}), 500
    except Exception as e:
        db.session.rollback()
        print(f"Error creating credentials: {e}")
        return jsonify({"error": str(e)}), 500

@bp.route('/automation/<automation_id>/credentials/<int:credential_id>', methods=['DELETE'])
@api_login_required
def delete_credentials(automation_id, credential_id):
    """Delete API credentials."""
    try:
        automation = get_user_automation(automation_id)
        if not automation:
            return jsonify({"error": "Automation not found"}), 404
            
        credentials = ExchangeCredentials.query.filter_by(
            id=credential_id,
            user_id=session['user_id']
        ).first()
        
        if not credentials:
            return jsonify({"error": "Credentials not found"}), 404
            
        db.session.delete(credentials)
        db.session.commit()
        
        return jsonify({"success": True})
    except Exception as e:
        db.session.rollback()
        print(f"Error deleting credentials: {e}")
        return jsonify({"error": str(e)}), 500

# Legacy Routes
@bp.route('/create-automation', methods=['POST'])
@api_login_required
def create_automation_legacy():
    return create_automation()

@bp.route('/update_automation_name', methods=['POST'])
@api_login_required
def update_automation_name():
    data = request.get_json()
    return update_automation(data['automation_id'])

@bp.route('/deactivate-automation/<automation_id>', methods=['POST'])
@api_login_required
def deactivate_automation(automation_id):
    request.get_json = lambda: {"is_active": False}
    return update_automation_status(automation_id)

@bp.route('/activate-automation/<automation_id>', methods=['POST'])
@api_login_required
def activate_automation(automation_id):
    request.get_json = lambda: {"is_active": True}
    return update_automation_status(automation_id)

@bp.route('/delete_automation', methods=['POST'])
@api_login_required
def delete_automation_legacy():
    data = request.get_json()
    return delete_automation(data['automation_id'])