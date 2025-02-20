# app/routes/automation.py
from flask import Blueprint, request, jsonify, session, send_from_directory, render_template, current_app
from flask_login import current_user, login_required
from functools import wraps
from app import db
from app.models.automation import Automation
from app.models.webhook import WebhookLog
from app.models.exchange_credentials import ExchangeCredentials
from app.services.oauth_service import get_oauth_credentials
from app.services.coinbase_service import CoinbaseService
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
    
    # Get available portfolios if OAuth is connected
    portfolios = []
    oauth_creds = get_oauth_credentials(current_user.id, 'coinbase')
    if oauth_creds:
        try:
            coinbase = CoinbaseService(current_user.id)
            portfolios = coinbase.list_portfolios()
        except Exception as e:
            current_app.logger.error(f"Error fetching portfolios: {str(e)}")
    
    return render_template(
        'automation.html', 
        automation=automation,
        portfolios=portfolios
    )

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
    """Get credentials for a specific automation."""
    try:
        automation = get_user_automation(automation_id)
        if not automation:
            return jsonify({"error": "Automation not found"}), 404
            
        credentials = ExchangeCredentials.query.filter_by(
            automation_id=automation_id
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
    """Create new API credentials for a specific automation."""
    try:
        automation = get_user_automation(automation_id)
        if not automation:
            return jsonify({"error": "Automation not found"}), 404
            
        data = request.get_json()
        if not all(k in data for k in ['name', 'api_key', 'secret_key', 'portfolio_id', 'portfolio_name']):
            return jsonify({"error": "Missing required fields"}), 400
            
        # Validate input
        if not data['name'].strip():
            return jsonify({"error": "Name cannot be empty"}), 400
            
        # Check if credentials already exist for this automation
        existing_creds = ExchangeCredentials.query.filter_by(
            automation_id=automation_id
        ).first()
        if existing_creds:
            return jsonify({"error": "Credentials already exist for this automation"}), 400
            
        credentials = ExchangeCredentials(
            user_id=current_user.id,
            automation_id=automation_id,
            name=data['name'].strip(),
            exchange='coinbase',
            portfolio_id=data['portfolio_id'],
            portfolio_name=data['portfolio_name']
        )
        
        credentials.api_key = data['api_key'].strip()
        credentials.secret_key = data['secret_key'].strip()
        
        db.session.add(credentials)
        db.session.commit()
        
        return jsonify({
            "id": credentials.id,
            "name": credentials.name,
            "exchange": credentials.exchange,
            "portfolio_name": credentials.portfolio_name,
            "created_at": credentials.created_at.isoformat(),
            "is_active": credentials.is_active
        })
    except Exception as e:
        db.session.rollback()
        current_app.logger.error(f"Error creating credentials: {str(e)}")
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

@bp.route('/automation/<automation_id>/portfolios', methods=['GET'])
@api_login_required
def get_portfolios(automation_id):
    """Get available portfolios for the automation."""
    try:
        automation = get_user_automation(automation_id)
        if not automation:
            return jsonify({"error": "Automation not found"}), 404

        oauth_creds = get_oauth_credentials(current_user.id, 'coinbase')
        if not oauth_creds:
            return jsonify({"error": "Coinbase not connected"}), 400

        coinbase = CoinbaseService(current_user.id)
        portfolios = coinbase.list_portfolios()
        
        return jsonify({"portfolios": portfolios})
    except Exception as e:
        current_app.logger.error(f"Error fetching portfolios: {str(e)}")
        return jsonify({"error": str(e)}), 500

@bp.route('/automation/<automation_id>/portfolios', methods=['POST'])
@api_login_required
def create_portfolio(automation_id):
    """Create a new portfolio for the automation."""
    try:
        automation = get_user_automation(automation_id)
        if not automation:
            return jsonify({"error": "Automation not found"}), 404

        data = request.get_json()
        if not data or 'name' not in data:
            return jsonify({"error": "Missing portfolio name"}), 400

        oauth_creds = get_oauth_credentials(current_user.id, 'coinbase')
        if not oauth_creds:
            return jsonify({"error": "Coinbase not connected"}), 400

        coinbase = CoinbaseService(current_user.id)
        portfolio = coinbase.create_portfolio(data['name'])
        
        return jsonify({"portfolio": portfolio})
    except Exception as e:
        current_app.logger.error(f"Error creating portfolio: {str(e)}")
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