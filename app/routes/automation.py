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
@login_required
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
                "portfolio_id": cred.portfolio_id,
                "portfolio_name": cred.portfolio_name,
                "last_used": cred.last_used.isoformat() if cred.last_used else None,
                "created_at": cred.created_at.isoformat(),
                "is_active": cred.is_active
            } for cred in credentials]
        })
    except Exception as e:
        current_app.logger.error(f"Error fetching credentials: {str(e)}")
        return jsonify({"error": str(e)}), 500

@bp.route('/automation/<automation_id>/credentials', methods=['POST'])
@login_required
def connect_portfolio(automation_id):
    """Connect a portfolio to an automation."""
    current_app.logger.debug(f"Received credential request for automation {automation_id}")
    current_app.logger.debug(f"Request data: {request.get_json()}")
    
    try:
        # Verify automation exists and belongs to user
        automation = get_user_automation(automation_id)
        current_app.logger.debug(f"Found automation: {automation}")
        if not automation:
            current_app.logger.error("Automation not found")
            return jsonify({"error": "Automation not found"}), 404
            
        # Get request data
        data = request.get_json()
        if not data.get('portfolio_id'):
            current_app.logger.error("Missing portfolio_id in request")
            return jsonify({"error": "Missing portfolio_id"}), 400
            
        # Check if credentials already exist
        existing_creds = ExchangeCredentials.query.filter_by(
            automation_id=automation_id
        ).first()
        current_app.logger.debug(f"Existing credentials: {existing_creds}")
        if existing_creds:
            current_app.logger.error("Credentials already exist")
            return jsonify({"error": "Credentials already exist for this automation"}), 400
            
        try:
            # Initialize Coinbase service
            current_app.logger.debug(f"Initializing Coinbase service for user {current_user.id}")
            coinbase = CoinbaseService(current_user.id)
            
            # Get portfolio details to verify it exists
            current_app.logger.debug(f"Getting portfolio details for {data['portfolio_id']}")
            portfolio = coinbase.get_portfolio(data['portfolio_id'])
            current_app.logger.debug(f"Portfolio details: {portfolio}")
            
            if not portfolio:
                current_app.logger.error("Portfolio not found")
                return jsonify({"error": "Portfolio not found"}), 404
            
            # Create the exchange credentials
            current_app.logger.debug("Creating exchange credentials")
            credentials = ExchangeCredentials(
                user_id=current_user.id,
                automation_id=automation_id,
                name=portfolio['name'],  # Use portfolio name from Coinbase
                exchange='coinbase',
                portfolio_id=portfolio['id'],
                portfolio_name=portfolio['name'],
                encrypted_api_key=b'',  # These will be populated when executing trades
                encrypted_secret_key=b''
            )
            
            current_app.logger.debug("Adding credentials to database")
            db.session.add(credentials)
            db.session.commit()
            current_app.logger.debug("Credentials saved successfully")
            
            return jsonify({
                "success": True,
                "message": "Portfolio connected successfully",
                "credentials": {
                    "id": credentials.id,
                    "name": credentials.name,
                    "exchange": credentials.exchange,
                    "portfolio_id": credentials.portfolio_id,
                    "portfolio_name": credentials.portfolio_name,
                    "created_at": credentials.created_at.isoformat()
                }
            })
            
        except Exception as e:
            current_app.logger.error(f"Error connecting to Coinbase: {str(e)}")
            db.session.rollback()
            return jsonify({"error": "Failed to connect to Coinbase"}), 500
            
    except Exception as e:
        current_app.logger.error(f"Error creating credentials: {str(e)}")
        return jsonify({"error": str(e)}), 500


@bp.route('/automation/<automation_id>/credentials/<int:credential_id>', methods=['DELETE'])
@login_required
def delete_credentials(automation_id, credential_id):
    """Delete automation credentials."""
    try:
        automation = get_user_automation(automation_id)
        if not automation:
            return jsonify({"error": "Automation not found"}), 404
            
        credentials = ExchangeCredentials.query.filter_by(
            id=credential_id,
            user_id=current_user.id
        ).first()
        
        if not credentials:
            return jsonify({"error": "Credentials not found"}), 404
            
        db.session.delete(credentials)
        db.session.commit()
        
        return jsonify({"success": True})
    except Exception as e:
        db.session.rollback()
        current_app.logger.error(f"Error deleting credentials: {str(e)}")
        return jsonify({"error": str(e)}), 500

# Portfolio Routes
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
            return jsonify({"error": "Coinbase not connected"}), 401

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
            return jsonify({"error": "Coinbase not connected"}), 401

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