# app/routes/automation.py
from flask import Blueprint, request, jsonify, session, send_from_directory, render_template
from flask_login import current_user
from functools import wraps
from app import db
from app.models.automation import Automation
import os

bp = Blueprint('automation', __name__)

def api_login_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        auth_header = request.environ.get('HTTP_AUTHORIZATION')
        if not auth_header and not session.get('user_id'):
            return jsonify({"error": "Unauthorized"}), 403
        return f(*args, **kwargs)
    return decorated_function

def get_user_automation(automation_id):
    """Helper function to get an automation for the current user"""
    return Automation.query.filter_by(
        automation_id=automation_id,
        user_id=session['user_id']
    ).first()

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

# API Routes
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

# Legacy route aliases for backward compatibility
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