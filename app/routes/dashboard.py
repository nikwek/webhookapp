# app/routes/dashboard.py
from flask import Blueprint, render_template, session, redirect, url_for, request, Response, jsonify
from app.models.webhook import WebhookLog
from app.models.automation import Automation
from app.models.user import User
from app import db, bcrypt
import time, json
from datetime import datetime, timezone

bp = Blueprint('dashboard', __name__)

def format_timestamp(ts):
    return ts.replace('T', ' ').rstrip('Z')

@bp.route('/dashboard')
def dashboard():
    if not session.get('user_id'):
        return redirect(url_for('auth.login'))

    user_automations = Automation.query.filter_by(user_id=session['user_id']).all()
    automation_ids = [a.automation_id for a in user_automations]
    
    webhook_logs = WebhookLog.query\
        .filter(WebhookLog.automation_id.in_(automation_ids))\
        .order_by(WebhookLog.timestamp.desc())\
        .all()

    logs = [json.dumps({
        "timestamp": log.timestamp.strftime("%Y-%m-%d %H:%M:%S"),
        "payload": log.payload
    }) for log in webhook_logs]

    return render_template('dashboard.html', 
                         automations=user_automations,
                         logs=logs)

@bp.route('/settings', methods=['GET', 'POST'])
def settings():
    if request.method == 'POST':
        new_password = bcrypt.generate_password_hash(request.form['password']).decode('utf-8')
        user = User.query.get(session['user_id'])
        user.password = new_password
        db.session.commit()
        return redirect(url_for('dashboard.dashboard'))
    return render_template('settings.html')

@bp.route('/users')
def users():
    all_users = User.query.all()
    return render_template('users.html', users=all_users)

@bp.route('/webhook-updates')
def webhook_updates():
    user_id = request.args.get('user_id')  # Get user_id outside the generator

    def generate():
        from app import create_app
        app = create_app()
        
        with app.app_context():
            last_id = -1
            while True:
                try:
                    if user_id:  # Only proceed if we have a user_id
                        user_automations = Automation.query.filter_by(user_id=user_id).all()
                        automation_ids = [a.automation_id for a in user_automations]
                        
                        logs = WebhookLog.query\
                            .filter(WebhookLog.id > last_id)\
                            .filter(WebhookLog.automation_id.in_(automation_ids))\
                            .order_by(WebhookLog.timestamp.desc())\
                            .all()
                        
                        if logs:
                            last_id = max(log.id for log in logs)
                            for log in logs:
                                data = {
                                    "timestamp": log.timestamp.strftime("%Y-%m-%d %H:%M:%S"),
                                    "payload": log.payload
                                }
                                yield f"data: {json.dumps(data)}\n\n"
                except Exception as e:
                    print(f"Error in webhook updates: {e}")
                time.sleep(0.5)

    return Response(generate(), mimetype='text/event-stream')

@bp.route('/clear-logs', methods=['POST'])
def clear_logs():
    if not session.get('is_admin'):
        return jsonify({"error": "Unauthorized"}), 403
    
    try:
        WebhookLog.query.delete()
        db.session.commit()
        return jsonify({"success": True})
    except Exception as e:
        db.session.rollback()
        return jsonify({"error": str(e)})
    
@bp.route('/create-automation', methods=['POST'])
def create_automation():
    if not session.get('user_id'):
        return jsonify({"error": "Unauthorized"}), 403
        
    try:
        data = request.get_json()
        automation = Automation(
            automation_id=Automation.generate_automation_id(),
            name=data.get('name'),
            user_id=session['user_id']
        )
        db.session.add(automation)
        db.session.commit()
        
        return jsonify({
            "success": True,
            "automation_id": automation.automation_id
        })
    except Exception as e:
        print(f"Error creating automation: {e}")
        db.session.rollback()
        return jsonify({"error": str(e)}), 500
    
@bp.route('/update_automation_name', methods=['POST'])
def update_automation_name():
    if not session.get('user_id'):
        return jsonify({"error": "Unauthorized"}), 403
        
    try:
        data = request.get_json()
        automation = Automation.query.filter_by(
            automation_id=data['automation_id'],
            user_id=session['user_id']
        ).first()
        
        if not automation:
            return jsonify({"error": "Automation not found"}), 404
            
        automation.name = data['name']
        db.session.commit()
        
        return jsonify({"success": True})
    except Exception as e:
        print(f"Error updating automation name: {e}")
        db.session.rollback()
        return jsonify({"error": str(e)}), 500
    
@bp.route('/delete_automation', methods=['POST'])
def delete_automation():
    if not session.get('user_id'):
        return jsonify({"error": "Unauthorized"}), 403
        
    try:
        data = request.get_json()
        automation = Automation.query.filter_by(
            automation_id=data['automation_id'],
            user_id=session['user_id']
        ).first()
        
        if not automation:
            return jsonify({"error": "Automation not found"}), 404
            
        db.session.delete(automation)
        db.session.commit()
        
        return jsonify({"success": True})
    except Exception as e:
        print(f"Error deleting automation: {e}")
        db.session.rollback()
        return jsonify({"error": str(e)}), 500
    
@bp.route('/deactivate-automation/<automation_id>', methods=['POST'])
def deactivate_automation(automation_id):
    if not session.get('user_id'):
        return jsonify({"error": "Unauthorized"}), 403
        
    try:
        automation = Automation.query.filter_by(
            automation_id=automation_id,
            user_id=session['user_id']
        ).first()
        
        if not automation:
            return jsonify({"error": "Automation not found"}), 404
            
        automation.is_active = False
        db.session.commit()
        
        return jsonify({"success": True})
    except Exception as e:
        print(f"Error deactivating automation: {e}")
        db.session.rollback()
        return jsonify({"error": str(e)}), 500
    
@bp.route('/activate-automation/<automation_id>', methods=['POST'])
def activate_automation(automation_id):
    if not session.get('user_id'):
        return jsonify({"error": "Unauthorized"}), 403
        
    try:
        automation = Automation.query.filter_by(
            automation_id=automation_id,
            user_id=session['user_id']
        ).first()
        
        if not automation:
            return jsonify({"error": "Automation not found"}), 404
            
        automation.is_active = True
        db.session.commit()
        
        return jsonify({"success": True})
    except Exception as e:
        print(f"Error activating automation: {e}")
        db.session.rollback()
        return jsonify({"error": str(e)}), 500